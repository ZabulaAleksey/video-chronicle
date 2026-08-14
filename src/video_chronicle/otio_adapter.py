"""Bounded native OpenTimelineIO JSON adapter for the approved subset.

The optional dependency is intentionally imported only while constructing this
adapter.  Core/project modules never expose OpenTimelineIO objects.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any
from urllib.parse import urlsplit
from urllib.request import url2pathname

from .interchange import (
    ImportResult,
    InterchangeTimeline,
    ProposedClip,
)
from .project import TARGET_FRAME_US


MAX_BYTES = 32 * 1024 * 1024
MAX_DEPTH = 32
MAX_NODES = 262_144
MAX_CLIPS = 4096
MAX_STRING = 4096
MAX_METADATA_BYTES = 64 * 1024
MAX_METADATA_DEPTH = 8
MAX_METADATA_ENTRIES = 1024


class InterchangeError(ValueError):
    """The payload is outside the safe interoperable OTIO subset."""


class NativeOtioAdapter:
    def __init__(self) -> None:
        import opentimelineio as otio

        if getattr(otio, "__version__", None) != "0.18.1":
            raise RuntimeError("OpenTimelineIO 0.18.1 is required")
        self._otio = otio

    def export_timeline(self, timeline: InterchangeTimeline) -> bytes:
        if len(timeline.clips) > MAX_CLIPS:
            raise InterchangeError("timeline exceeds the 4096 clip limit")
        otio = self._otio
        result = otio.schema.Timeline(name="Video Chronicle")
        result.metadata["video_chronicle"] = {
            "project_id": timeline.project_id,
            "project_revision": timeline.project_revision,
        }
        track = otio.schema.Track(name="Video", kind=otio.schema.TrackKind.Video)
        for source in timeline.clips:
            reference = otio.schema.ExternalReference(target_url=source.source_path.as_uri())
            source_range = otio.opentime.TimeRange(
                otio.opentime.RationalTime(source.in_us, 1_000_000),
                otio.opentime.RationalTime(source.out_us - source.in_us, 1_000_000),
            )
            clip = otio.schema.Clip(
                name=source.item_id,
                media_reference=reference,
                source_range=source_range,
            )
            clip.metadata["video_chronicle"] = {
                "project_id": timeline.project_id,
                "project_revision": timeline.project_revision,
                "item_id": source.item_id,
                "group_id": source.group_id,
            }
            track.append(clip)
        result.tracks.append(track)
        native_json = otio.core.serialize_json_to_string(result, None, -1)
        encoded = json.dumps(
            json.loads(native_json),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
        if len(encoded) > MAX_BYTES:
            raise InterchangeError("export exceeds the 32 MiB interchange limit")
        return encoded

    def import_timeline(
        self, payload: bytes, known_project: InterchangeTimeline
    ) -> ImportResult:
        document, foreign_metadata = _preflight(payload)
        # Call the native core JSON codec directly: ActiveManifest adapter
        # dispatch, hooks and default media-linkers are intentionally bypassed.
        try:
            parsed = self._otio.core.deserialize_json_from_string(
                payload.decode("utf-8", errors="strict")
            )
        except Exception as exc:
            raise InterchangeError(f"OpenTimelineIO rejected the payload: {exc}") from exc
        if not isinstance(parsed, self._otio.schema.Timeline):
            raise InterchangeError("payload did not decode to a Timeline")

        warnings = list(foreign_metadata)
        timeline_metadata = _video_chronicle_metadata(document["metadata"])
        source_project_id = timeline_metadata.get("project_id", known_project.project_id)
        source_revision = timeline_metadata.get(
            "project_revision", known_project.project_revision
        )
        if not isinstance(source_project_id, str) or not source_project_id:
            raise InterchangeError("invalid Video Chronicle project_id metadata")
        if (
            isinstance(source_revision, bool)
            or not isinstance(source_revision, int)
            or source_revision < 0
        ):
            raise InterchangeError("invalid Video Chronicle project_revision metadata")

        by_path: dict[str, list[str]] = {}
        for known in known_project.clips:
            identity = _safe_existing_identity(known.source_path)
            by_path.setdefault(identity, []).append(known.item_id)
        known_ids = {clip.item_id for clip in known_project.clips}
        raw_clips = document["tracks"]["children"][0]["children"]
        proposals: list[ProposedClip] = []
        for index, raw in enumerate(raw_clips):
            reference = raw["media_references"]["DEFAULT_MEDIA"]
            source_path = _local_file_path(reference["target_url"])
            identity = _safe_existing_identity(source_path)
            path_matches = by_path.get(identity, [])
            metadata = _video_chronicle_metadata(raw["metadata"])
            trusted = (
                metadata.get("project_id") == known_project.project_id
                and metadata.get("project_revision") == known_project.project_revision
            )
            item_id: str | None = None
            group_id: str | None = None
            if trusted and "item_id" in metadata:
                candidate = metadata["item_id"]
                if not isinstance(candidate, str) or not candidate:
                    raise InterchangeError(f"clip {index} has invalid item_id metadata")
                group_id = metadata.get("group_id")
                if group_id is not None and (not isinstance(group_id, str) or not group_id):
                    raise InterchangeError(f"clip {index} has invalid group_id metadata")
                if candidate in known_ids:
                    if path_matches == [candidate]:
                        item_id = candidate
                    elif path_matches:
                        raise InterchangeError(
                            f"clip {index} metadata conflicts with its local reference"
                        )
                    else:
                        warnings.append(
                            f"clip {index}: trusted ID has no matching known local reference; left unmapped"
                        )
                else:
                    warnings.append(f"clip {index}: trusted item ID is unknown; left unmapped")
            elif len(path_matches) == 1:
                item_id = path_matches[0]
            elif not path_matches:
                warnings.append(f"clip {index}: local source is not known; left unmapped")
            else:
                warnings.append(f"clip {index}: local source identity is ambiguous; left unmapped")

            time_range = raw["source_range"]
            start_us = _time_to_us(time_range["start_time"], f"clip {index} start")
            duration_us = _time_to_us(time_range["duration"], f"clip {index} duration")
            if duration_us < TARGET_FRAME_US:
                raise InterchangeError(f"clip {index} is shorter than one target frame")
            proposals.append(
                ProposedClip(source_path, start_us, start_us + duration_us, item_id, group_id)
            )
        return ImportResult(
            known_project.project_id,
            known_project.project_revision,
            tuple(proposals),
            tuple(warnings),
        )


def _reject_constant(value: str) -> None:
    raise InterchangeError(f"non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InterchangeError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _preflight(payload: bytes) -> tuple[dict[str, Any], tuple[str, ...]]:
    if not isinstance(payload, bytes):
        raise TypeError("OTIO payload must be bytes")
    if len(payload) > MAX_BYTES:
        raise InterchangeError("OTIO payload exceeds 32 MiB")
    try:
        text = payload.decode("utf-8", errors="strict")
        root = json.loads(
            text, parse_constant=_reject_constant, object_pairs_hook=_unique_object
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InterchangeError(f"invalid bounded UTF-8 JSON: {exc}") from exc
    if not isinstance(root, dict):
        raise InterchangeError("OTIO top level must be an object")
    _walk_json(root)
    foreign: list[str] = []
    _validate_timeline(root, foreign)
    return root, tuple(foreign)


def _walk_json(value: Any) -> None:
    nodes = 0

    def visit(
        node: Any, depth: int, *, in_metadata: bool = False, vc_metadata: bool = False
    ) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES:
            raise InterchangeError("OTIO JSON exceeds 262144 nodes")
        if depth > MAX_DEPTH:
            raise InterchangeError("OTIO JSON exceeds depth 32")
        if isinstance(node, str):
            if len(node) > MAX_STRING:
                raise InterchangeError("OTIO JSON string exceeds 4096 characters")
        elif isinstance(node, list):
            for child in node:
                visit(child, depth + 1, in_metadata=in_metadata, vc_metadata=vc_metadata)
        elif isinstance(node, dict):
            for key, child in node.items():
                if len(key) > MAX_STRING:
                    raise InterchangeError("OTIO JSON key exceeds 4096 characters")
                visit(
                    child,
                    depth + 1,
                    in_metadata=in_metadata or key == "metadata",
                    vc_metadata=in_metadata and key == "video_chronicle",
                )
        elif isinstance(node, float) and not math.isfinite(node):
            raise InterchangeError("OTIO JSON contains a non-finite number")

    visit(value, 1)


_FIELDS = {
    "Timeline.1": {"OTIO_SCHEMA", "metadata", "name", "global_start_time", "tracks"},
    "Stack.1": {"OTIO_SCHEMA", "metadata", "name", "source_range", "effects", "markers", "enabled", "color", "children"},
    "Track.1": {"OTIO_SCHEMA", "metadata", "name", "source_range", "effects", "markers", "enabled", "color", "children", "kind"},
    "Clip.2": {"OTIO_SCHEMA", "metadata", "name", "source_range", "effects", "markers", "enabled", "color", "media_references", "active_media_reference_key"},
    "ExternalReference.1": {"OTIO_SCHEMA", "metadata", "name", "available_range", "available_image_bounds", "target_url"},
    "TimeRange.1": {"OTIO_SCHEMA", "duration", "start_time"},
    "RationalTime.1": {"OTIO_SCHEMA", "rate", "value"},
}


def _exact(node: Any, schema: str) -> dict[str, Any]:
    if not isinstance(node, dict) or node.get("OTIO_SCHEMA") != schema:
        raise InterchangeError(f"expected {schema}")
    if set(node) != _FIELDS[schema]:
        raise InterchangeError(f"{schema} contains missing or forbidden structural fields")
    return node


def _metadata(value: Any, location: str, foreign: list[str]) -> None:
    if not isinstance(value, dict):
        raise InterchangeError(f"{location} metadata must be an object")
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InterchangeError(f"{location} metadata is not JSON data") from exc
    if len(encoded) > MAX_METADATA_BYTES:
        raise InterchangeError(f"{location} metadata exceeds 64 KiB")
    entries = 0

    def visit(node: Any, depth: int) -> None:
        nonlocal entries
        if depth > MAX_METADATA_DEPTH:
            raise InterchangeError(f"{location} metadata exceeds depth 8")
        if isinstance(node, dict):
            entries += len(node)
            if entries > MAX_METADATA_ENTRIES:
                raise InterchangeError(f"{location} metadata exceeds 1024 entries")
            for child in node.values():
                visit(child, depth + 1)
        elif isinstance(node, list):
            entries += len(node)
            if entries > MAX_METADATA_ENTRIES:
                raise InterchangeError(f"{location} metadata exceeds 1024 entries")
            for child in node:
                visit(child, depth + 1)

    visit(value, 1)
    if any(key != "video_chronicle" for key in value):
        foreign.append(f"{location}: foreign metadata was discarded")


def _common_composable(
    node: dict[str, Any],
    location: str,
    foreign: list[str],
    *,
    allow_source_range: bool = False,
) -> None:
    _metadata(node["metadata"], location, foreign)
    if not isinstance(node["name"], str):
        raise InterchangeError(f"{location} name must be a string")
    if (
        (not allow_source_range and node.get("source_range") is not None)
        or node.get("effects") != []
        or node.get("markers") != []
    ):
        raise InterchangeError(f"{location} uses source range, effects, or markers")
    if node.get("enabled") is not True or node.get("color") is not None:
        raise InterchangeError(f"{location} must use default enabled/color values")


def _validate_timeline(root: dict[str, Any], foreign: list[str]) -> None:
    timeline = _exact(root, "Timeline.1")
    _metadata(timeline["metadata"], "timeline", foreign)
    if not isinstance(timeline["name"], str) or timeline["global_start_time"] is not None:
        raise InterchangeError("timeline name/global_start_time is outside the subset")
    stack = _exact(timeline["tracks"], "Stack.1")
    _common_composable(stack, "stack", foreign)
    if not isinstance(stack["children"], list) or len(stack["children"]) != 1:
        raise InterchangeError("timeline must contain exactly one video track")
    track = _exact(stack["children"][0], "Track.1")
    _common_composable(track, "track", foreign)
    if track["kind"] != "Video" or not isinstance(track["children"], list):
        raise InterchangeError("the only track must have kind=Video")
    if len(track["children"]) > MAX_CLIPS:
        raise InterchangeError("timeline exceeds 4096 clips")
    for index, raw_clip in enumerate(track["children"]):
        clip = _exact(raw_clip, "Clip.2")
        _common_composable(clip, f"clip {index}", foreign, allow_source_range=True)
        if clip["active_media_reference_key"] != "DEFAULT_MEDIA":
            raise InterchangeError(f"clip {index} has a non-default media reference")
        references = clip["media_references"]
        if not isinstance(references, dict) or set(references) != {"DEFAULT_MEDIA"}:
            raise InterchangeError(f"clip {index} must have one media reference")
        reference = _exact(references["DEFAULT_MEDIA"], "ExternalReference.1")
        _metadata(reference["metadata"], f"clip {index} media reference", foreign)
        if (
            not isinstance(reference["name"], str)
            or reference["available_range"] is not None
            or reference["available_image_bounds"] is not None
            or not isinstance(reference["target_url"], str)
        ):
            raise InterchangeError(f"clip {index} media reference is outside the subset")
        time_range = _exact(clip["source_range"], "TimeRange.1")
        _rational(time_range["start_time"], f"clip {index} start")
        _rational(time_range["duration"], f"clip {index} duration")


def _rational(value: Any, label: str) -> None:
    node = _exact(value, "RationalTime.1")
    for key in ("rate", "value"):
        number = node[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise InterchangeError(f"{label} {key} must be numeric")
        if not math.isfinite(float(number)):
            raise InterchangeError(f"{label} {key} must be finite")
    if node["rate"] <= 0 or node["value"] < 0:
        raise InterchangeError(f"{label} has negative value or non-positive rate")


def _time_to_us(value: dict[str, Any], label: str) -> int:
    try:
        exact = Decimal(str(value["value"])) * Decimal(1_000_000) / Decimal(str(value["rate"]))
    except (InvalidOperation, ZeroDivisionError) as exc:
        raise InterchangeError(f"{label} cannot be represented") from exc
    rounded = exact.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    if abs(exact - rounded) > Decimal("0.5"):
        raise InterchangeError(f"{label} loses more than 0.5 microseconds")
    result = int(rounded)
    if result < 0:
        raise InterchangeError(f"{label} must be non-negative")
    return result


def _video_chronicle_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    value = metadata.get("video_chronicle", {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InterchangeError("video_chronicle metadata must be an object")
    allowed = {"project_id", "project_revision", "item_id", "group_id"}
    if any(key not in allowed for key in value):
        raise InterchangeError("video_chronicle metadata contains conflicting fields")
    return value


def _local_file_path(target_url: str) -> Path:
    parsed = urlsplit(target_url)
    if parsed.scheme.casefold() != "file" or parsed.query or parsed.fragment:
        raise InterchangeError("target_url must be a local file: reference")
    if parsed.netloc not in {"", "localhost"}:
        raise InterchangeError("UNC/remote file references are forbidden")
    # url2pathname performs the one and only percent-decode.  Validating the
    # resulting filesystem segments prevents encoded separators/traversal.
    path = Path(url2pathname(parsed.path))
    if os.name == "nt" and len(str(path)) >= 3 and str(path)[0] in {"/", "\\"} and str(path)[2] == ":":
        path = Path(str(path)[1:])
    text = str(path)
    if re.search(r"%(?:2e|2f|5c)", text, flags=re.IGNORECASE):
        raise InterchangeError("encoded traversal or path separator is forbidden")
    normalized_parts = Path(text.replace("\\", "/")).parts
    if ".." in normalized_parts:
        raise InterchangeError("relative traversal is forbidden in target_url")
    if not path.is_absolute() or "\x00" in text or text.startswith(("\\\\", "//", "\\\\?\\", "\\\\.\\")):
        raise InterchangeError("target_url must be an absolute local non-device path")
    return path


def _is_link_or_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _safe_existing_identity(path: Path) -> str:
    candidate = path
    while candidate != candidate.parent:
        if candidate.exists() and _is_link_or_reparse(candidate):
            raise InterchangeError(f"local reference traverses symlink/reparse: {path}")
        candidate = candidate.parent
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise InterchangeError(f"local reference does not exist: {path}") from exc
    if not resolved.is_file() or _is_link_or_reparse(path):
        raise InterchangeError(f"local reference is not a safe regular file: {path}")
    return os.path.normcase(os.path.normpath(str(resolved)))

"""Qt-free implementation of the approved DATE-001 selection policy."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from .domain import DateCandidate, DateDecision


POLICY_VERSION = "DATE-001/v1"

DATE_TAGS = (
    "creation_time",
    "com.apple.quicktime.creationdate",
    "date_time_original",
    "datetimeoriginal",
    "media_create_date",
    "create_date",
    "encoded_date",
    "date",
)

FILENAME_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<!\d)(\d{8}[_-]\d{6})(?!\d)"), "%Y%m%d_%H%M%S"),
    (re.compile(r"(?<!\d)(\d{14})(?!\d)"), "%Y%m%d%H%M%S"),
    (
        re.compile(
            r"(?<!\d)(\d{4}[-.]\d{2}[-.]\d{2}[ _-]\d{2}[-.]\d{2}[-.]\d{2})(?!\d)"
        ),
        "flexible",
    ),
    (
        re.compile(
            r"(?<!\d)(\d{2}[.]\d{2}[.]\d{4}[ _-]\d{2}[-.]\d{2}(?:[-.]\d{2})?)(?!\d)"
        ),
        "day-first",
    ),
)

_OFFSET_SUFFIX = re.compile(r"([+-]\d{2}:?\d{2})$")


def iter_tag_pairs(probe: dict[str, Any]) -> Iterable[tuple[str, Any]]:
    """Yield FFprobe tags in stable format-then-stream order."""

    format_value = probe.get("format", {})
    format_tags = format_value.get("tags", {}) if isinstance(format_value, dict) else {}
    if isinstance(format_tags, dict):
        yield from format_tags.items()
    streams = probe.get("streams", [])
    if not isinstance(streams, list):
        return
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        tags = stream.get("tags", {})
        if isinstance(tags, dict):
            yield from tags.items()


def _iter_located_tag_pairs(
    probe: dict[str, Any],
) -> Iterator[tuple[str, str, Any]]:
    format_value = probe.get("format", {})
    format_tags = format_value.get("tags", {}) if isinstance(format_value, dict) else {}
    if isinstance(format_tags, dict):
        for key, value in format_tags.items():
            yield "format", str(key), value
    streams = probe.get("streams", [])
    if not isinstance(streams, list):
        return
    for index, stream in enumerate(streams):
        if not isinstance(stream, dict):
            continue
        tags = stream.get("tags", {})
        if isinstance(tags, dict):
            for key, value in tags.items():
                yield f"stream:{index}", str(key), value


def _parse_datetime(value: Any) -> tuple[datetime, str, str | None] | None:
    if not isinstance(value, str):
        return None
    raw_value = value
    text = value.strip()
    if not text:
        return None

    timezone: str | None = None
    if text.startswith("UTC "):
        timezone = "UTC"
        text = text[4:]

    iso_candidate = text
    if text.endswith("Z"):
        timezone = "Z"
        iso_candidate = text[:-1] + "+00:00"
    else:
        offset_match = _OFFSET_SUFFIX.search(text)
        if offset_match:
            timezone = offset_match.group(1)
    try:
        parsed = datetime.fromisoformat(iso_candidate)
        return parsed.replace(tzinfo=None), raw_value, timezone
    except ValueError:
        pass

    local_text = (
        text[: -len(timezone)]
        if timezone is not None and timezone not in {"UTC", "Z"}
        else text
    )
    formats = (
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y%m%d_%H%M%S",
        "%Y%m%d-%H%M%S",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
    )
    for date_format in formats:
        try:
            return datetime.strptime(local_text, date_format), raw_value, timezone
        except ValueError:
            continue
    return None


def parse_datetime_text(value: Any) -> datetime | None:
    """Legacy parser returning recorded wall-clock fields without tzinfo."""

    parsed = _parse_datetime(value)
    return parsed[0] if parsed is not None else None


def metadata_candidates(probe: dict[str, Any]) -> tuple[DateCandidate, ...]:
    """Collect valid candidates by tag priority and source occurrence."""

    located = tuple(_iter_located_tag_pairs(probe))
    candidates: list[DateCandidate] = []
    for priority, wanted_key in enumerate(DATE_TAGS):
        for location, actual_key, value in located:
            if actual_key.casefold() != wanted_key.casefold():
                continue
            parsed = _parse_datetime(value)
            if parsed is None:
                continue
            wall_time, raw_value, timezone = parsed
            candidates.append(
                DateCandidate(
                    wall_time=wall_time,
                    raw_value=raw_value,
                    origin="metadata",
                    key=wanted_key,
                    raw_key=actual_key,
                    location=location,
                    timezone=timezone,
                    priority=priority,
                )
            )
    return tuple(candidates)


def filename_candidate(path: Path) -> DateCandidate | None:
    """Return the first valid legacy filename date pattern, if present."""

    stem = path.stem
    for pattern, date_format in FILENAME_PATTERNS:
        match = pattern.search(stem)
        if not match:
            continue
        raw_value = match.group(1)
        try:
            if date_format == "%Y%m%d_%H%M%S":
                parsed = datetime.strptime(raw_value.replace("-", "_"), date_format)
            elif date_format == "flexible":
                parsed = datetime.strptime(re.sub(r"\D", "", raw_value), "%Y%m%d%H%M%S")
            elif date_format == "day-first":
                digits = re.sub(r"\D", "", raw_value)
                date_format = "%d%m%Y%H%M%S" if len(digits) == 14 else "%d%m%Y%H%M"
                parsed = datetime.strptime(digits, date_format)
            else:
                parsed = datetime.strptime(raw_value, date_format)
        except ValueError:
            continue
        return DateCandidate(
            wall_time=parsed,
            raw_value=raw_value,
            origin="filename",
            key=None,
            raw_key=None,
            location="filename",
            timezone=None,
            priority=len(DATE_TAGS),
        )
    return None


def decide_date(probe: dict[str, Any], path: Path) -> DateDecision | None:
    """Resolve a date and retain every valid candidate for diagnostics."""

    candidates = list(metadata_candidates(probe))
    from_filename = filename_candidate(path)
    if from_filename is not None:
        candidates.append(from_filename)
    if not candidates:
        return None
    selected = candidates[0]
    conflicts = tuple(
        candidate
        for candidate in candidates[1:]
        if (candidate.wall_time, candidate.timezone)
        != (selected.wall_time, selected.timezone)
    )
    return DateDecision(
        selected=selected,
        all_valid=tuple(candidates),
        conflicts=conflicts,
        policy_version=POLICY_VERSION,
    )


def datetime_from_metadata(probe: dict[str, Any]) -> tuple[datetime, str] | None:
    """Legacy adapter for callers that only need the selected metadata date."""

    candidates = metadata_candidates(probe)
    if not candidates:
        return None
    selected = candidates[0]
    return selected.wall_time, selected.source


def datetime_from_filename(path: Path) -> tuple[datetime, str] | None:
    """Legacy adapter for callers that only need the filename date."""

    candidate = filename_candidate(path)
    if candidate is None:
        return None
    return candidate.wall_time, candidate.source

"""Qt-free immutable configuration for the date overlay."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
import stat
from typing import Literal


OverlayFormat = Literal["dd.MM.yy ddd", "dd.MM.yyyy", "dd.MM.yyyy HH:mm"]
OverlayPosition = Literal[
    "top-left", "top-right", "bottom-left", "bottom-right"
]

OVERLAY_FORMATS: tuple[OverlayFormat, ...] = (
    "dd.MM.yy ddd",
    "dd.MM.yyyy",
    "dd.MM.yyyy HH:mm",
)
OVERLAY_POSITIONS: tuple[OverlayPosition, ...] = (
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
)
MAX_FONT_BYTES = 64 * 1024 * 1024
FontIdentity = tuple[int, int, int, int]


@dataclass(frozen=True)
class OverlayConfig:
    """Validated date-overlay values shared by planning, preview and export.

    Defaults reproduce the historical ``join_media.py`` drawtext appearance.
    ``font_file=None`` means that the caller has not resolved the verified
    system fallback yet; tool-facing requests must call
    :func:`resolve_overlay_font` first.
    """

    enabled: bool = True
    format: OverlayFormat = "dd.MM.yy ddd"
    position: OverlayPosition = "bottom-left"
    horizontal_margin: int = 20
    vertical_margin: int = 20
    font_size: int = 72
    text_color: str = "#000000"
    outline_color: str = "#FFFFFF"
    outline_width: int = 4
    font_file: Path | None = None
    font_identity: FontIdentity | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ValueError("overlay enabled must be a boolean")
        if self.format not in OVERLAY_FORMATS:
            raise ValueError(f"unsupported overlay format: {self.format}")
        if self.position not in OVERLAY_POSITIONS:
            raise ValueError(f"unsupported overlay position: {self.position}")
        _validate_range("horizontal margin", self.horizontal_margin, 0, 300)
        _validate_range("vertical margin", self.vertical_margin, 0, 300)
        _validate_range("font size", self.font_size, 12, 200)
        _validate_range("outline width", self.outline_width, 0, 20)
        _validate_color("text color", self.text_color)
        _validate_color("outline color", self.outline_color)
        if self.font_file is not None:
            font, identity = _validated_font(self.font_file, ValueError)
            object.__setattr__(self, "font_file", font)
            object.__setattr__(self, "font_identity", identity)


def resolve_overlay_font(
    config: OverlayConfig, fallback: Path | None
) -> OverlayConfig:
    """Return a config with one verified font path or a clear diagnostic."""

    if not config.enabled:
        return config
    if config.font_file is not None:
        return config
    if fallback is None or not fallback.is_file():
        raise RuntimeError(
            "No supported overlay font was found. Select an existing .ttf or .otf file."
        )
    return replace(config, font_file=fallback.resolve())


def require_resolved_overlay_font(config: OverlayConfig) -> None:
    """Revalidate the exact font identity immediately before a tool boundary."""

    if not config.enabled:
        return
    if config.font_file is None:
        raise RuntimeError(
            "No supported overlay font was found. Select an existing .ttf or .otf file."
        )
    _, identity = _validated_font(config.font_file, RuntimeError)
    if identity != config.font_identity:
        raise RuntimeError(f"overlay font changed after validation: {config.font_file}")


def _validated_font(
    value: Path, error_type: type[ValueError] | type[RuntimeError]
) -> tuple[Path, FontIdentity]:
    font = value.expanduser()
    if str(font).startswith((r"\\", "//")):
        raise error_type("overlay font must be a local file, not a UNC path")
    try:
        source_stat = font.lstat()
    except OSError as exc:
        raise error_type(f"overlay font does not exist: {font}") from exc
    attributes = getattr(source_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if stat.S_ISLNK(source_stat.st_mode) or bool(attributes & reparse_flag):
        raise error_type(f"overlay font must not be a symlink or reparse point: {font}")
    try:
        resolved = font.resolve(strict=True)
        resolved_stat = resolved.stat()
    except OSError as exc:
        raise error_type(f"overlay font does not exist: {font}") from exc
    if resolved.suffix.casefold() not in {".ttf", ".otf"}:
        raise error_type("overlay font must be a .ttf or .otf file")
    if not stat.S_ISREG(resolved_stat.st_mode):
        raise error_type(f"overlay font must be a regular file: {resolved}")
    if resolved_stat.st_size > MAX_FONT_BYTES:
        raise error_type(
            f"overlay font exceeds the {MAX_FONT_BYTES // (1024 * 1024)} MiB limit: {resolved}"
        )
    identity: FontIdentity = (
        resolved_stat.st_dev,
        resolved_stat.st_ino,
        resolved_stat.st_size,
        resolved_stat.st_mtime_ns,
    )
    return resolved, identity


def _validate_range(label: str, value: int, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"overlay {label} must be between {minimum} and {maximum}")


def _validate_color(label: str, value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 7
        or value[0] != "#"
        or any(character not in "0123456789abcdefABCDEF" for character in value[1:])
    ):
        raise ValueError(f"overlay {label} must use #RRGGBB")


DEFAULT_OVERLAY_CONFIG = OverlayConfig()

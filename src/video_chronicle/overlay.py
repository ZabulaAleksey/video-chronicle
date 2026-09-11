"""Qt-free immutable configuration and formatting for the date/time overlay."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from functools import lru_cache
import os
from pathlib import Path
import re
import stat
from typing import Literal


LegacyOverlayFormat = Literal[
    "dd.MM.yy ddd", "dd.MM.yyyy", "dd.MM.yyyy HH:mm"
]
DateFormat = Literal[
    "DD.MM.YY ddd",
    "DD.MM.YYYY",
    "DD/MM/YYYY",
    "YYYY-MM-DD",
    "MM/DD/YYYY",
    "DD MMM YYYY",
    "DD MMMM YYYY",
    "CUSTOM",
]
TimeFormat = Literal["HH:mm", "HH:mm:ss", "hh:mm A", "hh:mm:ss A"]
OverlayLayout = Literal["inline", "separator", "multiline"]
OverlayPosition = Literal[
    "top-left", "top-right", "bottom-left", "bottom-right"
]

OVERLAY_FORMATS: tuple[LegacyOverlayFormat, ...] = (
    "dd.MM.yy ddd",
    "dd.MM.yyyy",
    "dd.MM.yyyy HH:mm",
)
DATE_FORMATS: tuple[DateFormat, ...] = (
    "DD.MM.YY ddd",
    "DD.MM.YYYY",
    "DD/MM/YYYY",
    "YYYY-MM-DD",
    "MM/DD/YYYY",
    "DD MMM YYYY",
    "DD MMMM YYYY",
    "CUSTOM",
)
TIME_FORMATS: tuple[TimeFormat, ...] = (
    "HH:mm",
    "HH:mm:ss",
    "hh:mm A",
    "hh:mm:ss A",
)
OVERLAY_LAYOUTS: tuple[OverlayLayout, ...] = (
    "inline",
    "separator",
    "multiline",
)
OVERLAY_POSITIONS: tuple[OverlayPosition, ...] = (
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
)
MAX_FONT_BYTES = 64 * 1024 * 1024
FontIdentity = tuple[int, int, int, int]
_CUSTOM_DATE_TOKENS = ("YYYY", "MMMM", "MMM", "ddd", "YY", "MM", "DD")
_CUSTOM_DATE_LITERALS = frozenset(" .,/:-_")
_MONTHS_ABBREV_EN = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)
_MONTHS_FULL_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_WEEKDAY_ABBREV_RU = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


@dataclass(frozen=True, slots=True)
class FontFace:
    """One locally available file-backed system font face."""

    family: str
    path: Path
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True)
class OverlayConfig:
    """Validated settings shared by planning, preview, persistence and export.

    ``format`` is the accepted OVERLAY-001 compatibility input. New callers set
    it to ``None`` and use the semantic date/time fields. A resolved system
    family path is runtime-only so projects remain portable between machines.
    """

    enabled: bool = True
    format: LegacyOverlayFormat | None = "dd.MM.yy ddd"
    show_date: bool = True
    show_time: bool = False
    date_format: DateFormat = "DD.MM.YY ddd"
    custom_date_format: str | None = None
    time_format: TimeFormat = "HH:mm"
    layout: OverlayLayout = "inline"
    separator: str = " "
    position: OverlayPosition = "bottom-left"
    horizontal_margin: int = 20
    vertical_margin: int = 20
    font_family: str | None = None
    font_size: int = 72
    bold: bool = False
    italic: bool = False
    text_color: str = "#000000"
    opacity: float = 1.0
    outline_enabled: bool = True
    outline_color: str = "#FFFFFF"
    outline_width: int = 4
    shadow_enabled: bool = False
    shadow_opacity: float = 0.5
    shadow_offset_x: int = 2
    shadow_offset_y: int = 2
    font_file: Path | None = None
    resolved_font_file: Path | None = field(
        default=None, compare=False, repr=False
    )
    font_identity: FontIdentity | None = field(
        init=False, default=None, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ValueError("overlay enabled must be a boolean")
        if self.format is not None:
            try:
                date_format, show_time, time_format = {
                    "dd.MM.yy ddd": ("DD.MM.YY ddd", False, "HH:mm"),
                    "dd.MM.yyyy": ("DD.MM.YYYY", False, "HH:mm"),
                    "dd.MM.yyyy HH:mm": ("DD.MM.YYYY", True, "HH:mm"),
                }[self.format]
            except KeyError as exc:
                raise ValueError(f"unsupported overlay format: {self.format}") from exc
            object.__setattr__(self, "show_date", True)
            object.__setattr__(self, "show_time", show_time)
            object.__setattr__(self, "date_format", date_format)
            object.__setattr__(self, "time_format", time_format)
            object.__setattr__(self, "layout", "inline")
            object.__setattr__(self, "separator", " ")
        for value, label in (
            (self.show_date, "show_date"),
            (self.show_time, "show_time"),
            (self.bold, "bold"),
            (self.italic, "italic"),
            (self.outline_enabled, "outline_enabled"),
            (self.shadow_enabled, "shadow_enabled"),
        ):
            if type(value) is not bool:
                raise ValueError(f"overlay {label} must be a boolean")
        if self.enabled and not (self.show_date or self.show_time):
            raise ValueError("enabled overlay must show date, time, or both")
        if self.date_format not in DATE_FORMATS:
            raise ValueError(f"unsupported overlay date format: {self.date_format}")
        if self.date_format == "CUSTOM":
            validate_custom_date_format(self.custom_date_format)
        elif self.custom_date_format is not None:
            raise ValueError("custom date format requires the CUSTOM preset")
        if self.time_format not in TIME_FORMATS:
            raise ValueError(f"unsupported overlay time format: {self.time_format}")
        if self.layout not in OVERLAY_LAYOUTS:
            raise ValueError(f"unsupported overlay layout: {self.layout}")
        _validate_separator(self.separator)
        if self.position not in OVERLAY_POSITIONS:
            raise ValueError(f"unsupported overlay position: {self.position}")
        _validate_range("horizontal margin", self.horizontal_margin, 0, 300)
        _validate_range("vertical margin", self.vertical_margin, 0, 300)
        _validate_range("font size", self.font_size, 12, 200)
        _validate_range("outline width", self.outline_width, 0, 20)
        _validate_range("shadow offset x", self.shadow_offset_x, -50, 50)
        _validate_range("shadow offset y", self.shadow_offset_y, -50, 50)
        _validate_opacity("opacity", self.opacity)
        _validate_opacity("shadow opacity", self.shadow_opacity)
        _validate_color("text color", self.text_color)
        _validate_color("outline color", self.outline_color)
        if self.font_family is not None:
            if (
                not isinstance(self.font_family, str)
                or not self.font_family
                or self.font_family.strip() != self.font_family
                or len(self.font_family) > 128
                or any(ord(character) < 32 for character in self.font_family)
            ):
                raise ValueError("overlay font family must be a valid local family name")
        if self.font_family is not None and self.font_file is not None:
            raise ValueError(
                "overlay font family and explicit font file are mutually exclusive"
            )
        identities: list[FontIdentity] = []
        if self.font_file is not None:
            font, identity = _validated_font(self.font_file, ValueError)
            object.__setattr__(self, "font_file", font)
            identities.append(identity)
        if self.resolved_font_file is not None:
            font, identity = _validated_font(self.resolved_font_file, ValueError)
            object.__setattr__(self, "resolved_font_file", font)
            identities.append(identity)
        if identities:
            object.__setattr__(self, "font_identity", identities[-1])

    @property
    def effective_font_file(self) -> Path | None:
        return self.font_file or self.resolved_font_file


def validate_custom_date_format(value: str | None) -> str:
    """Validate a bounded token format without exposing strftime/FFmpeg syntax."""

    if not isinstance(value, str) or not value or len(value) > 64:
        raise ValueError("custom date format must contain 1..64 characters")
    offset = 0
    token_count = 0
    while offset < len(value):
        token = next(
            (candidate for candidate in _CUSTOM_DATE_TOKENS if value.startswith(candidate, offset)),
            None,
        )
        if token is not None:
            token_count += 1
            offset += len(token)
            continue
        if value[offset] not in _CUSTOM_DATE_LITERALS:
            raise ValueError(
                "custom date format contains an unsupported token or character"
            )
        offset += 1
    if token_count == 0:
        raise ValueError("custom date format must contain at least one date token")
    return value


def format_overlay_text(value: datetime, config: OverlayConfig) -> str:
    """Canonical deterministic formatter used before every text renderer."""

    if not isinstance(value, datetime):
        raise TypeError("overlay value must be a datetime")
    parts: list[str] = []
    if config.show_date:
        pattern = (
            validate_custom_date_format(config.custom_date_format)
            if config.date_format == "CUSTOM"
            else config.date_format
        )
        parts.append(_format_date(value, pattern))
    if config.show_time:
        parts.append(_format_time(value, config.time_format))
    if len(parts) < 2:
        return parts[0] if parts else ""
    if config.layout == "multiline":
        return "\n".join(parts)
    if config.layout == "separator":
        return config.separator.join(parts)
    return " ".join(parts)


def _format_date(value: datetime, pattern: str) -> str:
    replacements = {
        "YYYY": f"{value.year:04d}",
        "YY": f"{value.year % 100:02d}",
        "MMMM": _MONTHS_FULL_EN[value.month - 1],
        "MMM": _MONTHS_ABBREV_EN[value.month - 1],
        "MM": f"{value.month:02d}",
        "DD": f"{value.day:02d}",
        "ddd": _WEEKDAY_ABBREV_RU[value.weekday()],
    }
    result: list[str] = []
    offset = 0
    while offset < len(pattern):
        token = next(
            (candidate for candidate in _CUSTOM_DATE_TOKENS if pattern.startswith(candidate, offset)),
            None,
        )
        if token is None:
            result.append(pattern[offset])
            offset += 1
        else:
            result.append(replacements[token])
            offset += len(token)
    return "".join(result)


def _format_time(value: datetime, pattern: TimeFormat) -> str:
    if pattern == "HH:mm":
        return f"{value.hour:02d}:{value.minute:02d}"
    if pattern == "HH:mm:ss":
        return f"{value.hour:02d}:{value.minute:02d}:{value.second:02d}"
    hour = value.hour % 12 or 12
    suffix = "AM" if value.hour < 12 else "PM"
    if pattern == "hh:mm A":
        return f"{hour:02d}:{value.minute:02d} {suffix}"
    return f"{hour:02d}:{value.minute:02d}:{value.second:02d} {suffix}"


def resolve_overlay_font(
    config: OverlayConfig,
    fallback: Path | None,
    *,
    fonts: tuple[FontFace, ...] | None = None,
) -> OverlayConfig:
    """Resolve a selected family to a face, or use the verified fallback."""

    if not config.enabled:
        return config
    if config.font_file is not None or config.resolved_font_file is not None:
        return config
    selected: Path | None = None
    if config.font_family is not None:
        face = select_font_face(
            config.font_family,
            config.bold,
            config.italic,
            available_overlay_fonts() if fonts is None else fonts,
        )
        if face is not None and face.path.is_file():
            selected = face.path
    if selected is None and fallback is not None and fallback.is_file():
        selected = fallback
    if selected is None:
        raise RuntimeError(
            "No supported overlay font was found. Select an existing .ttf or .otf file."
        )
    selected, _identity = _validated_font(selected, RuntimeError)
    if config.font_family is not None:
        return replace(config, resolved_font_file=selected)
    return replace(config, font_file=selected)


def require_resolved_overlay_font(config: OverlayConfig) -> None:
    """Revalidate the exact effective font immediately before a tool boundary."""

    if not config.enabled:
        return
    font = config.effective_font_file
    if font is None:
        raise RuntimeError(
            "No supported overlay font was found. Select an existing .ttf or .otf file."
        )
    _, identity = _validated_font(font, RuntimeError)
    if identity != config.font_identity:
        raise RuntimeError(f"overlay font changed after validation: {font}")


def select_font_face(
    family: str,
    bold: bool,
    italic: bool,
    fonts: tuple[FontFace, ...],
) -> FontFace | None:
    """Choose an exact style, then the closest deterministic family face."""

    matches = sorted(
        (face for face in fonts if face.family.casefold() == family.casefold()),
        key=lambda face: (
            (face.bold != bold) + (face.italic != italic),
            face.bold,
            face.italic,
            str(face.path),
        ),
    )
    return matches[0] if matches else None


def available_overlay_font_families() -> tuple[str, ...]:
    families = {face.family for face in available_overlay_fonts()}
    return tuple(sorted(families, key=str.casefold))


@lru_cache(maxsize=1)
def available_overlay_fonts() -> tuple[FontFace, ...]:
    """Return deterministic file-backed system faces without hardcoded user paths."""

    faces: list[FontFace] = []
    if os.name == "nt":
        faces.extend(_windows_registry_fonts())
    if not faces:
        faces.extend(_fonts_from_standard_directories())
    deduplicated: dict[tuple[str, bool, bool], FontFace] = {}
    for face in faces:
        key = (face.family.casefold(), face.bold, face.italic)
        if face.path.is_file() and key not in deduplicated:
            deduplicated[key] = face
    return tuple(
        sorted(
            deduplicated.values(),
            key=lambda face: (face.family.casefold(), face.bold, face.italic, str(face.path)),
        )
    )


def _windows_registry_fonts() -> list[FontFace]:
    try:
        import winreg
    except ImportError:
        return []
    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    locations = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts", windows_dir / "Fonts"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts", Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/Fonts"),
    )
    result: list[FontFace] = []
    for hive, key_name, base in locations:
        try:
            key = winreg.OpenKey(hive, key_name)
        except OSError:
            continue
        with key:
            index = 0
            while True:
                try:
                    display_name, raw_path, _kind = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                if not isinstance(raw_path, str):
                    continue
                path = Path(raw_path)
                if not path.is_absolute():
                    path = base / path
                face = _font_face_from_label(display_name, path)
                if face is not None:
                    result.append(face)
    return result


def _fonts_from_standard_directories() -> list[FontFace]:
    home = Path.home()
    candidates = [
        home / ".local/share/fonts",
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        home / "Library/Fonts",
        Path("/Library/Fonts"),
    ]
    windows_dir = os.environ.get("WINDIR")
    if windows_dir:
        candidates.insert(0, Path(windows_dir) / "Fonts")
    result: list[FontFace] = []
    for directory in candidates:
        if not directory.is_dir():
            continue
        try:
            paths = sorted(
                path for path in directory.rglob("*")
                if path.suffix.casefold() in {".ttf", ".otf"}
            )
        except OSError:
            continue
        for path in paths:
            face = _font_face_from_label(path.stem, path)
            if face is not None:
                result.append(face)
    return result


def _font_face_from_label(label: str, path: Path) -> FontFace | None:
    if path.suffix.casefold() not in {".ttf", ".otf"}:
        return None
    cleaned = re.sub(r"\s*\((?:TrueType|OpenType)\)\s*$", "", label, flags=re.I)
    cleaned = cleaned.replace("-", " ").strip()
    bold = bool(re.search(r"\b(?:bold|semibold|demibold|black)\b", cleaned, re.I))
    italic = bool(re.search(r"\b(?:italic|oblique)\b", cleaned, re.I))
    family = re.sub(
        r"\s*\b(?:regular|normal|bold|semibold|demibold|black|italic|oblique)\b",
        "",
        cleaned,
        flags=re.I,
    )
    family = re.sub(r"\s+", " ", family).strip()
    return FontFace(family or cleaned, path, bold, italic)


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


def _validate_opacity(label: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"overlay {label} must be between 0 and 1")


def _validate_color(label: str, value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 7
        or value[0] != "#"
        or any(character not in "0123456789abcdefABCDEF" for character in value[1:])
    ):
        raise ValueError(f"overlay {label} must use #RRGGBB")


def _validate_separator(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 8
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("overlay separator must contain 1..8 printable characters")


def overlay_settings_mapping(value: OverlayConfig) -> dict[str, object]:
    """Return the canonical persisted/digested mapping for one config.

    Legacy configs keep their exact OVERLAY-001 shape so existing project plan
    IDs remain valid. New configs use the nested overlay schema version 2.
    Runtime family resolution is deliberately excluded.
    """

    font_identity = (
        list(value.font_identity)
        if value.font_file is not None and value.font_identity is not None
        else None
    )
    common: dict[str, object] = {
        "enabled": value.enabled,
        "position": value.position,
        "horizontal_margin": value.horizontal_margin,
        "vertical_margin": value.vertical_margin,
        "font_size": value.font_size,
        "text_color": value.text_color,
        "outline_color": value.outline_color,
        "outline_width": value.outline_width,
        "font_file": None if value.font_file is None else str(value.font_file),
        "font_identity": font_identity,
    }
    if value.format is not None:
        return {"enabled": value.enabled, "format": value.format, **{
            key: item for key, item in common.items() if key != "enabled"
        }}
    return {
        "version": 2,
        "enabled": value.enabled,
        "show_date": value.show_date,
        "show_time": value.show_time,
        "date_format": value.date_format,
        "custom_date_format": value.custom_date_format,
        "time_format": value.time_format,
        "layout": value.layout,
        "separator": value.separator,
        "font_family": value.font_family,
        "bold": value.bold,
        "italic": value.italic,
        "opacity": value.opacity,
        "outline_enabled": value.outline_enabled,
        "shadow_enabled": value.shadow_enabled,
        "shadow_opacity": value.shadow_opacity,
        "shadow_offset_x": value.shadow_offset_x,
        "shadow_offset_y": value.shadow_offset_y,
        **{key: item for key, item in common.items() if key != "enabled"},
    }


DEFAULT_OVERLAY_CONFIG = OverlayConfig()

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

import pytest

import join_media


def _close_join_media_logger() -> None:
    logger = logging.getLogger("join_media")
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()


def test_parse_args_preserves_legacy_cli_contract(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "медиа folder"
    output = tmp_path / "готовое video.mp4"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "join_media.py",
            "--input-dir",
            str(input_dir),
            "--output",
            str(output),
            "--ffmpeg",
            "custom ffmpeg",
            "--ffprobe",
            "custom ffprobe",
            "--crf",
            "18",
            "--preset",
            "slow",
            "--overwrite",
        ],
    )

    args = join_media.parse_args()

    assert args.input_dir == input_dir
    assert args.output == output
    assert args.ffmpeg == "custom ffmpeg"
    assert args.ffprobe == "custom ffprobe"
    assert args.crf == 18
    assert args.preset == "slow"
    assert args.overwrite is True


def test_collect_source_paths_is_sorted_and_excludes_outputs(tmp_path: Path) -> None:
    output = tmp_path / "output.mp4"
    error_log = tmp_path / "errors.log"
    accepted = [tmp_path / "Бета.JPG", tmp_path / "alpha.mp4"]
    ignored = [tmp_path / "notes.txt", output, error_log]
    for path in accepted + ignored:
        path.write_bytes(b"fixture")

    result = join_media.collect_source_paths(tmp_path, output, error_log)

    assert result == [tmp_path / "alpha.mp4", tmp_path / "Бета.JPG"]


def test_existing_output_is_not_changed_without_overwrite(
    monkeypatch, tmp_path: Path
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output = tmp_path / "existing.mp4"
    original = b"existing-result"
    output.write_bytes(original)
    error_log = tmp_path / "errors.log"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "join_media.py",
            "--input-dir",
            str(input_dir),
            "--output",
            str(output),
            "--error-log",
            str(error_log),
        ],
    )

    try:
        exit_code = join_media.main()
    finally:
        _close_join_media_logger()

    assert exit_code == 1
    assert output.read_bytes() == original
    assert "output already exists" in error_log.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2024-01-02T03:04:05Z", datetime(2024, 1, 2, 3, 4, 5)),
        ("2024:01:02 03:04:05", datetime(2024, 1, 2, 3, 4, 5)),
        ("02.01.2024 03:04", datetime(2024, 1, 2, 3, 4)),
    ],
)
def test_parse_datetime_text_characterizes_supported_formats(
    value: str, expected: datetime
) -> None:
    assert join_media.parse_datetime_text(value) == expected


def test_metadata_date_has_priority_over_filename_date(tmp_path: Path) -> None:
    probe = {
        "format": {"tags": {"creation_time": "2024-01-02T03:04:05Z"}},
        "streams": [{"codec_type": "video"}],
    }

    path = tmp_path / "clip_20250102_030405.mp4"
    original_probe_media = join_media.probe_media
    join_media.probe_media = lambda _path, _ffprobe: probe
    try:
        item = join_media.inspect_item(path, "ffprobe")
    finally:
        join_media.probe_media = original_probe_media

    assert item.taken_at == datetime(2024, 1, 2, 3, 4, 5)
    assert item.date_source == "metadata:creation_time"


def test_main_orders_items_by_date_then_casefolded_name(
    monkeypatch, tmp_path: Path
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    paths = [input_dir / "z.mp4", input_dir / "B.mp4", input_dir / "a.mp4"]
    for path in paths:
        path.write_bytes(b"source")
    output = tmp_path / "result.mp4"
    error_log = tmp_path / "errors.log"
    timestamps = {
        "z.mp4": datetime(2024, 1, 2),
        "B.mp4": datetime(2024, 1, 1),
        "a.mp4": datetime(2024, 1, 1),
    }
    encoded_order: list[str] = []

    def fake_inspect(path: Path, _ffprobe: str) -> join_media.MediaItem:
        return join_media.MediaItem(
            path=path,
            taken_at=timestamps[path.name],
            is_photo=False,
            has_audio=True,
            date_source="fixture",
        )

    def fake_normalize(
        item: join_media.MediaItem,
        destination: Path,
        _ffmpeg: str,
        _font_file: Path | None,
        _crf: int,
        _preset: str,
    ) -> None:
        encoded_order.append(item.path.name)
        destination.write_bytes(b"clip")

    def fake_concatenate(
        _clips: list[Path],
        _concat_file: Path,
        temporary_output: Path,
        _ffmpeg: str,
    ) -> None:
        temporary_output.write_bytes(b"movie")

    monkeypatch.setattr(join_media, "resolve_executable", lambda value, label: value)
    monkeypatch.setattr(join_media, "find_default_font", lambda: None)
    monkeypatch.setattr(join_media, "inspect_item", fake_inspect)
    monkeypatch.setattr(join_media, "normalize_item", fake_normalize)
    monkeypatch.setattr(join_media, "concatenate", fake_concatenate)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "join_media.py",
            "--input-dir",
            str(input_dir),
            "--output",
            str(output),
            "--error-log",
            str(error_log),
        ],
    )

    try:
        exit_code = join_media.main()
    finally:
        _close_join_media_logger()

    assert exit_code == 0
    assert encoded_order == ["a.mp4", "B.mp4", "z.mp4"]
    assert output.read_bytes() == b"movie"


def test_publish_output_refuses_file_created_during_processing(tmp_path: Path) -> None:
    temporary_output = tmp_path / "output.building.mp4"
    output = tmp_path / "output.mp4"
    temporary_output.write_bytes(b"new-result")
    output.write_bytes(b"appeared-during-render")

    with pytest.raises(RuntimeError, match="appeared during processing"):
        join_media.publish_output(temporary_output, output, overwrite=False)

    assert output.read_bytes() == b"appeared-during-render"
    assert temporary_output.read_bytes() == b"new-result"


def test_publish_output_atomically_creates_new_result(tmp_path: Path) -> None:
    temporary_output = tmp_path / "output.building.mp4"
    output = tmp_path / "output.mp4"
    temporary_output.write_bytes(b"new-result")

    join_media.publish_output(temporary_output, output, overwrite=False)

    assert output.read_bytes() == b"new-result"
    assert temporary_output.exists() is False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows no-replace path")
def test_windows_publish_does_not_require_hard_link(
    monkeypatch, tmp_path: Path
) -> None:
    temporary_output = tmp_path / "output.building.mp4"
    output = tmp_path / "output.mp4"
    temporary_output.write_bytes(b"new-result")
    monkeypatch.setattr(
        join_media.os,
        "link",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("unsupported")),
    )

    join_media.publish_output(temporary_output, output, overwrite=False)

    assert output.read_bytes() == b"new-result"

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

import join_media


def _close_join_media_logger() -> None:
    logger = logging.getLogger("join_media")
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()


def _run_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["join_media.py", *argv])
    try:
        return join_media.main()
    finally:
        _close_join_media_logger()


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("UTC 2024-02-29 23:59:59", datetime(2024, 2, 29, 23, 59, 59)),
        (
            "2024-01-02T03:04:05.987654+14:00",
            datetime(2024, 1, 2, 3, 4, 5, 987654),
        ),
        ("2023-02-29 12:00:00", None),
        ("2024-01-02T24:00:00Z", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_datetime_text_characterizes_boundaries(
    value: Any, expected: datetime | None
) -> None:
    assert join_media.parse_datetime_text(value) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("IMG_20240229_235959.jpg", datetime(2024, 2, 29, 23, 59, 59)),
        ("clip-20240229-235959.mp4", datetime(2024, 2, 29, 23, 59, 59)),
        ("VID_20240229235959.mov", datetime(2024, 2, 29, 23, 59, 59)),
        ("2024.02.29-23.59.59 vacation.mkv", datetime(2024, 2, 29, 23, 59, 59)),
        ("29.02.2024_23-59 family.png", datetime(2024, 2, 29, 23, 59)),
        ("29.02.2024-23.59.59 family.png", datetime(2024, 2, 29, 23, 59, 59)),
        ("IMG_20230229_120000.jpg", None),
        ("x120240229_2359599.jpg", None),
        ("undated.jpg", None),
    ],
)
def test_datetime_from_filename_characterizes_patterns(
    filename: str, expected: datetime | None
) -> None:
    result = join_media.datetime_from_filename(Path(filename))

    if expected is None:
        assert result is None
    else:
        assert result == (expected, "filename")


def test_metadata_priority_follows_date_tags_not_probe_order() -> None:
    probe = {
        "format": {
            "tags": {
                "create_date": "2024-05-06 07:08:09",
                "date": "2024-01-01 00:00:00",
            }
        },
        "streams": [
            {
                "codec_type": "video",
                "tags": {"creation_time": "2025-06-07T08:09:10Z"},
            }
        ],
    }

    assert join_media.datetime_from_metadata(probe) == (
        datetime(2025, 6, 7, 8, 9, 10),
        "metadata:creation_time",
    )


def test_invalid_higher_priority_metadata_falls_through_to_next_tag() -> None:
    probe = {
        "format": {
            "tags": {
                "creation_time": "not-a-date",
                "date_time_original": "2024:05:06 07:08:09",
            }
        }
    }

    assert join_media.datetime_from_metadata(probe) == (
        datetime(2024, 5, 6, 7, 8, 9),
        "metadata:date_time_original",
    )


def test_metadata_date_has_priority_over_filename_date(tmp_path: Path) -> None:
    probe = {
        "format": {"tags": {"creation_time": "2024-01-02T03:04:05Z"}},
        "streams": [{"codec_type": "video"}],
    }

    path = tmp_path / "clip_20250102_030405.mp4"
    original_probe_media = join_media.probe_media
    join_media.probe_media = lambda _path, _ffprobe, _runner=None: probe
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

    def fake_inspect(
        path: Path, _ffprobe: str, _probe=None, _runner=None
    ) -> join_media.MediaItem:
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
        _runner=None,
    ) -> None:
        encoded_order.append(item.path.name)
        destination.write_bytes(b"clip")

    def fake_concatenate(
        _clips: list[Path],
        _concat_file: Path,
        temporary_output: Path,
        _ffmpeg: str,
        _runner=None,
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


@pytest.mark.parametrize(
    ("is_photo", "has_audio", "expected_inputs", "expected_audio_map"),
    [
        (True, False, 2, "1:a:0"),
        (False, False, 2, "1:a:0"),
        (False, True, 1, "[a]"),
    ],
)
def test_normalize_item_builds_list_argv_for_each_media_shape(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    is_photo: bool,
    has_audio: bool,
    expected_inputs: int,
    expected_audio_map: str,
) -> None:
    source = tmp_path / "источник ' media.jpg"
    destination = tmp_path / "готовый clip.mp4"
    item = join_media.MediaItem(
        path=source,
        taken_at=datetime(2024, 2, 29, 23, 59, 59),
        is_photo=is_photo,
        has_audio=has_audio,
        date_source="fixture",
    )
    calls: list[tuple[list[str], str]] = []
    monkeypatch.setattr(
        join_media,
        "run_command",
        lambda command, context: calls.append((command, context)),
    )

    join_media.normalize_item(
        item,
        destination,
        "trusted ffmpeg",
        None,
        crf=17,
        preset="slow",
    )

    assert len(calls) == 1
    command, context = calls[0]
    assert isinstance(command, list)
    assert command[0] == "trusted ffmpeg"
    assert command.count("-i") == expected_inputs
    assert str(source) in command
    assert command[-1] == str(destination)
    assert command[command.index("-crf") + 1] == "17"
    assert command[command.index("-preset") + 1] == "slow"
    assert expected_audio_map in command
    assert "29.02.24 Чт" in command[command.index("-filter_complex") + 1]
    assert str(source) in context


def test_concatenate_writes_escaped_list_and_list_argv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clips = [tmp_path / "обычный clip.mp4", tmp_path / "quote's clip.mp4"]
    concat_file = tmp_path / "concat list.txt"
    temporary_output = tmp_path / "output building.mp4"
    calls: list[tuple[list[str], str]] = []
    monkeypatch.setattr(
        join_media,
        "run_command",
        lambda command, context: calls.append((command, context)),
    )

    join_media.concatenate(clips, concat_file, temporary_output, "trusted ffmpeg")

    concat_text = concat_file.read_text(encoding="utf-8")
    assert f"file '{join_media.concat_escape(clips[0])}'\n" in concat_text
    assert "quote'\\''s clip.mp4" in concat_text
    command, context = calls[0]
    assert isinstance(command, list)
    assert command == [
        "trusted ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(temporary_output),
    ]
    assert context == "failed to concatenate normalized clips"


def test_empty_input_returns_failure_before_media_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    input_dir = tmp_path / "empty input"
    input_dir.mkdir()
    output = tmp_path / "result.mp4"
    error_log = tmp_path / "errors.log"
    monkeypatch.setattr(join_media, "resolve_executable", lambda value, label: value)
    monkeypatch.setattr(join_media, "find_default_font", lambda: None)

    exit_code = _run_main(
        monkeypatch,
        [
            "--input-dir",
            str(input_dir),
            "--output",
            str(output),
            "--error-log",
            str(error_log),
        ],
    )

    assert exit_code == 1
    assert output.exists() is False
    assert "no supported videos or photos" in error_log.read_text(encoding="utf-8")


def test_corrupt_input_is_skipped_and_source_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    corrupt = input_dir / "20240101_000000-corrupt.mp4"
    original = b"not-media"
    corrupt.write_bytes(original)
    output = tmp_path / "result.mp4"
    error_log = tmp_path / "errors.log"
    monkeypatch.setattr(join_media, "resolve_executable", lambda value, label: value)
    monkeypatch.setattr(join_media, "find_default_font", lambda: None)
    monkeypatch.setattr(
        join_media,
        "inspect_item",
        lambda path, ffprobe: (_ for _ in ()).throw(join_media.MediaError("corrupt")),
    )

    exit_code = _run_main(
        monkeypatch,
        [
            "--input-dir",
            str(input_dir),
            "--output",
            str(output),
            "--error-log",
            str(error_log),
        ],
    )

    assert exit_code == 1
    assert corrupt.read_bytes() == original
    assert output.exists() is False
    log_text = error_log.read_text(encoding="utf-8")
    assert "SKIPPED during inspection" in log_text
    assert "none of the 1 files could be inspected" in log_text


def test_partial_encoding_success_publishes_only_complete_result_and_keeps_inputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    sources = [
        input_dir / "20240101_000000-good.mp4",
        input_dir / "20240102_000000-bad.mp4",
    ]
    originals = {path: f"source-{path.name}".encode() for path in sources}
    for path, content in originals.items():
        path.write_bytes(content)
    output = tmp_path / "result.mp4"
    error_log = tmp_path / "errors.log"

    monkeypatch.setattr(join_media, "resolve_executable", lambda value, label: value)
    monkeypatch.setattr(join_media, "find_default_font", lambda: None)
    monkeypatch.setattr(
        join_media,
        "inspect_item",
        lambda path, ffprobe, probe=None, runner=None: join_media.MediaItem(
            path=path,
            taken_at=datetime_from_name(path.name),
            is_photo=False,
            has_audio=True,
            date_source="filename",
        ),
    )

    def fake_normalize(
        item: join_media.MediaItem,
        destination: Path,
        ffmpeg: str,
        font_file: Path | None,
        crf: int,
        preset: str,
        runner=None,
    ) -> None:
        if "bad" in item.path.name:
            raise join_media.MediaError("encoding failed")
        destination.write_bytes(b"normalized-good")

    def fake_concatenate(
        clips: list[Path], concat_file: Path, temporary_output: Path, ffmpeg: str,
        runner=None,
    ) -> None:
        assert len(clips) == 1
        assert clips[0].read_bytes() == b"normalized-good"
        temporary_output.write_bytes(b"complete-movie")

    monkeypatch.setattr(join_media, "normalize_item", fake_normalize)
    monkeypatch.setattr(join_media, "concatenate", fake_concatenate)

    exit_code = _run_main(
        monkeypatch,
        [
            "--input-dir",
            str(input_dir),
            "--output",
            str(output),
            "--error-log",
            str(error_log),
        ],
    )

    assert exit_code == 0
    assert output.read_bytes() == b"complete-movie"
    assert {path: path.read_bytes() for path in sources} == originals
    assert "SKIPPED during encoding" in error_log.read_text(encoding="utf-8")


def datetime_from_name(filename: str) -> datetime:
    result = join_media.datetime_from_filename(Path(filename))
    assert result is not None
    return result[0]


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


def test_publish_output_replaces_existing_result_only_with_overwrite(
    tmp_path: Path,
) -> None:
    temporary_output = tmp_path / "output.building.mp4"
    output = tmp_path / "output.mp4"
    temporary_output.write_bytes(b"complete-new-result")
    output.write_bytes(b"old-result")

    join_media.publish_output(temporary_output, output, overwrite=True)

    assert output.read_bytes() == b"complete-new-result"
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

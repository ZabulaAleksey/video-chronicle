from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path

import pytest

import join_media


MINIMUM_FFMPEG_VERSION = (9, 0, 1)


def _resolve_tool(environment_name: str, command_name: str) -> str | None:
    configured = os.environ.get(environment_name)
    candidates = [configured, command_name] if configured else [command_name]
    for candidate in candidates:
        if candidate is None:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path.resolve())
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _tool_version(executable: str) -> tuple[tuple[int, int, int], str]:
    result = subprocess.run(
        [executable, "-version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    match = re.search(r"\bversion\s+(?:n)?(\d+)\.(\d+)(?:\.(\d+))?", first_line)
    if result.returncode != 0 or match is None:
        pytest.fail(f"cannot read tool version from {executable!r}: {first_line!r}")
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
    ), first_line


def _run(command: list[str], context: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"{context} failed with exit code {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result


def _snapshot(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest, stat.st_size, stat.st_mtime_ns


def _probe_json(ffprobe: str, path: Path, *arguments: str) -> dict[str, object]:
    result = _run(
        [ffprobe, "-v", "error", *arguments, "-of", "json", str(path)],
        f"probing {path.name}",
    )
    return json.loads(result.stdout)


def _require_media_tools() -> tuple[str, str]:
    ffmpeg = _resolve_tool("VIDEO_CHRONICLE_FFMPEG", "ffmpeg")
    ffprobe = _resolve_tool("VIDEO_CHRONICLE_FFPROBE", "ffprobe")
    missing = [
        name
        for name, executable in (("FFmpeg", ffmpeg), ("FFprobe", ffprobe))
        if executable is None
    ]
    if missing:
        pytest.skip(
            "real media regression skipped: "
            + ", ".join(missing)
            + " not found; set VIDEO_CHRONICLE_FFMPEG/VIDEO_CHRONICLE_FFPROBE "
            "or add the tools to PATH"
        )
    assert ffmpeg is not None
    assert ffprobe is not None
    return ffmpeg, ffprobe


def test_final_concat_keeps_video_timeline_and_encodes_one_continuous_audio_stream(
    tmp_path: Path,
) -> None:
    """MEDIA-SYNC-AC-001..006: AAC payload must not grow past its PTS timeline."""

    ffmpeg, ffprobe = _require_media_tools()
    ffmpeg_version, ffmpeg_line = _tool_version(ffmpeg)
    ffprobe_version, ffprobe_line = _tool_version(ffprobe)
    assert ffmpeg_version >= MINIMUM_FFMPEG_VERSION, ffmpeg_line
    assert ffprobe_version >= MINIMUM_FFMPEG_VERSION, ffprobe_line

    source_cases = (
        ("cfr30", "30", None),
        ("ntsc2997", "30000/1001", None),
        ("ntsc5994", "60000/1001", None),
        (
            "smartphone_vfr",
            "60",
            "select='not(eq(mod(n,7),2)+eq(mod(n,11),4))'",
        ),
    )
    normalized: list[Path] = []
    normalized_frame_counts: list[int] = []
    for index, (name, rate, video_filter) in enumerate(source_cases):
        source = tmp_path / f"{name}.mp4"
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=160x90:rate={rate}:duration=0.5",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={440 + index * 110}:sample_rate=44100:duration=0.5",
        ]
        if video_filter is not None:
            command += ["-vf", video_filter, "-fps_mode", "vfr"]
        command += [
            "-t",
            "0.5",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-video_track_timescale",
            "90000",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-y",
            str(source),
        ]
        _run(command, f"{name} source generation")

        source_streams = _probe_json(
            ffprobe,
            source,
            "-show_entries",
            "stream=codec_type,time_base,r_frame_rate,avg_frame_rate,sample_rate",
        )["streams"]
        source_video = next(
            stream for stream in source_streams if stream["codec_type"] == "video"
        )
        source_audio = next(
            stream for stream in source_streams if stream["codec_type"] == "audio"
        )
        assert source_video["time_base"] == "1/90000"
        assert source_audio["sample_rate"] == "44100"
        if video_filter is None:
            assert Fraction(source_video["r_frame_rate"]) == Fraction(rate)
            assert abs(
                Fraction(source_video["avg_frame_rate"]) - Fraction(rate)
            ) < Fraction(1, 100)
        else:
            assert source_video["r_frame_rate"] != source_video["avg_frame_rate"]

        clip = tmp_path / f"normalized-{name}.mp4"
        join_media.normalize_item(
            join_media.MediaItem(
                path=source,
                taken_at=datetime(2026, 7, index + 1),
                is_photo=False,
                has_audio=True,
                date_source="fixture",
            ),
            clip,
            ffmpeg,
            join_media.OverlayConfig(enabled=False),
            crf=35,
            preset="ultrafast",
        )
        normalized.append(clip)
        normalized_probe = _probe_json(
            ffprobe,
            clip,
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames",
        )
        normalized_frame_counts.append(
            int(normalized_probe["streams"][0]["nb_read_frames"])
        )
        assert normalized_frame_counts[-1] == 30

    repetitions = 90
    clips = normalized * repetitions
    output = tmp_path / "three-minute-timeline.mp4"
    join_media.concatenate(
        clips,
        tmp_path / "timeline-concat.txt",
        output,
        ffmpeg,
    )

    stream_probe = _probe_json(
        ffprobe,
        output,
        "-count_frames",
        "-show_entries",
        "stream=codec_type,time_base,start_time,duration,r_frame_rate,avg_frame_rate,nb_read_frames,sample_rate",
    )
    video_stream = next(
        stream for stream in stream_probe["streams"] if stream["codec_type"] == "video"
    )
    audio_stream = next(
        stream for stream in stream_probe["streams"] if stream["codec_type"] == "audio"
    )
    assert video_stream["time_base"] == "1/60000"
    assert video_stream["r_frame_rate"] == "60/1"
    assert video_stream["avg_frame_rate"] == "60/1"
    assert int(video_stream["nb_read_frames"]) == repetitions * sum(
        normalized_frame_counts
    )
    assert audio_stream["time_base"] == "1/48000"
    assert audio_stream["sample_rate"] == "48000"

    video_frames = _probe_json(
        ffprobe,
        output,
        "-select_streams",
        "v:0",
        "-show_frames",
        "-show_entries",
        "frame=best_effort_timestamp,duration",
    )["frames"]
    video_frame_values = [
        (int(frame["best_effort_timestamp"]), int(frame["duration"]))
        for frame in video_frames
        if "best_effort_timestamp" in frame and "duration" in frame
    ]
    assert len(video_frame_values) == int(video_stream["nb_read_frames"])
    assert all(
        left_timestamp < right_timestamp
        for (left_timestamp, _), (right_timestamp, _) in zip(
            video_frame_values, video_frame_values[1:]
        )
    )

    audio_packets = _probe_json(
        ffprobe,
        output,
        "-select_streams",
        "a:0",
        "-show_packets",
        "-show_entries",
        "packet=pts,dts,duration:packet_side_data=side_data_type,skip_samples,discard_padding",
    )["packets"]
    packet_values = [
        (int(packet["pts"]), int(packet["dts"]), int(packet["duration"]))
        for packet in audio_packets
    ]
    assert all(
        current_pts == previous_pts + previous_duration
        for (previous_pts, _, previous_duration), (current_pts, _, _) in zip(
            packet_values, packet_values[1:]
        )
    )
    assert all(
        previous_dts < current_dts
        for (_, previous_dts, _), (_, current_dts, _) in zip(
            packet_values, packet_values[1:]
        )
    )

    codec_side_data = [
        side_data
        for packet in audio_packets
        for side_data in packet.get("side_data_list", [])
        if side_data.get("side_data_type") == "Skip Samples"
    ]
    skip_samples = sum(int(side_data.get("skip_samples", 0)) for side_data in codec_side_data)
    discard_padding = sum(
        int(side_data.get("discard_padding", 0)) for side_data in codec_side_data
    )
    assert skip_samples >= 0
    assert discard_padding >= 0

    audio_frames = _probe_json(
        ffprobe,
        output,
        "-select_streams",
        "a:0",
        "-show_frames",
        "-show_entries",
        "frame=best_effort_timestamp,nb_samples:frame_side_data=side_data_type,skip_samples,discard_padding",
    )["frames"]
    audio_frame_values = [
        (int(frame["best_effort_timestamp"]), int(frame["nb_samples"]))
        for frame in audio_frames
        if "best_effort_timestamp" in frame and "nb_samples" in frame
    ]
    assert audio_frame_values
    decoded_samples = sum(nb_samples for _, nb_samples in audio_frame_values)
    packet_timeline_samples = sum(duration for _, _, duration in packet_values)
    effective_access_unit_samples = (
        len(packet_values) * 1024 - skip_samples - discard_padding
    )
    assert abs(effective_access_unit_samples - decoded_samples) <= 1024
    assert abs(decoded_samples - packet_timeline_samples) <= 1024

    decoded_checkpoint_surplus: list[int] = []
    first_audio_timestamp = audio_frame_values[0][0]
    for frame_count in (1, len(audio_frame_values) // 2, len(audio_frame_values)):
        decoded_checkpoint_samples = sum(
            nb_samples for _, nb_samples in audio_frame_values[:frame_count]
        )
        last_timestamp, last_nb_samples = audio_frame_values[frame_count - 1]
        timestamp_checkpoint_samples = (
            last_timestamp + last_nb_samples - first_audio_timestamp
        )
        decoded_checkpoint_surplus.append(
            decoded_checkpoint_samples - timestamp_checkpoint_samples
        )
    assert max(abs(value) for value in decoded_checkpoint_surplus) <= 1024
    assert max(decoded_checkpoint_surplus) - min(decoded_checkpoint_surplus) <= 1024

    video_time_base = Fraction(video_stream["time_base"])
    audio_time_base = Fraction(audio_stream["time_base"])
    video_decoded_start = video_frame_values[0][0] * video_time_base
    video_decoded_end = sum(video_frame_values[-1]) * video_time_base
    audio_decoded_start = audio_frame_values[0][0] * audio_time_base
    audio_decoded_end = sum(audio_frame_values[-1]) * audio_time_base
    aac_unit = Fraction(1024, 48000)

    video_stream_start = Fraction(video_stream["start_time"])
    video_stream_end = video_stream_start + Fraction(video_stream["duration"])
    audio_stream_start = Fraction(audio_stream["start_time"])
    audio_stream_end = audio_stream_start + Fraction(audio_stream["duration"])
    assert abs(video_stream_start - video_decoded_start) <= aac_unit
    assert abs(video_stream_end - video_decoded_end) <= aac_unit
    assert abs(audio_stream_start - audio_decoded_start) <= aac_unit
    assert abs(audio_stream_end - audio_decoded_end) <= aac_unit
    assert abs(video_decoded_start - audio_decoded_start) <= aac_unit
    assert abs(video_decoded_end - audio_decoded_end) <= aac_unit

    audio_absolute_points = [
        timestamp * audio_time_base for timestamp, _ in audio_frame_values
    ] + [audio_decoded_end]
    video_checkpoints = (
        video_decoded_start,
        (video_decoded_start + video_decoded_end) / 2,
        video_decoded_end,
    )
    av_checkpoint_separation = [
        min(abs(video_checkpoint - audio_point) for audio_point in audio_absolute_points)
        for video_checkpoint in video_checkpoints
    ]
    assert max(av_checkpoint_separation) <= aac_unit
    assert max(av_checkpoint_separation) - min(av_checkpoint_separation) <= aac_unit


def test_final_concat_materializes_real_segment_audio_gaps_as_pcm_silence(
    tmp_path: Path,
) -> None:
    """MEDIA-SYNC-AC-007: preserved segment PTS gaps must become PCM silence."""

    ffmpeg, ffprobe = _require_media_tools()
    source = tmp_path / "real-like-source.mp4"
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x90:rate=60000/1001:duration=3.226111",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=3.199958",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-video_track_timescale",
            "90000",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-y",
            str(source),
        ],
        "real-like mismatched source generation",
    )

    normalized = tmp_path / "normalized-real-like.mp4"
    join_media.normalize_item(
        join_media.MediaItem(
            path=source,
            taken_at=datetime(2026, 7, 1),
            is_photo=False,
            has_audio=True,
            date_source="fixture",
        ),
        normalized,
        ffmpeg,
        join_media.OverlayConfig(enabled=False),
        crf=35,
        preset="ultrafast",
    )

    normalized_streams = _probe_json(
        ffprobe,
        normalized,
        "-show_entries",
        "stream=codec_type,time_base,start_time,duration",
    )["streams"]
    normalized_video = next(
        stream for stream in normalized_streams if stream["codec_type"] == "video"
    )
    normalized_audio = next(
        stream for stream in normalized_streams if stream["codec_type"] == "audio"
    )
    assert abs(Fraction(normalized_video["duration"]) - Fraction(97, 30)) <= Fraction(
        1, 1_000_000
    )
    assert Fraction(normalized_audio["duration"]) < Fraction(
        normalized_video["duration"]
    )
    normalized_audio_frames = _probe_json(
        ffprobe,
        normalized,
        "-select_streams",
        "a:0",
        "-show_frames",
        "-show_entries",
        "frame=nb_samples",
    )["frames"]
    normalized_decoded_samples = sum(
        int(frame["nb_samples"])
        for frame in normalized_audio_frames
        if "nb_samples" in frame
    )
    normalized_video_samples = round(
        Fraction(normalized_video["duration"]) * 48000
    )
    assert normalized_video_samples - normalized_decoded_samples == 576

    repetitions = 60
    output = tmp_path / "repeated-real-segment.mp4"
    join_media.concatenate(
        [normalized] * repetitions,
        tmp_path / "real-segment-concat.txt",
        output,
        ffmpeg,
    )

    streams = _probe_json(
        ffprobe,
        output,
        "-show_entries",
        "stream=codec_type,time_base,start_time,duration,sample_rate,r_frame_rate,avg_frame_rate",
    )["streams"]
    video_stream = next(stream for stream in streams if stream["codec_type"] == "video")
    audio_stream = next(stream for stream in streams if stream["codec_type"] == "audio")
    assert video_stream["time_base"] == "1/60000"
    assert video_stream["r_frame_rate"] == "60/1"
    assert abs(Fraction(video_stream["avg_frame_rate"]) - 60) <= Fraction(
        1, 100_000
    )
    assert audio_stream["time_base"] == "1/48000"
    assert audio_stream["sample_rate"] == "48000"

    video_frames = _probe_json(
        ffprobe,
        output,
        "-select_streams",
        "v:0",
        "-show_frames",
        "-show_entries",
        "frame=best_effort_timestamp,duration",
    )["frames"]
    video_values = [
        (int(frame["best_effort_timestamp"]), int(frame["duration"]))
        for frame in video_frames
        if "best_effort_timestamp" in frame and "duration" in frame
    ]
    assert video_values
    assert all(
        right_pts == left_pts + left_duration
        for (left_pts, left_duration), (right_pts, _) in zip(
            video_values, video_values[1:]
        )
    )

    audio_frames = _probe_json(
        ffprobe,
        output,
        "-select_streams",
        "a:0",
        "-show_frames",
        "-show_entries",
        "frame=best_effort_timestamp,nb_samples",
    )["frames"]
    audio_values = [
        (int(frame["best_effort_timestamp"]), int(frame["nb_samples"]))
        for frame in audio_frames
        if "best_effort_timestamp" in frame and "nb_samples" in frame
    ]
    assert audio_values
    signed_gaps = [
        right_pts - (left_pts + left_samples)
        for (left_pts, left_samples), (right_pts, _) in zip(
            audio_values, audio_values[1:]
        )
    ]
    positive_gaps = [gap for gap in signed_gaps if gap > 0]
    negative_overlap_samples = -sum(gap for gap in signed_gaps if gap < 0)
    net_gap_samples = sum(positive_gaps)
    net_discontinuity_samples = sum(signed_gaps)
    assert len(positive_gaps) <= 1, (
        f"decoded audio has {len(positive_gaps)} positive PTS gaps totaling "
        f"{net_gap_samples} samples"
    )
    assert net_gap_samples <= 1024
    assert negative_overlap_samples <= 1024
    assert abs(net_discontinuity_samples) <= 1024

    video_time_base = Fraction(video_stream["time_base"])
    audio_time_base = Fraction(audio_stream["time_base"])
    video_start = video_values[0][0] * video_time_base
    video_end = sum(video_values[-1]) * video_time_base
    audio_start = audio_values[0][0] * audio_time_base
    decoded_audio_samples = sum(samples for _, samples in audio_values)
    audio_content_end = audio_start + Fraction(decoded_audio_samples, 48000)
    aac_unit = Fraction(1024, 48000)

    checkpoint_errors: list[Fraction] = []
    for proportion in (Fraction(1, 10), Fraction(1, 2), Fraction(3, 4), Fraction(1)):
        target = video_start + (video_end - video_start) * proportion
        frame_count = max(
            index
            for index, (pts, _) in enumerate(audio_values, start=1)
            if pts * audio_time_base <= target
        )
        decoded_to_checkpoint = sum(
            samples for _, samples in audio_values[:frame_count]
        )
        timestamp_to_checkpoint = (
            audio_values[frame_count - 1][0]
            + audio_values[frame_count - 1][1]
            - audio_values[0][0]
        )
        checkpoint_errors.append(
            Fraction(timestamp_to_checkpoint - decoded_to_checkpoint, 48000)
        )

    assert abs(video_start - audio_start) <= aac_unit
    assert abs(video_end - audio_content_end) <= aac_unit
    assert max(abs(error) for error in checkpoint_errors) <= aac_unit
    assert max(checkpoint_errors) - min(checkpoint_errors) <= aac_unit


@pytest.mark.parametrize(
    "mode_args",
    [pytest.param([], id="implicit-chronicle"), pytest.param(["--mode", "join"], id="join")],
)
def test_synthetic_photo_video_cli_smoke_preserves_sources(
    tmp_path: Path, mode_args: list[str]
) -> None:
    ffmpeg = _resolve_tool("VIDEO_CHRONICLE_FFMPEG", "ffmpeg")
    ffprobe = _resolve_tool("VIDEO_CHRONICLE_FFPROBE", "ffprobe")
    missing = [
        name
        for name, executable in (("FFmpeg", ffmpeg), ("FFprobe", ffprobe))
        if executable is None
    ]
    if missing:
        pytest.skip(
            "synthetic media smoke skipped: "
            + ", ".join(missing)
            + " not found; set VIDEO_CHRONICLE_FFMPEG/VIDEO_CHRONICLE_FFPROBE "
            "or add the tools to PATH"
        )
    assert ffmpeg is not None
    assert ffprobe is not None

    ffmpeg_version, ffmpeg_line = _tool_version(ffmpeg)
    ffprobe_version, ffprobe_line = _tool_version(ffprobe)
    assert ffmpeg_version >= MINIMUM_FFMPEG_VERSION, ffmpeg_line
    assert ffprobe_version >= MINIMUM_FFMPEG_VERSION, ffprobe_line

    input_dir = tmp_path / "медиа ' smoke"
    input_dir.mkdir()
    photo = input_dir / "IMG_20240102_030405.bmp"
    video = input_dir / "VID_20240103_040506.mp4"
    output = tmp_path / "результат smoke.mp4"
    error_log = tmp_path / "ошибки smoke.log"

    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x48",
            "-frames:v",
            "1",
            "-y",
            str(photo),
        ],
        "synthetic photo generation",
    )
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=96x64:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "0.3",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            "-shortest",
            "-y",
            str(video),
        ],
        "synthetic video generation",
    )
    before = {path: _snapshot(path) for path in (photo, video)}

    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    cache_args: list[str] = []
    cache_dir = tmp_path / "normalized-cache"
    if mode_args == ["--mode", "join"]:
        cache_dir.mkdir()
        cache_args = ["--cache", "--cache-dir", str(cache_dir)]
    command = [
            sys.executable,
            str(project_root / "join_media.py"),
            "--input-dir",
            str(input_dir),
            "--output",
            str(output),
            "--error-log",
            str(error_log),
            "--ffmpeg",
            ffmpeg,
            "--ffprobe",
            ffprobe,
            "--crf",
            "35",
            "--preset",
            "ultrafast",
            *mode_args,
            *cache_args,
        ]
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=180,
        env=env,
    )
    assert result.returncode == 0, (
        f"join_media CLI failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}\n"
        f"error log:\n{error_log.read_text(encoding='utf-8') if error_log.exists() else ''}"
    )
    assert output.is_file()
    assert output.stat().st_size > 0
    assert {path: _snapshot(path) for path in (photo, video)} == before

    probe = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-of",
            "json",
            str(output),
        ],
        "result probing",
    )
    streams = json.loads(probe.stdout)["streams"]
    assert any(stream.get("codec_type") == "video" for stream in streams)
    assert any(stream.get("codec_type") == "audio" for stream in streams)

    if cache_args:
        clean_digest = hashlib.sha256(output.read_bytes()).hexdigest()
        entries = list(cache_dir.glob("clip-v1-*"))
        assert len(entries) == 2
        output.unlink()
        resumed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=180,
            env=env,
        )
        assert resumed.returncode == 0, resumed.stderr
        assert hashlib.sha256(output.read_bytes()).hexdigest() == clean_digest
        assert {path: _snapshot(path) for path in (photo, video)} == before

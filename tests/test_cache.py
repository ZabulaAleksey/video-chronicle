from __future__ import annotations

import json
import subprocess
import os
import threading
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from video_chronicle.cache import CacheEntryRejected, NormalizedClipCache, build_clip_identity, cache_key
from video_chronicle.domain import DateCandidate, DateDecision, ExportMode, ExportRequest, MediaItem, SourceFingerprint
from video_chronicle.execution import ExecutionContext, ExportCancelled, bind_execution_context
from video_chronicle.overlay import OverlayConfig


STREAMS = json.dumps(
    {
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1600,
                "height": 900,
                "r_frame_rate": "60/1",
                "pix_fmt": "yuv420p",
                "profile": "High",
                "level": 42,
                "time_base": "1/60000",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
            },
        ]
    }
)


def _runner(command: list[str], context: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
    output = "ffmpeg version test" if command[-1] == "-version" else STREAMS
    return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")


def _case(tmp_path: Path) -> tuple[MediaItem, ExportRequest]:
    source_dir = tmp_path / "Вход"
    source_dir.mkdir(parents=True)
    source = source_dir / "фото 01.jpg"
    source.write_bytes(b"source-content")
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffprobe = tmp_path / "ffprobe.exe"
    ffmpeg.write_bytes(b"ffmpeg-tool")
    ffprobe.write_bytes(b"ffprobe-tool")
    item = MediaItem(
        path=source,
        taken_at=datetime(2026, 1, 2, 3, 4, 5),
        is_photo=True,
        has_audio=False,
        date_source="filename",
        source_fingerprint=SourceFingerprint.capture(source),
    )
    request = ExportRequest(
        input_dir=source_dir,
        output=tmp_path / "out.mp4",
        error_log=tmp_path / "errors.log",
        ffmpeg=str(ffmpeg),
        ffprobe=str(ffprobe),
        crf=20,
        preset="medium",
        overwrite=False,
        keep_work=False,
        overlay=OverlayConfig(enabled=False),
        mode=ExportMode.JOIN,
    )
    return item, request


def test_clip_key_is_canonical_unicode_and_excludes_output_policy(tmp_path: Path) -> None:
    item, request = _case(tmp_path)
    first = cache_key(build_clip_identity(item, request, _runner))
    changed = replace(
        request,
        output=tmp_path / "different.mp4",
        error_log=tmp_path / "different.log",
        overwrite=True,
        keep_work=True,
    )
    second = cache_key(build_clip_identity(item, changed, _runner))
    assert first == second
    assert first.startswith("clip-v1-")


@pytest.mark.parametrize("field,value", [("crf", 21), ("preset", "slow")])
def test_clip_key_changes_with_normalization_settings(
    tmp_path: Path, field: str, value: object
) -> None:
    item, request = _case(tmp_path)
    original = cache_key(build_clip_identity(item, request, _runner))
    changed = cache_key(build_clip_identity(item, replace(request, **{field: value}), _runner))
    assert changed != original


def test_clip_key_invalidates_all_canonical_identity_dimensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import video_chronicle.cache as cache_module

    item, request = _case(tmp_path)
    original = cache_key(build_clip_identity(item, request, _runner))

    assert cache_key(build_clip_identity(replace(item, taken_at=datetime(2026, 1, 2, 3, 4, 6)), request, _runner)) != original
    assert cache_key(build_clip_identity(replace(item, is_photo=False, has_audio=True), request, _runner)) != original
    assert cache_key(build_clip_identity(item, replace(request, mode=ExportMode.CHRONICLE), _runner)) != original
    assert cache_key(build_clip_identity(item, replace(request, overlay=OverlayConfig(enabled=False, font_size=73)), _runner)) != original

    item.path.write_bytes(b"changed-content")
    content_item = replace(item, source_fingerprint=SourceFingerprint.capture(item.path))
    assert cache_key(build_clip_identity(content_item, request, _runner)) != original

    item, request = _case(tmp_path / "stat-case")
    stat_original = cache_key(build_clip_identity(item, request, _runner))
    os.utime(item.path, ns=(item.path.stat().st_atime_ns, item.path.stat().st_mtime_ns + 1_000_000))
    stat_item = replace(item, source_fingerprint=SourceFingerprint.capture(item.path))
    assert cache_key(build_clip_identity(stat_item, request, _runner)) != stat_original

    monkeypatch.setattr(cache_module, "NORMALIZATION_PROFILE", "normalize-v2-test")
    assert cache_key(build_clip_identity(stat_item, request, _runner)) != cache_key(
        {**build_clip_identity(stat_item, request, _runner), "normalization": "normalize-v1"}
    )


def test_clip_key_invalidates_font_and_tool_identity(tmp_path: Path) -> None:
    item, request = _case(tmp_path)
    font = tmp_path / "font.ttf"
    font.write_bytes(b"font-one")
    chronicle = replace(
        request,
        mode=ExportMode.CHRONICLE,
        overlay=OverlayConfig(enabled=True, font_file=font),
    )
    original = cache_key(build_clip_identity(item, chronicle, _runner))
    identity_only_overlay = OverlayConfig(enabled=True, font_file=font)
    assert identity_only_overlay.font_identity is not None
    object.__setattr__(
        identity_only_overlay,
        "font_identity",
        (*identity_only_overlay.font_identity[:-1], identity_only_overlay.font_identity[-1] + 1),
    )
    assert cache_key(
        build_clip_identity(
            item, replace(chronicle, overlay=identity_only_overlay), _runner
        )
    ) != original
    font.write_bytes(b"font-two")
    changed_font = replace(chronicle, overlay=OverlayConfig(enabled=True, font_file=font))
    assert cache_key(build_clip_identity(item, changed_font, _runner)) != original

    def changed_version(command: list[str], context: str, **kwargs: object):
        output = "different tool version" if command[-1] == "-version" else STREAMS
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    assert cache_key(build_clip_identity(item, changed_font, changed_version)) != cache_key(
        build_clip_identity(item, changed_font, _runner)
    )
    tool_original = cache_key(build_clip_identity(item, request, _runner))
    Path(request.ffmpeg).write_bytes(b"ffmpeg-tool-with-new-size")
    assert cache_key(build_clip_identity(item, request, _runner)) != tool_original


def test_store_and_restore_verified_copy_with_path_free_manifest(tmp_path: Path) -> None:
    item, request = _case(tmp_path)
    cache = NormalizedClipCache(tmp_path / "private-cache")
    normalized = tmp_path / "normalized.mp4"
    normalized.write_bytes(b"normalized-clip")

    assert cache.store(item, request, normalized, _runner)
    restored = tmp_path / "workspace" / "clip.mp4"
    assert cache.restore(item, request, restored, _runner)
    assert restored.read_bytes() == b"normalized-clip"

    manifests = list(cache.root.glob("clip-v1-*/manifest.json"))
    assert len(manifests) == 1
    text = manifests[0].read_text(encoding="utf-8")
    assert str(item.path) not in text
    assert str(request.ffmpeg) not in text
    assert "argv" not in text


def test_corrupt_artifact_is_a_miss_and_never_materialized(tmp_path: Path) -> None:
    item, request = _case(tmp_path)
    cache = NormalizedClipCache(tmp_path / "private-cache")
    normalized = tmp_path / "normalized.mp4"
    normalized.write_bytes(b"normalized-clip")
    assert cache.store(item, request, normalized, _runner)
    artifact = next(cache.root.glob("clip-v1-*/clip.mp4"))
    artifact.chmod(0o600)
    artifact.write_bytes(b"tampered")

    restored = tmp_path / "workspace" / "clip.mp4"
    with pytest.raises(CacheEntryRejected, match="size mismatch"):
        cache.restore(item, request, restored, _runner)
    assert not restored.exists()


def test_manifest_with_extra_field_is_rejected(tmp_path: Path) -> None:
    item, request = _case(tmp_path)
    cache = NormalizedClipCache(tmp_path / "private-cache")
    normalized = tmp_path / "normalized.mp4"
    normalized.write_bytes(b"normalized-clip")
    assert cache.store(item, request, normalized, _runner)
    manifest_path = next(cache.root.glob("clip-v1-*/manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["unexpected"] = True
    manifest_path.chmod(0o600)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CacheEntryRejected, match="manifest fields"):
        cache.restore(item, request, tmp_path / "restored.mp4", _runner)


def test_explicit_purge_keeps_root_marker(tmp_path: Path) -> None:
    item, request = _case(tmp_path)
    cache = NormalizedClipCache(tmp_path / "private-cache")
    normalized = tmp_path / "normalized.mp4"
    normalized.write_bytes(b"normalized-clip")
    assert cache.store(item, request, normalized, _runner)

    assert cache.purge() == 1
    assert cache.root.is_dir()
    assert (cache.root / ".video-chronicle-cache").is_file()
    assert not list(cache.root.glob("clip-v1-*"))


def test_purge_rejects_unmarked_directory(tmp_path: Path) -> None:
    root = tmp_path / "not-a-cache"
    root.mkdir()
    (root / "important.txt").write_text("keep", encoding="utf-8")
    cache = NormalizedClipCache(root)
    with pytest.raises(RuntimeError, match="marker"):
        cache.purge()
    assert (root / "important.txt").read_text(encoding="utf-8") == "keep"


def test_purge_is_unavailable_during_active_operation(tmp_path: Path) -> None:
    cache = NormalizedClipCache(tmp_path / "private-cache")
    with cache.operation():
        with pytest.raises(RuntimeError, match="active operation"):
            cache.purge()


def test_purge_rejects_home_input_and_output_parent(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="unsafe cache purge root"):
        NormalizedClipCache(Path.home()).purge()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    with pytest.raises(RuntimeError, match="protected"):
        NormalizedClipCache(input_dir / "cache").purge(protected_input=input_dir)
    output = tmp_path / "result.mp4"
    with pytest.raises(RuntimeError, match="output"):
        NormalizedClipCache(tmp_path).purge(protected_output=output)


def test_unc_and_device_paths_are_rejected_before_filesystem_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_exists = Path.exists

    def forbidden_exists(path: Path) -> bool:
        if str(path).replace("/", "\\").startswith("\\\\"):
            raise AssertionError("UNC filesystem access occurred")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", forbidden_exists)
    with pytest.raises(RuntimeError, match="UNC or device"):
        NormalizedClipCache(Path("//server/share/cache"))
    with pytest.raises(RuntimeError, match="UNC or device"):
        NormalizedClipCache(Path(r"\\.\C:\cache"))


def test_cli_explicit_purge_removes_only_verified_entries(tmp_path: Path) -> None:
    from video_chronicle import cli

    item, request = _case(tmp_path)
    cache_dir = tmp_path / "cache"
    cache = NormalizedClipCache(cache_dir)
    artifact = tmp_path / "normalized.mp4"
    artifact.write_bytes(b"normalized")
    assert cache.store(item, request, artifact, _runner)
    assert cli.main(
        [
            "--purge-cache",
            "--cache-dir",
            str(cache_dir),
            "--input-dir",
            str(request.input_dir),
            "--output",
            str(request.output),
        ]
    ) == 0
    assert not list(cache_dir.glob("clip-v1-*"))
    assert (cache_dir / ".video-chronicle-cache").exists()


def test_existing_empty_custom_root_is_initialized_but_nonempty_unmarked_is_rejected(
    tmp_path: Path,
) -> None:
    item, request = _case(tmp_path)
    empty = tmp_path / "empty-cache"
    empty.mkdir()
    artifact = tmp_path / "normalized.mp4"
    artifact.write_bytes(b"normalized")
    cache = NormalizedClipCache(empty)
    assert cache.store(item, request, artifact, _runner)
    assert (empty / ".video-chronicle-cache").is_file()

    unmarked = tmp_path / "unmarked"
    unmarked.mkdir()
    (unmarked / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(RuntimeError, match="marker"):
        NormalizedClipCache(unmarked).store(item, request, artifact, _runner)
    assert (unmarked / "keep.txt").exists()


def test_hash_and_copy_checkpoint_cancellation_cleans_partial_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import video_chronicle.cache as cache_module

    source = tmp_path / "large.bin"
    source.write_bytes(b"a" * (3 * 1024 * 1024))
    destination = tmp_path / "partial.bin"
    context = ExecutionContext()
    context.start()
    calls = 0
    original = cache_module._execution_checkpoint

    def cancel_on_second_chunk() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            assert context.request_cancel()
        original()

    monkeypatch.setattr(cache_module, "_execution_checkpoint", cancel_on_second_chunk)
    with bind_execution_context(context), pytest.raises(ExportCancelled):
        cache_module._copy_with_checkpoints(source, destination)
    assert calls == 2
    assert not destination.exists()


def test_source_hash_honors_execution_cancellation_between_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import video_chronicle.cache as cache_module

    source = tmp_path / "large-source.bin"
    source.write_bytes(b"s" * (3 * 1024 * 1024))
    context = ExecutionContext()
    context.start()
    calls = 0
    original = cache_module._execution_checkpoint

    def cancel_on_second_chunk() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            assert context.request_cancel()
        original()

    monkeypatch.setattr(cache_module, "_execution_checkpoint", cancel_on_second_chunk)
    with bind_execution_context(context), pytest.raises(ExportCancelled):
        cache_module._sha256_stable(source)
    assert calls == 2


def test_bounded_manifest_and_artifact_are_rejected_before_unbounded_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import video_chronicle.cache as cache_module

    item, request = _case(tmp_path)
    cache = NormalizedClipCache(tmp_path / "cache")
    artifact = tmp_path / "normalized.mp4"
    artifact.write_bytes(b"normalized")
    assert cache.store(item, request, artifact, _runner)
    manifest = next(cache.root.glob("clip-v1-*/manifest.json"))
    monkeypatch.setattr(cache_module, "MAX_MANIFEST_BYTES", 8)
    with pytest.raises(CacheEntryRejected, match="exceeds"):
        cache.restore(item, request, tmp_path / "restored.mp4", _runner)
    monkeypatch.setattr(cache_module, "MAX_MANIFEST_BYTES", 1024 * 1024)
    manifest.chmod(0o600)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["artifact_size"] = 4
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(cache_module, "MAX_CACHE_BYTES", 4)
    with pytest.raises(CacheEntryRejected, match="size cap"):
        cache.restore(item, request, tmp_path / "restored.mp4", _runner)


def test_retention_uses_verified_actual_bytes_and_30_day_age(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import video_chronicle.cache as cache_module

    item, request = _case(tmp_path)
    cache = NormalizedClipCache(tmp_path / "cache")
    artifact = tmp_path / "normalized.mp4"
    artifact.write_bytes(b"normalized")
    assert cache.store(item, request, artifact, _runner)
    entry = next(cache.root.glob("clip-v1-*"))
    old = datetime.now().timestamp() - 31 * 86400
    os.utime(entry, (old, old))
    assert cache.prune() == 1
    assert not entry.exists()


def test_no_replace_does_not_overwrite_existing_empty_final(tmp_path: Path) -> None:
    item, request = _case(tmp_path)
    cache = NormalizedClipCache(tmp_path / "cache")
    artifact = tmp_path / "normalized.mp4"
    artifact.write_bytes(b"normalized")
    assert cache.store(item, request, artifact, _runner)
    entry = next(cache.root.glob("clip-v1-*"))
    for child in entry.iterdir():
        child.chmod(0o600)
        child.unlink()
    with pytest.raises(CacheEntryRejected, match="existing"):
        cache.store(item, request, artifact, _runner)
    assert entry.is_dir() and not any(entry.iterdir())


def test_concurrent_store_never_replaces_published_entry(tmp_path: Path) -> None:
    item, request = _case(tmp_path)
    cache = NormalizedClipCache(tmp_path / "cache")
    artifact = tmp_path / "normalized.mp4"
    artifact.write_bytes(b"normalized")
    assert cache.store(item, request, artifact, _runner)
    assert cache.purge() == 1
    results: list[bool] = []

    def store() -> None:
        results.append(cache.store(item, request, artifact, _runner))

    threads = [threading.Thread(target=store) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert results == [True, True]
    assert len(list(cache.root.glob("clip-v1-*"))) == 1
    restored = tmp_path / "restored.mp4"
    assert cache.restore(item, request, restored, _runner)


def test_corrupt_actual_bytes_count_toward_cache_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import video_chronicle.cache as cache_module

    item, request = _case(tmp_path)
    cache = NormalizedClipCache(tmp_path / "cache")
    first = tmp_path / "first.mp4"
    first.write_bytes(b"1234567890")
    assert cache.store(item, request, first, _runner)
    cached = next(cache.root.glob("clip-v1-*/clip.mp4"))
    cached.chmod(0o600)
    cached.write_bytes(b"x" * 15)

    second_source = request.input_dir / "second.mp4"
    second_source.write_bytes(b"source-two")
    second_item = replace(
        item, path=second_source, source_fingerprint=SourceFingerprint.capture(second_source)
    )
    second = tmp_path / "second-normalized.mp4"
    second.write_bytes(b"abcdefghij")
    monkeypatch.setattr(cache_module, "MAX_CACHE_BYTES", 20)
    assert cache.store(second_item, request, second, _runner) is False
    assert len(list(cache.root.glob("clip-v1-*"))) == 1


def test_crash_tmp_and_trash_bytes_are_counted_and_reaped_before_store(
    tmp_path: Path,
) -> None:
    item, request = _case(tmp_path)
    cache = NormalizedClipCache(tmp_path / "cache")
    artifact = tmp_path / "normalized.mp4"
    artifact.write_bytes(b"normalized")
    assert cache.store(item, request, artifact, _runner)
    entry = next(cache.root.glob("clip-v1-*"))
    trash_entry = cache.root / "trash" / f"{entry.name}-crash"
    entry.rename(trash_entry)
    tmp_entry = cache.root / "tmp-crash"
    tmp_entry.mkdir()
    (tmp_entry / "clip.mp4").write_bytes(b"partial-bytes")
    old = datetime.now().timestamp() - 10 * 60
    os.utime(tmp_entry, (old, old))
    assert cache._actual_cache_bytes() >= len(b"normalized") + len(b"partial-bytes")

    assert cache.store(item, request, artifact, _runner)
    assert not trash_entry.exists()
    assert not tmp_entry.exists()
    assert len(list(cache.root.glob("clip-v1-*"))) == 1


def test_failed_staging_reap_prevents_new_cache_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import video_chronicle.cache as cache_module

    item, request = _case(tmp_path)
    cache = NormalizedClipCache(tmp_path / "cache")
    artifact = tmp_path / "normalized.mp4"
    artifact.write_bytes(b"normalized")
    assert cache.store(item, request, artifact, _runner)
    entry = next(cache.root.glob("clip-v1-*"))
    trash_entry = cache.root / "trash" / f"{entry.name}-crash"
    entry.rename(trash_entry)
    before = cache._actual_cache_bytes()

    original_remove = cache_module._remove_verified_tree

    def fail_trash(path: Path, *, allow_tmp: bool = False) -> None:
        if path == trash_entry:
            raise OSError("trash deletion failed")
        original_remove(path, allow_tmp=allow_tmp)

    monkeypatch.setattr(cache_module, "_remove_verified_tree", fail_trash)
    with pytest.raises(OSError, match="trash deletion failed"):
        cache.store(item, request, artifact, _runner)
    assert cache._actual_cache_bytes() == before
    assert not list(cache.root.glob("clip-v1-*"))


def test_second_instance_never_reaps_old_but_live_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import video_chronicle.cache as cache_module

    item, request = _case(tmp_path)
    root = tmp_path / "cache"
    first = NormalizedClipCache(root)
    artifact = tmp_path / "normalized.mp4"
    artifact.write_bytes(b"normalized")
    assert first.store(item, request, artifact, _runner)
    assert first.purge() == 1
    second = NormalizedClipCache(root)
    ready = threading.Event()
    release = threading.Event()
    live_tmp = root / "tmp-live-owner"

    def live_writer() -> None:
        with first._mutation_lock():
            live_tmp.mkdir()
            (live_tmp / "clip.mp4").write_bytes(b"live-partial")
            old = datetime.now().timestamp() - 3600
            os.utime(live_tmp, (old, old))
            ready.set()
            release.wait(timeout=2)

    thread = threading.Thread(target=live_writer)
    thread.start()
    assert ready.wait(timeout=2)
    monkeypatch.setattr(cache_module, "MUTATION_LOCK_TIMEOUT", 0.1)
    with pytest.raises(RuntimeError, match="mutation lock is busy"):
        second.store(item, request, artifact, _runner)
    assert live_tmp.is_dir()
    assert (live_tmp / "clip.mp4").read_bytes() == b"live-partial"
    release.set()
    thread.join(timeout=2)
    assert second.store(item, request, artifact, _runner)
    assert not live_tmp.exists()


def test_two_instances_serialize_cap_check_and_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import video_chronicle.cache as cache_module

    item, request = _case(tmp_path)
    root = tmp_path / "cache"
    first_cache = NormalizedClipCache(root)
    first_artifact = tmp_path / "first.mp4"
    first_artifact.write_bytes(b"normalized-a")
    assert first_cache.store(item, request, first_artifact, _runner)
    one_entry_bytes = first_cache._actual_cache_bytes()
    assert first_cache.purge() == 1

    second_source = request.input_dir / "second.mp4"
    second_source.write_bytes(b"source-two")
    second_item = replace(
        item, path=second_source, source_fingerprint=SourceFingerprint.capture(second_source)
    )
    second_artifact = tmp_path / "second.mp4"
    second_artifact.write_bytes(b"normalized-b")
    monkeypatch.setattr(cache_module, "MAX_CACHE_BYTES", one_entry_bytes + 4)
    second_cache = NormalizedClipCache(root)
    results: list[bool] = []

    threads = [
        threading.Thread(
            target=lambda: results.append(
                first_cache.store(item, request, first_artifact, _runner)
            )
        ),
        threading.Thread(
            target=lambda: results.append(
                second_cache.store(second_item, request, second_artifact, _runner)
            )
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert sorted(results) == [False, True]
    assert len(list(root.glob("clip-v1-*"))) == 1
    assert first_cache._actual_cache_bytes() <= cache_module.MAX_CACHE_BYTES


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL contract")
def test_windows_custom_root_has_verified_owner_only_dacl(tmp_path: Path) -> None:
    import video_chronicle.cache as cache_module

    item, request = _case(tmp_path)
    root = tmp_path / "custom-cache"
    root.mkdir()
    artifact = tmp_path / "normalized.mp4"
    artifact.write_bytes(b"normalized")
    cache = NormalizedClipCache(root)
    assert cache.store(item, request, artifact, _runner)
    cache_module._verify_windows_owner_acl(root)


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL contract")
@pytest.mark.parametrize(
    ("control", "access_mask", "message"),
    [
        (0, 0x001F01FF, "not protected"),
        (0x1000, 0x00120089, "full access"),
    ],
)
def test_windows_acl_contract_rejects_unprotected_or_underprivileged_owner_ace(
    control: int, access_mask: int, message: str
) -> None:
    import video_chronicle.cache as cache_module

    with pytest.raises(RuntimeError, match=message):
        cache_module._validate_windows_acl_contract(
            control=control,
            dacl_present=True,
            ace_count=1,
            owner_matches=True,
            ace_type=0,
            ace_flags=0x03,
            access_mask=access_mask,
            ace_sid_matches=True,
        )


def test_key_includes_full_date_provenance(tmp_path: Path) -> None:
    item, request = _case(tmp_path)
    first = DateCandidate(
        datetime(2026, 1, 2, 3, 4, 5), "raw", "metadata", "creation_time",
        "creation_time", "format.tags", "+02:00", 1,
    )
    second = replace(first, location="streams[0].tags")
    one = replace(item, date_decision=DateDecision(first, (first,), (), "date-v1"))
    two = replace(item, date_decision=DateDecision(second, (second,), (), "date-v1"))
    assert cache_key(build_clip_identity(one, request, _runner)) != cache_key(
        build_clip_identity(two, request, _runner)
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("format", {"format_name": "matroska"}),
        ("pix_fmt", "yuv444p"),
        ("profile", "Main"),
        ("level", 41),
        ("time_base", "1/1000"),
    ],
)
def test_stream_contract_rejects_incompatible_profile(
    tmp_path: Path, field: str, value: object
) -> None:
    import video_chronicle.cache as cache_module

    payload = json.loads(STREAMS)
    if field == "format":
        payload["format"] = value
    else:
        payload["streams"][0][field] = value

    def runner(command, context, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    artifact = tmp_path / "clip.mp4"
    artifact.write_bytes(b"clip")
    with pytest.raises(ValueError, match="incompatible"):
        cache_module._validate_normalized_stream(artifact, "ffprobe", runner)

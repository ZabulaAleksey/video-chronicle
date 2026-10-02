# Контекст проекта

Video Chronicle — Python-проект для обработки и сборки медиахронологии с GUI, CLI и FFmpeg-интеграцией. `src/video_chronicle/pipeline.py` и application services владеют медиаконвейером; `join_media.py` является compatibility wrapper; проектные документы и stage-контекст находятся в `docs/`, прежде всего `docs/STAGES.md`.

Исторические project-local `ffmpeg/` и `ffmpeg1/` сохраняются как отдельные assets, если они существуют. Активный DEV-managed runtime использует `${DEV_ROOT}/tools/ffmpeg` согласно решению от 2026-09-28; governance-миграция не изменяла содержимое старых каталогов.

## Structured DEV bridge

- Global owner: `${DEV_ROOT}/context/global/codex-dev` владеет общим router,
  разрешением путей, bootstrap, doctor и versioned capability contracts.
- Project owner: `${PROJECTS_ROOT}/video-chronicle` владеет product code,
  `AGENTS.md`, SPEC, выбранным `docs/STAGES.md`, media behavior, `pyproject.toml`
  и `uv.lock`.
- Граница наследования: `.codex/dev-project.toml` является structured opt-in;
  точная строка в AGENTS — human-readable declaration. Проектные правила
  уточняют global contract без ослабления безопасности и утверждённых решений.
- Portable roots: `${DEV_ROOT}`, `${PROJECTS_ROOT}`, `${PROJECT_ROOT}`;
  Windows bootstrap-пример допускает `E:\DEV`. `~` означает machine-local runtime.
- Владелец tools: Global DEV владеет `${DEV_ROOT}/tools/ffmpeg`, версией,
  provenance и SHA-256 FFmpeg/FFprobe; проект владеет Python environment и lockfile.
- Исключения: исторические `ffmpeg/` и `ffmpeg1/` сохраняются как assets, но не
  являются active portable prerequisites. WinGet fallback standalone GUI не
  удовлетворяет DEV doctor. Product redistribution и LICENSE — gates Stage 16.

## Backend DX Delta

- Applicability level: `BDX-L2` — local GUI/CLI, durable JSON, Qt workers и real FFmpeg.
- Supported local environments: Windows, тестовый offscreen Qt; Linux support требует отдельного текущего CI evidence.
- Canonical working directory: `${PROJECT_ROOT}`.
- Toolchain/runtime versions: Python >=3.11; actual tested 3.12.5, PySide6 6.11.1, FFmpeg/FFprobe9.0.1.
- Package manager and lockfile: `uv`, `pyproject.toml` + `uv.lock`.
- Canonical commands:
  - bootstrap: `uv sync --locked --extra dev --extra otio`.
  - doctor: `uv lock --check --offline` и `uv pip check`; external portable tool ownership — Global DEV doctor.
  - dev: `uv run --locked video-chronicle-gui`.
  - stop: закрыть GUI после подтверждённого worker/process cleanup; отдельного фонового сервиса нет.
  - check: `uv run --locked --offline --extra dev --extra otio python -m pytest -q -rs`.
  - test-fast: `uv run --locked --offline --extra dev --extra otio python -m pytest -q tests/test_project_queue_model.py tests/test_review_regressions.py`.
  - test-integration: `uv run --locked --offline --extra dev --extra otio python -m pytest -q -rs tests/test_ffmpeg_smoke.py tests/test_wheel_cli_export.py`.
  - build: `uv run --locked --offline --extra dev python scripts/build_wheel.py --offline --out-dir <fresh-directory>`; installed setuptools/wheel versions must match lock, no global pip/backend.
  - clean-build: `uv run --locked --offline --extra dev --extra otio python -m pytest tests/test_clean_wheel_build.py -q`; actual FFmpeg required, private writable basetemp supported.
  - logs: explicit `--error-log`, paths checked before opening; GUI bounded displayed journal.
- Required local services: N/A — приложение не требует network services.
- Readiness/status command: N/A — нет локального сервиса; CLI `--help` и tool discovery проверяют prerequisites.
- Ports and collision policy: N/A — нет listening socket.
- Config source, profiles and required variables: optional VIDEO_CHRONICLE_FFMPEG/FFPROBE → DEV_ROOT/tools → PATH; QT_QPA_PLATFORM=offscreen только test profile.
- Secret redaction/effective-config diagnostics: product credentials не нужны; media/environment dumps запрещены.
- API docs/spec and generated-contract drift command: N/A — нет network API/generated client; CLI help/exit contract тестируется.
- DB migration/status/seed/reset-local commands: N/A — нет database. JSON repository save/get/restore_backup revision guarded и отдельно tested.
- Destructive command guard: generic reset отсутствует; cache purge marker/identity scoped; unknown user state сохраняется.
- Worker/scheduler commands: Qt workers выполняют analysis/export через managed media processes; independent scheduler отсутствует.
- External sandbox/stub/fallback modes: real trusted FFmpeg default; optional OTIO/whisper/GPU explicit flags/evidence/fallback. Authenticated remote provider отсутствует.
- Clean-room smoke command or documented manual scenario: wheel build → fresh private venv → offline wheel install → CLI help/export authored media → ffprobe output → source hashes unchanged. PASS на текущем Windows host без global pip/setuptools/wheel, из hash-locked runtime export; actual installed offscreen GUI и CLI/FFmpeg paths проверены. Clean VM/cross-OS distribution этим не доказаны.
- Project-specific quality gates: dependency consistency, unchanged accepted tests, managed setup46 и clean build9 focused PASS, managed legacy14 focused PASS, full actual FFmpeg458 PASS/0 skips, independent bounded security review; Stage15 terminal verdict остаётся open.
- Known limitations: Production WinGet setup managed, raw setup constructor остаётся compatibility seam; explicit legacy CLI managed; PATH executable provenance и interactive setup cancellation не доказаны. Linux/clean-VM/Android semantic acceptance не refreshed; terminal Stage15 review remains automatic engineering tail.
- Explicit deviations from global Backend DX Policy: canonical build больше не требует global Python packages; production setup managed. Legacy global-pip accepted tests и raw constructor seam сохранены как compatibility evidence; whole terminal security scope ещё open в selected STAGES.

| BDX ID | Evidence | Status / limitation |
|---|---|---|
| BDX-BOOT-001 / BDX-TOOL-001 | locked graph + no-pip clean consumer | PASS current Windows host; no clean VM/release claim |
| BDX-TEST-001 / BDX-CI-001 | 458 tests, actual FFmpeg, private basetemp | PASS this Windows host; cross-OS CI not refreshed |
| BDX-SVC-001 / BDX-JOB-001 | managed media + production setup lifecycle tests | PASS inspected boundaries; legacy CLI lifecycle verified in bounded Windows scope; POSIX reaper limitations explicit |
| BDX-DB-001 | no DB | N/A; JSON repository separately tested |
| BDX-API-001 | no network API | N/A; CLI help/exit contract tested |
| BDX-DOC-001 | current command map and STAGES tails | PASS documented; no all-gates completion assertion |

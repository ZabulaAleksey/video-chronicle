# Контекст проекта

Video Chronicle — Python-проект для обработки и сборки медиахронологии с GUI, CLI и FFmpeg-интеграцией. `join_media.py` является текущей эталонной реализацией; проектные документы и stage-контекст находятся в `docs/`, прежде всего `docs/STAGES.md`.

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

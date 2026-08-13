# Текущий план для AI

## Срез

- Этап: **02 — Package foundation**
- Статус: выполняется по прямой команде пользователя
- Prompt: `prompts/stages/02-package-foundation.md`
- Зависимости: этап 01 завершён; baseline и FFmpeg smoke зелёные
- Требования: `SYS-FR-001`, `SYS-FR-002`, `SYS-COMP-001`, `FR-011`
- Критерии: `SYS-AC-001`, `SYS-AC-002`, `AC-008`, `GUI-AC-001–003`

## Цель

Создать устанавливаемую структуру Python-пакета, единые console/GUI entry
points, dependency groups и logging/config boundary, сохранив legacy scripts и
весь characterization baseline.

## Scope

- `pyproject.toml` и `src/` package layout;
- runtime/dev dependency groups;
- package console и GUI entry points;
- тонкие compatibility shims `join_media.py`, `gui_contract.py` и
  `video_chronicle_gui.py`;
- install/import/entry point tests в изолированном окружении.

## Non-goals

- извлечение медиалогики из legacy-модуля;
- изменение CLI, дат, FFmpeg argv или UI;
- EXE packaging, БД, очередь, cancel и cache;
- изменение `ffmpeg/` или `ffmpeg1/`.

## Quality gates и DoD

- editable/wheel install и import проходят в чистом venv;
- `video-chronicle` и `video-chronicle-gui` entry points запускаются;
- legacy scripts сохраняют parity и весь этап 01 зелёный;
- dependency check, compileall, `git diff --check` проходят;
- архитектура/решение package layout обновлены;
- после commit `AI_STATUS` и `AI_PLAN` переключены на этап 03.

## Откат

Legacy scripts остаются compatibility boundary. Package additions удаляются
одним stage commit без изменения пользовательских медиа или результатов.

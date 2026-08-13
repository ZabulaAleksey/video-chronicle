# Этап 02 — Package foundation

## Цель

Создать устанавливаемую структуру Python-пакета, единые entry points,
конфигурацию и логирование, сохранив поведение legacy CLI и GUI-001.

## Зависимости и контекст

- Этап 01 полностью завершён, baseline и FFmpeg smoke зелёные.
- Прочитать system SPEC, `FR-011`/`AC-008`, architecture, decisions, testing,
  текущие entry points и `AI_STATUS`.
- Перед реализацией заменить `docs/AI_PLAN.md` ограниченным планом этапа 02.

## Scope / non-goals

- `pyproject.toml`, package layout, dependency groups, logging/config boundary,
  console и GUI entry points, перенос тестов без потери покрытия.
- Оставить совместимый запуск `python join_media.py` либо документировать тонкий
  compatibility shim.
- Не извлекать медиалогику, не менять даты/FFmpeg argv/UI и не пакетировать EXE.

## Области файлов и контракты

- Разрешены: package/entry modules, manifests, tests, README, architecture,
  decisions, status/plan.
- Запрещены: `ffmpeg/`, `ffmpeg1/`, новая БД и поведенческие изменения.
- Контракт: прежние аргументы, defaults, exit codes и overwrite semantics.

## Tests и quality gates

- Все tests этапа 01; import/install test в чистом venv; оба entry points;
  dependency check, compileall, `git diff --check`.
- CLI parity подтверждается тем же characterization-набором, не копией тестов.

## DoD / acceptance artifacts / rollback

- Package устанавливается из локального checkout, CLI и GUI запускаются.
- Архитектура и решение package layout зафиксированы; `AI_PLAN` переведён на 03.
- Откат: compatibility shims позволяют вернуть старый layout одним commit;
  при изменении CLI остановиться и согласовать миграцию до продолжения.

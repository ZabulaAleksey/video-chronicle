# Этап 01 — Discovery и baseline

## Назначение и запуск

Завершить characterization baseline эталонного `join_media.py`. Запускать по
команде `Начинай этап 01` через `$implement-stage`. Текущий исполняемый срез
уже находится в `docs/AI_PLAN.md`.

## Зависимости и контекст

- Этап 00 и GUI-001 завершены.
- Прочитать: `specs/system.spec.md`, `FR-011`/`AC-008` feature SPEC,
  `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `docs/SECURITY.md`,
  `join_media.py`, `tests/`, `docs/AI_STATUS.md`.
- Не загружать другие stage prompts.

## Scope / non-goals

- Зафиксировать даты, сортировку, фильтры, argv, ошибки, partial success,
  временную область и финализацию.
- Добавить короткий синтетический FFmpeg/FFprobe smoke-test и проверенную
  минимальную версию.
- Не менять публичный CLI, медиаполитику, GUI, package layout, очередь или кэш.
- Не изменять `ffmpeg/` и `ffmpeg1/`.

## Контракты и области файлов

- Инварианты: read-only inputs, list argv, explicit overwrite, atomic publish.
- Разрешены: `tests/`, узкая тестируемость в `join_media.py`, testing/SPEC/status.
- Изменение наблюдаемого поведения требует сначала решения в SPEC.

## Проверки и quality gates

- `pytest`, synthetic media smoke, `compileall`, CLI `--help`, `git diff --check`.
- Трассировка: `SYS-AC-001/003/005`, `AC-008/010` → tests → implementation.
- Недоступный FFmpeg допускает только явный skip с причиной; этап не считается
  полностью завершённым без воспроизводимого smoke на доступном runtime.

## DoD, артефакты и откат

- Матрица baseline и версия инструментов записаны в `docs/TESTING.md`.
- Characterization и smoke tests проходят; product behavior не расширено.
- `AI_STATUS` обновлён, `AI_PLAN` переключён на этап 02.
- При неоднозначной политике остановиться до изменения кода; additions тестов
  откатываются независимо, корректные тесты не ослабляются.

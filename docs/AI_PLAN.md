# Текущий план для AI

## Срез

- Этап: **04 — Metadata/date engine**
- Статус: выполняется по прямой команде пользователя
- Prompt: `prompts/stages/04-metadata-date-engine.md`
- Зависимости: этапы 01–03 завершены; единый package application path и baseline зелёные
- Требования: `FR-002–FR-004`, `NFR-001`
- Критерии: `AC-002`, `AC-008`, системные инварианты сохранности данных

## Утверждённая для текущего среза политика

В рамках команды пользователя последовательно выполнить этапы 01–05
формализуется существующая, обратно совместимая политика:

1. metadata keys из `DATE_TAGS` в зафиксированном порядке;
2. дата из имени файла, если валидной metadata-даты нет;
3. отсутствие даты приводит к наблюдаемому пропуску элемента;
4. все валидные кандидаты и конфликты сохраняются в provenance;
5. timezone не преобразуется: сохраняются исходный offset и wall-clock поля;
6. одинаковые даты разрешаются стабильным `path.name.casefold()`.

ExifTool и новые источники метаданных в этот срез не входят.

## Цель

Выделить детерминированный Qt-free date engine с типизированным результатом:
выбранное значение, origin, raw value, timezone и conflict diagnostics — без
изменения legacy overlay и порядка существующих корректных наборов.

## Последовательность

1. До production-кода закрепить policy в feature SPEC и `DECISIONS.md`.
2. Добавить чистые модели кандидата/решения и парсеры metadata/filename.
3. Подключить текущий FFprobe adapter через единый engine.
4. Добавить table tests ключей, invalid/timezone/conflict/equal/Unicode случаев.
5. Подтвердить CLI parity и реальный FFmpeg smoke.

## Non-goals

- ExifTool, EXIF dependency или licensing decision;
- пользовательское редактирование timeline;
- SQLite, очередь, cache, ML или OTIO;
- неявное timezone conversion.

## Quality gates и DoD

- два запуска дают одинаковые решение, объяснение и порядок;
- provenance доступен application consumers, конфликты не скрываются;
- текущие overlay/CLI/GUI и FFmpeg argv сохраняют parity;
- unit/contract/full smoke, compileall и `git diff --check` зелёные;
- после commit `AI_STATUS` и `AI_PLAN` переключены на этап 05.

## Откат

Новый engine подключается за существующим FFprobe/filename adapter. При
несовместимости откатывается stage commit без изменения исходных медиа.

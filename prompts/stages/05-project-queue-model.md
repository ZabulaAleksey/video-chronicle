# Этап 05 — Project/queue model

## Цель

Создать независимые от UI модели timeline, export plan и жизненного цикла
долгого задания, на которые смогут опереться GUI, progress/cancel и resume.

## Предварительный decision gate

До выбора SQLite или другого persistence описать контракт модели, состояния и
восстановления. Хранилище не утверждать по упоминанию в roadmap; решение
фиксируется в SPEC/DECISIONS после сравнения in-memory/file/SQLite вариантов.

## Зависимости и контекст

- Этап 04 завершён; metadata/date result стабилен.
- Прочитать `FR-004/005/009/010`, `AC-002/006/007`, architecture, security и
  testing. Обновить `AI_PLAN` только на согласованный срез этапа 05.

## Scope / non-goals

- Timeline items, stable identifiers/order, export plan snapshot, job states и
  допустимые transitions; сначала in-memory reference implementation.
- Не строить GUI, не запускать FFmpeg из модели, не реализовывать resume/cache.
- Не добавлять сеть, server queue или multi-user semantics.

## Области и контракты

- Разрешены: domain/application models, repository port, tests, SPEC/ADR/docs.
- Запрещены: widgets imports в модели и команды/paths из недоверенного state.
- Состояния должны различать planned/running/succeeded/failed/cancel-requested,
  не выдавая incomplete output за готовый.

## Tests и gates

- State-transition/table tests, stable ordering/IDs, serialization round-trip
  только для утверждённого формата, invalid/corrupt state rejection.
- Никаких внешних процессов в domain tests; full regression suite остаётся зелёным.

## DoD / artifacts / rollback

- UI-независимые контракты и storage decision задокументированы; migrations,
  если появились, имеют forward/backward test; `AI_PLAN` → 06.
- Persistence adapter заменяем; rollback возвращает in-memory adapter без
  изменения domain API и без потери исходников/готовых результатов.

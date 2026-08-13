# Этап 04 — Metadata/date engine

## Цель

Сделать выбор даты объяснимым и детерминированным: политика приоритетов,
provenance, timezone и адаптеры источников метаданных.

## Предварительный decision gate

Feature SPEC пока содержит открытые вопросы. До production-кода подготовить и
получить утверждение пользователя для приоритета metadata/EXIF/filename,
поведения missing/conflict и timezone. Если решения нет — завершить только
SPEC/ADR/планирование и остановиться.

## Зависимости и контекст

- Этап 03 завершён; metadata port выделен.
- Прочитать `FR-002–FR-004`, `NFR-001`, `AC-002`, system invariants,
  metadata sections architecture/testing/security и профиль
  `.codex/agents/metadata_forensics_specialist.toml` только при необходимости.

## Scope / non-goals

- Typed result с выбранной датой, origin, raw value/conflict diagnostics и
  явной timezone policy; adapters текущего FFprobe и утверждённых источников.
- Не добавлять пользовательское редактирование timeline, SQLite, ML и OTIO.
- ExifTool добавлять только после отдельного dependency/licensing decision.

## Области и контракты

- Разрешены: metadata/date core, adapters, tests, feature SPEC, decisions/docs.
- Запрещено: молчаливое timezone conversion и скрытие конфликтов.

## Tests и gates

- Table/property tests: metadata keys/casing, invalid values, equal dates,
  filename Unicode, timezone-aware/naive, conflicts и deterministic ordering.
- Adapter contract и regression smoke; SPEC validation для `AC-002`.

## DoD / artifacts / rollback

- Утверждённая policy записана в SPEC/DECISIONS; provenance доступен consumers.
- Дважды выполненный набор даёт один результат и объяснение; `AI_PLAN` → 05.
- Новые adapters feature-gated; при несовместимости fallback — проверенный
  FFprobe/filename path без изменения сохранённых raw values.

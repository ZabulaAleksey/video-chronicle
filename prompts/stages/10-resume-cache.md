# Этап 10 — Resume и cache

## Цель

Завершить MVP совместимым возобновлением: повторно использовать только
проверенные промежуточные данные, связанные с входами, планом и инструментами.

## Зависимости, decision gate и контекст

- Этап 09 завершён; export/cancel state machine стабилен.
- Утвердить identity/key schema, versioning, retention, integrity и cleanup.
- Прочитать `FR-010`, `AC-007`, `SEC-005`, job/project model, architecture,
  security/testing и решение persistence этапа 05.

## Scope / non-goals

- Content/metadata identity, parameter/tool-version key, cache manifest,
  validation/invalidation, safe resume и explicit purge.
- Не доверять cache paths/commands, не использовать partial final как success.
- Не добавлять cloud sync, distributed cache или ML artifacts.

## Области и контракты

- Разрешены: cache/resume domain and storage adapter, migrations, export
  integration, GUI status, tests, security/architecture/SPEC.
- Cache является оптимизацией: полный clean export остаётся fallback.

## Tests и gates

- Resume after interruption; input/content/mtime/parameters/tool-version change;
  corrupt/tampered/old manifest; permissions/space; purge and clean fallback.
- Property tests stable keys; integration parity resumed vs clean output;
  security review обязателен.

## DoD / artifacts / rollback

- `AC-007` подтверждён; incompatible state rejected before reuse; MVP 02–10
  отмечен завершённым только после full mixed-media regression.
- `AI_STATUS` фиксирует MVP, `AI_PLAN` создаётся для утверждённого этапа 11 или
  для release hardening по решению пользователя.
- Cache можно полностью отключить без потери функциональности или данных.

# Этап 03 — Core extraction

## Цель

Извлечь из legacy-модуля тестируемые domain/application границы без изменения
наблюдаемого CLI/GUI-поведения и без второго медиаконвейера.

## Зависимости и контекст

- Этап 02 завершён; package и compatibility entry points стабильны.
- Прочитать system SPEC, `FR-011`, `NFR-001`, `AC-008`, architecture,
  security/testing, baseline tests и текущий package.
- Создать текущий `AI_PLAN` с последовательными маленькими extraction-блоками.

## Scope / non-goals

- Чистые модели/функции, ports для probe/process/filesystem и application
  service для plan/execute boundary.
- CLI и переходный GUI должны использовать один production path.
- Не утверждать новую metadata policy, очередь, persistence, cancel или cache.
- Не переписывать всё одним большим изменением.

## Области и контракты

- Разрешены: package core/application/adapters, legacy shims, tests, architecture.
- Запрещены: внешние бинарники, UI redesign, новые продуктовые режимы.
- Контракты: deterministic inputs/outputs, typed public boundaries, list argv,
  atomic publish и прежние codes/messages в пределах утверждённой совместимости.

## Tests и gates

- До каждого extraction шага существует characterization test.
- Unit tests чистого core, adapter contract tests, CLI/GUI parity, FFmpeg smoke,
  compileall и diff check.
- Reviewer обязателен; security review — для subprocess/filesystem boundary.

## DoD / artifacts / rollback

- `join_media.py` стал тонким entry/compatibility layer; медиалогика не
  дублируется; architecture отражает ports/adapters.
- Все baseline tests зелёные, `AI_PLAN` переключён на 04.
- Каждый extraction block обратим отдельным commit; при parity regression
  откатить последний блок, а не ослаблять characterization.

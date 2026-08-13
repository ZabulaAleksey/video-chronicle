# Этап 09 — Export, progress и safe cancel

## Цель

Реализовать структурированный export lifecycle с проверкой плана, наблюдаемым
прогрессом, безопасной отменой всего process tree и атомарной финализацией.

## Зависимости, decision gate и контекст

- Этап 08 завершён.
- До кода утвердить семантику процента, timeout/escalation cancel и cleanup.
- Прочитать `FR-005/006/008/009/012`, `AC-003/005/006/009/010`, system
  security, job model, architecture, testing/security и platform process rules.

## Scope / non-goals

- Preflight tools/paths/space where feasible, structured progress events,
  cancellation token/process-tree termination, terminal states и cleanup.
- GUI progress/cancel и CLI-compatible diagnostics.
- Не реализовывать resume/cache, background service или parallel exports.

## Области и контракты

- Разрешены: export application service, subprocess adapter, job states,
  GUI/CLI consumers, integration tests, security/architecture/SPEC.
- Запрещено считать kill одного Python-процесса безопасной отменой на Windows.
- Final output существует только после success; existing output защищён.

## Tests и gates

- Integration tests normal/failure/cancel before/during encode/during concat,
  orphan-process check, collision/permissions/Unicode и bounded cancel time.
- GUI event-loop responsiveness; security review обязателен.

## DoD / artifacts / rollback

- `AC-003/005/006/009/010` подтверждены автоматикой или явным platform test;
  отмена не меняет inputs/result и не оставляет живой FFmpeg; `AI_PLAN` → 10.
- Feature flag позволяет отключить cancel UI; fallback — дождаться завершения,
  а не небезопасно убивать только родителя.

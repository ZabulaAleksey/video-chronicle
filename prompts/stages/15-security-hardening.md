# Этап 15 — Security hardening

## Цель

Провести release-oriented аудит недоверенных медиа, subprocess, путей,
permissions, cache/state и supply chain; устранить подтверждённые риски до
Windows-пакетирования.

## Зависимости и контекст

- Все выбранные v1-функции реализованы; feature set для release заморожен.
- Прочитать system/feature SPEC, full architecture/data boundaries,
  `docs/SECURITY.md`, tests, dependency manifests и packaging assumptions.
- Обновить `AI_PLAN` на threat-model → fixes → verification, не на redesign.

## Scope / non-goals

- Threat model, input/resource limits, process tree, path/symlink/reparse-point
  handling, atomic publish, cache tampering, log disclosure, dependency audit.
- Не добавлять новые продуктовые функции и не обещать sandbox, которого нет.

## Области и контракты

- Разрешены: boundary validation, adapters, limits/config, negative tests,
  SECURITY/DECISIONS/release docs.
- Источники immutable; custom executable является trusted-code decision;
  cleanup ограничен известной work/cache областью.

## Tests и gates

- Corpus corrupt/large/pathological media; Unicode/quotes/long paths;
  permissions/space/collision/cancel; tampered state/cache; orphan processes;
  dependency/license/vulnerability audit.
- Независимый security review обязателен; high findings блокируют этап 16.

## DoD / artifacts / rollback

- Threat model и residual risks документированы, high findings закрыты,
  negative suite автоматизирован; `AI_PLAN` → 16.
- Каждый hardening change имеет compatibility test и отдельную точку отката.

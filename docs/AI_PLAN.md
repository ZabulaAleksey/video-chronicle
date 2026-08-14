# Текущий план для AI

## Срез

- Этап: **10 — Resume и cache**
- Статус: CACHE-001 утверждён; production-реализация в работе
- Prompt: `prompts/stages/10-resume-cache.md`
- Зависимости: этапы 01–09 завершены; export lifecycle, source fingerprint,
  process-tree cancel и atomic publication стабильны
- Требования: `FR-010`, `SEC-005`
- Критерий: `AC-007`

## Цель

Добавить безопасное возобновление как отключаемую оптимизацию: повторно
использовать только подтверждённые intermediates, связанные с точной identity
входа, immutable plan, параметрами и совместимой версией инструментов.

## Утверждённый contract

- opt-in normalized-clip cache; legacy/default CLI остаётся clean;
- `clip-v1` canonical key связывает content/stat/date/settings/profile/font и
  FFmpeg/FFprobe identities, но не output/order/overwrite;
- strict path-free manifest v1 и bounded FFprobe validation;
- private platform cache root, atomic no-replace store, 10 GiB/30-day limits;
- I/O/corruption означает miss + clean fallback; explicit purge scoped marker;
- cache hit копируется в active workspace и завершает одну progress unit.

## Scope

- Qt-free cache/resume contracts и storage adapter;
- интеграция reuse в единственный `execute_plan`;
- GUI status и явное отключение/purge;
- resume/corruption/parity/security tests.

## Non-goals

- cloud/distributed cache, background service и parallel exports;
- ML artifacts;
- использование partial final output как success.

## Quality gates и DoD

- несовместимый state отвергается до reuse;
- изменение content/metadata/mtime, plan parameters или tool version
  инвалидирует соответствующий cache entry;
- resumed export эквивалентен clean export, а отключённый cache не меняет
  функциональность или сохранность данных;
- security review, full mixed-media regression, compileall и `git diff --check`
  зелёные;
- после acceptance этапы 02–10 отмечаются как завершённый MVP, `AI_PLAN`
  переключается на этап 11.

## Откат

Cache должен отключаться целиком; clean export остаётся каноническим fallback,
а purge удаляет только подтверждённую private cache область.

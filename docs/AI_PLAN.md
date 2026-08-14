# Текущий план для AI

## Срез

- Этап: **10 — Resume и cache**
- Статус: decision gate; identity/key/storage contract ещё не утверждён
- Prompt: `prompts/stages/10-resume-cache.md`
- Зависимости: этапы 01–09 завершены; export lifecycle, source fingerprint,
  process-tree cancel и atomic publication стабильны
- Требования: `FR-010`, `SEC-005`
- Критерий: `AC-007`

## Цель

Добавить безопасное возобновление как отключаемую оптимизацию: повторно
использовать только подтверждённые intermediates, связанные с точной identity
входа, immutable plan, параметрами и совместимой версией инструментов.

## Decision gate до production-кода

- утвердить канонический cache key и manifest schema/version;
- выбрать локальный storage adapter, atomic write и crash recovery;
- определить integrity validation, invalidation, retention и explicit purge;
- зафиксировать поведение при corrupt/tampered/old state и нехватке места;
- сохранить clean export как обязательный fallback и не доверять cache paths.

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

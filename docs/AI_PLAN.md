# Текущий план для AI

## Срез

- Этап: **09 — Export, progress и safe cancel**
- Статус: EXEC-001 утверждён; реализация в работе
- Prompt: `prompts/stages/09-export-progress-cancel.md`
- Зависимости: этапы 01–08 завершены; Join/Chronicle используют один
  application/pipeline path и immutable plan
- Требования: `FR-005/006/008/009/012`, `SEC-002/003`
- Критерии: `AC-003/005/006/009/010`

## Цель

Ввести structured export lifecycle с наблюдаемым прогрессом, безопасной
отменой всего принадлежащего заданию process tree и неизменной атомарной
финализацией.

## Утверждённый contract

- analysis total — source count; export total — accepted items + concat + publish;
- progress показывает completed units, не ETA, и достигает 100% только после
  publication;
- cancellation token принимает запрос только до atomic publication commit;
- Windows: Job Object; POSIX: process group; cooperative grace 2 с, forced
  tree termination/reap ещё 3 с, acceptance bound 5.5 с;
- terminal state использует существующий `JobState`; неподтверждённая остановка
  означает failed;
- `VIDEO_CHRONICLE_CANCEL_UI=0` и unsupported/legacy backend оставляют только
  безопасный fallback «дождаться завершения».

## Scope

- Qt-free lifecycle/events/cancellation contracts и application orchestration;
- subprocess adapter, владеющий дочерним process tree;
- GUI progress/cancel и CLI-compatible diagnostics;
- normal/failure/cancel integration tests до/during encode/concat, orphan check,
  collisions, permissions и Unicode.

## Non-goals

- resume/cache, durable queue или background service;
- parallel exports;
- отмена через kill только Python parent process.

## Quality gates и DoD

- SPEC утверждает progress/cancel/finalization contract до production-кода;
- cancel ограничен по времени, не меняет inputs/existing result и не оставляет
  принадлежащий заданию FFmpeg;
- final output появляется только после success;
- GUI event loop остаётся отзывчивым, terminal states различимы;
- focused/platform integration, security review, full regression, compileall и
  `git diff --check` зелёные;
- после acceptance `AI_STATUS`/`ROADMAP` обновлены, `AI_PLAN` переключён на 10.

## Откат

Cancel UI управляется feature flag. При недоступном безопасном tree adapter
fallback только ждёт завершения и не имитирует отмену parent-only kill.

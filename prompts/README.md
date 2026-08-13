# Библиотека этапов Video Chronicle

Stage prompts — самостоятельные входы для поэтапной работы Codex. Они не
являются источником продуктовых требований и не загружаются все одновременно.
Канонические роли: SPEC — требования, `ROADMAP` — порядок, `AI_PLAN` — один
текущий срез, `AI_STATUS` — факты.

## Как запускать этап

1. Пользователь пишет: `Начинай этап NN`.
2. Codex читает `AGENTS.md`, `docs/AI_STATUS.md`, текущий `docs/AI_PLAN.md` и
   только соответствующий prompt.
3. Проверяет DoD предыдущего этапа и утверждённость нужных требований.
4. Переносит ограниченный исполняемый срез в `docs/AI_PLAN.md`.
5. Выполняет этап через `$implement-stage`; если SPEC не утверждена, сначала
   завершает только specification/planning gate и запрашивает решение.
6. После acceptance обновляет `AI_STATUS` и переключает `AI_PLAN` на следующий
   этап. `PROGRESS.md` не создаётся.

## Индекс

| Фаза | Этапы | Результат |
| --- | --- | --- |
| Foundation | [01](stages/01-discovery-baseline.md)–[05](stages/05-project-queue-model.md) | baseline, package, core, metadata и UI-независимая модель |
| MVP | [06](stages/06-gui-application-services.md)–[10](stages/10-resume-cache.md) | полноценный GUI, overlay, режимы, export/cancel и resume |
| v1 | [11](stages/11-nondestructive-editing.md)–[16](stages/16-windows-packaging.md) | монтаж, optional adapters, hardening и Windows release |
| Experiments | [17](stages/17-experimental-adapters.md) | только доказанные feature-flagged эксперименты |

Этапы 01–10 последовательны. Этапы 11–16 требуют отдельного утверждения
относящейся feature SPEC. Этап 17 не начинается без проблемы, метрики успеха,
fallback и решения пользователя.

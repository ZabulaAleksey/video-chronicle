# Текущий план для AI

## Срез

- Этап: **05 — Project/queue model**
- Статус: выполняется по прямой команде пользователя
- Prompt: `prompts/stages/05-project-queue-model.md`
- Зависимости: этапы 01–04 завершены; metadata/date result DATE-001 стабилен
- Требования: `FR-004`, `FR-005`, `FR-009`, `FR-010`
- Критерии: `AC-002`, подготовительные части `AC-006/007`, `NFR-001`

## Цель

Создать Qt-free модели timeline, неизменяемого export snapshot и жизненного
цикла долгого задания, пригодные для будущих GUI/progress/cancel/resume, но не
запускающие FFmpeg и не выдающие незавершённый результат за готовый.

## Предварительный decision gate

До production-кода закрепить в feature SPEC:

- стабильный идентификатор timeline item и tie-breaker порядка;
- immutable project/export snapshot;
- состояния и допустимые transitions задания;
- versioned JSON-compatible serialization contract;
- `InMemoryProjectRepository` как reference adapter этапа 05.

SQLite и файловое persistence не утверждаются: они сравниваются позже, когда
появятся требования к resume/cache и миграциям.

## Последовательность

1. Записать MODEL-001 и storage decision в SPEC/DECISIONS.
2. Добавить Qt-free timeline/project/job models и transition validation.
3. Добавить repository port и in-memory reference adapter.
4. Добавить versioned serialization round-trip и отказ на corrupt/unknown state.
5. Подтвердить отсутствие Qt/subprocess side effects и весь regression baseline.

## Non-goals

- GUI/widgets, FFmpeg execution, progress transport и process-tree cancel;
- SQLite/file persistence, migrations, resume или cache;
- server queue, network и multi-user semantics;
- пользовательское изменение порядка/trim/grouping.

## Quality gates и DoD

- stable IDs/order повторяемы для одного source/date snapshot;
- planned/running/cancel-requested/succeeded/failed различимы, invalid transition
  отвергается;
- success требует зафиксированный final output, incomplete job не становится success;
- versioned serialization принимает только утверждённую схему;
- domain tests не импортируют Qt и не запускают внешние процессы;
- full tests, compileall и `git diff --check` зелёные;
- после commit `AI_STATUS` и `AI_PLAN` переключены на этап 06.

## Откат

Reference repository хранит только in-memory snapshots. Stage commit можно
откатить без изменения исходных медиа и готовых результатов.

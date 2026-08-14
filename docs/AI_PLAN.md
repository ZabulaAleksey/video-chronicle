# Текущий план для AI

## Срез

- Этап: **11 — Неразрушающее редактирование timeline**
- Статус: specification gate; production-код до утверждения EDIT-001 не писать
- Prompt: `prompts/stages/11-nondestructive-editing.md`
- Зависимости: этапы 01–10 завершены; MVP стабилен, cache/resume является opt-in
- Требования: будут выделены из `FR-002`, `FR-003`, `FR-005`, `FR-006`, `FR-007`
- Критерии: будут утверждены в отдельной feature SPEC

## Цель текущего среза

Определить Qt-free contract неразрушающих edits: stable reorder, trim in/out,
groups и versioned presets как данные проекта. Preview, export, persistence и
cache identity должны использовать один и тот же immutable snapshot, не меняя
и не переименовывая исходные медиафайлы.

## Specification gate

До реализации необходимо:

- создать отдельную editing SPEC с терминами, инвариантами и критериями приёмки;
- определить границы trim, порядок/group semantics и версионирование presets;
- выбрать durable persistence/migration contract с backup/rollback либо feature flag;
- определить влияние edits на preview/export и cache key;
- явно исключить multi-track NLE, effects graph, collaboration и cloud storage.

## Quality gates и DoD этапа

- model/property tests для reorder/trim/group и утверждённых state transitions;
- проект повторно открывается без потери edits;
- preview/export parity и точная invalidation cache;
- исходники побайтно неизменны;
- migration имеет воспроизводимый rollback;
- full regression, GUI QA, review и security review зелёные;
- после acceptance `AI_PLAN` переключается на этап 12.

## Откат

Editing schema должна быть feature-gated либо иметь backup/rollback. Отключение
редактора не должно менять legacy/MVP export path и существующие schema-v1 проекты.

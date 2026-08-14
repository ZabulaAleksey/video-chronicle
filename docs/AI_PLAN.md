# Текущий план для AI

## Срез

- Этап: **11 — Неразрушающее редактирование timeline**
- Статус: EDIT-001 утверждён; production-реализация в работе
- Prompt: `prompts/stages/11-nondestructive-editing.md`
- Зависимости: этапы 01–10 завершены; MVP стабилен, cache/resume является opt-in
- Требования: будут выделены из `FR-002`, `FR-003`, `FR-005`, `FR-006`, `FR-007`
- SPEC: `specs/features/nondestructive-editing.spec.md`
- Критерии: `EDIT-AC-001–007`

## Цель текущего среза

Определить Qt-free contract неразрушающих edits: stable reorder, trim in/out,
groups и versioned presets как данные проекта. Preview, export, persistence и
cache identity должны использовать один и тот же immutable snapshot, не меняя
и не переименовывая исходные медиафайлы.

## Утверждённый contract

- date-sorted `Timeline` остаётся baseline, ручная перестановка живёт в layout;
- trim хранится в integer µs, runtime snapshot содержит resolved bounds;
- группы непрерывны, не вложены и перемещаются блоком;
- immutable presets versioned, snapshot хранит ref и resolved settings;
- schema v2 мигрирует v1 только с backup-before-replace и rollback;
- full-source cache v1 совместим, реальный trim использует cache v2 identity.

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

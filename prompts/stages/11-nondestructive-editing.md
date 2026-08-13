# Этап 11 — Неразрушающее редактирование timeline

## Цель и specification gate

Добавить reorder, trim, grouping и presets как изменения проекта, а не
исходных файлов. Текущая feature SPEC не определяет эти контракты: сначала
создать/утвердить отдельную feature SPEC и критерии; без утверждения код не писать.

## Зависимости и контекст

- MVP 02–10 завершён и стабилен.
- Прочитать system invariants, timeline/export/cache contracts, DESIGN,
  SECURITY/TESTING и только новую editing SPEC после её создания.
- Обновить `AI_PLAN` сначала на specification slice, затем на implementation.

## Scope / non-goals

- Stable reorder, non-destructive in/out trim, groups и versioned presets;
  preview/export используют один project model.
- Не изменять/переименовывать inputs; не делать multi-track NLE, effects graph,
  collaboration или cloud storage.

## Области и контракты

- Разрешены: project/timeline domain, persistence migrations, GUI editor,
  application services, tests, SPEC/DESIGN/DECISIONS.
- Trim bounds и ordering валидируются до export; cache keys учитывают edits.

## Tests и gates

- Model/property tests reorder/trim/group; undoable state transitions если
  утверждены; migration, cache invalidation, preview/export parity и GUI QA.
- Regression MVP и immutable-input checks обязательны.

## DoD / artifacts / rollback

- Утверждённая editing SPEC связана с tests; проект повторно открывается без
  потери edits; исходники побайтно неизменны; `AI_PLAN` → выбранный этап 12.
- Migration имеет backup/rollback либо новая схема feature-gated.

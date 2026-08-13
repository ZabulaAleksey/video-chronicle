# Этап 06 — GUI поверх application services

## Цель

Заменить переходный запуск whole CLI на application-service boundary и дать
пользователю проверку состава и порядка до экспорта, сохранив отзывчивость UI.

## Зависимости и контекст

- Этап 05 завершён; timeline/export plan/job model стабильны.
- Прочитать `FR-001/004/005/012`, `NFR-003/004`, `AC-001/002/009/010`,
  system SPEC, architecture, design, security/testing и существующий PySide6 GUI.
- Перед implementation обновить `AI_PLAN`; если поведение preview не
  утверждено, сначала уточнить feature SPEC.

## Scope / non-goals

- Асинхронный анализ папки, список accepted/skipped/error items, выбранная дата
  и порядок, export plan summary, loading/empty/error states.
- Перевести GUI с whole-CLI adapter на application services без дублирования.
- Не добавлять ручной reorder/trim, overlay editor, cancel, cache или persistence UI.

## Области и контракты

- Разрешены: GUI presenters/view models/widgets, application adapters, tests,
  design/architecture/status.
- Запрещена медиаработа в UI thread и прямой FFmpeg orchestration в widgets.
- Закрытие/worker lifecycle явны; paths остаются list values без shell.

## Tests и gates

- GUI tests loading/empty/error/populated, responsiveness, Unicode paths,
  повторный запуск и cleanup; application contract tests; legacy CLI parity.
- Visual QA на Windows, keyboard/focus и light/dark system palette.

## DoD / artifacts / rollback

- Пользователь видит состав и порядок до запуска; GUI и CLI используют один
  application path; переходный adapter можно удалить без потери поведения.
- DESIGN/ARCHITECTURE отражают фактический UI, `AI_PLAN` → 07.
- Feature flag/adapter boundary позволяет временно вернуть GUI-001 при
  регрессии, не создавая второй core.

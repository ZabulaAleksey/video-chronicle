# Текущий план для AI

## Срез

- Этап: **06 — GUI поверх application services**
- Статус: в работе; preview contract `GUI-APP-001` утверждён
- Prompt: `prompts/stages/06-gui-application-services.md`
- Зависимости: этапы 01–05 завершены; DATE-001 и MODEL-001 стабильны
- Требования: `FR-001`, `FR-004`, `FR-005`, `FR-012`, `NFR-003/004`
- Критерии: `AC-001`, `AC-002`, `AC-009`, `AC-010`

## Цель

Заменить переходный запуск whole CLI на application-service boundary и показать
пользователю принятые/пропущенные элементы, выбранные даты и порядок до
экспорта, сохранив отзывчивость PySide6 UI и единый production path.

## Утверждённый контракт

- accepted item: порядок, имя/путь, выбранная wall-clock дата, provenance,
  timezone и признак конфликта;
- skipped item: путь и диагностическая причина;
- loading/empty/error/populated — явные состояния;
- изменение формы инвалидирует preview, export требует актуального непустого plan;
- overwrite подтверждается отдельно непосредственно перед export;
- worker/close lifecycle не имитирует безопасную отмену до этапа 09.

## Scope

- асинхронный анализ папки через application services;
- preview состава, порядка, date provenance и export summary;
- presenters/view models и worker lifecycle вне UI thread;
- сохранение legacy CLI parity и fallback GUI-001 на adapter boundary.

## Non-goals

- ручной reorder/trim/grouping;
- overlay editor, Join/Chronicle modes;
- progress/cancel, resume/cache или durable persistence;
- FFmpeg orchestration внутри widgets.

## Quality gates и DoD

- GUI показывает состав и порядок до export;
- анализ/экспорт не блокируют UI thread;
- GUI и CLI используют один application path;
- loading/empty/error/populated, Unicode paths, repeat-run и cleanup покрыты;
- Windows visual/keyboard/focus QA выполнен;
- full regression, compileall и `git diff --check` зелёные;
- после acceptance `AI_PLAN` переключён на этап 07.

## Откат

Переходный GUI-001 остаётся adapter fallback до завершения acceptance этапа 06;
второй core или второй медиаконвейер не создаётся.

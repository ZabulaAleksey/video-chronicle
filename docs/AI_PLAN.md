# Текущий план для AI

## Срез

- Этап: **07 — Overlay editor**
- Статус: подготовлен, не начат
- Prompt: `prompts/stages/07-overlay-editor.md`
- Зависимости: этапы 01–06 завершены; preview использует immutable `ExportPlan`
- Требования: `FR-002`, `FR-007`, `NFR-003/004`
- Критерий: `AC-004`

## Цель

Ввести один typed overlay config для настройки подписи даты, быстрого
representative-frame preview и финального FFmpeg export path.

## Decision gate

До production-кода утвердить в feature SPEC:

- формат подписи и default enabled policy;
- допустимые позиции, margins, font size и color values;
- font fallback и поведение при отсутствующем explicit font;
- representative-frame preview, loading/error/disabled states;
- правила escaping Unicode text/font paths только в adapter boundary.

## Scope

- Qt-free immutable overlay config с валидацией и defaults;
- единый adapter к FFmpeg filter generation;
- PySide6 controls и асинхронный representative-frame preview;
- overlay on/off integration smoke без изменения источников.

## Non-goals

- полноценный video editor, animation/keyframes и arbitrary FFmpeg expressions;
- marketplace/templates, manual timeline editing и mode switch;
- progress/cancel, resume/cache или persistence UI.

## Quality gates и DoD

- `AC-004` прослеживается до config, preview и synthetic export test;
- preview и export получают один config object;
- Unicode text/font paths экранируются adapter’ом, не widgets;
- scaling, keyboard, contrast, loading/error preview проверены;
- full regression, compileall и `git diff --check` зелёные;
- после acceptance `AI_PLAN` переключён на этап 08.

## Откат

Overlay config имеет `enabled=False`; preview adapter removable, а выключение
overlay возвращает действующий media filter без изменения source или plan schema.

# Текущий план для AI

## Срез

- Этап: **07 — Overlay editor**
- Статус: в работе; overlay contract `OVERLAY-001` утверждён
- Prompt: `prompts/stages/07-overlay-editor.md`
- Зависимости: этапы 01–06 завершены; preview использует immutable `ExportPlan`
- Требования: `FR-002`, `FR-007`, `NFR-003/004`
- Критерий: `AC-004`

## Цель

Ввести один typed overlay config для настройки подписи даты, быстрого
representative-frame preview и финального FFmpeg export path.

## Утверждённый контракт

- default: enabled, `dd.MM.yy ddd`, `bottom-left`, margins 20, font size 72,
  black text, white outline width 4;
- только три format preset и четыре corner position; numeric/hex ranges строгие;
- explicit `.ttf`/`.otf` обязан существовать; иначе проверенный system fallback;
- preview первого accepted item — PNG 640×360 через тот же filter adapter;
- overlay-only change не повторяет FFprobe, но инвалидирует visual preview;
- text/font paths экранируются только в pipeline adapter, argv остаётся list.

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

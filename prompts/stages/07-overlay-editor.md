# Этап 07 — Overlay editor

## Цель

Дать единую конфигурацию подписи даты и быстрый предпросмотр, применяемые
одинаково к плану, preview и финальному экспорту.

## Зависимости, decision gate и контекст

- Этап 06 завершён.
- Утвердить в feature SPEC формат, включение, позицию, font fallback, цвета,
  границы допустимых значений и поведение при отсутствующем шрифте.
- Прочитать `FR-002/007`, `AC-004`, design, architecture, security/testing,
  текущий `make_video_filter` и export-plan contract.

## Scope / non-goals

- Typed overlay config, UI controls, representative frame preview и единый
  adapter к FFmpeg filter generation.
- Не делать полноценный video editor, animation/keyframes, templates marketplace
  или произвольные FFmpeg expressions.

## Области и контракты

- Разрешены: overlay domain/config, preview service, PySide6 controls, tests,
  SPEC/DESIGN/DECISIONS.
- Один config object используется preview и export; пользовательский текст и
  paths экранируются в adapter, а не в widgets.

## Tests и gates

- Unit tests config/escaping/defaults; golden/screenshot checks representative
  preview; integration test overlay on/off; Unicode font/path negatives.
- Visual QA: scaling, keyboard, contrast и loading/error preview.

## DoD / artifacts / rollback

- `AC-004` прослеживается до config, preview и synthetic export test.
- DESIGN фиксирует controls/tokens/states, `AI_PLAN` → 08.
- Overlay можно выключить без изменения исходников и pipeline; новый preview
  adapter removable без изменения export plan schema.

# Этап 08 — Join и Chronicle modes

## Цель

Сделать два понятных режима поверх одного медиаконвейера: совместимый Join и
Chronicle с датами/overlay, без расхождения core semantics.

## Зависимости, decision gate и контекст

- Этап 07 завершён.
- В feature SPEC утвердить различия режимов, defaults, migration CLI и
  допустимые сочетания параметров.
- Прочитать `FR-006/007/011`, `AC-003/004/008`, system compatibility,
  architecture/design/testing и текущие plan/overlay contracts.

## Scope / non-goals

- Явный mode enum/config, единый plan builder с mode-specific policy,
  GUI selector и совместимое CLI representation.
- Не дублировать normalize/concat, не добавлять trim/reorder/cache и не менять
  codecs без отдельного требования.

## Области и контракты

- Разрешены: mode config/policy, application/CLI/GUI adapters, tests, docs/SPEC.
- Legacy invocation сохраняет прежний результат либо получает утверждённую
  migration; режим является данными плана, не ветвлением widgets.

## Tests и gates

- Matrix tests mode × overlay × media type; CLI compatibility; same-plan
  determinism; mixed-media smoke для обоих режимов.
- Отсутствие duplicated FFmpeg pipeline подтверждается review.

## DoD / artifacts / rollback

- Пользователь понимает различия до экспорта, оба режима проходят один core;
  migration и defaults задокументированы; `AI_PLAN` → 09.
- Новый mode policy обратим, старый Join остаётся безопасным fallback.

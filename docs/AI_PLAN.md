# Текущий план для AI

## Срез

- Этап: **08 — Join и Chronicle modes**
- Статус: подготовка decision gate; реализация не начата
- Prompt: `prompts/stages/08-join-chronicle-modes.md`
- Зависимости: этапы 01–07 завершены; единый `ExportPlan` содержит immutable
  `OverlayConfig`
- Требования: `FR-006`, `FR-007`, `FR-011`, system compatibility
- Критерии: `AC-003`, `AC-004`, `AC-008`

## Цель

Утвердить и реализовать два понятных режима поверх одного медиаконвейера:
обратно совместимый Join и Chronicle с date policy/overlay.

## Decision gate до кода

- определить наблюдаемую разницу режимов и их defaults;
- решить, является ли overlay допустимым в Join и как mode влияет на date
  requirement;
- зафиксировать legacy CLI default и совместимое явное representation mode;
- описать недопустимые сочетания и сообщения пользователю;
- добавить требования и acceptance matrix в feature SPEC.

## Scope

- Qt-free mode enum/config и policy на уровне request/plan;
- единый plan builder и существующий normalize/concat path;
- GUI selector с объяснением результата до экспорта;
- совместимое CLI representation и migration tests;
- matrix tests mode × overlay × media type и mixed-media smoke обоих режимов.

## Non-goals

- второй медиаконвейер или дублирование FFmpeg filters;
- новые codecs, trim/reorder, progress/cancel, cache/resume;
- изменение legacy поведения без утверждённой migration policy.

## Quality gates и DoD

- SPEC утверждает mode contract до production-кода;
- legacy invocation сохраняет ожидаемый результат;
- mode хранится как данные immutable plan, а не как ветвление widgets;
- оба режима проходят один application/pipeline path;
- focused matrix, CLI characterization, mixed-media smoke, full regression,
  compileall и `git diff --check` зелёные;
- после acceptance `AI_STATUS` и `ROADMAP` обновлены, `AI_PLAN` переключён на 09.

## Откат

Mode policy должна быть обратимой: legacy Join остаётся безопасным fallback,
а mode selector удаляется без изменения normalize/concat/publication adapters.

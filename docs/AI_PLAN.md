# Текущий план для AI

## Срез

- Этап: **12 — Optional timeline interchange и scene analysis**
- Статус: **завершён; дальнейшая реализация приостановлена по указанию пользователя**
- Prompt: `prompts/stages/12-timeline-interchange-scene.md`
- SPEC: `specs/features/timeline-interchange-scene.spec.md`, версия 1.1
- Acceptance: `INTEROP-AC-001–003`, `SCENE-AC-001/002`,
  `OPTIONAL-AC-001`, `LICENSE-AC-001` выполнены

## Принятый результат

- native `.otio` реализован как removable optional adapter с exact pin
  `opentimelineio==0.18.1`;
- import создаёт immutable proposal и требует явного применения к новой
  project revision;
- strict preflight ограничивает schemas, поля, local refs, JSON resources и
  не вызывает ambient OTIO plugins/hooks/media linker;
- `ffmpeg-scdet-v1` возвращает только source-relative предложения сцен и
  использует managed process/cancel/tool-identity boundary;
- synthetic benchmark прошёл continue-gate: P/R/F1 `1.0/1.0/1.0`, FP/min `0`,
  p95 `0 µs`, timestamps `3/3`, wall/media `0.080509`;
- feature flags по умолчанию выключены, schema v2 и обычный export не зависят
  от OTIO или scene adapter.

## Проверки acceptance

- focused: `34 passed`;
- full: `298 passed, 2 skipped`;
- correctness review: READY;
- security review: READY;
- `compileall`/CLI help/`git diff --check`: пройдены.

## Точка продолжения

Следующим по roadmap является этап 13 — optional local transcription, но он
**не начат**, его prompt не выбран как текущий срез и новые зависимости не
исследуются. Возобновлять его только по новой команде пользователя.

## Сохраняющиеся release blockers

- у проекта пока нет утверждённой `LICENSE`;
- FFmpeg остаётся отдельно устанавливаемым executable, его redistribution
  требует отдельного review этапов 15–16;
- optional adapters не считаются release-ready до общего hardening/packaging.

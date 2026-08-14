# Текущий план для AI

## Срез

- Этап: **12 — Optional timeline interchange и scene analysis**
- Статус: INTEROP-001 утверждён; bounded experiment implementation в работе
- Prompt: `prompts/stages/12-timeline-interchange-scene.md`
- Зависимости: этапы 01–11 завершены; project schema v2 и editing snapshot стабильны
- SPEC: `specs/features/timeline-interchange-scene.spec.md`
- AC: `INTEROP-AC-001–003`, `SCENE-AC-001/002`, `OPTIONAL-AC-001`, `LICENSE-AC-001`

## Цель текущего среза

Проверить полезность одного timeline interchange adapter и optional scene
detector, который создаёт только предложения edits. Core project schema,
legacy export и ручной editor не должны зависеть от optional формата/библиотеки.

## Утверждённый experiment

- native `.otio` bounded subset, optional `opentimelineio==0.18.1`/Apache-2.0;
- integer-µs native export и explicit rational-time import rounding;
- FFmpeg `scdet=10.0` выдаёт suggestions, но никогда не auto-edits;
- flags default off и clean fallback без dependency;
- synthetic corpus и численные precision/recall/FP/error/runtime gates;
- adapters удаляются без migration schema v2.

## Non-goals

- внедрение OTIO или другого формата в core domain/schema;
- silent download моделей/бинарников;
- автоматическое необратимое редактирование;
- обещание lossless round-trip без golden verification.

## DoD

- отдельная утверждённая SPEC и ADR continue/drop;
- golden round-trip/timebase и bounded parser negatives;
- scene benchmark достигает заранее выбранных метрик либо эксперимент удалён;
- optional dependency отсутствует в default install и имеет clean fallback;
- full regression/review/security/license gates зелёные;
- после acceptance `AI_PLAN` переключается на этап 13.

## Откат

Adapter и feature flag удаляются без migration project schema. Предложения сцен
не применяются автоматически и могут быть отброшены без изменения проекта.

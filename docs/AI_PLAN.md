# Текущий план для AI

## Срез

- Этап: **12 — Optional timeline interchange и scene analysis**
- Статус: experiment/specification gate; adapter-код до решения SCENE-001 не писать
- Prompt: `prompts/stages/12-timeline-interchange-scene.md`
- Зависимости: этапы 01–11 завершены; project schema v2 и editing snapshot стабильны
- SPEC/AC: будут созданы только после выбора формата, corpus и метрик

## Цель текущего среза

Проверить полезность одного timeline interchange adapter и optional scene
detector, который создаёт только предложения edits. Core project schema,
legacy export и ручной editor не должны зависеть от optional формата/библиотеки.

## Experiment gate

До implementation необходимо:

- сравнить доступные interchange formats/versions и выбрать ровно один;
- определить явную обработку unknown fields, rates и timebase;
- создать bounded golden fixtures и malformed/large negative corpus;
- определить scene benchmark corpus, ground truth и метрики качества/скорости;
- провести dependency/license/security review и определить clean fallback;
- зафиксировать feature flag, критерии continue/drop и удаляемость adapter.

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

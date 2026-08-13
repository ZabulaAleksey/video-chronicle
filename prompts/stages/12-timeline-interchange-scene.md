# Этап 12 — Optional timeline interchange и scene analysis

## Цель и experiment gate

Проверить полезность импорта/экспорта timeline и анализа сцен за адаптерами.
До кода нужны отдельная feature SPEC, форматы/версии, benchmark corpus, метрики
точности и fallback. OTIO/scene libraries не считаются выбранными заранее.

## Зависимости и контекст

- Этап 11 завершён либо явно исключён решением пользователя; project/timeline
  model стабилен.
- Прочитать relevant SPEC, architecture, security/testing, dependency/license
  constraints и compatibility decision. Создать ограниченный `AI_PLAN`.

## Scope / non-goals

- Один утверждённый interchange format через port/adapter; optional scene
  detector, преобразующий результат в предложения, а не необратимые edits.
- Не внедрять формат в core model, не скачивать модели молча, не включать
  auto-edit по умолчанию и не обещать lossless round-trip без теста.

## Области и контракты

- Разрешены: optional adapters, feature flag, fixtures/benchmarks, SPEC/ADR.
- Unknown fields/timebase/rates обрабатываются явно; недоверенные файлы имеют
  size/structure limits.

## Tests и gates

- Golden round-trip fixtures, malformed/large input negatives, timebase tests,
  scene benchmark и clean fallback без optional dependency.
- Security/license review для dependency и parser.

## DoD / artifacts / rollback

- Метрики успеха достигнуты на corpus; adapter можно удалить/выключить без
  изменения project schema; решение continue/drop зафиксировано.
- Если критерии не достигнуты, результат этапа — документированный отказ, а не
  постоянная зависимость.

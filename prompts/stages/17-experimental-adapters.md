# Этап 17 — Experimental adapters

## Цель и обязательный experiment gate

Исследовать только одну подтверждённую проблему, которую нельзя разумно решить
существующим core. До любого кода пользователь утверждает hypothesis, dataset,
метрики успеха, time/resource budget, feature flag, fallback и критерий удаления.

## Зависимости и контекст

- Stable v1/RC существует; эксперимент не блокирует основной продукт.
- Создать отдельную draft feature SPEC/ADR и `AI_PLAN` только для одного
  эксперимента. Не загружать остальные optional prompts без необходимости.

## Scope / non-goals

- Один adapter/ML/scene/timeline hypothesis за port и feature flag;
  воспроизводимый benchmark и сравнительный baseline.
- Не менять canonical project schema, default export или privacy boundary до
  доказательства; не добавлять dependency «на будущее».

## Области и контракты

- Разрешены: isolated adapter, fixtures/benchmark, flag/config, SPEC/ADR/report.
- Запрещены: silent downloads/network, обязательная модель/GPU, второй pipeline
  и использование benchmark data без provenance/license.

## Tests и gates

- Functional fallback/off-path, resource limits, deterministic benchmark where
  applicable, security/privacy/license review и comparison with baseline.

## DoD / acceptance / rollback

- Результат — одно из: promote с утверждённой production SPEC; оставить
  disabled experiment с owner/date; удалить как не достигший metrics.
- Отключение flag полностью возвращает stable v1; experimental state/cache не
  требуется для открытия обычного проекта.

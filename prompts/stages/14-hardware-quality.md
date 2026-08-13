# Этап 14 — Hardware capabilities и quality metrics

## Цель и decision gate

Добавить обнаружение аппаратных возможностей, проверяемое ускорение и метрики
качества с обязательным software fallback. До кода утвердить поддерживаемые
backends, качество, benchmark machines и пределы регрессии.

## Зависимости и контекст

- Export pipeline и resume/cache стабильны; optional ML adapters учитываются,
  только если утверждены.
- Прочитать `NFR-005`, architecture, testing/security, FFmpeg capability
  outputs и новую performance/quality SPEC; создать `AI_PLAN`.

## Scope / non-goals

- Capability probe, explicit backend selection, deterministic fallback,
  benchmark harness и output quality/compatibility checks.
- Не включать hardware path только по наличию устройства; не ухудшать quality
  или portability молча; не поддерживать все GPU vendors без evidence.

## Области и контракты

- Разрешены: capability/performance adapters, export policy, benchmarks,
  fixtures, SPEC/ADR/docs.
- Probe failure безопасен; cache key включает backend/tool version.

## Tests и gates

- Capability matrix available/unavailable/broken driver; software parity;
  reproducible speed/quality benchmark; representative playback checks.
- Performance review обязателен, security review — для driver/tool boundary.

## DoD / artifacts / rollback

- Hardware backend включается только после probe и проходит thresholds;
  benchmark report/ADR записаны; software fallback всегда тестируется.
- Feature flags позволяют отключить любой backend без migration данных.

# Этап 13 — Optional локальная транскрипция

## Цель и model gate

Добавить локальную транскрипцию как optional adapter с provenance модели и
явными resource/privacy constraints. До кода утвердить feature SPEC, языки,
формат результата, модель/лицензию, размер загрузки и критерии качества.

## Зависимости и контекст

- Project/timeline model и optional-adapter boundary стабильны.
- Прочитать новую transcription SPEC, architecture, security/testing,
  dependency/model provenance rules; обновить `AI_PLAN`.

## Scope / non-goals

- Extraction аудио, локальный inference adapter, timestamped transcript,
  provenance/version и ручное включение.
- Не отправлять медиа в cloud, не загружать модель без согласия, не считать
  transcript достоверным без confidence/limitations.

## Области и контракты

- Разрешены: optional AI adapter, model manifest/cache, project attachments,
  GUI states, benchmarks/tests, SECURITY/SPEC/ADR.
- Transcript не становится командой/путём; cache связан с input/model identity.

## Tests и gates

- Golden short-audio corpus, timestamps/language/error/cancel, corrupt model,
  offline mode, memory/time benchmark и privacy review.
- Приложение полностью работает без модели/dependency.

## DoD / artifacts / rollback

- Model provenance, license, resource envelope и quality metrics видимы;
  optional feature достигает утверждённого threshold.
- Feature flag и удаляемый model cache обеспечивают безопасный rollback.

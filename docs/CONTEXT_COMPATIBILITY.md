# Совместимость проектного контекста

Аудит выполнен 2026-08-13 для миграции `video_chronicle_context_delta` и
актуализирован 2026-08-14 для `AI_PLAN` и stage prompts. Проект остаётся
минимальным overlay над общей AI Dev Team.

## Матрица решений

| Возможность | Существующий источник | Потребность Video Chronicle | Статус | Решение и канонический источник |
| --- | --- | --- | --- | --- |
| Архитектура и дизайн | `docs/ARCHITECTURE.md`, `docs/DESIGN.md` | Отделить работающий CLI от целевого GUI | `CONFLICT` | Текущие docs остаются фактическими; будущее поведение — в `specs/` и roadmap |
| План и статус | `docs/AI_PLAN.md`, `docs/AI_STATUS.md` | Один исполняемый срез и один фактический снимок вместо `PROGRESS.md` | `CONFLICT` | `AI_PLAN` — текущая работа, `AI_STATUS` — факт; `PROGRESS.md` не создавать |
| Системные требования | Feature SPEC и проектные инварианты | Отделить стабильный baseline от черновых целевых функций | `EXTEND` | `specs/system.spec.md` — системный контракт; `specs/features/` — поведение функций |
| Stage prompts | Общие `$plan-stage`, `$implement-stage` и roadmap проекта | Самостоятельно запускать этапы 01–17 без загрузки всего roadmap/context | `PROJECT_ONLY` | Тонкая библиотека `prompts/stages/`; один prompt загружается по команде `Начинай этап NN` |
| Обучающий журнал | `docs/LEARNING_LOG.md` | Сохранить причины и воспроизводимые шаги | `CONFLICT` | Продолжать `docs/LEARNING_LOG.md`; `LEARNING.md` и пустой `DEV_LOG.md` не переносить |
| QA / тестирование | Общие test/review-роли и SDLC-правила | Media/date/FFmpeg characterization и negative cases | `EXTEND` | Проектные сценарии хранятся в `docs/TESTING.md` |
| Безопасность | Общий security review | Недоверенные медиа, subprocess, пути, результат и кэш | `EXTEND` | Инварианты хранятся в `docs/SECURITY.md` |
| Review | Общий reviewer | Отдельной специализации нет | `INHERITED` | Локальный generic reviewer не создаётся |
| Git workflow | `~/codex-workspace/AGENTS.md` и прямые инструкции пользователя | Специального потока проекта нет | `INHERITED` | Локальный дубликат Git workflow не создаётся |
| Hooks | Активная конфигурация Codex / workspace | Подтверждённого локального пробела нет | `INHERITED` | Не устанавливать второй hook runner; локальный hook добавлять только под проверенный риск |
| MCP | Активная конфигурация Codex | Начальным этапам project MCP не нужен | `INHERITED` | Локальный MCP не создаётся; будущие tools должны вызывать application services, а не копировать бизнес-логику |
| Skills | Общая библиотека Codex и AI Dev Team | Проектного Skill пока не требуется | `INHERITED` | Не копировать глобальные Skills в репозиторий |
| Доменные agents | Универсальные роли не покрывают детали медиадат и FFmpeg полностью | Два узких профиля | `PROJECT_ONLY` | Хранить только `media_pipeline_specialist` и `metadata_forensics_specialist` в `.codex/agents/` |
| Конфигурация Codex | Глобальная активная конфигурация | Общих локальных настроек не требуется | `INHERITED` | Не создавать второй config; `.codex/agents/` содержит только проектные профили |

## Канонические источники

- правила работы — `AGENTS.md`;
- фактическая архитектура и интерфейс — `docs/ARCHITECTURE.md` и
  `docs/DESIGN.md`;
- текущий снимок — `docs/AI_STATUS.md`;
- текущий исполняемый срез — `docs/AI_PLAN.md`;
- требования и их статус — `specs/README.md` и связанные SPEC; черновики не
  считаются утверждёнными контрактами;
- порядок реализации — `docs/ROADMAP.md`;
- библиотека самостоятельных этапов — `prompts/README.md` и один выбранный
  `prompts/stages/NN-*.md`; prompt не является источником требований;
- решения и накопленное обучение — `docs/DECISIONS.md` и
  `docs/LEARNING_LOG.md`;
- проектные quality gates — `docs/TESTING.md` и `docs/SECURITY.md`.

Прежние staged prompts из delta-пакета были временными входными материалами и
не переносились. Текущая библиотека `prompts/stages/` создана заново из
канонических SPEC/ROADMAP как project-only routing layer. Параллельные журналы
и `PROGRESS.md` не создаются.

Новые hooks, MCP, Skills, generic agents и Codex config для маршрутизации не
добавлены: общие процессы наследуются, локальная delta ограничена документами.

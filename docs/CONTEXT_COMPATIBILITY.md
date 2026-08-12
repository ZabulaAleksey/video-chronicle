# Совместимость проектного контекста

Аудит выполнен 2026-08-13 для миграции
`video_chronicle_context_delta`. Проект остаётся минимальным overlay над общей
AI Dev Team.

## Матрица решений

| Возможность | Существующий источник | Потребность Video Chronicle | Статус | Решение и канонический источник |
| --- | --- | --- | --- | --- |
| Архитектура и дизайн | `docs/ARCHITECTURE.md`, `docs/DESIGN.md` | Отделить работающий CLI от целевого GUI | `CONFLICT` | Текущие docs остаются фактическими; будущее поведение — в `specs/` и roadmap |
| Статус и прогресс | `docs/AI_STATUS.md` | Сохранить этап и следующую задачу из `PROGRESS.md` | `CONFLICT` | Обновлять только `docs/AI_STATUS.md`; отдельный `PROGRESS.md` не создавать |
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
- требования и их статус — `specs/README.md` и связанные SPEC; черновики не
  считаются утверждёнными контрактами;
- порядок реализации — `docs/ROADMAP.md`;
- решения и накопленное обучение — `docs/DECISIONS.md` и
  `docs/LEARNING_LOG.md`;
- проектные quality gates — `docs/TESTING.md` и `docs/SECURITY.md`.

Delta-каталог, его manifest, staged prompts и параллельные журналы являются
временными входными материалами и после этой миграции не остаются каноническим
контекстом.

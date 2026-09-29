# Правила проекта Video Chronicle

Global DEV bridge: enabled

- Перед существенной задачей прочитай общие правила AI Dev Team из `~/.codex/AGENTS.md`, затем применяй этот файл как более локальное уточнение.
- Работай с Git из корня `${PROJECTS_ROOT}/video-chronicle`; родительский каталог не должен отслеживать этот project repository.
- Для DEV-managed media readiness используй global portable FFmpeg/FFprobe из `${DEV_ROOT}/tools/ffmpeg`; проверяй `doctor.ps1 -Scope Bootstrap -Check -Project video-chronicle`. Старые project-local `ffmpeg/` и `ffmpeg1/` не являются canonical tool locations; если они встретятся, сохраняй их как отдельные исторические assets до проверки происхождения.
- Для portable DEV используй `${DEV_ROOT}`, `${PROJECTS_ROOT}` и `${PROJECT_ROOT}`; Windows bootstrap-примеры могут указывать `E:\DEV`. `~` обозначает только действительно host-local пути.
- Перед изменениями проверяй `git status`; после изменений выполняй относящиеся к задаче проверки Python/FFmpeg и `git diff --check`.
- Проектные архитектурные документы и журнал решений находятся в `docs/`; обновляй только действительно затронутые документы.
- Считай `join_media.py` эталонной текущей реализацией: до извлечения логики или изменения CLI сначала зафиксируй поведение characterization/regression-тестами.
- Сохраняй инварианты медиаконвейера: исходники только читаются, внешние процессы получают argv-списки без `shell=True`, коллизия результата требует явного разрешения, а итог публикуется только после успешной обработки.
- Разделяй факты и планы: `docs/ARCHITECTURE.md`, `docs/DESIGN.md` и выбранный record `docs/STAGES.md` описывают текущее состояние, `specs/` — требования с явно указанным статусом, `docs/ROADMAP.md` — порядок будущих этапов. Черновую SPEC не считай утверждённым контрактом до смены её статуса.
- Проект является overlay над общей AI Dev Team. Не дублируй универсальные agents, hooks, MCP, Skills или Git workflow; локально допустимы только подтверждённые проектные расширения из `docs/CONTEXT_COMPATIBILITY.md`.

## Маршрутизация проектного контекста

- `specs/system.spec.md` содержит стабильные системные инварианты, а
  `specs/features/` — наблюдаемое поведение функций и его статус.
- `docs/STAGES.md` содержит ровно один текущий selector/record, plan, status, blockers, evidence и NEXT. `PROGRESS.md` не создавать.
- При команде `Начинай этап NN` сначала сверить selected record, DoD зависимостей и утверждённость SPEC. Исторический каталог в `docs/notes/` не является launcher; повреждённый подробный контракт уточнять по SPEC/ROADMAP до implementation.
- После acceptance обновлять только фактический selected record `docs/STAGES.md`; отдельный следующий stage не запускать автоматически. Если пользователь явно запустил master prompt/master execution, dependency-ready slices внутри уже разрешённого master track продолжаются по глобальным Continuous Master Execution stop conditions; граница stage внутри этого track сама по себе не останавливает выполнение. Новый stage/master вне разрешённого scope требует отдельного запуска.
- Не загружать весь исторический stage catalog, logs и все SPEC.


## Локальные правила тестирования

### Тестовый контракт
- После принятия тестов/fixtures/golden-сценариев они становятся контрактом и в этом цикле только запускаются для проверки.
- Переопределение или удаление разрешается только отдельным explicit-требованием.

### Unit / integration / component
- Unit + integration: `uv run --locked --extra dev --extra otio python -m pytest`
- Component/contract smoke: `uv run --locked --extra dev --extra otio python -m pytest tests/test_cli_characterization.py tests/test_gui_contract.py tests/test_gui_application.py`
- Канонический менеджер Python-зависимостей — uv, source of truth — `pyproject.toml` + `uv.lock`. Restore выполняй через `uv sync --locked --extra dev --extra otio`; общий uv cache разрешён, `.venv` disposable. Global FFmpeg payload находится вне project Git и не относится к dependency cleanup.

### E2E (критические)
1. Пайплайн `join_media` для набора тестовых файлов.
2. Генерация таймлайна/overlay и сохранение проекта в корректном формате.
3. Ненарушающее редактирование (non-destructive edit) и смена режима после ручного отката.

- Если FFmpeg/внешние бинарники недоступны в CI: `BLOCKED_BY_INFRASTRUCTURE_FFMPEG`.

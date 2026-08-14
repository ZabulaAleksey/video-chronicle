# Технические решения

## 2026-08-11 — отдельный рабочий репозиторий

- Решение: хранить проект в `~/codex-workspace/projects/video-chronicle` и публиковать его в отдельный GitHub-репозиторий.
- Причина: код проекта больше не должен смешиваться с глобальной рабочей областью `htdocs`.
- Последствие: история прежнего `Join_Media` сохранена, а старый remote доступен под именем `legacy`.

## 2026-08-11 — локальные FFmpeg-каталоги не публикуются

- Решение: сохранить `ffmpeg/` и `ffmpeg1/` внутри локального каталога проекта, но оставить их в `.gitignore`.
- Причина: `ffmpeg/` содержит вложенный upstream-репозиторий и крупную Git-историю, а `ffmpeg1/` — сторонние бинарные файлы почти у лимита GitHub.
- Альтернатива: Git LFS или включение исходников в основной репозиторий.
- Последствие: после обычного клонирования FFmpeg требуется установить или восстановить отдельно.

## 2026-08-11 — переносимые пользовательские пути

- Решение: использовать `~` и `Path.home()` вместо путей конкретного диска и пользователя.
- Причина: проект должен работать после переноса в домашний каталог другого пользователя.

## 2026-08-13 — проектный контекст является overlay

- Решение: сохранить текущие `docs/ARCHITECTURE.md`, `docs/DESIGN.md` и
  `docs/AI_STATUS.md` каноническими источниками фактического состояния, хранить
  будущие требования с явным статусом в `specs/`, а последовательность этапов
  — в `docs/ROADMAP.md`. Черновая SPEC не является утверждённым контрактом.
- Причина: исходный delta-пакет одновременно содержал факты о работающем CLI и
  целевую GUI/queue/cache-модель. Их прямое наложение выдавало бы планы за уже
  реализованную архитектуру.
- Альтернативы: заменить текущие документы файлами delta-пакета или хранить
  параллельные `PROGRESS.md`, `LEARNING.md` и `DEV_LOG.md`.
- Последствие: полезные требования, testing/security guidance и два узких
  доменных профиля сохранены; универсальные agents, hooks, MCP, Skills и Git
  workflow наследуются из общей AI Dev Team. Временный delta-пакет после
  миграции удаляется.

## 2026-08-13 — переходная GUI-оболочка на PySide6

- Решение: начать GUI отдельным PySide6-приложением, которое запускает
  совместимый legacy CLI `join_media.py` через асинхронный `QProcess` и
  передаёт argv отдельными строками. CLI-контракт сохранён, а финальная
  публикация усилена атомарной защитой от поздней коллизии.
- Причина: пользователь подтвердил начало GUI на выбранном стеке, тогда как
  безопасное извлечение медиаконвейера ещё требует characterization-тестов.
  Адаптер даёт рабочий интерфейс без второго медиаконвейера и без изменения
  CLI-контракта.
- Альтернативы: преждевременно извлечь application services; вызвать
  `join_media.main()` в GUI-процессе; блокировать GUI до этапа 06.
- Последствия: PySide6 становится принятой зависимостью GUI. Адаптер считается
  переходным и позже заменяется application-service boundary. Отмена пока не
  предоставляется: остановка только родительского процесса может оставить
  дочерний FFmpeg работающим на Windows.

## 2026-08-14 — AI_PLAN, AI_STATUS и самостоятельные stage prompts

- Решение: использовать `docs/AI_PLAN.md` как единственный текущий исполняемый
  срез, `docs/AI_STATUS.md` как единственный фактический снимок и не создавать
  `PROGRESS.md`. Этапы 01–17 хранятся по одному в `prompts/stages/` и
  загружаются только по команде `Начинай этап NN`.
- Причина: roadmap описывает долгосрочный порядок, но недостаточен для
  безопасного автономного запуска этапа; один большой prompt перегружал бы
  контекст и смешивал текущую работу с будущими идеями.
- Альтернативы: один общий stage prompt, `PROGRESS.md` рядом с `AI_STATUS`,
  отдельные project Skills или hook-based загрузка всей библиотеки.
- Последствия: prompts являются project-only routing layer, а не источником
  требований. Перед этапом Codex проверяет SPEC и DoD зависимости, переносит
  только выбранный срез в `AI_PLAN`, после acceptance обновляет `AI_STATUS` и
  следующий `AI_PLAN`. Новые hooks, Skills или generic agents не добавляются.

## 2026-08-14 — устанавливаемый пакет поверх совместимых entry points

- Решение: использовать `pyproject.toml`, `setuptools` и `src/video_chronicle`
  для устанавливаемого пакета; предоставить `video-chronicle` и
  `video-chronicle-gui`, сохранив root-level модули в wheel как временные
  compatibility modules.
- Причина: единая установка и стабильные entry points нужны до извлечения core,
  но этап 02 не должен менять уже охарактеризованный медиаконвейер.
- Альтернативы: сразу перенести всю медиалогику; оставить только запуск файлов
  из checkout; дублировать root-level код внутри пакета.
- Последствия: package wrappers импортируют legacy-модули лениво, поэтому CLI
  не загружает PySide6. Временные compatibility modules удаляются постепенно
  после этапа 03, сохраняя один production path.

## 2026-08-14 — единый package application path

- Решение: разделить охарактеризованный конвейер на Qt-free `domain`, typed
  `ports`, `application` orchestration и production `pipeline` adapters;
  `join_media.py` оставить тонким shim, который экспортирует канонические
  объекты и поддерживает прямой запуск из checkout.
- Причина: CLI, GUI subprocess и будущий desktop application должны использовать
  одну медиалогику, которую можно тестировать с подменяемыми границами.
- Альтернативы: сохранить всю логику в root-модуле; скопировать реализацию в
  package; сразу добавить metadata policy, queue и persistence.
- Последствия: прежние argv/messages/codes и атомарная публикация сохранены;
  дальнейшие metadata и project models добавляются независимо от Qt.

## 2026-08-14 — безопасные границы workspace, log и subprocess

- Решение: включить command/probe/workspace lifecycle в typed ports; до открытия
  error log отвергать его коллизии с output/source и symlink/reparse targets;
  не включать symlink media в план; запрещать управляющие символы в concat
  manifest; ограничить FFprobe 30 секундами и 8 MiB ответа.
- Причина: извлечение core сделало границы явно тестируемыми и выявило
  унаследованные пути усечения данных, чтения вне input и неограниченного
  буферизования ответа инструмента.
- Альтернативы: отложить всё до общего hardening; разрешать symlink после
  canonical containment; добавить timeout всему FFmpeg-конвейеру.
- Последствия: существующий `.log` остаётся перезаписываемым по контракту, но
  существующий файл другого типа не используется как log. Общий FFmpeg timeout
  не вводится до process-tree cancellation этапа 09.

## 2026-08-14 — обратно совместимая политика даты DATE-001

- Решение: выбирать FFprobe metadata по существующему порядку `DATE_TAGS`,
  затем filename fallback; missing item пропускать с диагностикой; сохранять
  все валидные кандидаты, raw values и конфликты; timezone offset сохранять
  отдельно без преобразования записанных wall-clock полей; равные даты
  разрешать через `path.name.casefold()`.
- Причина: команда последовательно реализовать этапы 01–05 требует закрыть
  decision gate этапа 04, а сохранение уже охарактеризованного CLI является
  обязательным условием.
- Альтернативы: предпочесть filename/EXIF; нормализовать всё в UTC; использовать
  filesystem mtime для missing; подключить ExifTool сейчас.
- Последствия: overlay и порядок существующих корректных наборов не меняются,
  но consumers получают объяснимый typed result. ExifTool, исправление даты и
  timezone conversion требуют отдельного решения.

## 2026-08-14 — MODEL-001 и in-memory reference repository

- Решение: определить immutable timeline/export/job/project contracts,
  JSON-compatible schema `video-chronicle-project` версии 1 и repository port;
  на этапе 05 реализовать только `InMemoryProjectRepository`.
- Причина: GUI, progress/cancel и resume требуют стабильных моделей раньше,
  чем становится понятна нагрузка, concurrent access и migration policy
  durable storage.
- Рассмотрены: только in-memory без serialization; JSON-файл как production
  storage; SQLite; Pydantic-модели.
- Последствия: domain API и тестовый round-trip стабилизируются без зависимости
  от Qt/FFmpeg/БД. Сериализуемый state не содержит tool commands. Выбор
  file/SQLite, транзакций и миграций остаётся отдельным решением этапа 10.

## 2026-08-14 — GUI по умолчанию использует application services

- Решение: строить `ExportPlan` и выполнять `execute_plan` в отдельных
  `QThread` workers; widgets только валидируют форму, показывают immutable plan
  и подтверждают overwrite. Whole-CLI `QProcess` доступен временно только через
  `VIDEO_CHRONICLE_GUI_ADAPTER=legacy-cli`.
- Причина: пользователь должен проверить состав и порядок до длительного
  экспорта, а CLI и GUI обязаны сходиться в одном application path без
  блокировки event loop.
- Альтернативы: продолжить парсить stderr whole CLI; перенести FFmpeg
  orchestration в widgets; удалить fallback сразу.
- Последствия: изменение формы инвалидирует preview, анализ/экспорт имеют явный
  worker lifecycle, а legacy fallback можно удалить после стабилизации. До
  этапа 09 окно по-прежнему нельзя закрыть во время активного worker, потому
  что process-tree cancellation ещё не реализована.

## 2026-08-14 — единый typed date overlay

- Решение: хранить immutable `OverlayConfig` в `ExportRequest` и использовать
  один объект для representative preview и каждого элемента export; разрешить
  только утверждённые format/position/range presets и явное отключение.
- Причина: preview обязан соответствовать финальному фильтру, а widgets не
  должны строить FFmpeg DSL или дублировать media policy.
- Альтернативы: отдельные GUI/CLI filter builders; произвольная строка
  `drawtext`; preview без FFmpeg; копирование шрифта в каждый clip workspace.
- Последствия: шрифт валидируется как локальный bounded regular file и
  перепроверяется у tool boundary; FFmpeg escaping сосредоточен в adapter;
  overlay-only change сохраняет inspection plan, но требует нового visual
  preview. Video playback, keyframes и arbitrary expressions остаются вне scope.

## 2026-08-14 — Join и Chronicle как policy одного плана

- Решение: хранить `ExportMode` в immutable `ExportRequest`; Join использует
  тот же date-sorted plan и media pipeline, но требует disabled overlay,
  Chronicle разрешает OVERLAY-001 on/off.
- Причина: пользователю нужен понятный экспорт без надписи и режим хроники,
  при этом legacy `join_media.py` уже сортирует по дате и добавляет overlay.
- Альтернативы: отдельный Join pipeline; filename-order/undated Join; сменить
  legacy default на Join; скрыто переключать mode внутри widgets.
- Последствия: CLI без `--mode` и `--mode chronicle` сохраняют прежний результат;
  `--mode join` — новый opt-in. GUI default Chronicle объясняет различие и
  инвалидирует plan при переключении, не изменяя сохранённый overlay checkbox.

## 2026-08-14 — EXEC-001: progress и platform-owned process tree

- Решение: использовать один Qt-free `ExecutionContext` и существующий
  `JobState`; считать export progress как accepted items + concat + publication;
  владеть каждым tool tree через Windows Job Object или POSIX process group.
- Причина: GUI должен оставаться отзывчивым и отменять весь FFmpeg tree, не
  публикуя partial result и не выдавая parent-only kill за успешную отмену.
- Альтернативы: `taskkill`, `psutil`/`pywin32`, kill только root, отдельный
  QProcess pipeline и парсинг FFmpeg ETA.
- Последствия: cancel принимается только до atomic publication commit; grace
  2 секунды и force/reap budget 3 секунды; source identity и workspace cleanup
  подтверждаются; unsafe/legacy backend не показывает кнопку отмены.

## 2026-08-14 — CACHE-001: opt-in cache нормализованных клипов

- Решение: сохранять только полностью нормализованный clip в private filesystem
  cache по canonical `clip-v1` identity; legacy/default export оставлять без
  persistent cache. Все мутации root сериализовать platform OS lock.
- Причина: безопасно возобновлять длинный export без признания partial final или
  workspace источником истины и без ослабления source/output invariants.
- Альтернативы: кэшировать весь workspace или final MP4; SQLite; path-based key;
  автоматический cache без opt-in; mtime-only staging cleanup.
- Последствия: manifest path-free и strict, hit повторно валидируется FFprobe,
  ошибки дают clean fallback, content/tool/edit identity инвалидирует запись,
  storage ограничен 10 GiB/30 днями и имеет explicit protected purge. Same-user
  attacker остаётся вне гарантии аутентичности локального desktop cache.

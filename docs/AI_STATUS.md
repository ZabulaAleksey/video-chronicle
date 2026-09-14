# Состояние проекта для AI

## Local wall time для generic FFprobe creation_time — 2026-09-14

- Исправление локально слито в `main`; push/release не выполнялись.
- DATE-001/v3 переводит общий `creation_time` с `Z`/`UTC` из UTC instant в
  системное локальное wall time на дату записи; именно оно используется в
  timeline и overlay.
- Explicit camera/QuickTime tags сохраняют записанные wall-clock поля без
  conversion. Metadata остаётся приоритетной, filename — диагностическим
  fallback; raw value и исходный timezone marker сохраняются в provenance.
- Детерминированный regression фиксирует `06:41:11Z` → `09:41:11` при
  injected `+03:00`; focused gate: `112 passed, 6 skipped`, полный локальный
  gate: `333 passed, 31 skipped`; independent review не обнаружил
  функциональных дефектов.

## Export reuse, delta-analysis и metadata wall time — 2026-09-14

- Валидные изменения output/tools/CRF/preset/mode/overlay и timeline edits
  пересобирают immutable plan без повторного FFprobe и не блокируют export при
  неизменном source set/fingerprints; visual preview остаётся независимым.
- `QFileSystemWatcher` отслеживает input folder и до 4096 accepted/skipped
  source files, а export boundary повторно проверяет source set/fingerprints.
  Missing fingerprint считается stale. После изменения источников repeat
  analysis переиспользует unchanged accepted/skipped items и инспектирует
  только new/changed; другая папка не использует reuse.
- Form signals выполняют pure settings rebind без filesystem scan и без
  перестроения timeline widgets. Delta reuse использует stat identity, а
  полный SHA-256 остаётся обязательным на FFmpeg boundary.
- Delta-analysis добавляет новые принятые sources в конец project layout как
  full-source entries, не меняя порядок и edits старых IDs, и обновляет
  inspection-owned metadata/duration известных items. Reconcile применяется
  атомарно: ошибка layout/trim не публикует частичный state, а фактическое
  изменение timeline очищает stale `current_plan`/`jobs` прежней revision.
- DATE-001/v3 предпочитает explicit camera/QuickTime wall-clock tags общему
  FFprobe-normalized UTC `creation_time`; generic `Z`/`UTC` переводится в
  системное локальное wall time, raw value, offset и conflict сохраняются.
- Acceptance gate: `12 passed`; focused subsystem gate:
  `126 passed, 7 skipped`; полный локальный gate:
  `350 passed, 12 skipped`.

## GUI export после смены date/time format — 2026-09-13

- Выбор timeline item больше не создаёт persistent `ProjectState` только ради
  вычисления доступности editor actions; state сохраняется после реальной edit
  mutation.
- Для media с неизвестной длительностью смена date/time format больше не
  оставляет GUI в невалидном editing snapshot. Текущий контракт выше дополнительно
  убрал повторный analysis и representative-preview gate для такого изменения.
- Focused GUI/editing gate: `48 passed, 1 skipped`; полный локальный gate:
  `341 passed, 12 skipped`.

## Stage 15 security hardening — 2026-09-13

- Добавлены release threat model/spec и отдельный audit report.
- Усилены symlink/reparse parent boundaries optional transcription/hardware;
  benchmark использует no-replace `-n`, production assertions заменены явными
  fail-closed checks.
- Full gate: `340 passed, 12 skipped`; lock/installed compatibility PASS;
  pip-audit — 0 known vulnerabilities; Bandit — 0 high, 0 medium, 7 low,
  оставшиеся low triaged как intentional boundaries/handlers.
- Статус `implemented_unverified`: независимый semantic reviewer не был
  доступен. По fail-closed dependency stage 16 и следующий stage 17 не начаты.

## Stage 14 hardware/quality gate — 2026-09-13

- Добавлены typed capability report и managed FFmpeg probes для `libx264`,
  `h264_nvenc`, `h264_qsv` и `h264_amf`; software остаётся default.
- Явный недоступный hardware backend детерминированно возвращает
  `software/libx264`; произвольные codec options не принимаются.
- Quality promotion сравнивает один source с software reference по SSIM и
  wall time, сохраняя tool/source identity и platform в JSON evidence.
- Контрактные тесты проходят, но реальный hardware/driver benchmark в этой
  среде не запускался. Ни один hardware backend не promoted; этап имеет статус
  `implemented_unverified`, а production export/cache остаются software path.

## Stage 13 local transcription — 2026-09-13

- Добавлены `TRANSCRIBE-001`, explicit `video-chronicle-transcribe` и local
  `whisper.cpp` adapter с model manifest/hash/license provenance.
- FFmpeg extraction и inference идут через managed list argv; source/model/tool
  проверяются до/после, JSON/resources bounded, temporary data очищается,
  sidecar публикуется атомарно.
- `5 passed`, CLI help и `uv lock --check` PASS. Реальный model WER/CER benchmark
  не выполнялся: model bytes не входят в project и не скачиваются молча, поэтому
  статус этапа — `implemented_unverified`, feature — optional/beta.

## Main integration и thumbnail branch — 2026-09-13

- `feature/configurable-datetime-overlay` слита локально в `main` merge-коммитом
  `7af7f3e`; push не выполнялся.
- В `feature/timeline-thumbnail-dnd` accepted media показываются 16:9
  карточками: overlay-free PNG создаются последовательно в worker через managed
  FFmpeg port, загружаются в `QPixmap` и удаляются; item failure сохраняет
  placeholder и tooltip.
- Internal drag одной или нескольких карточек направляется только через
  `ProjectState.move_items`; grid/table selection и order синхронизированы,
  partial-group move откатывает projection к canonical order.
- Focused gate: `47 passed, 1 skipped`; полный локальный gate:
  `329 passed, 12 skipped`. Offscreen render подтвердил светлую поверхность и
  отсутствие clipping у четырёх карточек на размере 1060×860.
- Исправлен post-analysis lifecycle: после thumbnails Chronicle автоматически
  строит representative preview; ошибка preview видима и допускает ручной retry,
  но не блокирует export уже проанализированных неизменных sources.

## Unified light GUI surface — 2026-09-13

- Timeline tab/viewport/content и журнал получили явные светлые surfaces,
  поэтому Windows dark palette больше не создаёт чёрный фон между controls.
- Normal/disabled buttons используют transparent border и визуально отделены
  от внешнего card boundary; keyboard focus сохраняет бирюзовую рамку.
- Render regression и полный локальный gate: `326 passed, 12 skipped`.

## Main/timeline navigation и reorder — 2026-09-13

- В `feature/configurable-datetime-overlay` первой открывается вкладка
  «Основное» с input/output/mode; plan/editor/representative preview находятся
  в отдельной вкладке «План хронологии».
- Selected accepted clips перемещаются «Выше»/«Ниже» через существующий
  immutable EDIT-001 layout. Selection сохраняется после move, source не
  изменяется; по текущему контракту preview становится stale, а export остаётся
  доступным.
- Move/group/ungroup/trim/preset/project-save actions disabled, когда текущий
  plan/selection/boundary не допускает meaningful transition.
- Focused navigation/editing gate: `53 passed, 1 skipped`; полный локальный
  gate с последующим visual fix: `326 passed, 12 skipped`.

## Analysis/export stop actions — 2026-09-13

- В `feature/configurable-datetime-overlay` GUI показывает раздельные кнопки
  «Остановить анализ» и «Остановить экспорт» только для активной cancellable
  операции; неподдерживаемые и legacy adapters их не рекламируют.
- Analysis использует cooperative token на границах items и managed FFprobe;
  после принятой остановки частичный plan не публикуется.
- Export сохраняет прежние process-tree, cleanup и atomic publication
  guarantees; terminal `cancelled` появляется только после завершения worker.
- Focused cancellation gate: `53 passed, 1 skipped`; полный локальный gate после
  `uv sync --locked --extra dev --extra otio`: `324 passed, 12 skipped`.

## Automatic encoding tools и GUI focus — 2026-09-13

- В `feature/configurable-datetime-overlay` GUI по умолчанию открывает
  «Основное», а технические параметры остаются во вкладке «Дополнительно».
- Существующие FFmpeg/FFprobe разрешаются в абсолютные env/PATH-пути; при
  отсутствии на Windows неблокирующий `QProcess` запускает pinned user-scope
  `Gyan.FFmpeg==9.0.1` через WinGet без shell и заполняет оба поля после success.
- Failure сохраняет ручной fallback; существующие инструменты не обновляются.
- UI и README поясняют, что opt-in cache повторно использует только проверенные
  normalized clips и не хранит исходники, project state или итоговый MP4.
- Focused GUI/tooling gate: `23 passed`; полный локальный gate с последующим
  последующими GUI-срезами: `326 passed, 12 skipped`. WinGet metadata подтверждает
  доступность `Gyan.FFmpeg 9.0.1`;
  live system installation тестами намеренно не выполнялась.

## Configurable date/time overlay — 2026-09-12

- В `feature/configurable-datetime-overlay` существующий OVERLAY-001 расширен
  semantic date/time/layout и practical typography без второго renderer path.
- `overlay.py` владеет единым formatter, custom token validation и file-backed
  system font resolution; неизвестное family использует проверенный fallback.
- Project schema v2 читает legacy exact overlay shape и новый nested overlay
  `version: 2`; family сохраняется переносимо, resolved path остаётся runtime-only.
- Representative preview и export используют один immutable config и один
  FFmpeg filter adapter; overlay-only edit по-прежнему требует обновить preview.
- Полный локальный gate: `313 passed, 12 skipped`; skips включают недоступный
  FFmpeg/FFprobe runtime, поэтому real multiline typography остаётся `NOT VERIFIED`.

## Governance migration — 2026-08-24

- 17 stage-файлов объединены в `prompts/STAGES.md`, старые workspace paths обновлены; overlay — PASS.
- Полный Python gate: 294 tests PASS, 6 SKIPPED по доступности внешних компонентов.
- Репозиторий находится в `${PROJECTS_ROOT}/video-chronicle` (локальный default: `~/video-chronicle`); dependency-manager migration интегрирована и опубликована в `main`.

## Dependency manager migration — 2026-08-24

- Канонический dependency contract: `pyproject.toml` + `uv.lock`; дублирующие `requirements.txt` и `requirements-dev.txt` удалены после clean restore.
- `uv sync --locked --extra dev --extra otio` использует общий uv cache и создаёт локальную disposable `.venv` с установленными CLI entrypoints.
- Полный gate после clean restore: 294 tests PASS, 6 SKIPPED; `video-chronicle --help` и `python -m video_chronicle --help` — PASS.
- Pytest использовал repo-local `--basetemp`, потому что общий `%TEMP%/pytest-of-aleks` имеет недоступный ACL; это инфраструктурное ограничение, не failure проекта.
- `ffmpeg/` и `ffmpeg1/` не изменялись и не удалялись: это отдельные upstream/runtime assets, а не Python dependency cache.

## Текущий этап

Этапы 00–12 завершены; этапы 13–14 реализованы с явно перечисленным внешним
verification debt. Default PySide6 GUI
строит plan и representative overlay preview через application services и
запускает тот же immutable plan вне UI thread. Whole-CLI `QProcess` сохранён
только как явный диагностический fallback. Runtime-очередь отсутствует; durable
project schema v2 и opt-in normalized-clip cache являются разными storage boundaries.

Текущий непрерывный track и точка продолжения хранятся в `docs/AI_PLAN.md`. Этапы 01–17
разделены на самостоятельные project prompts в `prompts/stages/`; они
загружаются по одному и не заменяют SPEC или текущий план.

## Текущая истина

- `src/video_chronicle/` содержит единственный production path:
  `domain → ports → application → pipeline adapters`;
- `src/video_chronicle/metadata.py` реализует утверждённую DATE-001 policy и
  отдаёт typed provenance/conflict/timezone result;
- `src/video_chronicle/overlay.py` реализует immutable OVERLAY-001/002 config,
  canonical date/time formatter, font inventory/identity/fallback и approved
  formats/layout/positions/typography ranges;
- `ExportMode` входит в immutable request/plan: Join требует disabled overlay,
  Chronicle сохраняет configurable OVERLAY-001;
- `src/video_chronicle/project.py`, `repository.py` и `serialization.py`
  реализуют MODEL-001: stable timeline IDs/order, immutable export snapshot,
  job transitions, strict schema v1 и in-memory repository;
- `join_media.py` — тонкий compatibility shim и direct-source entry point;
- доступны прямой CLI и application-service GUI без сервера и базы данных;
- `src/video_chronicle/gui_services.py` управляет `QThread` workers для
  `plan_export`/`execute_plan`, а `video_chronicle_gui.py` показывает preview,
  не копируя медиалогику;
- `src/video_chronicle/execution.py` задаёт typed lifecycle/progress и atomic
  publication commit point, а `process_control.py` подтверждённо завершает
  Windows Job Object или POSIX process group;
- canonical plan фиксирует source fingerprint до/после inspection и проверяет
  его перед каждым export tool boundary;
- `src/video_chronicle/cache.py` реализует CACHE-001: canonical clip identity,
  strict path-free manifest, validated restore, private platform storage и
  interprocess mutation lock;
- `project.py`/`serialization.py`/`repository.py` реализуют EDIT-001: immutable
  layout/trim/groups/presets, strict schema v2, v1 migration и durable atomic
  JSON repository с revision/backup/rollback;
- `application.apply_project_state` связывает сохранённые edits со свежим
  analysis и создаёт один `plan-v2` для preview, export и cache identity;
- `interchange.py` и `otio_adapter.py` реализуют adapter-neutral proposal и
  strict optional native OTIO subset без типов OTIO в schema v2/core;
- `scene.py` реализует default-off `ffmpeg-scdet-v1` suggestions через bounded
  managed process и source/tool fingerprints; `scene_benchmark.py` хранит
  воспроизводимый corpus/metrics contract;
- `docs/ARCHITECTURE.md` и `docs/DESIGN.md` описывают только реализованное;
- целевое развитие Timeline Builder описано отдельно в
  `specs/features/timeline-builder.spec.md` и не считается готовой функцией;
- проектный контекст дополняет общую AI Dev Team, не создавая второй набор
  универсальных agents, hooks, MCP или Git-процессов;
- `specs/system.spec.md` фиксирует системные инварианты, а feature SPEC —
  утверждённое и черновое пользовательское поведение.

## Реализовано

- сортировка видео и фотографий по дате;
- получение дат из метаданных и имён файлов;
- нормализация до 1600×900, 60 FPS, H.264/AAC;
- русская сокращённая метка дня недели;
- обработка файлов без аудиодорожки;
- пропуск повреждённых элементов с журналированием;
- переносимые пути от домашнего каталога пользователя;
- GUI-выбор входа/результата и параметров FFmpeg/FFprobe, CRF и preset;
- явное подтверждение перезаписи, объединённый журнал процесса и проверка
  результата после кода завершения;
- асинхронный preview accepted/skipped items с порядком, выбранной датой,
  provenance, timezone, conflicts и причинами пропуска;
- invalidation preview при изменении формы, loading/empty/error/populated/stale
  состояния и доступный layout 820×660 через прокрутку;
- вкладка настройки date overlay, representative 640×360 preview и единый
  config для preview и всех accepted items экспорта;
- overlay on/off и пути шрифтов с Unicode/пробелами/апострофами подтверждены
  реальным FFmpeg 9.0.1; literal `%03d` photo path не расширяется в sequence;
- GUI объясняет Chronicle/Join до анализа, сохраняет overlay preference при
  переключении и показывает mode в plan summary;
- CLI без `--mode` эквивалентен legacy Chronicle; новый `--mode join` проходит
  тот же mixed photo/video production path без `drawtext`;
- GUI показывает determinate progress и раздельно останавливает default
  analysis/export; partial plan и partial export не публикуются;
  cancel/timeout/output-limit завершают всё дерево процессов в bounded time;
- cancellation/publication race, strict private-workspace cleanup и terminal
  states `succeeded/failed/cancelled` имеют явный Qt-free контракт;
- завершённый characterization baseline дат, сортировки, FFmpeg argv, ошибок,
  partial success, коллизий и неизменности исходников;
- синтетический mixed photo/video smoke на FFmpeg/FFprobe 9.0.1;
- устанавливаемый пакет версии 0.2.0 с console/GUI entry points и группой
  зависимостей `dev`;
- атомарная no-replace финализация закрывает коллизию, возникшую уже во время
  длительного рендера;
- cache выключен по умолчанию; opt-in reuse, custom private root, hit/miss,
  bounded prune и protected purge доступны в CLI и GUI;
- clean и resumed mixed photo/video exports дают byte-identical output, а
  interruption/corruption/identity changes используют безопасный clean fallback;
- GUI поддерживает stable reorder, integer-µs trim через ms controls,
  contiguous groups, versioned presets и async Open/Save project;
- video/audio trim и representative preview используют один resolved snapshot;
  real FFmpeg test подтверждает длительность с допуском один target frame;
- optional extra `otio` фиксирует `opentimelineio==0.18.1`; без flag/dependency
  основной package/import graph и schema v2 не меняются;
- OTIO golden покрывает 0/1/4096 clips и rational timebases; импорт всегда
  возвращает proposal, неизвестные/неоднозначные local refs не auto-bind;
- synthetic scene benchmark на FFmpeg 9.0.1 дал P/R/F1 `1.0/1.0/1.0`,
  `0` FP/min, p95 `0 µs`, deterministic `3/3` и wall/media `0.080509`;
- 326 тестов проходят, включая configurable overlay, navigation/reorder, stop actions,
  interchange/parser/security/scene benchmark; 12 platform/runtime checks
  пропущены в текущем worktree, включая недоступные FFmpeg/FFprobe.

## Локальные зависимости

- `ffmpeg/` — чистый upstream-репозиторий исходников FFmpeg;
- `ffmpeg1/` — Windows runtime с FFmpeg и FFprobe;
- оба FFmpeg-каталога намеренно исключены из основного Git;
- `.venv/` — игнорируемое локальное окружение Python с PySide6 и pytest.

## Известные ограничения

- полный прогон на пользовательской медиатеке после переноса не выполнялся;
- после нового клонирования FFmpeg необходимо установить отдельно;
- версии FFmpeg/FFprobe старше 9.0.1 могут работать, но не входят в
  подтверждённый baseline;
- drag-and-drop, undo/redo, playback, multi-track, transitions и nested groups
  не входят в EDIT-001;
- same-user process остаётся вне гарантии аутентичности cache/project files;
- SQLite, ExifTool и Pydantic остаются неутверждёнными кандидатами;
- OTIO/scdet приняты только как default-off removable adapters, не как часть
  project schema или автоматическое редактирование;
- у проекта нет утверждённой `LICENSE`; release и FFmpeg redistribution
  заблокированы до отдельных этапов hardening/packaging;
- PySide6 принят только для GUI.

## Следующая задача

Этапы 13–15 реализованы до доступного evidence. Следующий dependency-ready шаг
— независимый semantic security review этапа 15. Этап 16 нельзя начинать до
review без high findings; этап 17 дополнительно требует stable RC и явно
утверждённых experiment hypothesis/dataset/metrics/resource budget. Точная
точка продолжения зафиксирована в `docs/AI_PLAN.md`.

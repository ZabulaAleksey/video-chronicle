# Состояние проекта для AI

## Текущий этап

Этапы 00–12 завершены; целевой MVP, non-destructive editor и optional
timeline-interchange/scene experiment приняты. Дальнейшая реализация
приостановлена по указанию пользователя; этап 13 не начат. Default PySide6 GUI
строит plan и representative overlay preview через application services и
запускает тот же immutable plan вне UI thread. Whole-CLI `QProcess` сохранён
только как явный диагностический fallback. Runtime-очередь отсутствует; durable
project schema v2 и opt-in normalized-clip cache являются разными storage boundaries.

Принятый срез этапа 12 и точка продолжения хранятся в `docs/AI_PLAN.md`. Этапы 01–17
разделены на самостоятельные project prompts в `prompts/stages/`; они
загружаются по одному и не заменяют SPEC или текущий план.

## Текущая истина

- `src/video_chronicle/` содержит единственный production path:
  `domain → ports → application → pipeline adapters`;
- `src/video_chronicle/metadata.py` реализует утверждённую DATE-001 policy и
  отдаёт typed provenance/conflict/timezone result;
- `src/video_chronicle/overlay.py` реализует immutable OVERLAY-001 config,
  font identity policy и approved formats/positions/ranges;
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
- GUI показывает determinate progress и безопасно отменяет default export;
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
- 298 тестов проходят, включая interchange/parser/security/scene benchmark;
  два
  Windows symlink/reparse теста пропущены из-за WinError 1314.

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

Работа приостановлена после принятия этапа 12. Следующим по roadmap остаётся
этап 13 — optional local transcription, но он не начат и не является текущим
срезом. Возобновлять его только по новой команде пользователя; точка
продолжения зафиксирована в `docs/AI_PLAN.md`.

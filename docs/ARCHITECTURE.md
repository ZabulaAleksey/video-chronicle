# Архитектура

## Назначение

`video-chronicle` — устанавливаемое локальное desktop-приложение на Python для
сортировки, нормализации и объединения фотографий и видео в единый MP4-файл.
Эталонный медиаконвейер находится внутри устанавливаемого пакета; PySide6 GUI
вызывает те же application services, что и package CLI, через worker boundary.

## Компоненты

- `pyproject.toml` — metadata пакета, runtime/dev зависимости и console/GUI
  entry points.
- `src/video_chronicle/domain.py` — Qt-free модели принятого медиа и запроса
  экспорта, включая выбранное date decision и typed `ExportMode`.
- `src/video_chronicle/metadata.py` — Qt-free DATE-001 engine: metadata и
  filename candidates, provenance, raw values, timezone и conflicts.
- `src/video_chronicle/overlay.py` — immutable `OverlayConfig`, проверка
  диапазонов, цветов и identity локального шрифта.
- `src/video_chronicle/project.py` — immutable MODEL-001 timeline и EDIT-001
  layout: reorder, integer-µs trim, contiguous groups, versioned presets,
  editing export snapshot и job/project lifecycle.
- `src/video_chronicle/repository.py` — revision-aware `ProjectRepository`,
  process-local reference adapter и durable `JsonProjectRepository` с lock,
  atomic save, backup и monotonic rollback.
- `src/video_chronicle/serialization.py` — строгий JSON-compatible schema v2,
  pure v1 migration и exact-field validation без выполнения команд.
- `src/video_chronicle/ports.py` — типизированные границы inspection,
  normalization, concatenation, publication и source discovery.
- `src/video_chronicle/application.py` — orchestration одного экспорта и
  partial-success policy, structured progress и checkpoints отмены.
- `src/video_chronicle/execution.py` — Qt-free lifecycle одного экспорта,
  `ProgressEvent`, cancellation token и atomic publication commit point.
- `src/video_chronicle/process_control.py` — platform-owned subprocess tree:
  Windows Job Object либо POSIX process group с bounded terminate/reap.
- `src/video_chronicle/cache.py` — opt-in immutable normalized-clip cache:
  canonical `clip-v1` identity, строгий path-free manifest, bounded validation,
  private platform root и межпроцессная сериализация мутаций.
- `src/video_chronicle/interchange.py` — Qt/OTIO-free DTO, port и явное
  применение immutable import proposal к новой revision проекта.
- `src/video_chronicle/otio_adapter.py` — optional native `.otio` adapter:
  bounded strict JSON/subset validation, exact rational-time conversion и
  direct OTIO core codec без ambient adapter/plugin/media-linker dispatch.
- `src/video_chronicle/scene.py` — optional `ffmpeg-scdet-v1` suggestions с
  source-relative timestamps, managed process tree и source/tool identity.
- `src/video_chronicle/scene_benchmark.py` — deterministic synthetic corpus,
  maximum-cardinality matching и воспроизводимый quality/performance report.
- `src/video_chronicle/pipeline.py` — production adapters FFprobe/FFmpeg и
  атомарной публикации.
- `src/video_chronicle/cli.py` — парсинг/валидация CLI и mapping в application
  request.
- `src/video_chronicle/gui_services.py` — PySide6 `QThread`/worker boundary для
  `plan_export`, representative-frame preview и `execute_plan`, без widgets и
  собственного медиаконвейера.
- `join_media.py` — тонкий legacy compatibility shim и direct-source entry point.
- `gui_contract.py` — чистая конфигурация одного GUI-запуска и построение argv.
- `video_chronicle_gui.py` — PySide6 Widgets UI, preview presenter и временный
  диагностический `QProcess` fallback `VIDEO_CHRONICLE_GUI_ADAPTER=legacy-cli`.
- FFprobe — чтение потоков, метаданных и дат создания.
- FFmpeg — преобразование каждого источника и объединение подготовленных клипов.
- `~/Input` — входной каталог по умолчанию; исходные файлы только читаются.
- временный `video_join_work_*` рядом с результатом — нормализованные клипы и concat-список.

## Поток данных

1. Пользователь запускает `video-chronicle`, `python -m video_chronicle`,
   совместимый `join_media.py` либо заполняет GUI-форму.
2. GUI валидирует форму и вне UI thread создаёт `ExportRequest`, разрешает
   инструменты и вызывает `plan_export` с явным набором `PipelinePorts`.
   Chronicle разрешает OVERLAY-001 on/off; Join канонически отключает overlay.
3. Immutable `ExportPlan` возвращается в GUI: accepted/skipped элементы,
   date provenance и порядок показываются до экспорта. Изменение формы
   инвалидирует plan; overwrite подтверждается непосредственно перед запуском.
4. Изменение только `OverlayConfig` сохраняет уже проанализированные items, но
   инвалидирует визуальный preview. Первый принятый item рендерится через тот же
   filter adapter в 640×360 PNG до разблокировки экспорта.
5. При открытом/созданном project GUI связывает текущий analysis с immutable
   layout: применяет reorder, resolved trim/groups и active preset, создавая
   `plan-v2`. Любой edit инвалидирует representative preview и export.
6. GUI передаёт тот же plan в `execute_plan` через отдельный worker; execution
   context транслирует typed progress и принимает отмену только до publication
   commit. CLI создаёт тот же `ExportRequest` и вызывает тот же application path.
7. Source adapter находит поддерживаемые медиафайлы во входном каталоге.
8. FFprobe adapter возвращает метаданные, kind и effective duration `0:v:0`.
9. DATE-001 engine собирает кандидатов, выбирает дату из метаданных или имени
   файла и сохраняет provenance/conflicts без timezone conversion.
10. Перед каждым tool boundary source fingerprint сравнивается со снимком,
   полученным до и после inspection. FFmpeg adapter приводит каждый элемент к
   1600×900, 60 FPS, H.264 и AAC и
   применяет единый typed date overlay ко всем элементам либо полностью
   исключает `drawtext`, если подпись выключена.
11. Trimmed video использует `trim/atrim + setpts/asetpts`, фото — resolved
   duration; preview и export применяют один resolved clip snapshot.
12. При включённом cache каждый accepted item получает content/tool/settings
   identity. Подтверждённый hit копируется в active workspace; miss проходит
   обычную normalization и атомарно сохраняется. Повреждение даёт warning и
   clean fallback, но никогда не подменяет plan или output path.
13. Подготовленные клипы объединяются без повторного кодирования.
14. Каждый subprocess принадлежит Windows Job Object или POSIX process group;
   cancel, timeout и output-limit завершают и подтверждают остановку всего дерева.
15. Без разрешения overwrite временный результат публикуется атомарным
   no-replace rename на Windows или create-if-absent hard link на POSIX;
   подтверждённая замена использует `os.replace`. Рабочий каталог удаляется,
   если не указан `--keep-work`.
16. После успешной публикации cache pruning применяет лимиты 10 GiB/30 дней;
   explicit purge работает только внутри подтверждённого private cache root.
17. GUI получает log-сообщения через Qt signal и принимает успех только при
   результате 0 и подтверждённой новой identity итогового файла.
18. Только при явном experimental flag application лениво создаёт optional
   interchange/scene adapter. OTIO import формирует proposal и не меняет
   project до explicit apply; scene detection формирует suggestions и никогда
   не создаёт edit автоматически.

## Границы

Проект использует `src` layout и один production path через package application
service. Root-level CLI только экспортирует канонические функции для обратной
совместимости. MODEL-001 предоставляет состояния будущих заданий, но проект не
содержит сервера, базы данных или runtime-очереди. Durable project storage —
строгие локальные JSON documents schema v2; normalized cache остаётся отдельной
отключаемой оптимизацией и не является источником истины проекта. GUI не
дублирует сортировку, анализ дат, FFmpeg-команды или финализацию.
Join и Chronicle являются policy-данными одного `ExportRequest`: inspection,
normalization, concat и publication adapters у них общие.
Legacy whole-CLI `QProcess` остаётся только явным adapter fallback и может быть
удалён без изменения core. Safe cancel доступен только default application
backend либо явно объявленному совместимому backend; feature flag может скрыть
его без изменения pipeline. Каталоги `ffmpeg/` и `ffmpeg1/` являются локальными
сторонними зависимостями и не входят в историю основного репозитория.
OTIO extra и scene adapter выключены по умолчанию, не входят в schema v2/cache
authority и удаляются без migration. Любой imported proposal или scene
suggestion остаётся недоверенным transient data до явной проверки/применения.

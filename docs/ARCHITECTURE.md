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
  экспорта, включая выбранное date decision.
- `src/video_chronicle/metadata.py` — Qt-free DATE-001 engine: metadata и
  filename candidates, provenance, raw values, timezone и conflicts.
- `src/video_chronicle/overlay.py` — immutable `OverlayConfig`, проверка
  диапазонов, цветов и identity локального шрифта.
- `src/video_chronicle/project.py` — immutable MODEL-001 timeline, export
  snapshot, job lifecycle и project state.
- `src/video_chronicle/repository.py` — `ProjectRepository` port и process-local
  `InMemoryProjectRepository` reference adapter.
- `src/video_chronicle/serialization.py` — строгий JSON-compatible schema v1
  mapping без файлового I/O и выполнения команд.
- `src/video_chronicle/ports.py` — типизированные границы inspection,
  normalization, concatenation, publication и source discovery.
- `src/video_chronicle/application.py` — orchestration одного экспорта и
  partial-success policy.
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
3. Immutable `ExportPlan` возвращается в GUI: accepted/skipped элементы,
   date provenance и порядок показываются до экспорта. Изменение формы
   инвалидирует plan; overwrite подтверждается непосредственно перед запуском.
4. Изменение только `OverlayConfig` сохраняет уже проанализированные items, но
   инвалидирует визуальный preview. Первый принятый item рендерится через тот же
   filter adapter в 640×360 PNG до разблокировки экспорта.
5. GUI передаёт тот же plan в `execute_plan` через отдельный worker; CLI создаёт
   тот же `ExportRequest` и вызывает тот же application path напрямую.
6. Source adapter находит поддерживаемые медиафайлы во входном каталоге.
7. FFprobe adapter возвращает метаданные и сведения о потоках.
8. DATE-001 engine собирает кандидатов, выбирает дату из метаданных или имени
   файла и сохраняет provenance/conflicts без timezone conversion.
9. FFmpeg adapter приводит каждый элемент к 1600×900, 60 FPS, H.264 и AAC и
   применяет единый typed date overlay ко всем элементам либо полностью
   исключает `drawtext`, если подпись выключена.
10. Подготовленные клипы объединяются без повторного кодирования.
11. Без разрешения overwrite временный результат публикуется атомарным
   no-replace rename на Windows или create-if-absent hard link на POSIX;
   подтверждённая замена использует `os.replace`. Рабочий каталог удаляется,
   если не указан `--keep-work`.
12. GUI получает log-сообщения через Qt signal и принимает успех только при
   результате 0 и подтверждённой новой identity итогового файла.

## Границы

Проект использует `src` layout и один production path через package application
service. Root-level CLI только экспортирует канонические функции для обратной
совместимости. MODEL-001 предоставляет состояния будущих заданий, но проект не
содержит сервера, базы данных, durable storage или runtime-очереди. GUI не
дублирует сортировку, анализ дат, FFmpeg-команды или финализацию.
Legacy whole-CLI `QProcess` остаётся только явным adapter fallback и может быть
удалён без изменения core. Безопасная отмена пока отсутствует: окно нельзя
закрыть во время активного worker. Каталоги `ffmpeg/` и `ffmpeg1/` являются локальными сторонними
зависимостями и не входят в историю основного репозитория.

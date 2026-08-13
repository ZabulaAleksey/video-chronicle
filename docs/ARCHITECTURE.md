# Архитектура

## Назначение

`video-chronicle` — устанавливаемое локальное desktop-приложение на Python для
сортировки, нормализации и объединения фотографий и видео в единый MP4-файл.
Эталонный медиаконвейер находится внутри устанавливаемого пакета; PySide6 GUI
является переходной subprocess-оболочкой над единым package CLI.

## Компоненты

- `pyproject.toml` — metadata пакета, runtime/dev зависимости и console/GUI
  entry points.
- `src/video_chronicle/domain.py` — Qt-free модели принятого медиа и запроса
  экспорта.
- `src/video_chronicle/ports.py` — типизированные границы inspection,
  normalization, concatenation, publication и source discovery.
- `src/video_chronicle/application.py` — orchestration одного экспорта и
  partial-success policy.
- `src/video_chronicle/pipeline.py` — production adapters FFprobe/FFmpeg и
  атомарной публикации.
- `src/video_chronicle/cli.py` — парсинг/валидация CLI и mapping в application
  request.
- `join_media.py` — тонкий legacy compatibility shim и direct-source entry point.
- `gui_contract.py` — чистая конфигурация одного GUI-запуска и построение argv.
- `video_chronicle_gui.py` — PySide6 Widgets UI и асинхронный `QProcess`-адаптер.
- FFprobe — чтение потоков, метаданных и дат создания.
- FFmpeg — преобразование каждого источника и объединение подготовленных клипов.
- `~/Input` — входной каталог по умолчанию; исходные файлы только читаются.
- временный `video_join_work_*` рядом с результатом — нормализованные клипы и concat-список.

## Поток данных

1. Пользователь запускает `video-chronicle`, `python -m video_chronicle`,
   совместимый `join_media.py` либо заполняет GUI-форму.
2. GUI валидирует только форму, подтверждает коллизию результата и передаёт
   Python executable и argv раздельно в неблокирующий `QProcess`. Для
   диагностического канала дочернего Python явно задаётся UTF-8, а GUI
   декодирует поток с сохранением неполных многобайтовых последовательностей.
3. CLI создаёт `ExportRequest`, а application service получает явный набор
   `PipelinePorts`.
4. Source adapter находит поддерживаемые медиафайлы во входном каталоге.
5. FFprobe adapter возвращает метаданные и сведения о потоках.
6. Дата выбирается из метаданных или имени файла.
7. FFmpeg adapter приводит каждый элемент к 1600×900, 60 FPS, H.264 и AAC и
   добавляет дату.
8. Подготовленные клипы объединяются без повторного кодирования.
9. Без разрешения overwrite временный результат публикуется атомарным
   no-replace rename на Windows или create-if-absent hard link на POSIX;
   подтверждённая замена использует `os.replace`. Рабочий каталог удаляется,
   если не указан `--keep-work`.
10. GUI показывает объединённый вывод процесса и принимает успех только при
   коде 0 и наличии итогового файла.

## Границы

Проект использует `src` layout и один production path через package application
service. Root-level CLI только экспортирует канонические функции для обратной
совместимости. Проект не содержит сервера, базы данных или очереди заданий. GUI
не дублирует сортировку, анализ дат, FFmpeg-команды или финализацию.
Безопасная отмена пока отсутствует: окно нельзя закрыть во время активного
процесса. Каталоги `ffmpeg/` и `ffmpeg1/` являются локальными сторонними
зависимостями и не входят в историю основного репозитория.

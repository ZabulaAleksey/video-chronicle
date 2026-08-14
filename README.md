# Video Chronicle

`video-chronicle` нормализует видео и фотографии, сортирует их по выбранной дате
и собирает в один MP4-файл. Chronicle может добавлять на кадр дату, а Join
использует тот же план без подписи.

PySide6 GUI анализирует и показывает immutable plan, representative overlay
preview и выполняет те же application services, что CLI, вне UI thread.

Рабочий репозиторий располагается в `~/codex-workspace/projects/video-chronicle`.

## Установка

```powershell
cd ~/codex-workspace/projects/video-chronicle
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

После установки доступны единые entry points:

```powershell
.venv/Scripts/video-chronicle --help
.venv/Scripts/video-chronicle-gui
.venv/Scripts/python -m video_chronicle --help
```

Совместимые `join_media.py` и `video_chronicle_gui.py` пока сохраняются.

## Что делает проект

- Сканирует папку с медиафайлами (`--input-dir` или `~/Input` по умолчанию).
- Извлекает дату из метаданных или имени файла.
- Приводит все материалы к единому формату: 1600x900, 60 FPS, H.264, аудиокодек AAC.
- В Chronicle добавляет настраиваемый текст с датой; Join отключает подпись.
- Объединяет нормализованные клипы в один итоговый MP4.

## Важные параметры в коде

В `src/video_chronicle/pipeline.py` можно изменить следующие настройки внешнего вида текста:

- `fontsize` — размер шрифта.
- `fontcolor` — цвет текста.
- `bordercolor` и `borderw` — цвет и ширина контура.
- `box` — режим подложки (`0` для прозрачной, `1` для непрозрачной).
- `boxcolor` — цвет подложки, если она используется.
- `x` и `y` — положение текста на экране.
- `find_default_font()` — путь к используемому шрифту, сейчас приоритет отдан `Comic Sans`.

## Параметры запуска

Основные параметры задаются через аргументы командной строки:

- `--input-dir` — папка с исходными файлами.
- `--output` — путь выходного MP4.
- `--ffmpeg` — путь к исполняемому файлу `ffmpeg.exe`.
- `--ffprobe` — путь к исполняемому файлу `ffprobe.exe`.
- `--overwrite` — перезаписать существующий выходной файл.
- `--crf` — качество H.264 (меньше = лучше).
- `--preset` — пресет кодирования libx264.
- `--mode chronicle|join` — Chronicle с legacy overlay по умолчанию либо Join
  без подписи; отсутствие аргумента сохраняет прежний Chronicle-результат.
- `--cache` — явно включить reuse проверенных нормализованных клипов.
- `--cache-dir` — выбрать приватную локальную папку cache; без `--cache` допустим
  только вместе с `--purge-cache`.
- `--purge-cache` — безопасно очистить подтверждённый cache root и завершить работу.

## Работа с папками

- Входная папка: по умолчанию `~/Input`.
- Итоговый файл создаётся рядом с входной папкой, если не указан `--output`.
- Логи ошибок сохраняются рядом с выходным файлом в `errors.log`.
- Для тестовой обработки одного файла можно создать отдельную подпапку в `~/Input`, например `~/Input/preview_one`.

Локально рядом со скриптом могут находиться два вспомогательных каталога:

- `ffmpeg/` — исходный репозиторий FFmpeg со своей историей Git;
- `ffmpeg1/` — готовая Windows-сборка с `bin/ffmpeg.exe` и `bin/ffprobe.exe`.

Оба каталога перемещены вместе с проектом, но исключены из основного Git-репозитория. Это предотвращает конфликт вложенных историй Git и публикацию крупных сторонних бинарных файлов. После нового клонирования репозитория установите FFmpeg в `PATH` либо отдельно восстановите локальную сборку в `ffmpeg1/`.

## Пример запуска

```powershell
python ~/codex-workspace/projects/video-chronicle/join_media.py --input-dir ~/Input --output ~/Input/preview.mp4 --ffmpeg ~/codex-workspace/projects/video-chronicle/ffmpeg1/bin/ffmpeg.exe --ffprobe ~/codex-workspace/projects/video-chronicle/ffmpeg1/bin/ffprobe.exe --overwrite
```

## Запуск GUI

```powershell
cd ~/codex-workspace/projects/video-chronicle
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/video-chronicle-gui
```

В окне можно выбрать Chronicle/Join, входную папку, итоговый MP4,
FFmpeg/FFprobe, CRF, preset и параметры подписи Chronicle. Перед экспортом GUI
показывает состав/order плана и representative кадр.
FFmpeg и FFprobe запускаются с правами пользователя, поэтому указывайте только
доверенные сборки. По умолчанию используются команды из `PATH`.
Существующий результат требует отдельного подтверждения. Во время обработки
окно показывает структурированный прогресс и остаётся отзывчивым. Default
application backend позволяет безопасно отменить активный экспорт: FFmpeg и
его дочерние процессы завершаются как одно дерево, partial output не
публикуется. Закрытие окна остаётся заблокированным до terminal state.

Cache выключен по умолчанию. При включении GUI показывает `hit`/`miss` для
клипов, позволяет выбрать private local cache и отдельно подтверждает purge.
Cache не содержит project state или partial final: повреждённая запись просто
отклоняется, после чего выполняется обычная clean normalization.

Если FFmpeg уже добавлен в `PATH`, параметры `--ffmpeg` и `--ffprobe` можно не указывать.

## Что ещё можно поменять

- Добавить поддержку других форматов даты в `datetime_from_filename()`.
- Изменить размеры итогового кадра в `make_video_filter()`.
- Добавить разные стили текста или дополнительные метки.

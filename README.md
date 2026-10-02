# Video Chronicle

`video-chronicle` нормализует видео и фотографии, сортирует их по выбранной дате
и собирает в один MP4-файл. В GUI режим «Хроника» позволяет настроить подпись,
а «Объединение — без даты и времени» использует тот же план без неё.

PySide6 GUI анализирует и показывает immutable plan, representative overlay
preview и выполняет те же application services, что CLI, вне UI thread.

Рабочий репозиторий располагается в `${PROJECTS_ROOT}/video-chronicle`.

## Установка

```powershell
cd "$env:PROJECTS_ROOT\video-chronicle"
uv sync --locked --extra dev
```

### FFmpeg в Portable DEV

Каноническая пара FFmpeg/FFprobe находится в `${DEV_ROOT}/tools/ffmpeg/bin`
(`E:\DEV\tools\ffmpeg\bin` на Windows). Provenance, дата получения, SHA-256 и
лицензия записаны рядом с payload в `metadata.json`; approved version и hashes
принадлежат global `bootstrap/versions.yaml`. Проверка перед media work:

```powershell
pwsh -NoProfile -File E:\DEV\bootstrap\doctor.ps1 -Scope Bootstrap -Check -Project video-chronicle
```

GUI сначала разрешает явно заданные пути, затем пару из `${DEV_TOOLS}/ffmpeg/bin`,
потом инструменты из `PATH`. Для самостоятельной установки проекта вне Portable
DEV сохраняется совместимый fallback: если пара неполна, GUI
асинхронно устанавливает `Gyan.FFmpeg==9.0.1` через WinGet. Этот host package не
заменяет проверку canonical portable payload в DEV-managed doctor. Scene adapter
использует именно FFmpeg `9.0.1`; другие версии требуют отдельного compatibility
review. Бинарники не входят в Git проекта и не являются частью Windows release.

Optional native OTIO interchange устанавливается отдельно и не нужен обычному
CLI/GUI экспорту:

```powershell
uv sync --locked --extra dev --extra otio
$env:VIDEO_CHRONICLE_EXPERIMENTAL_OTIO = "1"
```

Scene suggestions используют уже выбранный FFmpeg и также выключены по
умолчанию:

```powershell
$env:VIDEO_CHRONICLE_EXPERIMENTAL_SCENE = "ffmpeg-scdet"
```

Обе функции доступны через application API как экспериментальные adapters.
OTIO import возвращает proposal, а `scdet` — предложения cuts; ни один из них
не изменяет project автоматически и пока не добавляет отдельные GUI actions.

После установки доступны единые entry points:

```powershell
uv run --locked --extra dev --extra otio video-chronicle --help
uv run --locked --extra dev --extra otio video-chronicle-gui
uv run --locked --extra dev --extra otio python -m video_chronicle --help
```

Совместимые `join_media.py` и `video_chronicle_gui.py` пока сохраняются.

## Что делает проект

- Сканирует папку с медиафайлами (`--input-dir` или `~/Input` по умолчанию).
- Извлекает дату из метаданных или имени файла.
- Приводит все материалы к единому формату: 1600x900, 60 FPS, H.264, аудиокодек AAC.
- В режиме «Хроника» добавляет настраиваемые дату/время; режим
  «Объединение — без даты и времени» гарантированно отключает подпись.
- Объединяет нормализованные клипы в один итоговый MP4.

## Настройка даты, времени и текста

Во вкладке «Дата и время» можно независимо включить дату и время, выбрать
готовый пример формата, 12/24-hour time, строку/разделитель/две строки,
position и margins. Typography включает системное семейство или exact font
file, size, bold/italic, цвет/opacity, outline и shadow. Настройки входят в
versioned project preset; старый project без новых полей открывается с прежним
legacy видом. Неизвестное system family использует проверенный fallback.

Custom date format принимает только tokens `YYYY`, `YY`, `MMMM`, `MMM`, `MM`,
`DD`, `ddd` и безопасные разделители; некорректный шаблон отклоняется до preview.

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

Исторические project-local `ffmpeg/` и `ffmpeg1/` не являются действующим
источником инструментов. Их отсутствие в clean clone ожидаемо; восстанавливать
неизвестные локальные assets для обычного запуска не требуется.

## Что значит «использовать кэш»

При включённом кэше Video Chronicle сохраняет уже нормализованные клипы и при
повторном экспорте не кодирует их заново, если исходный файл, FFmpeg и настройки
не изменились. `hit` означает безопасное повторное использование проверенного
клипа, `miss` — обычное повторное кодирование.

На Windows папка по умолчанию — `%LOCALAPPDATA%\VideoChronicle\cache`. Кэш
может занимать до 10 GiB, а неиспользуемые записи старше 30 дней удаляются после
успешного экспорта. В нём нет исходных медиа, project state или итогового MP4;
кэш можно отключить или очистить без потери проекта и исходников.

## Пример запуска

```powershell
python "$env:PROJECTS_ROOT\video-chronicle\join_media.py" --input-dir ~/Input --output ~/Input/preview.mp4 --ffmpeg "$env:DEV_TOOLS\ffmpeg\bin\ffmpeg.exe" --ffprobe "$env:DEV_TOOLS\ffmpeg\bin\ffprobe.exe" --overwrite
```

## Запуск GUI

```powershell
cd "$env:PROJECTS_ROOT\video-chronicle"
uv sync --locked --extra dev
uv run --locked --extra dev video-chronicle-gui
```

Вкладка «Основное» открывается первой: в ней выбираются «Хроника» либо
«Объединение — без даты и времени», входная папка и итоговый MP4. Автоматически
разрешённые пути FFmpeg/FFprobe, CRF, preset
и cache доступны во вкладке «Дополнительно», а параметры подписи — во вкладке
«Дата и время». Перед экспортом вкладка «План хронологии» показывает
accepted-фрагменты карточками с автоматически созданными кадрами, подробный
состав/order в таблице и representative кадр. Порядок меняется перетаскиванием
одной или нескольких выбранных карточек, а также кнопками «Выше»/«Ниже».
В Chronicle representative preview после анализа также строится автоматически,
но остаётся независимым от экспорта: после успешного анализа кнопка
«Экспортировать» активна и при ошибке кадра, который можно повторить вручную.
Изменение настроек не требует повторного анализа неизменных исходников; после
добавления или изменения файлов следующий анализ инспектирует только дельту.
Skipped-файлы остаются в диагностической таблице. После анализа также можно
сохранить/открыть project JSON,
задать trim, создать contiguous groups и versioned render presets. Все edits
записываются в project и не изменяют исходные медиа.
Редакторские кнопки доступны только когда текущее selection допускает действие;
на границе списка или без выбора неработающая кнопка остаётся disabled.
Вкладки и вложенные области используют единую светлую поверхность независимо
от системной темы; рамка внешней карточки не повторяется вокруг каждой кнопки.
FFmpeg и FFprobe запускаются с правами пользователя, поэтому указывайте только
доверенные сборки. По умолчанию используются команды из `PATH`.
Существующий результат требует отдельного подтверждения. Во время обработки
окно показывает структурированный прогресс и остаётся отзывчивым. Default
application backend показывает отдельные кнопки «Остановить анализ» и
«Остановить экспорт» только для соответствующей активной операции. FFprobe,
FFmpeg и их дочерние процессы завершаются как одно дерево; частичный план или
partial output не публикуются. Закрытие окна остаётся заблокированным до
terminal state.

Cache выключен по умолчанию. При включении GUI показывает `hit`/`miss` для
клипов, позволяет выбрать private local cache и отдельно подтверждает purge.
Cache не содержит project state или partial final: повреждённая запись просто
отклоняется, после чего выполняется обычная clean normalization.

Optional OTIO/scene adapters не входят в project schema v2 и удаляются без
migration. Проект пока не имеет утверждённой `LICENSE`, а локальная FFmpeg
сборка не распространяется; release требует отдельного license/packaging review.

### Optional локальная транскрипция

Транскрипция выключена по умолчанию и не скачивает executable или модель.
Для явно установленного локального `whisper.cpp` используется отдельная команда:

```powershell
video-chronicle-transcribe "C:\media\clip.mp4" `
  --item-id item-local --duration-us 120000000 --language auto `
  --whisper-cli "C:\tools\whisper-cli.exe" `
  --model "C:\models\ggml-base.bin" `
  --model-manifest "C:\models\ggml-base.manifest.json" `
  --ffmpeg "$env:DEV_TOOLS\ffmpeg\bin\ffmpeg.exe" --output "C:\media\clip.transcript.json"
```

Manifest — strict JSON с полями `model_id`, `version`, `sha256`, `size_bytes`,
`license`, HTTPS `source_url`, массивом `languages` и `engine: "whisper.cpp"`.
Media обрабатывается локально; JSON содержит provenance и явное предупреждение,
что автоматическую расшифровку необходимо проверять.

Если FFmpeg уже добавлен в `PATH`, параметры `--ffmpeg` и `--ffprobe` можно не указывать.

### Локальные защитные лимиты

Admission ограничен 4096 файлами, 64 GiB на файл, 256 GiB суммарно и семью днями известной длительности одного source. Normalize/concat tools имеют default deadline 1800 секунд; derived-file cap 64 GiB проверяется при polling и перед публикацией. Output/error-log требуют локальный путь без UNC, existing reparse ancestors, Windows device names и ADS. Превышение отклоняется с ошибкой; эти проверки не заменяют OS quota и не предотвращают hostile same-user filesystem races. Evidence и точный release status — docs/STAGES.md.

### Воспроизводимая локальная сборка wheel

После `uv sync --locked --extra dev --extra otio` выполните `uv run --locked --offline --extra dev python scripts/build_wheel.py --offline --out-dir <новый-каталог>`. Команда проверяет версии build tools по `uv.lock` и не использует global pip/setuptools. Existing wheel не перезаписывается. Gate `tests/test_clean_wheel_build.py` устанавливает wheel и locked runtime в отдельный venv без pip/system-site-packages, проверяет реальные offscreen GUI/CLI/FFmpeg paths. Первый restore может требовать public registry download; последующий gate использует offline cache. Это source workflow, не утверждённый distribution package или release.

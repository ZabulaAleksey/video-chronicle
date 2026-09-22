# Учебный журнал

## 2026-08-11 — перенос проекта в `~/codex-workspace/projects`

### Задача

Перенести приложение, локальные FFmpeg-зависимости и Git-историю из общей директории в `~/codex-workspace/video-chronicle`, устранить конфликты и подготовить отдельную публикацию.

### Что исследовали

Проверили границы старого Git-репозитория, размеры каталогов `ffmpeg/` и `ffmpeg1/`, наличие вложенной истории FFmpeg, состояние целевого GitHub-репозитория и переносимость путей в коде и README.

### Основные команды

`git status -sb`

Показывает текущую ветку и незакоммиченные изменения перед переносом.

`git rev-parse --show-toplevel`

Подтверждает, что после переноса корнем репозитория стал каталог проекта.

`Get-FileHash -Algorithm SHA256`

Позволяет проверить побайтовое совпадение файлов, если Windows не разрешает обычное перемещение каталога.

### Как была устроена проблема

Git-метаданные проекта находились на уровне общей директории, а код уже лежал в отдельной подпапке. FFmpeg source и runtime располагались рядом и игнорировались основным репозиторием.

### Что изменили

Код, `.gitignore`, Git-история и оба FFmpeg-каталога перенесены в `~/codex-workspace/video-chronicle`. Старый remote сохранён как `legacy`, новый GitHub-репозиторий назначен `origin`.

### Почему выбран такой подход

Перенос существующего `.git` сохраняет историю проекта. Игнорирование сторонних FFmpeg-каталогов предотвращает вложенный Git-конфликт и публикацию крупных бинарников.

### Что пошло не так

Windows дважды отказал в прямом `Move-Item` для каталогов с Git-метаданными. Данные были скопированы, полностью сравнены по относительным путям, размерам и SHA-256, и только затем исходники удалены.

### Проверки

Для `ffmpeg/` совпали 10 613 файлов и 361 941 004 байта без расхождений. Для `.git` совпали 88 файлов без расхождений. Git подтвердил новый корень проекта и сохранённую рабочую ветку.

### Как повторить вручную

1. Проверить `git status -sb` и список remote.
2. Создать рабочую ветку.
3. Разместить независимый project repository непосредственно в `~/codex-workspace/<project>`.
4. При отказе Windows скопировать каталог и проверить каждый файл по SHA-256.
5. Удалять исходник только после нулевого числа расхождений.
6. Проверить новый корень через `git rev-parse --show-toplevel`.
7. Назначить новый `origin`, сохранив старый remote под отдельным именем.

### Что стоит изучить

Git remotes, вложенные репозитории, лимиты хранения крупных файлов и проверка целостности SHA-256.

## 2026-08-13 — миграция context delta без подмены текущей архитектуры

### Задача

Сопоставить контекст GitHub-репозитория с локальным
`video_chronicle_context_delta`, сохранить полезные проектные правила и удалить
временный пакет без дублирования общей AI Dev Team.

### Основной конфликт

Канонические документы описывали реально работающий CLI без GUI и базы данных,
а delta — целевой Timeline Builder с GUI, очередью, прогрессом и возобновлением.
Обе части полезны, но относятся к разным временным слоям.

### Решение

Факты оставлены в `docs/ARCHITECTURE.md`, `docs/DESIGN.md` и
`docs/AI_STATUS.md`. Будущее наблюдаемое поведение перенесено в product SPEC,
этапы — в roadmap, а проектные проверки — в `docs/TESTING.md` и
`docs/SECURITY.md`. Параллельные журналы и локальные копии универсальных
hooks/MCP/agents не создавались.

### Как повторить вручную

1. Проверить `git status -sb`, remote и актуальность `origin/main`.
2. Сверить Git blob SHA канонических файлов с GitHub.
3. Разделить материалы пакета на факты, требования, планы и временные шаблоны.
4. Заполнить `docs/CONTEXT_COMPATIBILITY.md` статусами `INHERITED`, `EXTEND`,
   `PROJECT_ONLY` и `CONFLICT`.
5. Проверить ссылки SPEC, TOML-профили, Python CLI и `git diff --check`.
6. Удалить delta-каталог только после проверки сохранённого контекста.

## 2026-08-13 — переходная GUI-оболочка без переписывания медиаконвейера

### Что и зачем изменено

Добавлен PySide6 GUI для настройки и запуска существующего `join_media.py`.
CLI-контракт и медиаконвейер сохранены, а финальная публикация точечно усилена
защитой от поздней коллизии, чтобы начало интерфейса не смешивалось с ещё не
завершённым извлечением core-логики.

### Ключевой поток данных / управления

Форма создаёт типизированный `GuiRunRequest`. Чистая функция превращает его в
список argv, после чего `QProcess` асинхронно запускает текущий Python и
`join_media.py`. Объединённый stderr/stdout поступает в журнал окна, а успех
подтверждается только кодом 0 и наличием результата.

### Команды и проверки

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
$env:QT_QPA_PLATFORM = "offscreen"
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m compileall -q join_media.py gui_contract.py video_chronicle_gui.py tests
git diff --check
```

### Решения и trade-offs

- `QProcess` сохраняет отзывчивость event loop без `QThread` и второго
  медиаконвейера.
- Текстовый журнал используется только для диагностики, не как бизнес-контракт
  прогресса.
- Отмена отложена: остановка GUI-процесса Python не гарантирует завершение его
  FFmpeg-потомка на Windows.
- Финальная публикация без `--overwrite` использует атомарный hard-link
  create-if-absent, поэтому поздняя коллизия не уничтожает другой файл.

### Проблемы и способы исправления

Windows с тёмной системной палитрой дал светлый текст на светлом фоне
приложения. Штатный Qt-скриншот выявил проблему; foreground-цвета были явно
заданы для labels, inputs, buttons и выпадающего списка.

### Как повторить самостоятельно

1. Создать `.venv` и установить `requirements-dev.txt`.
2. Запустить GUI командой `.venv/Scripts/python video_chronicle_gui.py`.
3. Выбрать тестовую папку, выходной MP4 и пути к FFmpeg/FFprobe.
4. Проверить отказ от перезаписи существующего файла.
5. Запустить экспорт и убедиться, что окно реагирует, а stderr виден в журнале.
6. Выполнить headless-тесты и `git diff --check` перед коммитом.

## 2026-08-14 — маршрутизация roadmap через AI_PLAN и stage prompts

### Что и зачем изменено

КАРКАС дополнен отсутствующим `docs/AI_PLAN.md`, системной SPEC и библиотекой
самостоятельных этапов 01–17. `AI_STATUS` остаётся фактическим снимком, а
`PROGRESS.md` не создаётся.

### Ключевой поток контекста

Короткая команда `Начинай этап NN` выбирает ровно один prompt. Он указывает
SPEC, зависимости, scope, запрещённые области, tests, quality gates, DoD,
acceptance artifacts и rollback. Затем выбранный срез становится текущим
`AI_PLAN`; вся библиотека prompts в контекст не загружается.

### Команды и проверки

```powershell
py -3 ~/.codex/tools/validate_project_overlay.py ~/codex-workspace/video-chronicle
rg --files prompts/stages
git diff --check
```

### Решения и trade-offs

- Один файл на этап позволяет продолжать проект короткой командой и не
  смешивать контекст соседних этапов.
- Prompts 11–14 и 17 содержат specification/experiment gate, потому что
  roadmap не делает optional-идею утверждённым требованием.
- Общие Skills и review-процессы наследуются; project hooks/Skills не нужны.

### Как повторить самостоятельно

1. Открыть `prompts/README.md` и выбрать ближайший этап.
2. Проверить DoD его зависимости в `docs/AI_STATUS.md`.
3. Дать команду `Начинай этап NN`.
4. Убедиться, что `docs/AI_PLAN.md` содержит только выбранный срез.
5. После acceptance проверить обновление `AI_STATUS` и следующего `AI_PLAN`.

## 2026-08-14 — Безопасный resume через normalized-clip cache

### Что изменилось

Этап 10 добавил отключаемый cache не как сохранённый workspace, а как набор
immutable нормализованных клипов. Ключ связывает content, metadata provenance,
настройки overlay/font, media profile и версии инструментов. Restore всегда
копирует подтверждённый артефакт в новый active workspace.

### Почему понадобился OS lock

Обычный `threading.RLock` защищает только один Python-объект. Два процесса могли
одновременно пройти disk-cap check или принять старый, но ещё записываемый tmp
за abandoned. Per-root `msvcrt`/`flock` lock сделал последовательность
`reap → cap check → copy → no-replace commit` атомарной между процессами.

### Команды и проверки

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:VIDEO_CHRONICLE_FFMPEG = (Resolve-Path "ffmpeg1/bin/ffmpeg.exe").Path
$env:VIDEO_CHRONICLE_FFPROBE = (Resolve-Path "ffmpeg1/bin/ffprobe.exe").Path
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m compileall -q src join_media.py gui_contract.py video_chronicle_gui.py
git diff --check
```

### Как повторить самостоятельно

1. Запустить экспорт без `--cache` и убедиться, что persistent root не создан.
2. Повторить с `--cache` и увидеть первый `miss`, затем `hit`.
3. Изменить source bytes, overlay/font или tool identity и проверить новый miss.
4. Повредить manifest/clip и убедиться, что экспорт использует clean fallback.
5. Выполнить `--purge-cache` только для выбранного private root.

## 2026-08-14 — Неразрушающий project editor и schema v2

### Что изменилось

Ручной порядок не заменил date-sorted `Timeline`: он хранится отдельным
immutable layout. Trim использует integer microseconds, groups обязаны быть
непрерывными, а preset revision сохраняет и ссылку, и resolved render settings.
Один `plan-v2` связывает GUI preview, FFmpeg export и cache identity.

### Почему project и cache разделены

Project JSON — источник истины пользовательских edits. Cache — отключаемая
оптимизация нормализации. Повреждённый cache можно удалить без потери проекта;
rollback project публикуется как новая revision, чтобы stale writer не смог
перезаписать восстановленное состояние.

### Команды и проверки

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:VIDEO_CHRONICLE_FFMPEG = (Resolve-Path "ffmpeg1/bin/ffmpeg.exe").Path
$env:VIDEO_CHRONICLE_FFPROBE = (Resolve-Path "ffmpeg1/bin/ffprobe.exe").Path
.venv/Scripts/python -m pytest -q tests/test_nondestructive_editing.py
.venv/Scripts/python -m pytest -q
```

### Как повторить самостоятельно

1. Проанализировать mixed photo/video папку и сохранить project.
2. Переместить элементы, создать группу и задать trim.
3. Обновить representative preview и выполнить export.
4. Закрыть приложение, открыть project и повторно проанализировать sources.
5. Проверить, что edits восстановлены, а SHA-256/size/mtime sources не изменились.

## 2026-08-14 — Removable OTIO interchange и измеримые scene suggestions

### Что изменилось

Этап 12 добавил adapter-neutral timeline DTO/proposal, optional native OTIO
subset и FFmpeg `scdet` suggestions. Оба adapter выключены по умолчанию, не
входят в schema v2 и ничего не редактируют автоматически.

### Почему parser вызывается не первым

Даже optional library может иметь глобальные adapter manifests, hooks и media
linkers. Поэтому payload сначала проходит собственный bounded JSON/subset
preflight, а затем используется direct OTIO core codec. Remote/traversal refs,
unknown schemas/fields и превышение limits отклоняются до project mutation.

### Как принималось решение scene detector

Checked synthetic corpus сравнивает suggestions с exact hard-cut boundaries
через maximum-cardinality matching. FFmpeg 9.0.1 получил P/R/F1 `1.0`, ноль
false positives на negatives, p95 `0 µs`, одинаковые результаты `3/3` и
wall/media `0.080509`, поэтому lightweight `ffmpeg-scdet-v1` сохранён, а
PySceneDetect не добавлен.

### Команды и проверки

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:VIDEO_CHRONICLE_FFMPEG = (Resolve-Path "ffmpeg1/bin/ffmpeg.exe").Path
$env:VIDEO_CHRONICLE_FFPROBE = (Resolve-Path "ffmpeg1/bin/ffprobe.exe").Path
.venv/Scripts/python -m pytest -q tests/test_timeline_interchange.py tests/test_scene_suggestions.py
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m compileall -q src tests
git diff --check
```

### Как повторить самостоятельно

1. Установить optional extra командой `pip install -e ".[dev,otio]"`.
2. Запустить focused OTIO/scene tests с локальным FFmpeg 9.0.1.
3. Проверить export/import golden для 0/1/4096 clips.
4. Подать forbidden schema, remote URL и oversized JSON и увидеть отказ без mutation.
5. Сгенерировать synthetic corpus и сравнить JSON/Markdown benchmark report.
6. Выключить оба flags и убедиться, что обычный import graph/export не изменился.

## 2026-09-22 — накопительный A/V drift после concat AAC-сегментов

### Problem

После обработки июльского корпуса звук при непрерывном воспроизведении всё
сильнее отставал от видео, хотя container durations и packet PTS/DTS выглядели
согласованными.

### Symptom

В начале A/V были синхронны; drift накапливался со временем. Seek во встроенном
Android-плеере `7.30.50.106` временно восстанавливал синхронизацию, после чего
расхождение снова росло.

### Root cause

Первое расследование нашло реальную проблему stream-copy независимо
закодированных AAC units, но ошибочно сочло её полным объяснением. После
`fed1309` final audio кодировался один раз, однако concat сохранял положительные
PTS gaps между decoded audio frames: video span нормализованного clip длиннее
его PCM payload. AAC encoder сохранял эти timestamps, но не материализовал
отсутствующий интервал samples. В post-fix `D:\output.mp4` найдено 343 gaps
суммарно 167 263 samples (`3.484645833 s`); decoded PCM длится
`1577.914667 s` при presentation timeline `1581.3993125 s`. В последовательной
sample-count модели это даёт decoded-content clock-deficit proxy `3.468667 s`
и slope `2193.44 ppm`. Это не прямое измерение semantic event offset:
timestamp-aware player может выдержать gaps как silence.
Counts 343 gaps и 343 boundaries после video items коррелируют, но не доказывают
one-to-one: conservative absolute-PTS reconstruction дала 119 exact matches,
0 matches после 17 photo boundaries; остальные связи скрыты cumulative
rounding и overlaps.

### Failed attempts

Commit `fed1309` устранил access-unit surplus, но regression использовал clips
с совпадающими audio/video spans и потому не создавал реальных положительных
PTS gaps. Проверены и отвергнуты constant offset, округление `60000/1001` до
60 и потеря video frames: video PTS непрерывны, а proxy slope `0.219344%`
не совпадает с NTSC mismatch около `0.100%`.

### Fix

На финальной сборке H.264 video сохраняется через stream copy. Между concat
decode и единственным AAC encode применяется bounded
`aresample=48000:async=1000:min_hard_comp=0.001:first_pts=0`: filter следует
PTS и превращает положительные gaps в PCM silence. Offset, `atempo` и FPS
correction не применяются. Подробности: [расследование A/V drift
v2](notes/av-sync-drift-investigation.md).

### Verification

Новый real-FFmpeg RED воспроизводит настоящий механизм: normalized segment
имеет `3.233333 s` video и 154 624 decoded samples (`3.221333 s`), deficit 576
samples; у первого real clip deficit равен 578 samples. 60 synthetic повторов
на `fed1309` дают 59 gaps по 576 samples — 33 984 samples
или `0.708 s`. После gap materialization exact argv characterization проходит,
post-fix artifact имеет 0 positive gaps и video-minus-decoded duration
difference `0.012004167 s`,
а новый и прежний multi-minute FFmpeg regressions дают `2 passed in 45.28s`.
Полный real candidate `D:\output-avsync-v2-diagnostic.mp4` содержит
75 907 168 decoded samples (`1581.399333 s`), 0 positive gaps, 0 negative
overlaps, 0 net gap и
video-minus-decoded difference `0.005333 s`; checkpoint error остаётся около
`-0.021333 s` без роста. В корректном user-profile temp окружении
characterization + все FFmpeg smoke tests дали `41 passed in 41.53s`, включая
cache scenario. Полный suite: `342 passed, 21 skipped, 3 failed in 101.12s`.
Оставшиеся failures environment/baseline-sensitive: GUI ожидает literal
`ffmpeg`, но discovery находит installed full-build path; base Python не имеет
`setuptools.build_meta`; scene golden закрепляет essentials-build identity
вместо обнаруженного full-build FFmpeg.
Проблемный MP4 имеет variable audio `stts` размером 23 064 bytes с durations
`768/1023/1024` и до `2027`; diagnostic candidate имеет `stts` 32 bytes и
continuous decoded PCM. Точный renderer mechanism Android `7.30.50.106` не
наблюдаем локально: гипотеза состоит в mishandling variable AAC schedule, а
seek сбрасывает prior render state и reanchor'ит clocks по текущим PTS.
Обязательный human gate перед root-cause closure/release — непрерывно
воспроизвести `D:\output-avsync-v2-diagnostic.mp4` на этом Android player и
подтвердить отсутствие накапливающегося слышимого A/V drift.
Differential matrix отделила timestamp gaps от codec/container/video encode:
re-encode A+V, PCM/MKV и Opus сохранили около `0.708 s`; `asetpts` закрыл gaps,
но неверно сократил semantic timeline; default soft `async=1` оставил
`0.072 s`; оба варианта с `min_hard_comp=0.001` закрыли gaps. На проблемном
artifact также были 1097 отрицательных overlaps по 1 sample; candidate удалил
и gaps, и overlaps. Manual non-zero-start fixture (video `0.500000 s`, audio
`0.478667 s`, 20 повторов) дал 0 gaps/net 0. Edit-list offsets ограничены
началом track, а interleaving не имеет длинных runs, поэтому они не объясняют
накопление.

### Prevention

Утверждён [MEDIA-SYNC-001](../specs/features/media-timeline-sync.spec.md):
регрессии должны создавать mismatched normalized segment, считать decoded-frame
PTS gaps и сравнивать decoded PCM с video timeline в нескольких checkpoints, а
не ограничиваться stream duration или packet continuity. Допуск — не более
одного AAC access unit на весь output без роста между checkpoint'ами.

### Links

- [Расследование накопительного A/V drift](notes/av-sync-drift-investigation.md)
- [MEDIA-SYNC-001 — Согласованная media timeline](../specs/features/media-timeline-sync.spec.md)

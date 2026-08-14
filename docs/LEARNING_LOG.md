# Учебный журнал

## 2026-08-11 — перенос проекта в `~/codex-workspace/projects`

### Задача

Перенести приложение, локальные FFmpeg-зависимости и Git-историю из общей директории в `~/codex-workspace/projects/video-chronicle`, устранить конфликты и подготовить отдельную публикацию.

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

Код, `.gitignore`, Git-история и оба FFmpeg-каталога перенесены в `~/codex-workspace/projects/video-chronicle`. Старый remote сохранён как `legacy`, новый GitHub-репозиторий назначен `origin`.

### Почему выбран такой подход

Перенос существующего `.git` сохраняет историю проекта. Игнорирование сторонних FFmpeg-каталогов предотвращает вложенный Git-конфликт и публикацию крупных бинарников.

### Что пошло не так

Windows дважды отказал в прямом `Move-Item` для каталогов с Git-метаданными. Данные были скопированы, полностью сравнены по относительным путям, размерам и SHA-256, и только затем исходники удалены.

### Проверки

Для `ffmpeg/` совпали 10 613 файлов и 361 941 004 байта без расхождений. Для `.git` совпали 88 файлов без расхождений. Git подтвердил новый корень проекта и сохранённую рабочую ветку.

### Как повторить вручную

1. Проверить `git status -sb` и список remote.
2. Создать рабочую ветку.
3. Переместить проект в `~/codex-workspace/projects/<project>`.
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
py -3 ~/codex-workspace/tools/validate_project_overlay.py ~/codex-workspace/projects/video-chronicle
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

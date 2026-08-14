# Стратегия тестирования

## Сначала характеристика текущего CLI

До извлечения логики из `join_media.py` зафиксировать регрессионными тестами:

- распознавание дат из поддерживаемых метаданных и имён файлов;
- детерминированную сортировку, включая одинаковые и отсутствующие даты;
- выбор поддерживаемых файлов и обработку пустой папки;
- построение фильтров FFmpeg и concat-списка;
- параметры CLI, коды завершения и правило явного перезаписывания;
- сообщения при отсутствии FFmpeg/FFprobe и при сбое обработки.

Эти тесты описывают baseline, но не объявляют все особенности старого скрипта
вечными требованиями. Обязательная совместимость определяется FR-011 в SPEC.

На текущий момент автоматизированы параметры CLI, форматы и граничные случаи
дат, все поддерживаемые filename patterns, приоритет метаданных, сортировка,
фильтрация исходников, FFmpeg normalize/concat argv, пустой и повреждённый
входы, частичный успех, коллизии результата, неизменность источников,
построение GUI argv, реальный legacy `QProcess`, application-service worker,
preview states, invalidation, overwrite timing и responsive scrolling.
Overlay покрыт validation/golden tests, preview lifecycle, synthetic multi-item
export и реальными FFmpeg preview/normalize с включённой и выключенной подписью.

## Матрица baseline этапа 01

| Сценарий | Уровень | Автоматическая проверка | Связь с SPEC |
| --- | --- | --- | --- |
| CLI-аргументы, Unicode и пробелы | characterization | `test_parse_args_preserves_legacy_cli_contract` | `SYS-AC-001`, `AC-008`, `AC-010` |
| Форматы, високосная дата, timezone-aware wall time, некорректные границы | unit | `test_parse_datetime_text_characterizes_*` | `SYS-AC-001`, `AC-008` |
| Filename patterns и границы числового совпадения | unit | `test_datetime_from_filename_characterizes_patterns` | `SYS-AC-001`, `AC-008` |
| Приоритет metadata tags и fallback после некорректного значения | unit | `test_metadata_priority_*`, `test_invalid_higher_priority_*` | `SYS-AC-001`, `AC-008` |
| Сортировка по дате и casefolded имени при равной дате | characterization | `test_main_orders_items_by_date_then_casefolded_name` | `SYS-AC-001`, `AC-008` |
| Фильтрация расширений и исключение output/error log | unit | `test_collect_source_paths_is_sorted_and_excludes_outputs` | `SYS-AC-001` |
| Photo, video with audio, video without audio normalize argv | contract | `test_normalize_item_builds_list_argv_for_each_media_shape` | `SYS-AC-001`, `AC-010` |
| Экранирование concat list и concat argv | contract | `test_concatenate_writes_escaped_list_and_list_argv` | `SYS-AC-001`, `AC-010` |
| Пустой, повреждённый и частично успешный набор | characterization | `test_empty_input_*`, `test_corrupt_input_*`, `test_partial_encoding_success_*` | `SYS-AC-001`, `SYS-FR-004`, `AC-008` |
| Ранняя и поздняя коллизии, no-replace и разрешённый overwrite | characterization | `test_existing_output_*`, `test_publish_output_*` | `SYS-AC-003`, `AC-008` |
| Неизменность valid/corrupt/skipped источников | characterization + integration | `test_corrupt_input_*`, `test_partial_encoding_success_*`, synthetic smoke | `SYS-AC-005` |
| Реальный mixed photo/video экспорт и проверка A/V streams | integration smoke | `test_synthetic_photo_video_cli_smoke_preserves_sources` | `SYS-AC-001`, `SYS-AC-005`, `AC-008`, `AC-010` |
| DATE-001 priority, raw provenance, timezone и conflicts | unit/table | `tests/test_metadata_date_engine.py` | `DATE-AC-001–003`, `AC-002` |
| MODEL-001 IDs/order, job transitions, schema v1 и repository | unit/table | `tests/test_project_queue_model.py` | `MODEL-AC-001–003` |
| GUI application preview, async lifecycle, Unicode, stale plan и overwrite | GUI/contract | `tests/test_gui_application.py` | `GUI-APP-AC-001–003`, `AC-001/002/010` |
| Единый overlay config, escaping шрифта, preview и multi-item export | unit/GUI/integration | `tests/test_overlay.py` | `OVERLAY-AC-001–003`, `AC-004/010` |
| Join/Chronicle invariant, CLI parity, GUI round-trip и оба real exports | matrix/GUI/integration | `tests/test_modes.py`, `tests/test_gui_application.py`, `tests/test_ffmpeg_smoke.py` | `MODE-AC-001–003`, `AC-003/004/008` |
| Structured progress, cancel checkpoints, publication race и cleanup | unit/integration/GUI | `tests/test_execution.py`, `tests/test_gui_application.py` | `EXEC-AC-001/003/004`, `AC-003/005/009/010` |
| Windows Job/POSIX group, descendants, timeout/output-limit и real FFmpeg cancel | platform/integration/security | `tests/test_process_control.py` | `EXEC-AC-002`, `AC-006` |
| Cache key/manifest, corruption fallback, bounds, purge и interprocess lock | unit/integration/security | `tests/test_cache.py`, `tests/test_execution.py` | `CACHE-AC-001–004`, `AC-007` |
| Interrupted/repeated mixed-media export и byte-identical clean/resumed result | integration smoke | `tests/test_execution.py`, `tests/test_ffmpeg_smoke.py` | `CACHE-AC-002/003`, `AC-005/007/010` |

Synthetic smoke создаёт короткие BMP и MP4 во временном каталоге с пробелом,
апострофом и Unicode, запускает CLI list-argv без shell, проверяет итоговые
video/audio streams и сравнивает SHA-256, размер и `mtime_ns` источников до и
после обработки. Инструменты ищутся сначала через
`VIDEO_CHRONICLE_FFMPEG` / `VIDEO_CHRONICLE_FFPROBE`, затем в `PATH`.

Минимальная подтверждённая версия smoke-контракта: **FFmpeg и FFprobe 9.0.1**.
Этап 01 не объявляет более старые версии поддерживаемыми без отдельного
воспроизводимого прогона. Проверенная Windows release essentials сборка:

```text
ffmpeg version 9.0.1-essentials_build-www.gyan.dev
ffprobe version 9.0.1-essentials_build-www.gyan.dev
```

Архив был загружен только во временную папку, его SHA-256
`fec81ae03971d9dd4be3ebe02e263bd2ec1d789483f931bdba5f5715e65da2e9`
совпал с опубликованным хешем. Синтетический mixed photo/video smoke прошёл;
бинарники не входят в репозиторий.

## Уровни проверок

- Unit: разбор дат, политика приоритетов и происхождение значения, стабильный
  порядок, экранирование concat-списка, построение плана экспорта.
- Property-based там, где это окупается: произвольные имена, Unicode, даты и
  стабильность сортировки без запуска внешних процессов.
- Integration: FFprobe/FFmpeg на коротких fixtures, смешанные фото/видео,
  корректность длительности и воспроизводимость результата.
- Contract: процессы получают argv-списки; CLI и будущий GUI используют один
  и тот же наблюдаемый план и правила ошибок.
- GUI: loading/error/empty/populated/stale preview, Unicode, worker cleanup,
  repeat-run guard, responsive scrolling, structured progress/cancel и
  отсутствие блокировки event loop.
- Resume/cache: повторный запуск, прерывание, изменение content/provenance/font/
  параметров/tool version, повреждённое состояние, bounded I/O, cap/retention,
  protected purge и межпроцессная сериализация мутаций.
- Packaging (когда появится): запуск на чистой Windows-машине, обнаружение
  зависимостей и короткий экспорт.

## Обязательные отрицательные сценарии

- повреждённое медиа и некорректные метаданные;
- конфликтующие, отсутствующие и timezone-aware даты;
- пробелы, кавычки и Unicode в путях;
- отсутствие или несовместимая версия FFmpeg/FFprobe и, если используется,
  ExifTool;
- чрезмерные размеры, длительность или объём метаданных;
- существующий выходной файл без разрешения перезаписи;
- ошибка прав и нехватка места во временной или выходной папке;
- отмена/авария во время рендера;
- повреждённый, подменённый или устаревший кэш.

## Критерий завершения изменения

Для затронутых требований должна прослеживаться цепочка
`SPEC → AC → тест → реализация`. Интеграционные тесты с внешними инструментами
могут быть явно пропущены только с указанной причиной и отдельным smoke-check.

## Локальный запуск текущих тестов

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
$env:QT_QPA_PLATFORM = "offscreen"
.venv/Scripts/python -m pytest -q
```

Только CLI-characterization и synthetic smoke:

```powershell
.venv/Scripts/python -m pytest -q tests/test_cli_characterization.py
$env:VIDEO_CHRONICLE_FFMPEG = "C:/tools/ffmpeg/bin/ffmpeg.exe"
$env:VIDEO_CHRONICLE_FFPROBE = "C:/tools/ffmpeg/bin/ffprobe.exe"
.venv/Scripts/python -m pytest -q -rs tests/test_ffmpeg_smoke.py
```

Если переменные не заданы и инструменты отсутствуют в `PATH`, smoke-test
намеренно завершается как `SKIPPED`, а не создаёт ложный зелёный integration
результат.

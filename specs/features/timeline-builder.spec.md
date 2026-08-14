# Timeline Builder / Video Chronicle

- Статус: черновик product SPEC; требования требуют утверждения до реализации
- Версия: 0.2
- Область: построение одного видео по набору фотографий и видеозаписей

## Утверждённый срез GUI-001 — оболочка legacy CLI

Этот раздел утверждён прямым запросом пользователя от 2026-08-13. Остальная
SPEC сохраняет статус черновика. Срез начинает GUI, но не объявляет
завершёнными этапы извлечения core/application services.

- **GUI-001 — Настройка запуска.** Локальное приложение на PySide6 позволяет
  выбрать входную папку и выходной MP4, указать FFmpeg/FFprobe, CRF и preset.
- **GUI-002 — Переходный execution adapter.** GUI запускает legacy CLI
  `join_media.py` через асинхронный `QProcess`; программа и каждый аргумент
  передаются отдельно, без shell и ручного quoting.
- **GUI-003 — Наблюдаемость.** Во время работы GUI остаётся отзывчивым,
  показывает объединённый текстовый вывод CLI и различает запуск, успех и
  ошибку. Успех подтверждается кодом 0 и наличием итогового файла.
- **GUI-004 — Коллизия результата.** Если выходной файл существует, процесс
  не запускается без отдельного подтверждения. Только после подтверждения в
  CLI передаётся `--overwrite`; окончательная проверка остаётся в CLI.
- **GUI-005 — Жизненный цикл.** Пока процесс активен, повторный запуск и
  закрытие окна блокируются. Безопасная отмена не имитируется до появления
  контракта остановки всего дерева Python/FFmpeg.

### Критерии приёмки среза

- **GUI-AC-001 (GUI-001, GUI-002, NFR-003, SEC-002).** Пути с пробелами и
  Unicode сохраняются отдельными argv-элементами; GUI не копирует медиалогику.
- **GUI-AC-002 (GUI-003, NFR-004).** `QProcess` не блокирует event loop,
  вывод CLI появляется в журнале, а повторный запуск во время работы запрещён.
- **GUI-AC-003 (GUI-003).** Ненулевой код, аварийный выход, ошибка запуска и
  отсутствие результата после кода 0 отображаются как ошибка.
- **GUI-AC-004 (GUI-004, FR-008, SEC-003).** Отказ от подтверждения не
  запускает процесс и не изменяет существующий файл; согласие добавляет
  `--overwrite` отдельным аргументом.
- **GUI-AC-005 (GUI-005).** Активный процесс нельзя оставить без контроля
  простым закрытием окна; отмена, очередь и структурированный прогресс явно не
  входят в этот срез.

### Не входит в срез

- предпросмотр и изменение порядка медиа;
- извлечение логики дат или FFmpeg-команд из `join_media.py`;
- очередь, SQLite, кэш и возобновление;
- безопасная отмена и процент выполнения;
- пакетирование приложения.

## Утверждённый срез GUI-APP-001 — preview через application services

Этот срез утверждён прямой командой пользователя от 2026-08-14 последовательно
выполнить оставшиеся этапы дорожной карты. Он заменяет default whole-CLI GUI
execution path, но сохраняет GUI-001 как временный диагностический fallback до
приёмки этапа 06.

- **GUI-APP-001 — Асинхронный анализ.** Пользователь явно запускает анализ
  выбранной папки. `plan_export` выполняется вне UI thread, а интерфейс различает
  loading, empty, error и populated состояния.
- **GUI-APP-002 — Состав и порядок.** Для accepted item отображаются номер в
  плане, имя/путь, выбранная wall-clock дата, date provenance, timezone и признак
  конфликта. Для skipped item отображаются путь и диагностическая причина.
- **GUI-APP-003 — Актуальный snapshot.** Preview содержит входную папку,
  выходной MP4, число accepted/skipped, CRF, preset и overwrite policy. Изменение
  любого поля формы инвалидирует preview; экспорт доступен только для актуального
  непустого плана.
- **GUI-APP-004 — Единый application path.** GUI вызывает `plan_export` и
  `execute_plan` через worker boundary; widgets не выполняют FFprobe/FFmpeg и не
  повторяют date/order/publish policy. CLI продолжает использовать те же
  application services.
- **GUI-APP-005 — Lifecycle до safe cancel.** Повторный анализ/экспорт и закрытие
  окна блокируются, пока worker активен. Этот срез не имитирует process-tree
  cancellation; безопасная отмена относится к этапу 09.

### Критерии приёмки среза

- **GUI-APP-AC-001 (GUI-APP-001/002, FR-001/004, AC-001/002).** Набор accepted,
  повреждённых и undated файлов дважды даёт одинаковый видимый порядок,
  provenance и причины пропуска, не изменяя источники.
- **GUI-APP-AC-002 (GUI-APP-003, FR-005, NFR-003).** Unicode/space paths
  сохраняются как `Path`, изменение формы инвалидирует plan, а overwrite не
  включается без отдельного подтверждения непосредственно перед экспортом.
- **GUI-APP-AC-003 (GUI-APP-004/005, FR-012, NFR-004).** Анализ и экспорт идут
  вне UI thread, повторный запуск и закрытие во время работы запрещены, worker и
  thread освобождаются после успеха и ошибки; legacy CLI characterization остаётся
  зелёной.

### Не входит в срез

- ручной reorder/trim/grouping и overlay editor;
- структурированный progress и безопасная process-tree cancellation;
- cache, resume и durable persistence.

## Утверждённый срез OVERLAY-001 — единая подпись и preview

Этот срез утверждён прямой командой пользователя от 2026-08-14 последовательно
выполнить оставшиеся этапы дорожной карты. Он формализует существующую подпись
даты и не разрешает arbitrary FFmpeg expressions.

- **OVERLAY-001 — Typed config.** Immutable Qt-free config содержит `enabled`,
  format preset, position, horizontal/vertical margins, font size, text/outline
  colors, outline width и optional explicit font path. Config целиком передаётся
  preview и каждому normalizing export item.
- **OVERLAY-002 — Formats.** Разрешены только `dd.MM.yy ddd` (default legacy с
  русским сокращением дня недели), `dd.MM.yyyy` и `dd.MM.yyyy HH:mm`.
- **OVERLAY-003 — Position и ranges.** Разрешены `top-left`, `top-right`,
  `bottom-left` (default legacy) и `bottom-right`; margins — `0..300`, font size —
  `12..200`, outline width — `0..20`, colors — `#RRGGBB`.
- **OVERLAY-004 — Font policy.** Существующий explicit `.ttf`/`.otf` используется
  как единый font path. Отсутствующий/неподдерживаемый explicit path отвергается
  до preview/export. Без explicit path используется проверенный системный
  fallback; если он не найден, операция получает явную диагностику.
- **OVERLAY-005 — Representative preview.** Для первого accepted item worker
  вне UI thread извлекает кадр в PNG 640×360 и применяет тот же filter adapter.
  Для видео используется начало media, для фото — исходный кадр. Loading, error,
  ready и disabled-overlay состояния различимы; временный preview удаляется после
  загрузки в GUI.
- **OVERLAY-006 — Plan update.** Изменение только overlay controls не повторяет
  FFprobe: GUI создаёт новый immutable request внутри текущего plan, инвалидирует
  старый visual preview и требует обновить его перед export. Изменение input,
  output, tools или encoding settings по-прежнему требует полного анализа.

### Критерии приёмки среза

- **OVERLAY-AC-001 (OVERLAY-001–003, FR-007, AC-004).** Golden unit-набор для
  всех форматов/позиций даёт детерминированный escaped filter; enabled config
  добавляет одну подпись ко всем clips, disabled config не добавляет `drawtext`.
- **OVERLAY-AC-002 (OVERLAY-004/005, NFR-003/004).** Unicode font path и
  representative media дают preview без shell; missing font и FFmpeg error
  отображаются, UI остаётся отзывчивым, временный PNG очищается.
- **OVERLAY-AC-003 (OVERLAY-006, FR-005/007).** Preview и export используют
  один и тот же config object; overlay-only change сохраняет accepted order, но
  export недоступен до обновления visual preview.

### Не входит в срез

- произвольный текст/FFmpeg expression, animation/keyframes и templates;
- полноценное воспроизведение видео или timeline editor;
- аппаратный preview acceleration, cache и persistence.

## Утверждённый срез MODE-001 — Join и Chronicle

Этот срез утверждён прямой командой пользователя от 2026-08-14 последовательно
выполнить оставшиеся этапы. Он вводит пользовательский mode как данные плана,
не создавая второй media pipeline.

- **MODE-001 — Typed mode.** Immutable `ExportRequest` и производный plan
  содержат один из двух mode: `join` или `chronicle`. Mode участвует в equality
  и snapshot determinism и меняется только созданием нового request/plan.
- **MODE-002 — Join.** Join использует тот же принятый date-sorted plan,
  normalization, codecs, concat и publication, но никогда не добавляет
  `drawtext`. Сочетание Join с `overlay.enabled=True` недопустимо на domain
  boundary; adapters обязаны строить disabled overlay.
- **MODE-003 — Chronicle.** Chronicle использует тот же date-sorted plan и
  разрешает утверждённый OVERLAY-001 как включённым, так и выключенным. Default
  Chronicle сохраняет legacy overlay: `dd.MM.yy ddd`, `bottom-left`.
- **MODE-004 — CLI compatibility.** Отсутствующий `--mode` и явный
  `--mode chronicle` эквивалентны прежнему CLI: текущие аргументы, порядок,
  overlay, коды и финализация сохраняются. `--mode join` является только новым
  opt-in; explicit `--font-file` с ним отклоняется как неприменимый параметр.
- **MODE-005 — GUI policy.** GUI по умолчанию показывает Chronicle и до анализа
  объясняет: Join создаёт хронологический MP4 без подписи, Chronicle разрешает
  подпись даты. Переключение mode инвалидирует plan; в Join overlay controls
  выключены, visual preview имеет явное disabled состояние.
- **MODE-006 — Один pipeline.** Mode-specific policy заканчивается на
  request/plan/overlay boundary. Inspection, normalize, concat и publication
  ports не дублируются и не получают widget-specific ветвлений.

### Критерии приёмки среза

- **MODE-AC-001 (MODE-001–003, FR-006/007, AC-003/004).** Matrix
  `mode × overlay × photo/video` отвергает только Join+enabled overlay; валидные
  планы детерминированы, Join не содержит `drawtext`, Chronicle on/off следует
  OVERLAY-001, а оба режима проходят те же media adapters.
- **MODE-AC-002 (MODE-004, FR-011, AC-008).** Characterization доказывает, что
  legacy invocation без `--mode` эквивалентен Chronicle, а новый `--mode join`
  не меняет прежние параметры, коды, overwrite и path handling.
- **MODE-AC-003 (MODE-005/006, FR-005/012, NFR-001/004).** GUI показывает mode
  и его последствия в plan summary, инвалидирует snapshot при переключении и
  остаётся отзывчивым; review подтверждает один application/pipeline path.

### Не входит в срез

- режим с filename/filesystem order или включение undated media;
- разные codecs/normalization для Join и Chronicle;
- trim/reorder, progress/cancel, cache/resume и persistence.

## Утверждённый срез EXEC-001 — progress и safe cancel

Этот срез утверждён прямой командой пользователя от 2026-08-14 последовательно
выполнить оставшиеся этапы. Он добавляет runtime lifecycle к одному
application/pipeline path и не меняет CLI argv или атомарную publication policy.

- **EXEC-001 — Typed lifecycle.** Qt-free execution context использует
  существующие `JobState`: `planned → running → cancel-requested → cancelled`
  либо `running → succeeded/failed`. `Succeeded` возможен только после
  publication; `cancelled` — только после подтверждённой остановки process tree
  и выполнения workspace cleanup policy. Неподтверждённая остановка означает
  `failed`, а не ложный `cancelled`.
- **EXEC-002 — Progress events.** Immutable event содержит operation, phase,
  `completed_units`, optional `total_units`, optional item index/path и outcome
  completed/skipped. Analysis total становится числом найденных source paths;
  каждый inspected/skipped source завершает одну единицу. Export total равен
  `len(plan.items) + 2`: каждый normalized/skipped item, concat и успешная
  publication завершают по одной единице. Preflight/cleanup не входят в total.
  Процент вычисляет consumer как `completed/total`; это не ETA и не оценка
  длительности. Failure/cancel не принудительно показываются как 100%.
- **EXEC-003 — Cooperative boundary.** Thread-safe cancellation request
  принимается только в running state до publication commit point. Checkpoint
  выполняется до workspace, между items, до concat и непосредственно перед
  publication. После начала атомарной publication request возвращает «слишком
  поздно», и terminal outcome определяется фактической publication.
- **EXEC-004 — Process-tree ownership.** Каждый tool process запускается без
  shell внутри platform-owned tree. Windows использует unnamed Job Object с
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, немедленный
  `AssignProcessToJobObject` и `TerminateJobObject` после cooperative grace.
  POSIX использует новую session/process group, `SIGTERM`, затем `SIGKILL`.
  Все процессы reaped; parent-only kill запрещён. Допустимое окно между Windows
  `Popen` и assignment ограничено доверенными tool binaries; assignment failure
  немедленно завершает root и делает safe cancel недоступным для операции.
- **EXEC-005 — Bounded cancellation.** Сначала tool получает cooperative
  остановку через закрываемый stdin (`q` для FFmpeg), grace — 2 секунды. Затем
  platform tree принудительно завершается; kill/reap budget — ещё 3 секунды,
  polling не реже 100 мс. Общий acceptance bound — 5.5 секунды. Timeout и
  output-limit используют тот же tree termination, а не `Popen.kill()` root.
- **EXEC-006 — Preflight и cleanup.** До encode повторно проверяются immutable
  plan, output/error-log collision, tool availability/version, source/font
  identity и возможность создать private workspace. Свободное место доступно
  как диагностика, но не имеет произвольного hard threshold без надёжной оценки
  размера. По умолчанию cancel/failure удаляет workspace; `--keep-work`
  сохраняет только диагностические intermediates и никогда не публикует их.
- **EXEC-007 — GUI и fallback.** Default GUI получает typed events через Qt
  signals, показывает determinate progress после появления total и разрешает
  cancel только активного export. `VIDEO_CHRONICLE_CANCEL_UI=0` отключает
  кнопку. Legacy `QProcess` fallback и неподдерживаемый backend сохраняют
  безопасное поведение «дождаться завершения»; окно остаётся заблокированным до
  terminal state.
- **EXEC-008 — Compatibility.** `execute_plan` сохраняет legacy success `int`,
  а новые execution/progress параметры optional. CLI argv, exit codes и
  существующие diagnostics не меняются; cancel является GUI application-service
  capability, а не скрытым завершением CLI parent.

### Критерии приёмки среза

- **EXEC-AC-001 (EXEC-001/002, FR-005/006/009, AC-003/009).** Progress events
  монотонны для success/skip/failure, следуют утверждённому denominator и
  достигают 100% только после подтверждённой publication; GUI event loop
  остаётся отзывчивым.
- **EXEC-AC-002 (EXEC-003–005, FR-009, AC-006).** Cancel до workspace, во время
  normalize, между items и во время concat завершается не дольше 5.5 секунды;
  helper process tree не оставляет живых child/grandchild, а failure
  подтверждения tree termination различим как failed.
- **EXEC-AC-003 (EXEC-003/006, FR-008, SEC-001/003, AC-005/010).** Cancel race
  до publication сохраняет sources/existing output и не публикует partial;
  cancel после commit не отменяет уже начатую атомарную publication. Default
  workspace очищается, `--keep-work` остаётся только диагностическим.
- **EXEC-AC-004 (EXEC-007/008, FR-011/012).** Feature-flag fallback не
  показывает небезопасную кнопку, GUI различает cancelled/failed/succeeded,
  legacy CLI characterization остаётся без изменения.

### Не входит в срез

- duration-weighted ETA и парсинг FFmpeg stderr/progress protocol;
- resume/cache, durable/background queue и parallel exports;
- `taskkill`, `psutil`, `pywin32` или второй subprocess pipeline;
- cancel analysis/representative preview: они остаются текущими bounded tool
  calls, а safe cancel в этом срезе относится к export.

## Утверждённый срез CACHE-001 — resume normalized clips

Этот срез утверждён прямой командой пользователя от 2026-08-14 последовательно
выполнить оставшиеся этапы. Cache является отключаемой оптимизацией единственного
`execute_plan` и не меняет результат, immutable preview plan или legacy default.

- **CACHE-001 — Opt-in policy.** GUI checkbox «Использовать кэш» и CLI
  `--cache` выключены по умолчанию. `--cache-dir` выбирает private root,
  `--purge-cache` выполняет отдельную explicit purge. Без opt-in persistent
  artifacts не создаются; legacy CLI argv/результат остаются прежними.
- **CACHE-002 — Единица reuse.** Entry содержит только один полностью
  нормализованный MP4 clip. Workspace, partial final, argv, команды, overwrite
  permission и durable runtime queue не сохраняются. Порядок и concat каждый
  раз строятся заново; hit материализуется копией в новый private workspace.
- **CACHE-003 — Canonical key.** `clip-v1-<sha256>` вычисляется из canonical
  JSON с sorted UTF-8 fields: hash нормализованного absolute source path;
  `SourceFingerprint`; full source SHA-256, подтверждённый stat до/после;
  recorded date/provenance, media shape; mode; весь `OverlayConfig` и hash/
  identity explicit font; CRF/preset; `normalize-v1`; bounded FFmpeg/FFprobe
  version-output digest и executable size/mtime. Output path/order,
  overwrite/keep-work/error-log в key не входят.
- **CACHE-004 — Strict manifest.** Отдельный exact-field schema
  `video-chronicle-normalized-clip-cache` v1 содержит key, canonical identity,
  UTC creation time и artifact size/SHA-256, но не paths/argv. Unknown version,
  extra/missing fields, key/directory mismatch, corrupt artifact, symlink/
  reparse или несовместимый bounded FFprobe stream дают cache miss.
- **CACHE-005 — Private atomic storage.** Default root использует user cache
  directory ОС; custom root получает exact marker и private permissions.
  Entry создаётся в random `tmp`, полностью проверяется и публикуется atomic
  no-replace directory rename; manifest/artifact immutable. Cache path никогда
  не передаётся concat напрямую. Ошибка cache I/O/validation/store означает
  warning и clean fallback, не failure media export.
- **CACHE-006 — Retention/purge.** Initial limits: 10 GiB и 30 дней без
  verified hit; entry больше cap не сохраняется. Automatic prune выполняется
  только после успешного export. Explicit purge разрешена только без активной
  операции, перемещает entry в verified `trash` и не удаляет root/marker.
  Root/home/source/output, каталоги без marker и symlink/reparse не удаляются.
- **CACHE-007 — Integration.** `execute_plan` получает optional typed cache
  port. На hit одна normalize progress-unit завершается с `cache_hit=True`; на
  miss выполняется текущий normalize и только после его проверки допускается
  store. Cancel/publication/cleanup semantics этапа 09 не меняются. GUI
  показывает hit/miss и подтверждаемую purge; widgets не читают manifest.
- **CACHE-008 — Trust model.** Hashes обнаруживают corruption и обычную
  подмену, но не заявляют аутентичность против same-user attacker, способного
  переписать artifact и manifest. Resume state никогда не становится источником
  command/path/overwrite authority; clean export всегда доступен.

### Критерии приёмки среза

- **CACHE-AC-001 (CACHE-002/003/007, FR-010, AC-007).** После cancel на
  позднем item повторный совместимый export подтверждённо reuse завершённые
  clips; изменение content/stat/date/settings/font/profile/tool version даёт
  miss до reuse, а clean/resumed outputs эквивалентны.
- **CACHE-AC-002 (CACHE-004/005/008, SEC-005, AC-007).** Corrupt/tampered/old
  manifest, hash/size/stream mismatch и unsafe paths не используются; cache
  failure даёт clean success либо явный warning и не меняет sources/output.
- **CACHE-AC-003 (CACHE-001/006, FR-011/012).** Cache disabled не создаёт
  storage и сохраняет CLI characterization; purge/retention затрагивают только
  verified private entries и недоступны во время active GUI operation.
- **CACHE-AC-004 (CACHE-003/007, NFR-001/003).** Key стабилен для Unicode и
  canonical field order; output/order/overwrite не инвалидируют совместимый
  normalized clip; mixed photo/video real FFmpeg проходит clean и resumed.

### Не входит в срез

- SQLite/project-schema migration, durable job manifest и background queue;
- hardlink cache artifact в active workspace, background GC и cloud cache;
- HMAC/keyring authenticity, distributed locks и ML artifacts.

## Утверждённый срез DATE-001 — metadata/date engine

Этот раздел утверждён в рамках прямой команды пользователя от 2026-08-14
последовательно выполнить этапы 01–05. Для сохранения CLI parity он формализует
существующую политику, не добавляя новый metadata tool.

- **DATE-001 — Приоритет metadata.** Сначала рассматриваются ключи FFprobe
  `creation_time`, `com.apple.quicktime.creationdate`, `date_time_original`,
  `datetimeoriginal`, `media_create_date`, `create_date`, `encoded_date`,
  `date` именно в этом порядке, без учёта регистра ключа. Для одного ключа
  первым выбирается первое валидное значение в порядке format tags, затем
  stream tags.
- **DATE-002 — Filename fallback.** Валидная дата из имени используется только
  когда ни один metadata-кандидат не выбран. Filename-кандидат всё равно
  сохраняется в provenance для диагностики конфликта.
- **DATE-003 — Missing.** Элемент без валидной metadata- или filename-даты не
  попадает в текущий export plan и получает наблюдаемую ошибку inspection.
- **DATE-004 — Provenance и conflict.** Результат анализа хранит выбранный
  кандидат, все валидные кандидаты, raw value, origin/key/location и отличные
  от выбранного конфликтующие значения. Конфликт не меняет приоритет молча.
- **DATE-005 — Timezone.** Offset или `Z` сохраняется отдельно от записанных
  wall-clock полей. В DATE-001 timezone не преобразуется и не участвует в
  неявном пересчёте overlay; факт offset доступен consumer-ам.
- **DATE-006 — Стабильный порядок.** Сортировка использует выбранные wall-clock
  поля, затем `path.name.casefold()`. Элементы без даты пропускаются до
  сортировки; одинаковые даты разрешаются одинаково на повторных запусках.

### Критерии приёмки среза

- **DATE-AC-001 (DATE-001–DATE-004, FR-002).** Набор с разным регистром ключей,
  невалидным приоритетным значением, конфликтом metadata/filename и Unicode в
  имени дважды даёт одинаковое решение и provenance.
- **DATE-AC-002 (DATE-005, FR-003).** Значения `Z`, с offset и без timezone
  сохраняют одинаковые записанные wall-clock поля без неявного conversion, а
  наличие/отсутствие offset различимо в результате.
- **DATE-AC-003 (DATE-006, FR-004, NFR-001).** Равные даты сортируются по
  стабильному filename tie-breaker; missing item получает явную ошибку.

### Не входит в срез

- ExifTool/EXIF dependency и licensing decision;
- пользовательское исправление даты или timezone conversion;
- включение missing item в export plan с искусственной датой.

## Утверждённый срез MODEL-001 — project/queue contracts

Этот раздел утверждён в рамках прямой команды пользователя от 2026-08-14
последовательно выполнить этапы 01–05. Он определяет UI-независимую reference
модель, но не утверждает durable persistence или resume.

- **MODEL-001 — Timeline item.** Принятый `MediaItem` преобразуется в immutable
  `TimelineItem` с локально стабильным ID, source path, выбранной wall-clock
  датой и date provenance. ID версии 1 вычисляется детерминированно из
  нормализованного абсолютного source path; перенос проекта в другой каталог
  считается новой identity до отдельного content-identity решения.
- **MODEL-002 — Timeline order.** `Timeline` хранит уникальные item IDs и
  строится в порядке `(taken_at, path.name.casefold(), stable_id)`. Ручное
  изменение порядка относится к этапу 11.
- **MODEL-003 — Export snapshot.** Immutable `ExportPlanSnapshot` фиксирует
  ordered item IDs, output MP4, CRF, preset и overwrite policy. `plan_id`
  детерминирован содержимым snapshot. Пути инструментов и команды не входят в
  сериализуемый snapshot.
- **MODEL-004 — Job lifecycle.** Поддерживаются `planned`, `running`,
  `cancel-requested`, `succeeded`, `failed`, `cancelled`. Разрешены переходы
  `planned → running`, `running → cancel-requested|succeeded|failed` и
  `cancel-requested → cancelled|failed`; terminal state не меняется. `succeeded`
  требует явно зафиксированный final output, совпадающий с plan output.
- **MODEL-005 — Project state.** Immutable `ProjectState` связывает project ID,
  timeline, optional current export snapshot и jobs; jobs могут ссылаться
  только на известный current plan, IDs уникальны.
- **MODEL-006 — Serialization.** Утверждён только JSON-compatible schema
  `video-chronicle-project` версии `1`. Неизвестная версия, лишние/отсутствующие
  поля, invalid path/date/state/transition или рассогласованные IDs отвергаются.
  Десериализация создаёт данные и никогда не запускает команды/процессы.
- **MODEL-007 — Repository port.** Domain зависит от `ProjectRepository` port.
  Этап 05 предоставляет только `InMemoryProjectRepository`, сохраняющий
  immutable snapshots. File/SQLite adapters, migrations и concurrent writers
  не входят в срез.

### Критерии приёмки среза

- **MODEL-AC-001 (MODEL-001–003, FR-004/005, NFR-001).** Один набор принятых
  media и settings дважды даёт те же IDs, порядок и `plan_id`.
- **MODEL-AC-002 (MODEL-004, FR-009).** Таблица допустимых переходов отвергает
  invalid/terminal изменения; incomplete job не становится `succeeded`.
- **MODEL-AC-003 (MODEL-005–007, FR-010, SEC-005).** State проходит точный
  version-1 round-trip через JSON-compatible mapping; corrupt/unknown state
  отвергается; in-memory adapter можно заменить через port без Qt/subprocess.

### Не входит в срез

- durable save/load, SQLite/file migrations, resume и cache;
- progress events и реальная process-tree cancellation;
- network/server queue, locks и multi-user semantics.

## Цель продукта

Пользователь выбирает локальные медиафайлы, проверяет их порядок и параметры,
после чего получает воспроизводимый MP4-файл с понятным статусом обработки и
без изменения исходников.

## Текущее состояние (информативно)

Эталонный медиаконвейер представлен скриптом `join_media.py` с CLI. Он сканирует
одну папку, извлекает дату из доступных данных, сортирует материалы, нормализует
их через FFmpeg, добавляет дату и объединяет клипы. CLI принимает пути к
входной папке, результату, FFmpeg/FFprobe, параметры H.264 и явный флаг
перезаписи. Утверждённый срез GUI-001 добавляет переходную PySide6-оболочку над
этим CLI без preview, очереди и application services.

Этот baseline не означает, что уже существуют проектная база, очередь заданий,
возобновление экспорта, ExifTool-интеграция или остальные целевые возможности
ниже.

## Границы

В область входят локальное обнаружение и анализ медиа, объяснимое определение
даты, построение порядка, предпросмотр параметров и экспорт хронологии.

Не входят:

- изменение или удаление исходных файлов;
- обязательная облачная обработка;
- собственная реализация кодеков вместо внешнего медиадвижка;
- автоматическая публикация результата.

## Функциональные требования

- **FR-001 — Выбор входа.** Пользователь может указать локальную папку с
  медиа; система сообщает, какие файлы приняты, пропущены или не удалось
  прочитать, не изменяя их.
- **FR-002 — Дата и происхождение.** Для каждого принятого элемента система
  определяет дату по документированной политике приоритетов и сохраняет
  источник выбранного значения. Отсутствующие и конфликтующие значения не
  скрываются от пользователя.
- **FR-003 — Часовой пояс.** Если значение даты содержит часовой пояс, система
  не преобразует его неявно. Любое преобразование требует выбранной политики
  и отображается в результате анализа.
- **FR-004 — Порядок.** Система строит детерминированный порядок по выбранным
  датам; одинаковые или отсутствующие даты разрешаются документированным
  стабильным правилом.
- **FR-005 — План до экспорта.** До запуска пользователь может проверить
  состав, порядок, выходной путь и параметры экспорта, а ошибки обязательных
  инструментов или входов получает до длительной обработки, когда это
  возможно.
- **FR-006 — Экспорт.** Система создаёт единый воспроизводимый MP4 из принятого
  плана и сообщает итоговый путь либо понятную причину сбоя.
- **FR-007 — Подпись даты.** В режиме хронологии пользователь может включить
  отображение выбранной даты на кадре; формат и размещение применяются
  последовательно ко всему плану.
- **FR-008 — Коллизия результата.** Существующий выходной файл не заменяется
  без явного разрешения пользователя. Отказ не повреждает существующий файл.
- **FR-009 — Прогресс и отмена.** Длительный экспорт сообщает наблюдаемый
  прогресс и допускает отмену; после отмены исходники и ранее существовавший
  результат остаются неизменными, а незавершённый результат не выдаётся за
  готовый.
- **FR-010 — Возобновление.** Целевая версия может возобновить прерванную
  работу только из совместимого состояния; устаревшие или изменённые входы
  обнаруживаются до повторного использования промежуточных данных.
- **FR-011 — CLI-совместимость.** При развитии продукта поддерживаемый CLI
  сохраняет документированные параметры и базовое поведение либо предоставляет
  явно описанную миграцию.
- **FR-012 — Графический интерфейс.** Целевая версия предоставляет локальный
  GUI для выбора входа, проверки порядка и управления экспортом; во время
  фоновой обработки интерфейс остаётся доступным для просмотра статуса и
  отмены.

## Нефункциональные требования

- **NFR-001 — Детерминизм.** Один набор входов, политика и параметры дают один
  и тот же порядок и эквивалентный план экспорта.
- **NFR-002 — Диагностируемость.** Ошибка указывает затронутый файл или этап и
  не требует раскрытия полного содержимого пользовательских файлов.
- **NFR-003 — Совместимость путей.** Поддерживаются пути с пробелами, кавычками
  и Unicode-символами в пределах возможностей ОС и внешних инструментов.
- **NFR-004 — Отзывчивость.** Анализ и экспорт не блокируют управление
  целевым GUI на протяжении длительной операции.
- **NFR-005 — Проверка возможностей.** Необязательное аппаратное ускорение и
  ML-функции включаются только после проверки доступности и имеют безопасный
  программный fallback либо явный отказ.

## Требования безопасности и сохранности данных

- **SEC-001 — Неизменность исходников.** Все входные медиа открываются только
  для чтения; продукт не переименовывает, не перемещает и не перезаписывает их.
- **SEC-002 — Запуск процессов.** Аргументы внешних программ передаются как
  список без shell-интерпретации; пользовательские пути не становятся частью
  исполняемой командной строки оболочки.
- **SEC-003 — Безопасная финализация.** Незавершённый экспорт создаётся во
  временной рабочей области и становится итоговым файлом только после успешной
  проверки; коллизии обрабатываются по FR-008.
- **SEC-004 — Недоверенные медиа.** Метаданные, размеры, длительности и объём
  промежуточных данных проверяются на допустимость до ресурсоёмких операций.
- **SEC-005 — Состояние возобновления.** Кэш и состояние задания проверяются
  на соответствие входам и параметрам и не принимаются как доверенный источник
  путей или команд.

## Критерии приёмки

- **AC-001 (FR-001, SEC-001).** После анализа валидных, повреждённых и
  неподдерживаемых файлов исходная папка побайтно не изменена, а каждый файл
  имеет наблюдаемый статус.
- **AC-002 (FR-002–FR-004, NFR-001).** Набор с конфликтующими метаданными,
  датой в имени, часовыми поясами и равными датами дважды даёт одинаковый
  порядок и объяснение выбора каждой даты.
- **AC-003 (FR-005, FR-006).** Валидный смешанный набор фото и видео проходит
  предварительную проверку и создаёт воспроизводимый MP4; отсутствие нужного
  инструмента приводит к диагностике до экспорта.
- **AC-004 (FR-007).** Включённая подпись использует выбранную дату и единые
  параметры на всех нормализованных элементах; при выключении подпись не
  добавляется.
- **AC-005 (FR-008, SEC-003).** При существующем результате экспорт без
  разрешения завершается отказом и сохраняет файл; с явным разрешением
  финализация происходит только после успешной обработки.
- **AC-006 (FR-009).** Отмена длительного экспорта завершается за ограниченное
  время, не оставляет результат, помеченный готовым, и не меняет исходники.
- **AC-007 (FR-010, SEC-005).** Изменение входа или параметров после прерывания
  инвалидирует несовместимую часть состояния и не позволяет выдать старый кэш
  за новый результат.
- **AC-008 (FR-011).** Набор зафиксированных CLI-сценариев сохраняет ожидаемые
  коды завершения, порядок и правила коллизий после внутреннего рефакторинга.
- **AC-009 (FR-012, NFR-004).** Во время целевого GUI-экспорта пользователь
  видит обновление статуса и может инициировать отмену без зависания интерфейса.
- **AC-010 (NFR-003, SEC-002).** Файлы и каталоги с пробелами, кавычками и
  Unicode обрабатываются без shell-интерпретации пути.

## Открытые продуктовые и технические решения

- Расширение DATE-001 новыми EXIF/ExifTool источниками и лицензирование.
- Пользовательское исправление missing/conflicting даты и явное timezone
  conversion после DATE-001.
- Новые режимы сверх утверждённых Join/Chronicle и форматы выхода кроме MP4.
- Семантика процента прогресса и предельное время отмены.
- Граница совместимости текущего CLI и политика устаревания параметров.
- Выбор durable хранилища проекта и библиотек валидации после MODEL-001.
  SQLite, Pydantic, ExifTool и OTIO остаются кандидатами, а не утверждёнными или
  уже реализованными компонентами. PySide6 выбран для GUI-оболочки GUI-001.
- Формат и доверительная модель кэша/состояния возобновления.

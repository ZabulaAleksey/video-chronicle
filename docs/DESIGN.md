# Дизайн

У проекта есть одностраничное desktop-приложение PySide6 поверх application
services и сохраняется прямой CLI-интерфейс.

## GUI baseline

- одно окно с выбором входной папки и итогового MP4;
- selector режима до input-полей: Chronicle по умолчанию разрешает подпись
  даты, Join явно создаёт хронологический MP4 без неё;
- вкладка «Основное» открывается первой и содержит mode, input и output;
  «План хронологии» содержит effective order/editor/representative preview,
  подпись настраивается в «Дата и время», а пути FFmpeg/FFprobe, CRF, preset и
  cache находятся в «Дополнительно»;
- доступные FFmpeg/FFprobe автоматически показываются абсолютными путями; при
  отсутствии на Windows GUI асинхронно запускает закреплённую WinGet-установку,
  а при ошибке оставляет понятный manual fallback;
- overlay имеет независимые переключатели даты/времени, понятные примеры date
  и 12/24-hour time formats, inline/custom-separator/multiline layout;
- typography содержит список file-backed системных семейств, optional exact
  `.ttf`/`.otf` override, size, bold/italic, text color/opacity, outline и
  shadow с opacity/offset; отсутствующее сохранённое семейство при рендере
  использует fallback;
- отдельное действие «Анализировать» строит immutable preview до экспорта;
- accepted items показаны 16:9 thumbnail-карточками и в подробной таблице;
  skipped элементы остаются в таблице с причиной пропуска;
- карточки поддерживают multi-selection и internal drag-and-drop через тот же
  immutable `ProjectState.move_items`, что и кнопки «Выше»/«Ниже»; grid и table
  синхронизируют stable-ID selection и effective order;
- кадры без overlay создаются через managed FFmpeg adapter вне UI thread;
  до загрузки или при изолированной ошибке item остаётся явный placeholder;
- project editor позволяет открыть/сохранить JSON project, перемещать selected
  items кнопками «Выше»/«Ниже», задавать trim в миллисекундах, группировать/разгруппировать
  contiguous items и сохранять/применять versioned render presets;
- editor actions disabled без подходящего selection, на границе списка и при
  нарушении group constraints; disabled action не маскирует no-op, а один
  выбор item не создаёт persistent project snapshot до edit mutation;
- сохранённый `item_id`, а не номер строки, связывает edits с source; partial
  success не переназначает edit соседнему элементу;
- preview summary показывает input/output, количество элементов, CRF, preset и
  явную overwrite policy;
- preview находится во внутренней прокрутке вкладки «План хронологии», а
  read-only журнал остаётся отдельной областью под основными actions;
- loading, empty, error, stale и populated состояния имеют явный текст;
- representative-frame preview имеет отдельные stale/loading/ready/disabled/
  error состояния; Chronicle экспорт доступен только для актуального preview,
  который автоматически строится после thumbnail batch; Join показывает явное
  disabled-состояние preview и доступен после анализа;
- determinate progress после появления известного total: analysis считает
  inspected/skipped sources, export — items + concat + publication; ETA не
  показывается, failure/cancel не переводятся искусственно в 100%;
- светлая нейтральная поверхность с бирюзовым акцентом, явными focus-состояниями
  и foreground-цветами, не зависящими от светлой или тёмной системной палитры;
- tab/scroll/content/log surfaces явно окрашены в белый и не наследуют тёмный
  platform background; normal/disabled buttons используют прозрачную рамку,
  отличную от card boundary, а keyboard focus получает бирюзовую рамку;
- изменение output/tools/mode/encoding/overlay и timeline edits сохраняет
  analysis и доступность export при неизменных источниках; overlay/timeline
  изменение инвалидирует только независимый representative preview;
- новая папка либо добавленный/удалённый/изменённый source блокирует export до
  delta-analysis; watcher обновляет состояние, а export boundary повторно
  проверяет accepted/skipped source set и fingerprints; отсутствие fingerprint
  считается stale;
- form signals выполняют только лёгкий settings rebind и обновление summary/
  status, сохраняя существующие timeline widgets; filesystem scan запускается
  только debounced watcher callback и непосредственно перед export. Эти две
  safety-проверки выполняют bounded O(N) stat validation по source set;
- переключение mode пересобирает plan без FFprobe и не меняет сохранённый
  пользовательский checkbox Chronicle overlay; в Join overlay controls
  недоступны;
- существующий файл требует модального подтверждения непосредственно перед
  экспортом;
- элементы настройки блокируются на время процесса;
- cache выключен по умолчанию; видимое пояснение определяет его как локальное
  хранение проверенных normalized clips для ускорения повторного экспорта, а не
  как хранилище исходников, project state или итогового MP4; пользователь может
  включить reuse, выбрать приватную папку, увидеть `hit`/`miss` в progress и
  отдельно подтвердить асинхронную очистку только в idle-состоянии;
- default application backend показывает раздельные «Остановить анализ» и
  «Остановить экспорт» только во время соответствующей cancellable operation;
  после запроса различаются `cancel-requested`, `cancelled`, `failed` и
  `succeeded`, partial analysis plan не отображается, а закрытие окна
  блокируется до terminal state.
- при размере 820×660 используется только вертикальная центральная прокрутка:
  path/tool/overlay fields сжимаются внутри доступной ширины, browse/action
  buttons справа остаются видимыми, а editor actions складываются в компактную
  двухколоночную сетку с собственной прокруткой timeline-вкладки;
  default layout 1060×860 показывает navigation и журнал без clipping.

GUI пока не поддерживает воспроизведение timeline, внешний file drop, undo/redo,
multi-track, transitions или nested groups. Cache хранит только проверенные
normalized clips и не является persistence проекта. Stop actions скрыты для
legacy/injected backend без явной safe capability и через
`VIDEO_CHRONICLE_CANCEL_UI=0`. Overlay ограничен утверждёнными token formats;
custom date не принимает `strftime`/FFmpeg expressions, animation и keyframes
отсутствуют.

## CLI

Принципы CLI:

- параметры имеют явные имена и справку `--help`;
- прогресс выводится краткими сообщениями по каждому файлу;
- ошибки отдельных медиафайлов не останавливают всю обработку;
- критические ошибки завершают процесс ненулевым кодом;
- подробности ошибок записываются в `errors.log` рядом с результатом.

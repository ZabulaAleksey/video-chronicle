# Состояние проекта для AI

## Текущий этап

Этапы 00–07 завершены. Следующий этап — 08, явные Join/Chronicle modes; его
decision gate ещё не утверждён. Default PySide6 GUI строит plan и
representative overlay preview через application services и запускает тот же
immutable plan вне UI thread. Whole-CLI `QProcess` сохранён только как явный
диагностический fallback. Runtime-очередь, durable storage и кэш отсутствуют.

Подготовленный ограниченный срез этапа 08 хранится в `docs/AI_PLAN.md`. Этапы 01–17
разделены на самостоятельные project prompts в `prompts/stages/`; они
загружаются по одному и не заменяют SPEC или текущий план.

## Текущая истина

- `src/video_chronicle/` содержит единственный production path:
  `domain → ports → application → pipeline adapters`;
- `src/video_chronicle/metadata.py` реализует утверждённую DATE-001 policy и
  отдаёт typed provenance/conflict/timezone result;
- `src/video_chronicle/overlay.py` реализует immutable OVERLAY-001 config,
  font identity policy и approved formats/positions/ranges;
- `src/video_chronicle/project.py`, `repository.py` и `serialization.py`
  реализуют MODEL-001: stable timeline IDs/order, immutable export snapshot,
  job transitions, strict schema v1 и in-memory repository;
- `join_media.py` — тонкий compatibility shim и direct-source entry point;
- доступны прямой CLI и application-service GUI без сервера и базы данных;
- `src/video_chronicle/gui_services.py` управляет `QThread` workers для
  `plan_export`/`execute_plan`, а `video_chronicle_gui.py` показывает preview,
  не копируя медиалогику;
- `docs/ARCHITECTURE.md` и `docs/DESIGN.md` описывают только реализованное;
- целевое развитие Timeline Builder описано отдельно в
  `specs/features/timeline-builder.spec.md` и не считается готовой функцией;
- проектный контекст дополняет общую AI Dev Team, не создавая второй набор
  универсальных agents, hooks, MCP или Git-процессов;
- `specs/system.spec.md` фиксирует системные инварианты, а feature SPEC —
  утверждённое и черновое пользовательское поведение.

## Реализовано

- сортировка видео и фотографий по дате;
- получение дат из метаданных и имён файлов;
- нормализация до 1600×900, 60 FPS, H.264/AAC;
- русская сокращённая метка дня недели;
- обработка файлов без аудиодорожки;
- пропуск повреждённых элементов с журналированием;
- переносимые пути от домашнего каталога пользователя;
- GUI-выбор входа/результата и параметров FFmpeg/FFprobe, CRF и preset;
- явное подтверждение перезаписи, объединённый журнал процесса и проверка
  результата после кода завершения;
- асинхронный preview accepted/skipped items с порядком, выбранной датой,
  provenance, timezone, conflicts и причинами пропуска;
- invalidation preview при изменении формы, loading/empty/error/populated/stale
  состояния и доступный layout 820×660 через прокрутку;
- вкладка настройки date overlay, representative 640×360 preview и единый
  config для preview и всех accepted items экспорта;
- overlay on/off и пути шрифтов с Unicode/пробелами/апострофами подтверждены
  реальным FFmpeg 9.0.1; literal `%03d` photo path не расширяется в sequence;
- завершённый characterization baseline дат, сортировки, FFmpeg argv, ошибок,
  partial success, коллизий и неизменности исходников;
- синтетический mixed photo/video smoke на FFmpeg/FFprobe 9.0.1;
- устанавливаемый пакет версии 0.2.0 с console/GUI entry points и группой
  зависимостей `dev`;
- 157 успешно пройденных unit/contract/GUI/integration тестов, включая реальный
  FFmpeg smoke;
- два symlink/reparse-specific теста корректно пропущены в текущем
  Windows-окружении без права на создание symbolic link;
- атомарная no-replace финализация закрывает коллизию, возникшую уже во время
  длительного рендера.

## Локальные зависимости

- `ffmpeg/` — чистый upstream-репозиторий исходников FFmpeg;
- `ffmpeg1/` — Windows runtime с FFmpeg и FFprobe;
- оба FFmpeg-каталога намеренно исключены из основного Git;
- `.venv/` — игнорируемое локальное окружение Python с PySide6 и pytest.

## Известные ограничения

- полный прогон на пользовательской медиатеке после переноса не выполнялся;
- после нового клонирования FFmpeg необходимо установить отдельно;
- версии FFmpeg/FFprobe старше 9.0.1 могут работать, но не входят в
  подтверждённый baseline;
- безопасная отмена GUI отсутствует, потому что остановка родительского Python
  пока не гарантирует остановку дочернего FFmpeg на Windows;
- SQLite, ExifTool, Pydantic и OTIO остаются неутверждёнными кандидатами;
  PySide6 принят только для GUI.

## Следующая задача

Начать этап 08: сначала утвердить в feature SPEC различия Join/Chronicle,
defaults, CLI migration и допустимую матрицу mode × overlay × media type; затем
ввести mode как данные плана без второго медиаконвейера. Подготовленный срез
находится в `docs/AI_PLAN.md` и `prompts/stages/08-join-chronicle-modes.md`.

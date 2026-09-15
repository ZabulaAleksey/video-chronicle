# План развития

Статусы ниже относятся к реализации. Упоминание будущей возможности не
означает, что она уже присутствует в приложении.

## Выполнено

- базовый конвейер нормализации и объединения медиа;
- перенос проекта в `~/codex-workspace/video-chronicle`;
- выделение отдельного GitHub-репозитория;
- отделение локальных FFmpeg-зависимостей от истории приложения;
- этап 00: объединение проектного контекста с общей AI Dev Team без
  дублирования канонических документов и automation.
- внеочередной ограниченный срез GUI-001: PySide6-форма запускает совместимый
  legacy CLI через `QProcess`, показывает журнал и сохраняет явную семантику
  перезаписи. Срез не заменяет этапы 01–05.

## Выполненный этап — 01. Discovery и baseline


- описать наблюдаемое поведение `join_media.py`: входы, даты, сортировку,
  фильтры, временные файлы, ошибки и финализацию;
- добавить characterization- и unit-тесты разбора дат и сортировки;
- добавить автоматический smoke-тест FFmpeg/FFprobe на коротких синтетических
  медиа;
- документировать проверенную минимальную версию FFmpeg/FFprobe.

Этап завершён: characterization baseline и synthetic smoke подтверждены на
FFmpeg/FFprobe 9.0.1.

## Выполненный этап — 02. Package foundation


Этап завершён: добавлены устанавливаемый `src`-package, runtime/dev dependency
groups, console/GUI entry points и временные compatibility modules без изменения
наблюдаемого CLI/GUI-поведения.

## Выполненный этап — 03. Core extraction


Этап завершён: медиаконвейер извлечён в package `domain/ports/application/pipeline`,
а root CLI оставлен тонким compatibility shim. CLI и переходный GUI сходятся в
одном production path.

## Выполненный этап — 04. Metadata/date engine


Этап завершён: DATE-001 engine детерминированно выбирает metadata/filename date,
сохраняет raw provenance, timezone и conflicts; generic UTC `creation_time`
отображается как системное локальное wall time, explicit camera tags не
пересчитываются.

## Выполненный этап — 05. Project/queue model


Этап завершён: MODEL-001 определяет stable timeline/order, immutable export
snapshot, job transitions, strict schema v1 и заменяемый repository port с
in-memory reference adapter.

## Выполненный этап — 06. GUI поверх application services


Этап завершён: default GUI строит и показывает immutable `ExportPlan`, а анализ
и экспорт вызывают канонические application services через `QThread` worker.
Whole-CLI `QProcess` сохранён только как явный диагностический fallback.

## Выполненный этап — 07. Overlay editor


Этап завершён: один immutable `OverlayConfig` управляет representative preview
и всеми элементами экспорта; GUI предоставляет ограниченные presets, а adapter
безопасно обрабатывает Unicode/апострофы, literal photo paths и font identity.

## Выполненный этап — 08. Join/Chronicle modes


Этап завершён: mode является typed policy immutable plan; Chronicle сохраняет
legacy overlay semantics, Join явно отключает подпись, а оба режима используют
одни application/pipeline adapters и проходят mixed-media smoke.

## Выполненный этап — 09. Export/progress/cancel


Этап завершён: typed progress и `JobState` lifecycle управляют одним export;
Windows Job Object/POSIX process group обеспечивают bounded whole-tree cancel,
а source identity, cleanup и atomic publication race подтверждены тестами.

## Выполненный MVP — этап 10


Этап завершён: opt-in normalized-clip cache имеет canonical identity, строгую
валидацию, clean fallback, private storage, 10 GiB/30-day policy и безопасный
interprocess lifecycle. Clean и resumed mixed-media exports эквивалентны.

## Текущий целевой v1 — этапы 11–16

- **11 — завершён:** schema v2, durable project, неразрушающие reorder/trim/groups и versioned presets;
- **12 — завершён:** removable native OTIO adapter и прошедшие benchmark FFmpeg scene suggestions за default-off flags;
- **13 — implemented_unverified:** optional local whisper.cpp adapter принят fixture tests; real model WER/CER остаётся внешним gate;
- **14 — implemented_unverified:** capability/benchmark policy реализована, software fallback обязателен; real driver benchmark не выполнен и hardware не promoted;
- **15 — implemented_unverified:** hardening, negative/full suite и tool audits выполнены; independent semantic review остаётся обязательным gate;
- **16 — blocked:** Windows-пакетирование с явной стратегией FFmpeg/metadata tools,
  лицензиями и smoke-тестом на чистой машине.

## Экспериментально / optional — этап 17

- **17 — blocked:**
  дополнительные ML/scene/timeline-адаптеры и автоматизация качества;
- каждое направление требует цели, feature flag, fallback, тестов, benchmark
  и ADR, если меняются архитектурные границы.

Текущий selector и правила запуска находятся в `docs/STAGES.md`; исторический индекс сохранён в `docs/notes/legacy-prompt-launcher.md`.

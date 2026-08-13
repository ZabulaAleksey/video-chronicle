# План развития

Статусы ниже относятся к реализации. Упоминание будущей возможности не
означает, что она уже присутствует в приложении.

## Выполнено

- базовый конвейер нормализации и объединения медиа;
- перенос проекта в `~/codex-workspace/projects/video-chronicle`;
- выделение отдельного GitHub-репозитория;
- отделение локальных FFmpeg-зависимостей от истории приложения;
- этап 00: объединение проектного контекста с общей AI Dev Team без
  дублирования канонических документов и automation.
- внеочередной ограниченный срез GUI-001: PySide6-форма запускает совместимый
  legacy CLI через `QProcess`, показывает журнал и сохраняет явную семантику
  перезаписи. Срез не заменяет этапы 01–05.

## Выполненный этап — 01. Discovery и baseline

Самостоятельный prompt: [`01-discovery-baseline.md`](../prompts/stages/01-discovery-baseline.md).

- описать наблюдаемое поведение `join_media.py`: входы, даты, сортировку,
  фильтры, временные файлы, ошибки и финализацию;
- добавить characterization- и unit-тесты разбора дат и сортировки;
- добавить автоматический smoke-тест FFmpeg/FFprobe на коротких синтетических
  медиа;
- документировать проверенную минимальную версию FFmpeg/FFprobe.

Этап завершён: characterization baseline и synthetic smoke подтверждены на
FFmpeg/FFprobe 9.0.1.

## Выполненный этап — 02. Package foundation

Самостоятельный prompt: [`02-package-foundation.md`](../prompts/stages/02-package-foundation.md).

Этап завершён: добавлены устанавливаемый `src`-package, runtime/dev dependency
groups, console/GUI entry points и временные compatibility modules без изменения
наблюдаемого CLI/GUI-поведения.

## Выполненный этап — 03. Core extraction

Самостоятельный prompt: [`03-core-extraction.md`](../prompts/stages/03-core-extraction.md).

Этап завершён: медиаконвейер извлечён в package `domain/ports/application/pipeline`,
а root CLI оставлен тонким compatibility shim. CLI и переходный GUI сходятся в
одном production path.

## Выполненный этап — 04. Metadata/date engine

Самостоятельный prompt: [`04-metadata-date-engine.md`](../prompts/stages/04-metadata-date-engine.md).

Этап завершён: DATE-001 engine детерминированно выбирает metadata/filename date,
сохраняет raw provenance, timezone и conflicts и не меняет legacy overlay.

## Текущий этап — 05. Project/queue model

Самостоятельный prompt: [`05-project-queue-model.md`](../prompts/stages/05-project-queue-model.md).

## Запланированный MVP — этапы 06–10

Этапы выполняются последовательно и только после критериев завершения
предыдущего этапа.

1. **[06 — GUI baseline](../prompts/stages/06-gui-application-services.md):** заменить переходный CLI-адаптер на application
   services, добавить проверку состава/порядка и сохранить отсутствие
   медиаработы в UI-потоке.
2. **[07 — Overlay editor](../prompts/stages/07-overlay-editor.md):** единая конфигурация подписи даты и предпросмотр.
3. **[08 — Join/Chronicle modes](../prompts/stages/08-join-chronicle-modes.md):** понятные режимы без дублирования
   медиаконвейера и с сохранением legacy join.
4. **[09 — Export/progress/cancel](../prompts/stages/09-export-progress-cancel.md):** план экспорта, прогресс, безопасная отмена,
   проверка коллизий и атомарная финализация.
5. **[10 — Resume/cache](../prompts/stages/10-resume-cache.md):** совместимые ключи, инвалидирование и безопасное
   возобновление. Этот этап завершает целевой MVP.

## Позже — целевой v1, этапы 11–16

- **[11](../prompts/stages/11-nondestructive-editing.md):** неразрушающее изменение порядка, trim, grouping и presets;
- **[12](../prompts/stages/12-timeline-interchange-scene.md):** optional timeline interchange и анализ сцен за интерфейсами;
- **[13](../prompts/stages/13-local-transcription.md):** optional локальная транскрипция с provenance модели;
- **[14](../prompts/stages/14-hardware-quality.md):** проверка возможностей оборудования, метрики качества и обязательный
  software fallback;
- **[15](../prompts/stages/15-security-hardening.md):** аудит недоверенных медиа, subprocess, путей, кэша и зависимостей;
- **[16](../prompts/stages/16-windows-packaging.md):** Windows-пакетирование с явной стратегией FFmpeg/metadata tools,
  лицензиями и smoke-тестом на чистой машине.

## Экспериментально / optional — этап 17

- **[17 — Experimental adapters](../prompts/stages/17-experimental-adapters.md):**
  дополнительные ML/scene/timeline-адаптеры и автоматизация качества;
- каждое направление требует цели, feature flag, fallback, тестов, benchmark
  и ADR, если меняются архитектурные границы.

Компактный индекс фаз и правила запуска находятся в `prompts/README.md`.

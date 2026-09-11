# Текущий план для AI

## Срез 2026-09-12 — configurable date/time overlay

- Статус: **реализован и валидирован локально в feature-ветке**
- Ветка: `feature/configurable-datetime-overlay`
- SPEC: `OVERLAY-007–009` в `specs/features/timeline-builder.spec.md`
- Scope: семантические форматы даты/времени, visibility/layout, system font
  family resolution/fallback, practical typography, project persistence и
  общий formatter для preview/export.

## Acceptance evidence

- focused overlay/project/GUI gate: `87 passed, 6 skipped`;
- полный Python gate: `313 passed, 12 skipped`;
- локальный system font inventory: `284` family / `437` file-backed faces;
- skips относятся к недоступным FFmpeg/FFprobe и platform privilege tests;
  новый real FFmpeg multiline/typography test добавлен, но локально не выполнен.

## NEXT

Работа ожидает пользовательской проверки либо явного разрешения merge.
Этап 13 optional local transcription остаётся приостановленным и не входит в
этот срез.

## Сохраняющиеся release blockers

- у проекта пока нет утверждённой `LICENSE`;
- FFmpeg остаётся отдельно устанавливаемым executable, его redistribution
  требует отдельного review этапов 15–16;
- optional adapters не считаются release-ready до общего hardening/packaging.

# Текущий план для AI

## Срез 2026-09-12–13 — configurable GUI и safe actions

- Статус: **реализован и валидирован локально в feature-ветке**
- Ветка: `feature/configurable-datetime-overlay`
- SPEC: `OVERLAY-007–009`, `GUI-TOOLS-001–005`, `EXEC-009–012` и
  `GUI-NAV-001–005` в
  `specs/features/timeline-builder.spec.md`
- Scope: семантические форматы даты/времени, visibility/layout, system font
  family resolution/fallback, practical typography, project persistence и
  общий formatter для preview/export, automatic env/PATH discovery и Windows
  WinGet bootstrap, secondary technical settings tab, объяснимый cache UX и
  раздельная безопасная остановка анализа/экспорта; default «Основное»,
  отдельный «План хронологии», reorder и meaningful editor button states.

## Acceptance evidence

- focused analysis/export cancellation gate: `53 passed, 1 skipped`;
- focused navigation/editing gate: `53 passed, 1 skipped`;
- полный Python gate: `326 passed, 12 skipped`;
- локальный system font inventory: `284` family / `437` file-backed faces;
- skips относятся к недоступным FFmpeg/FFprobe и platform privilege tests;
  новый real FFmpeg multiline/typography test добавлен, но локально не выполнен.

## NEXT

Работа ожидает пользовательской проверки либо явного разрешения merge.
Этап 13 optional local transcription остаётся приостановленным и не входит в
этот срез.

## Сохраняющиеся release blockers

- у проекта пока нет утверждённой `LICENSE`;
- FFmpeg автоматически устанавливается через WinGet на Windows при отсутствии,
  но его redistribution внутри будущего пакета по-прежнему требует отдельного
  review этапов 15–16;
- optional adapters не считаются release-ready до общего hardening/packaging.

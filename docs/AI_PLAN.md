# Текущий план для AI

## Срез 2026-09-13 — thumbnail cards и drag-and-drop

- Статус: **реализовано и проверено локально; ожидает пользовательской проверки/merge**
- Ветка: `feature/timeline-thumbnail-dnd`
- SPEC: `EDIT-008–011`, `EDIT-AC-008/009` в
  `specs/features/nondestructive-editing.spec.md`
- Scope: icon-grid accepted clips, actual local thumbnails через existing
  managed FFmpeg preview adapter, placeholder/error state, synchronized
  grid/table selection и drag-and-drop через `ProjectState.move_items`.

## Acceptance evidence

- PASS: thumbnail worker остаётся async, item failure изолирован, temporary PNG
  существует при signal delivery и удаляется после синхронной загрузки;
- PASS: single/multi-card reorder использует `ProjectState.move_items`, grid и
  table повторяют project order, partial-group move отклоняется без revision;
- PASS: анализ автоматически заполняет карточки кадрами и синхронизирует
  stable-ID selection;
- PASS: Chronicle автоматически продолжает analysis цепочкой representative
  preview и включает export после success; failure сохраняет safe disabled;
- полный локальный gate: `329 passed, 12 skipped`;
- baseline перед срезом: `326 passed, 12 skipped`.

## NEXT

Передать пользователю для визуальной проверки; merge выполнять только после
явного подтверждения.

## Сохраняющиеся release blockers

- у проекта пока нет утверждённой `LICENSE`;
- FFmpeg автоматически устанавливается через WinGet на Windows при отсутствии,
  но его redistribution внутри будущего пакета по-прежнему требует отдельного
  review этапов 15–16;
- optional adapters не считаются release-ready до общего hardening/packaging.

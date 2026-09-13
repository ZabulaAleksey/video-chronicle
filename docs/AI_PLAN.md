# Текущий план для AI

## Maintenance slice — export после смены date/time format

- Статус: **validated locally; ожидает merge approval**
- Ветка: `fix/export-after-overlay-change`
- Scope: убрать неявное создание project snapshot при простом выборе item и
  восстановить цепочку повторный analysis → representative preview → export.

## Acceptance evidence

- PASS: regression воспроизводит первый analysis, выбор item с неизвестной
  duration, смену date/time format и повторный analysis;
- PASS: после automatic representative preview кнопка export активна;
- PASS: реальные reorder/group/trim paths по-прежнему создают `ProjectState`;
- focused GUI/editing gate: `48 passed, 1 skipped`;
- полный локальный gate: `341 passed, 12 skipped`.

## NEXT

После ручной проверки получить merge approval для fix-ветки. Независимо от
этого release track остаётся заблокирован: нужен independent security review
без high findings перед этапом 16; merge, push и publication approval-gated.

## Сохраняющиеся release blockers

- у проекта пока нет утверждённой `LICENSE`;
- FFmpeg автоматически устанавливается через WinGet на Windows при отсутствии,
  но его redistribution внутри будущего пакета по-прежнему требует отдельного
  review этапов 15–16;
- optional adapters не считаются release-ready до общего hardening/packaging.

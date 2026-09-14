# Текущий план для AI

## Maintenance slice — явный GUI-режим объединения без даты и времени

- Статус: **validated locally; merged locally into main; push pending**
- Ветка: `feature/gui-combine-mode`
- Scope: представить существующий typed `join` как понятный режим
  «Объединение — без даты и времени», не создавая второй media pipeline и не
  меняя CLI machine key.

## Acceptance evidence

- PASS: GUI selector явно показывает «Объединение — без даты и времени»;
- PASS: выбор режима строит `ExportMode.JOIN` с `overlay.enabled=False`;
- PASS: preview/date-time controls явно отключены, plan summary не показывает
  внутренний англоязычный machine key;
- PASS: CLI `--mode join` и единый normalize/concat/publication pipeline
  сохраняются;
- focused GUI/mode gate: `14 passed`;
- полный локальный gate: `333 passed, 31 skipped`.

## NEXT

Локальный merge завершён; push `main` выполняется только по явному разрешению.
Release track независимо заблокирован: нужен independent security review без
high findings перед этапом 16; merge, push и publication approval-gated.

## Сохраняющиеся release blockers

- у проекта пока нет утверждённой `LICENSE`;
- FFmpeg автоматически устанавливается через WinGet на Windows при отсутствии,
  но его redistribution внутри будущего пакета по-прежнему требует отдельного
  review этапов 15–16;
- optional adapters не считаются release-ready до общего hardening/packaging.

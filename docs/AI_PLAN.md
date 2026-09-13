# Текущий план для AI

## Maintenance slice — export reuse, delta-analysis и metadata wall time

- Статус: **validated locally; independent review passed; ожидает merge approval**
- Ветка: `fix/export-delta-and-metadata-wall-time`
- Scope: сохранить export доступным после source-independent settings/edits,
  инспектировать только source delta и предпочитать явно записанное metadata
  wall time общему UTC `creation_time`.

## Acceptance evidence

- PASS: output/CRF/mode change пересобирает plan без inspection, оставляет
  export enabled и запускает export с новыми settings без обновления preview;
- PASS: repeat analysis той же папки переиспользует unchanged item и вызывает
  inspection только для changed/added, включая изменившийся skipped source;
  fingerprintless plan fail closed, другая папка получает полный analysis;
- PASS: project layout сохраняет старые edits и добавляет новый full-source item;
- PASS: changed known source обновляет metadata/duration в durable timeline, а
  невалидный rebound не публикует частично reconciled state; изменившийся
  timeline атомарно очищает stale `current_plan`/`jobs` и валидно round-trip'ится;
- PASS: QuickTime wall-clock `10:15:30+03:00` выбирается вместо общего
  `creation_time=07:15:30Z` без timezone conversion;
- focused acceptance gate: `12 passed`;
- focused subsystem gate: `126 passed, 7 skipped`;
- полный локальный gate: `350 passed, 12 skipped`.

## NEXT

Получить merge approval для fix-ветки. Независимо от
этого release track остаётся заблокирован: нужен independent security review
без high findings перед этапом 16; merge, push и publication approval-gated.

## Сохраняющиеся release blockers

- у проекта пока нет утверждённой `LICENSE`;
- FFmpeg автоматически устанавливается через WinGet на Windows при отсутствии,
  но его redistribution внутри будущего пакета по-прежнему требует отдельного
  review этапов 15–16;
- optional adapters не считаются release-ready до общего hardening/packaging.

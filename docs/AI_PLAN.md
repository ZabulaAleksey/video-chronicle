# Текущий план для AI

## Maintenance slice — local wall time для generic creation_time

- Статус: **validated locally; independent review passed; ожидает merge approval**
- Ветка: `fix/metadata-local-creation-time`
- Scope: отображать generic FFprobe `creation_time` с `Z`/`UTC` в системном
  локальном wall time, сохраняя metadata priority/raw provenance и не
  пересчитывая explicit camera/QuickTime wall-clock tags.

## Acceptance evidence

- RED→GREEN regression: `creation_time=2026-07-21T06:41:11Z` при injected
  timezone `+03:00` даёт `09:41:11`, оставаясь выбранным metadata-кандидатом;
- PASS: raw UTC value, marker `Z`/`UTC` и filename fallback сохраняются;
- PASS: explicit QuickTime wall-clock с offset не пересчитывается;
- focused metadata/CLI/core/overlay gate: `112 passed, 6 skipped`;
- полный локальный gate: `333 passed, 31 skipped`.

## NEXT

Получить merge approval для fix-ветки.
Release track независимо заблокирован: нужен independent security review без
high findings перед этапом 16; merge, push и publication approval-gated.

## Сохраняющиеся release blockers

- у проекта пока нет утверждённой `LICENSE`;
- FFmpeg автоматически устанавливается через WinGet на Windows при отсутствии,
  но его redistribution внутри будущего пакета по-прежнему требует отдельного
  review этапов 15–16;
- optional adapters не считаются release-ready до общего hardening/packaging.

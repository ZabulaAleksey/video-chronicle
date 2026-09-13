# Текущий план для AI

## Continuous track 2026-09-13 — этапы 13–17

- Статус: **этапы 13–15 implemented_unverified; этапы 16–17 blocked**
- Ветка: `feature/v1-release-track`
- Текущий scope завершён до обязательного external review gate.

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
- Stage 13 PASS: `5 passed`; CLI help и `uv lock --check` PASS.
- Stage 13 UNVERIFIED: WER/CER на real whisper.cpp/model не выполнялся, потому
  что модель не входит в project и не загружается автоматически.
- Stage 14 PASS: 10 focused tests для transcription/hardware; CLI help PASS.
- Stage 14 UNVERIFIED: FFmpeg отсутствует в текущем PATH, поэтому real
  hardware/driver quality benchmark не выполнялся и hardware не promoted.
- Stage 15 PASS: `340 passed, 12 skipped`; `uv lock --check`, `uv pip check`,
  pip-audit (0 known vulnerabilities) и Bandit (0 high/medium, 7 low) выполнены.
- Stage 15 UNVERIFIED: отсутствует независимый semantic reviewer; automated
  scanners не повышаются до этой evidence-категории.

## NEXT

Получить independent security review без high findings. Только затем начать
этап 16 на clean supported Windows VM с утверждённой project license; этап 17
дополнительно требует утверждённых hypothesis/dataset/metrics/resource budget.
Merge, push и publication остаются approval-gated.

## Сохраняющиеся release blockers

- у проекта пока нет утверждённой `LICENSE`;
- FFmpeg автоматически устанавливается через WinGet на Windows при отсутствии,
  но его redistribution внутри будущего пакета по-прежнему требует отдельного
  review этапов 15–16;
- optional adapters не считаются release-ready до общего hardening/packaging.

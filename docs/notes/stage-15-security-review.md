# Этап 15 — security review

## Scope и модель угроз

Проверены границы недоверенных media/project/transcript/cache данных,
configured executables, managed subprocess tree, temporary workspaces и atomic
publication. Противник может контролировать имена, metadata и bytes входных
файлов либо подменять derived state в пределах прав текущего пользователя, но
не считается способным переписать уже исполняемый процесс с теми же OS rights.

## Проверки 2026-09-13

- Полный regression gate: `340 passed, 12 skipped`.
- `uv lock --check`: PASS; `uv pip check`: 12 packages compatible.
- `pip-audit` по установленному locked environment: известных уязвимостей не
  найдено; local package ожидаемо отсутствует в PyPI и был пропущен.
- Bandit 1.9.4: 0 high, 0 medium, 7 low. Четыре production `assert` заменены
  явными fail-closed validation branches; оставшиеся low — три намеренно
  изолированных observational/cleanup exception handlers и четыре сообщения о
  централизованном `subprocess` boundary с `shell=False`.
- Транскрипция и hardware benchmark дополнительно отклоняют traversal через
  symlink/reparse parents. Benchmark больше не заменяет existing output и
  запускает FFmpeg с `-n`.

## Residual risks и gate

- Реальный corrupt-media corpus и внешние FFmpeg/whisper/GPU runs не прошли в
  этой среде: FFmpeg отсутствует в `PATH`, model bytes не предоставлены.
- `pip-audit --locked` не распознал `uv.lock`; аудит выполнен по `.venv`, чью
  совместимость с lock отдельно подтвердил `uv pip check`.
- Автоматические scanners являются независимым tool evidence, но не заменяют
  обязательный независимый semantic review другим reviewer. Поэтому этап 15
  остаётся `implemented_unverified`; этап 16 не разрешён до review без high
  findings.

## Bounded semantic pass — 2026-09-30

Finding `VC15-WINJOB-OWNERSHIP-01` (potential high, not exploit-reproduced):
`src/video_chronicle/process_control.py` creates a running Windows child with
`subprocess.Popen` and only afterward calls `_WindowsJob.assign`. Child
processes inherit a Job Object by default **after** the parent is associated
with it; a child created before association can remain outside the job.
`terminate_tree` checks/kills the Job Object and root, so this ordering does
not prove the whole descendant tree was contained during that interval.
Current `test_cancel_reaps_root_child_and_grandchild_inside_bound` waits for
descendants before cancellation and cannot force this creation window.
[Microsoft's Job Object contract](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject)
describes association and default child inheritance.

This is a code-order and contract finding, not a demonstrated escaped process.
The narrow repair must establish ownership before executable child code can
spawn descendants, then resume execution only after confirmed association.
Failure and cancellation must reap every process without weakening the current
bounded timeout/output behavior. A deterministic Windows regression should
force immediate child creation at the boundary; the full process-control and
project suites plus an independent semantic re-review are required. Stage 15
has no high-free review verdict and Stage 16 remains blocked.

## Rollback

Hardening delta ограничен explicit validation branches и optional adapters.
Его можно откатить одним checkpoint commit без migration project/cache schema.

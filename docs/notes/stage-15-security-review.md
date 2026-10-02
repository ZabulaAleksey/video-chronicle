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

## Night remediation — 2026-10-01

Independent child semantic review identified missing finite normalize/concat deadlines, output/log ancestor checks before mkdir/resolve and ordinary planner resource budgets under SEC-H-002/003/005. Root authorized bounded repair. Added safety helper, source preflight/hash budgets, finite managed deadlines, derived-file monitoring and pre-publication guard; CLI/GUI reject raw output/log paths before side effects. Root reviewer identified Windows reserved device/ADS gap; lexical helper and cross-platform cases added.

Final full suite with canonical E:\DEV\tools\ffmpeg\bin: 395 collected, 393 PASS/2 skipped, 58.55s. New security tests26 PASS; mode contract12 PASS; Ruff newfiles PASS. Existing accepted tests were not edited. Raw outputs docs/evidence/night-2026-10-01. Root final independent review accepted reserved-device/ADS/trailing-name rejection, meaningful regressions, lifecycle exception paths and finite bounds; no additional blocker in inspected changes. This is bounded review acceptance; Stage15 remains implemented_unverified for broader release-profile evidence. Historical scanner/supply-chain evidence is not relabeled fresh.

Important scope: finite 50ms disk polling can overshoot cap; local path stat preflight does not prevent hostile same-user TOCTOU races. Configured executable remains trusted code. Missing native GPU/model/corrupt-media corpus and packaging/license decisions retain their original gates.

Reviewer acceptance 2026-10-01: root controller independently reviewed child repair after implementation; known polling overshoot/filesystem TOCTOU limits acknowledged. No release, packaging, merge or deploy assertion.

Final third-sweep uv lock --check --offline PASS (12 packages); uv pip check --python root/.venv/Scripts/python.exe PASS (12 installed); uv audit --locked reports zero known vulnerabilities/adverse statuses in 11 dependencies. Actual full tests used supported CPython 3.11.4; lock command auto-resolved3.12.14 and reported stale ignored worktree .venv, preserved. No license inventory/clean packaging refresh is inferred.

## Fresh independent re-review — 2026-10-02

Initial current AV checkout did not contain prior security hardening. NIGHT FACTORY
authorized merge and review repairs. Candidate now retains both accepted Windows
process test variants, suspended Job assignment and incoming disk budget.
Independent security_reviewer accepted four fresh repairs: raw CLI paths before
side effects, cross-platform durable Windows aliases, strict snapshot version,
outer project/future-revision binding. Focused80 PASS; actual full suite418 PASS,
0 skips, 125.65s. No HIGH remains in inspected delta. This does not erase known
MEDIUM provisioning/build gaps: raw WinGet QProcess and machine-global wheel
build. BDX-L2 delta has now been added with those limits. Overall Stage15 remains
implemented_unverified; further automatic work is recorded in selected STAGES.

Independent read-only managed setup review20261002: BOUNDED_ACCEPTED after fixing Medium permanent wait-failure UI deadlock. Queued Qt finished/deleteLater delivers exactly one terminal callback after managed process-tree reap. 46 focused/435 full PASS, no remaining actionable lifecycle findings in this inspected delta. Explicit raw constructor/legacy paths, PATH executable provenance and no interactive setup cancellation remain documented; Stage15 remains partial. Evidence docs/evidence/night-20261002-managed-setup.

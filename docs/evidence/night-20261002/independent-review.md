# Video Chronicle Stage 15 — independent semantic security review

## Reviewed snapshot and verdict

- Repository: `E:\DEV\projects\video-chronicle`
- Branch / HEAD: `fix/av-sync-timeline-drift` / `6b65865ef128253f39dd9659e86bb92b050d2626`
- Scope: Stage `15-security-hardening`; input/path/process/file-publication/project-serialization paths; Windows suspended spawn and Job ownership; Backend DX security surface.
- Verdict: **FAIL — Stage 15 remains `implemented_unverified`; Stage 16 stays blocked.** The reviewed HEAD has actionable HIGH findings and does not contain the release-hardening implementation whose evidence is recorded on a divergent branch.

## Compact threat model

- Assets: immutable source media; project JSON, cache, model/transcript; final output and error log; local account credentials exposed implicitly by filesystem/network access; local disk availability.
- Untrusted inputs: media bytes and names, project/interchange JSON, external-tool stdout/stderr, configured paths and environment values.
- Trust boundaries: GUI/CLI to filesystem; JSON to domain/project state; application to FFmpeg/FFprobe/WinGet; private workspace/cache to atomic publication.
- Privilege boundary: desktop process and spawned tools run with the current user's rights. There is no HTTP listener, remote API, database, or authentication/authorization surface in this stage. Configured media tools are an explicit trusted-code decision; FFmpeg upstream is out of scope.

## Actionable findings

### HIGH-01 — Release write paths accept UNC/device and reparse-ancestor targets

Evidence:

- `src/video_chronicle/cli.py:85-99` resolves the output and creates `output.parent` before a local-path policy check.
- `src/video_chronicle/pipeline.py:127-140` creates the log parent and opens the leaf with `O_TRUNC`; it rejects a symlink/reparse leaf, but does not reject UNC/device paths or a symlink/reparse ancestor.
- `gui_contract.py:61-88` validates only the `.mp4` suffix and resolves the supplied path.
- `src/video_chronicle/pipeline.py:677-704` publishes without revalidating that temporary/final paths are local and do not traverse reparse ancestors.
- On exact HEAD, `video_chronicle.pipeline` exposes neither `validate_local_write_path` nor the Stage 15 local-write policy.

Impact: a supplied output/log path can trigger access to an SMB/UNC target and implicit Windows credential negotiation, or redirect write/truncate/publication through a junction/reparse ancestor. This violates `SEC-H-003`, `SEC-H-004`, and the documented local-publication boundary.

Action: port the `safety.py` local-write policy and all call sites from `1ad5e8d` (or an equivalent reviewed implementation) into the actual integration branch. Validate before `mkdir`, logging open, workspace creation, and publication; repeat validation immediately before the final write/rename. Preserve the existing no-replace/explicit-overwrite semantics and add the negative UNC/device/reserved-name/reparse tests to the integrated HEAD.

### HIGH-02 — Untrusted media can consume unbounded time and disk

Evidence:

- `src/video_chronicle/application.py:94-147` materializes and inspects all admitted sources with no count, per-file, aggregate-byte, or duration budget.
- `src/video_chronicle/domain.py:97-103` hashes each source to EOF without a maximum-size/growth budget.
- `src/video_chronicle/pipeline.py:171-205` leaves the default tool timeout as `None`; normalize at `pipeline.py:579` and concatenate use that unbounded default.
- `src/video_chronicle/process_control.py:413-478` bounds captured stdout/stderr but has no produced-file size budget.
- Exact-HEAD API evidence: `MAX_SOURCE_ITEMS=False`, `MAX_DERIVED_BYTES=False`; `run_managed_command` has no `output_file`/`max_output_file_bytes` parameters.

Impact: crafted or simply very large local media can keep FFmpeg alive indefinitely, force repeated full-file hashing, and fill the output volume before cancellation or publication. This violates `SEC-H-002` and `SEC-H-005` and is a local denial-of-service/data-availability risk.

Action: port the count/per-file/aggregate/duration limits, finite production-tool deadline, and live/final derived-file budget from `1ad5e8d`; retain cancellation checkpoints and terminate the already-owned process tree on every limit. Re-run the negative resource suite plus real FFmpeg smoke on the integrated commit.

### HIGH-03 — The documented Stage 15 implementation is not in the reviewed history

Evidence:

- `git merge-base --is-ancestor 1ad5e8d HEAD` returns non-zero.
- `1ad5e8d` is contained only by `docs/vc15-security-review-20260930`; the reviewed branch diverges from it at `019c637`.
- `HEAD..1ad5e8d` shows the missing `src/video_chronicle/safety.py`, `tests/test_security_release_bounds.py`, and production changes in application, CLI, domain, GUI services, pipeline, process control, and tooling.
- `docs/STAGES.md:7-13` records historical hardening evidence, while exact HEAD lacks the security APIs and tests above.

Impact: historical PASS/audit evidence cannot authorize release of this HEAD, and a review of only the Windows spawn patch would miss two release-blocking security gaps.

Action: integrate or port the hardening branch, resolving `process_control.py` in favor of `214fe73`'s newer suspended-spawn cleanup behavior plus the missing disk-budget additions. Then rerun all Stage 15 gates and perform a fresh independent semantic review on the integrated commit. Do not change Stage 15 to `completed` until that exact commit has no HIGH findings.

### HIGH-04 — CLI resolves and truncates a symlinked error log before validating the raw path

Evidence:

- `src/video_chronicle/cli.py:179-193` resolves `args.error_log`, then calls `configure_logging` before `_build_request`.
- The incoming hardening check is at `_build_request`, `cli.py:85-88`; it therefore runs only after the log has already been opened.
- `src/video_chronicle/pipeline.py:127-140` opens the supplied path with `O_TRUNC`. Because the CLI passed the resolved target rather than the raw symlink/reparse path, the leaf check sees an ordinary target file and cannot detect the redirection.

Impact: a chosen `errors.log` symlink/reparse can cause an unrelated same-user file to be truncated before the command rejects the request. This is a direct `SEC-H-003` preservation failure.

Action: validate the raw output and raw error-log paths at the start of `main`, before any `resolve`, `mkdir`, `validate_error_log_path`, or `configure_logging` call. Keep the later boundary recheck. Add a regression that points the error-log argument at a symlink/reparse target and proves the victim bytes remain unchanged and no log is created.

### MEDIUM-01 — Automatic WinGet installation is outside the owned, bounded process boundary

Evidence:

- `video_chronicle_gui.py:991-999` launches WinGet using raw `QProcess` with fixed argv but no timeout, bounded output drain, Job Object/tree ownership, or cancellation path.
- `video_chronicle_gui.py:2355-2366` refuses GUI close while the install is running, so a hung installer can block normal shutdown indefinitely.
- The fixed package ID/version prevents argv injection, but it does not provide lifecycle containment for the installer and its descendants.

Impact: the setup side effect can outlive or indefinitely pin the GUI, and its descendant lifecycle has weaker guarantees than the production media-tool path. This conflicts with the Stage 15 process boundary and the rule that bootstrap/fallback must not weaken security.

Action: run the pinned WinGet command through a bounded owned-process adapter, or add an equivalent Windows Job Object, timeout, bounded drain, explicit cancel/fail-closed cleanup, and tests for hang/descendant/error paths. Keep manual tool selection as a visibly degraded fallback after a confirmed stop.

### MEDIUM-02 — Backend DX security facts have no project delta owner

Evidence:

- `docs/project-context.md` contains only a short project description and the `ffmpeg1/` note; it has no `Backend DX Delta` or BDX evidence matrix.
- The project has stateful filesystem repositories/cache and external process/provider lifecycle, so it is `BDX-L2`, even though it has no network service or database.

Impact: config/redaction, local-only resource boundaries, destructive cache purge guards, provider/fallback provenance, and process-lifecycle evidence are scattered across code/docs. This contributed to a stage record that points at hardening not present in the reviewed branch.

Action: after code integration, add the minimal `BDX-L2` project delta to `docs/project-context.md`, mapping the canonical `uv` commands and evidence for config/redaction, local services/processes, test isolation, guarded `--purge-cache`, WinGet/manual fallback, CI parity, and documentation. Mark API/DB/listener/production-resource controls `N/A` with reasons; do not represent test/sandbox paths as production evidence.

### MEDIUM-03 — Windows device aliases are accepted as durable project IDs

Evidence: `src/video_chronicle/repository.py:188-193` rejects separators, colon, NUL, whitespace, `.` and `..`, but accepts Windows reserved aliases such as `CON`, `NUL`, `COM1`, `LPT1` and trailing-dot/space normalization variants. `_path("NUL")` therefore constructs `NUL.json`, which Windows treats as a device alias rather than an ordinary project file.

Impact: imported or programmatically created project identifiers can collide with device namespaces and make save/open/lock behavior fail unpredictably at the durable storage boundary.

Action: apply the same Windows reserved-name/normalization policy used for write paths to the complete generated filenames (`<project_id>.json`, `.lock`, `.bak`, `.rollback`) before any filesystem call. Add parameterized negative tests for device names, superscript COM/LPT aliases, trailing dot/space, and ordinary portable IDs.

### MEDIUM-04 — Strict project schema accepts boolean snapshot versions and cross-project editing snapshots

Evidence:

- `src/video_chronicle/serialization.py:460-470` branches on `version == 1`; Python treats `True == 1`, so `snapshot_version: true` reaches the v1 parser instead of failing strict schema validation.
- `src/video_chronicle/serialization.py:486` builds an `EditingExportSnapshot` from embedded `project_id` and `project_revision`, while `src/video_chronicle/project.py:637-662` validates referenced item IDs/jobs but never requires the snapshot identity/revision to equal the outer `ProjectState` identity/revision.

Impact: malformed project data can cross the declared identity/revision boundary and be accepted as internally consistent state. The current GUI rebind path does not directly use the persisted output target, which limits immediate write impact, but durable project/job integrity is weaker than documented.

Action: validate snapshot versions with the existing strict non-boolean integer helper, and in `ProjectState.__post_init__` require every `EditingExportSnapshot` to match `self.project_id` and the applicable project revision contract. Add negative round-trip tests with recomputed valid digests for mismatched project/revision values.

### MEDIUM-05 — Installed-wheel evidence depends on the machine-global base interpreter

Evidence: `tests/test_wheel_cli_export.py:43-46` invokes `sys._base_executable -m pip wheel --no-build-isolation`. This bypasses the active locked test environment and consumes whichever build tooling happens to be installed in the base Python.

Impact: the test can pass on a prepared workstation while a canonical clean/locked environment lacks or differs in build prerequisites. This is a Backend DX/CI-parity gap and cannot support clean-restore or release-readiness claims.

Action: build through the active `sys.executable` or a canonical project-owned `uv build`/equivalent command with pinned build requirements, then keep the isolated no-index installation and real consumer-path checks. Preserve the current documentation caveat until a clean restore is exercised.

## Integration-candidate read-back

After the original-head report, the parent agent began the authorized hardening integration. Read-only inspection of its resolved `process_control.py` found no new actionable defect: the `resume_primary` compatibility wrapper delegates to the retained `resume_primary_thread`; Windows remains `CREATE_SUSPENDED → Job assign → resume`; startup failure still kills/reaps and closes the Job; disk-output limits are checked during execution and after process exit. This does not clear HIGH-04 or the remaining medium findings, and fresh tests on the final integrated commit are still required.

### Candidate re-review — 2026-10-02

The current uncommitted integration candidate fixes the four requested review regressions:

- raw explicit/default output and error-log paths are validated before resolve, directory creation, and logger open;
- durable project IDs reuse the cross-platform Windows reserved-name/normalization guard;
- outer and nested snapshot tags use strict non-boolean integer validation;
- editing snapshots must match the outer project and cannot reference a future revision.

`editing_snapshot.project_revision <= project.revision` is the correct repository contract. Durable `save` and `restore_backup` advance the optimistic-concurrency revision while preserving the immutable snapshot. Ordinary edits clear `current_plan/jobs`, and a new export rebind creates a fresh snapshot, so strict equality would reject legitimate saved/restored states without adding execution safety.

Fresh candidate evidence: `tests/test_review_regressions.py`, `tests/test_nondestructive_editing.py`, and `tests/test_project_queue_model.py` — **80 passed in 1.42s** with locked/offline `uv`, external cache/environment and task-local basetemp. No conflict markers or `diff --check` errors were found.

Residual verdict: **no HIGH finding remains in the reviewed fixes, but Stage 15 stays partial/NO-GO for terminal completion**. `MEDIUM-01` WinGet lifecycle, `MEDIUM-02` missing Backend DX delta, and `MEDIUM-05` machine-global wheel build remain open. The parent full real-FFmpeg suite was still running at this checkpoint; its result requires separate read-back.

## Verification evidence

- `uv run --locked --offline --no-sync ... tests/test_process_control.py tests/test_nondestructive_editing.py tests/test_timeline_interchange.py tests/test_transcription.py tests/test_cache.py tests/test_gui_contract.py` — **107 passed**.
- Focused `tests/test_process_control.py` — **9 passed** on Windows, including suspended spawn, assignment/resume failure, descendant cancellation, timeout, and output-capture limit.
- `uv lock --check --offline` — lock resolved without update; current environment did not provide `pip-audit` or `bandit`, so historical vulnerability/static-analysis receipts were not promoted to exact-HEAD fresh evidence.
- Snapshot repository check before parent integration began: branch was clean and this reviewer changed no repository file. The shared checkout subsequently entered the separately owned merge/conflict-resolution operation; that state is outside this exact-HEAD review evidence.

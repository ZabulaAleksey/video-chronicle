# VC15 legacy CLI lifecycle — independent security review

Date: 2026-10-02

Repository: `E:\DEV\projects\video-chronicle`

Baseline: `c1a869368ca0633486e276d4b99d0b8da478884c`

Reviewed functional file identities:

- `src/video_chronicle/legacy_cli.py`: `B192E3D09FB8B5DEB30AF94CB020E3ECEF2DB32A8472CA62533BA84378CF096C`
- `src/video_chronicle/process_control.py`: `73F12F587A1553856968872DF5D5F6AA4082B7B8A5E1B3BD6B60C03C68955EC4`
- `video_chronicle_gui.py`: `7796CB46F6714D12FD6FB57E52713EDD312DFBAE4A6C8020438A63106FC18C6D`
- `tests/test_managed_legacy_cli.py`: `C4C9441E992E98D5B91CBA5D153750EA993CB044B8329D8440B7D6A2E3439723`

## Threat model

The changed boundary launches the trusted local Video Chronicle Python CLI from a desktop GUI. Untrusted media and user-selected paths can reach the CLI as list arguments, and the CLI may spawn FFmpeg descendants. The relevant threats are command injection, unintended working-directory/path interpretation, a hung or escaped descendant, unbounded stdout/stderr, a cancellation/completion race, inherited interactive stdin, and disclosure of local paths or environment-derived values through diagnostics. This is lifecycle containment for a trusted program; it is not an OS sandbox for a hostile executable.

The production path uses a fixed interpreter/script, `shell=False`, list argv, a fixed CLI-parent cwd, a finite 1800-second deadline, a shared 1 MiB stdout/stderr byte budget, Windows suspended launch followed by Job assignment, and typed/redacted setup errors. The outer noninteractive CLI gets `DEVNULL`; other FFmpeg consumers retain the explicit cooperative stdin-`q` policy. No raw `QProcess` fallback remains on this production path. No service listener, network request, authentication surface, deserialization format, dependency, database resource, or debug endpoint is added.

## Findings resolved during review

1. **Cancellation after worker terminal but before queued Qt delivery was accepted.** Terminal arbitration now occurs in `_LegacyThread.run()` via `OperationCancellation.complete()` before `QThread.finished` is queued. A cancellation that wins converts an otherwise successful result to `ProcessCancelled`; a terminal or safety error cannot be overwritten. Deterministic tests cover both orders.
2. **The noninteractive outer CLI inherited an open writable stdin pipe.** `run_managed_command` now has an explicit boolean stdin policy. `ManagedLegacyCli` selects `cooperative_stdin=False`, which gives the child `DEVNULL`/EOF, while existing FFmpeg users retain the default cooperative pipe. A real child waiting for stdin EOF proves this behavior.
3. **The new argv-snapshot test left deferred Qt ownership state and reproducibly aborted the following test.** The fixture now matches production parent ownership and drains `DeferredDelete`. The exact previously failing pair independently passes: `test_command_is_snapshotted_before_thread_admission` plus `test_legacy_noninteractive_stdin_is_eof`, 2 PASS.

## Independent checks

- Source readback confirms command tuple snapshot before worker admission, single terminal signal path, aggregate capture under one lock, split UTF-8 decoding per stream, callback-failure tree cleanup, constant exception display, output identity validation, and adapter reuse only after terminal delivery.
- `git diff --check`: PASS; only configured line-ending warnings were emitted.
- `test_legacy_noninteractive_stdin_is_eof` alone: 1 PASS.
- Previously failing lifecycle pair after fixture repair: 2 PASS.
- Before the fixture repair, the same pair reproduced a fatal Qt abort twice; that result is retained as negative evidence and is superseded by the repaired pair.

## Verdict

**BOUNDED_ACCEPTED for the reviewed VC15-LEGACY-LIFECYCLE functional bytes.** No current actionable security finding remains in the changed production path. Final acceptance still depends on the owner's actual-FFmpeg full locked suite and stable-index binding. This verdict does not complete whole Stage 15; the SPEC correctly retains the declared POSIX orphan/reaper limitation and the broader stage remains partial until its separate terminal gates are satisfied.

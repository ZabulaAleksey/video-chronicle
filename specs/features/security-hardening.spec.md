# SEC-HARDEN-001 — Release security hardening

- Статус: утверждён прямой командой пользователя для этапа 15
- Версия: 1.0
- Зависимости: SYS-SEC-001, EXEC-001, CACHE-001, TRANSCRIBE-001, HW-001

## Threat model и требования

- **SEC-H-001 — Assets.** Source media, project JSON, cache, transcript/model,
  output и configured executable считаются разными trust boundaries. Source
  data не становится command/path authority и никогда не изменяется.
- **SEC-H-002 — Processes.** Все production tools запускаются list argv без
  shell, с timeout, bounded output и подтверждённой остановкой process tree.
- **SEC-H-003 — Paths.** Durable/output/tool/cache boundaries отклоняют UNC,
  device paths и traversal через symlink/reparse; destructive cleanup разрешён
  только внутри marker/identity-bound private root.
- **SEC-H-004 — Publication.** Existing output не заменяется без explicit
  overwrite; derived artifacts публикуются atomically, partial files удаляются.
- **SEC-H-005 — Resource limits.** JSON/file/model/duration/item/output limits
  проверяются до resource-heavy processing; malformed external output fail
  closed и не меняет project/output.
- **SEC-H-006 — Disclosure.** Logs и errors не содержат media bytes, model
  content, environment dump или credentials; configured executable остаётся
  trusted-code decision пользователя.
- **SEC-H-007 — Supply chain.** `pyproject.toml` + `uv.lock` являются единственным
  dependency contract; compatibility, known-vulnerability и license inventory
  проверяются перед RC.

## Acceptance

### Local bounded profile (2026-10-01)

Production source admission: 4096 items, 64 GiB per source, 256 GiB aggregate; known source duration <=7 days. Managed normalize/concatenate tool default deadline is finite 1800 seconds. Individual derived files have a 64 GiB cap checked during 50ms process polling and before publication; finite polling overshoot is possible, this is not an OS disk quota. Windows output/log lexical guard rejects reserved devices, ADS, trailing-space/dot aliases and drive-relative paths before I/O; local fixed/removable drive and existing-ancestor reparse checks follow. Same-user filesystem replacement races are outside this preflight proof; no race-free adversarial filesystem guarantee. Injected pure test ports can carry symbolic source plans; production validation still requires existing regular sources.

- Negative tests покрывают malformed/oversized input, output collision,
  symlink/reparse/UNC boundaries, cache tampering, cancellation/output limits и
  отсутствие shell.
- Locked dependency compatibility проходит воспроизводимо.
- Независимый security review обязателен. До его evidence этап не получает
  `completed`, а этап 16 остаётся blocked независимо от локальных PASS.

### Review regression contract (2026-10-02)

- SEC-H-003: CLI проверяет raw output и error-log вместе с существующими
  ancestors до resolve, mkdir и открытия logger. Отклонённый путь не меняет
  существующий target и не создаёт output directories.
- SEC-H-005: durable project ID отклоняет Windows device aliases и trailing
  dot/space на всех ОС. Snapshot tags требуют integer, boolean/float запрещены.
- SEC-H-005: editing snapshot принадлежит тому же project_id и не ссылается
  на будущую project_revision. Более ранняя revision допустима: save/restore
  повышает durable revision, сохраняя immutable export snapshot; это не proof
  свежести для нового export.

### Managed GUI tool setup boundary (2026-10-02)

- VC15-BOOTSTRAP-LIFECYCLE: normal GUI entry points compose a managed setup
  adapter over existing run_managed_command. Pinned user-scope WinGet argv
  remains unchanged; no shell, finite 1800s deadline, aggregate 1MiB captured
  stdout/stderr, suspended Windows spawn/Job ownership/confirmed tree reap.
- Setup stays off the GUI thread. Timeout, output-limit, spawn/cancellation
  and process-tree errors produce one failure completion after worker reap,
  restoring manual paths/actions. Factory/start errors fail to manual setup;
  no automatic raw QProcess fallback.
- ChronicleWindow constructor with no setup factory retains its accepted
  raw-QProcess compatibility/test seam. Production main always injects the
  managed factory through build_main_window. This bounded repair does not
  establish SEC-H-002 coverage for every explicit legacy consumer.
- Configured/discovered executable is still trusted-code input; PATH selection
  provenance is not proven by lifecycle limits. No real WinGet package install
  or distribution/license approval is inferred from synthetic child tests.
- Acceptance: unchanged accepted GUI tests, composition and failure-state tests,
  real managed timeout/output/success/cancel children and worker cleanup, full
  locked suite, independent review. Stage15 stays partial until terminal review.

- Qt queued finished -> deleteLater is the worker lifecycle authority after
  managed runner confirms tree/Job reap; GUI does not synchronously join.
  Adapter cancellation is proven as a port; current GUI close waits for setup
  completion/deadline and does not expose interactive setup cancellation.

### Managed legacy GUI CLI boundary (2026-10-02)

- VC15-LEGACY-LIFECYCLE: explicit legacy-cli mode uses the existing owned
  run_managed_command port outside the GUI thread, list argv, CLI parent cwd,
  UTF-8 environment, finite1800s deadline and aggregate1MiB output budget.
  Outer noninteractive Python CLI stdin is DEVNULL/EOF; existing FFmpeg
  cooperative stdin-q policy stays enabled for other consumers.
  No raw QProcess launch or automatic unsafe fallback is permitted here.
- Bounded stdout/stderr chunks reach the GUI while the child runs; decoder
  preserves split UTF-8. Started denotes worker admission. Completion is emitted
  exactly once after runner tree/pipe cleanup, including failed spawn, timeout,
  overflow and cancellation. The adapter is reusable after terminal delivery.
- Legacy argv, nonzero/crash messages and new-output identity verification
  remain unchanged. No new interactive cancellation UI or artifact rollback is
  claimed: legacy CLI still owns atomic publication; a CLI-published output on
  later process failure is not treated as successful by the adapter.
- Acceptance: unchanged GUI contracts plus actual hanging descendant, output
  overflow, live split-UTF8, cancellation and repeat-run regressions; full locked
  suite and independent review. Stage15 remains implemented_unverified pending
  its complete terminal gate, and POSIX orphan/reaper limitations stay explicit.

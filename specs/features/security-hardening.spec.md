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

- Negative tests покрывают malformed/oversized input, output collision,
  symlink/reparse/UNC boundaries, cache tampering, cancellation/output limits и
  отсутствие shell.
- Locked dependency compatibility проходит воспроизводимо.
- Независимый security review обязателен. До его evidence этап не получает
  `completed`, а этап 16 остаётся blocked независимо от локальных PASS.

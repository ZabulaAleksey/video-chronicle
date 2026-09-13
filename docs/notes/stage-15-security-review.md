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

## Rollback

Hardening delta ограничен explicit validation branches и optional adapters.
Его можно откатить одним checkpoint commit без migration project/cache schema.

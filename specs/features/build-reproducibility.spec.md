# VC15-WHEEL-BOOTSTRAP — locked build workflow

Status: принят Night Factory запуском для existing READY DX tail Stage15;
не активирует Stage16 distribution или product license decision.

- Повторно использовать existing setuptools/wheel build backend и uv manager.
  Existing dev extra получает exact verified setuptools84.0.0/wheel0.48.0;
  uv.lock regenerates штатным uv без обновления unrelated runtime packages.
- Project build command проверяет locked graph и installed build versions,
  работает в project venv, затем uv build --no-build-isolation --python с этим
  interpreter. Global pip/setuptools не участвуют в canonical build path.
- Build subprocess ограничен deadline/output/process-tree boundary; output
  directory не перезаписывает existing wheels. Offline mode поддерживается.
- Clean-room proof: fresh venv WITHOUT pip/system-site-packages, locked runtime
  requirements export и offline install через uv; установить built wheel,
  подтвердить package origin внутри fresh environment. CLI help + actual
  synthetic media export/ffprobe/source hashes и real offscreen GUI composition
  без WinGet install подтверждают installed consumer paths.
- Accepted legacy wheel tests остаются без изменений и классифицируются как
  host compatibility evidence, а новый clean-room test даёт independent gate.
- Требуется full suite, lock consistency, dependency security audit, build
  before/after versions/hashes и актуальный BDX Delta. Stage15 terminal security,
  clean VM/cross-OS distribution/Android/license acceptance не заявляются.

Primary sources: https://pypi.org/project/setuptools/84.0.0/,
https://pypi.org/project/wheel/0.48.0/,
https://docs.astral.sh/uv/concepts/projects/build/.

Review acceptance: failed/timeout/output-limit builds leave no published project wheel; private same-filesystem staging is cleaned and complete zip-validated wheel is atomically promoted without overwriting any existing file. Test actual manifest-lock inconsistency before output creation, not just installed tool-version drift. Evidence digests bind exact versioned artifact bytes; raw captured hashes are separately labelled.

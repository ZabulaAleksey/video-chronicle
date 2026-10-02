# VC15 legacy CLI — final index readback

Date: 2026-10-02

- Repository: `E:\DEV\projects\video-chronicle`
- Baseline: `c1a869368ca0633486e276d4b99d0b8da478884c`
- Stable index tree: `b52f5a14e2585d5ece2c69eef6843dd3aa04e132`
- `git cat-file -t`: `tree`
- Read-only index comparison against the tree: exact (`git diff --cached --quiet <tree>` returned 0)
- Payload: 18 files, 339,348 bytes
- Staged raw full-index record: 1,226 bytes, SHA-256 `1bb01e7f173e7676d0a14ec308046d204ad02a11889877afddf4943bf98e8043`
- Full staged file table: 9,215 bytes, SHA-256 `90164866ba0db9e9f27023be6c9bb849a4a8197422df1f3fd957723abd0158ec`

Every staged blob was read directly through `git show :<path>` and compared with `work/vc-legacy-index-audit.json`: 18/18 SHA-256 values match and the recomputed byte total is 339,348. The four functional hashes are identical to the independently accepted review. `git diff --cached --check` passes.

The public-content scan found no user-home path, personal email, credential/token/private-key pattern, real media payload, authentication data, dependency or runtime-config change. The evidence contains only count-only pytest output, portable `${DEV_ROOT}` tool paths, source hashes, known limitations, and the approved repository path `E:\DEV\projects\video-chronicle`.

Owner verification is bound to this functional content: actual FFmpeg/FFprobe 9.0.1, 458 PASS, 0 skips, 239.61 seconds. Existing accepted test bytes are unchanged. The earlier 452/2-skip and 457/0-skip captures remain explicitly nonterminal historical evidence.

Verdict: **ACCEPTED for VC15-LEGACY-LIFECYCLE and this exact staged index.** No actionable security or publication-content finding remains. Whole Stage 15 remains partial; dependency-license provenance and the whole SEC-H terminal review remain separate gates, as recorded in canonical STAGES/SPEC.

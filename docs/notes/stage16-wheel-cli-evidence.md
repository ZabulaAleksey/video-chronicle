# Stage 16 installed-wheel CLI rehearsal (local only)

2026-09-30: an isolated `--no-deps` wheel install ran all three text CLI help
entry points. A two-source, synthetic MP4 export via the installed package CLI
and portable FFmpeg 9.0.1 succeeded on Windows. Original file SHA-256 digests
were unchanged. The output was H.264/AAC, 2.021333 seconds and 61,949 bytes;
SHA-256 `8b834713ff2c8e3fc122e61180af00b25eb03ef1b9bd73334266caac3455cb1a`.
The first attempted input names lacked supported dates and were correctly
rejected; the reproducible regression uses dated `VID_...` names.

Regression read-back: `tests/test_wheel_cli_export.py` 1 PASS with portable FFmpeg;
full locked project suite 370 PASS with real FFmpeg and `-p no:cacheprovider`
(isolated short `--basetemp`).

This is package consumer-path evidence only. `--no-deps` does not prove clean
dependency restore or GUI launch. Project LICENSE, FFmpeg redistribution,
independent Stage 15 review and a clean VM remain open release gates.

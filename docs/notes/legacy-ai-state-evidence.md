# Сохранённые факты прежнего AI state

- `docs/AI_PLAN.md` SHA-256 source worktree `ed6bef970d155ce9a3cb15019fb03a1f8890a30d2e21b52384f9e1a4131ca10c`; полный исходник доступен через Git parent миграции.
- `docs/AI_STATUS.md` SHA-256 source worktree `7e9f8abc9c602e99ec9a7f3406332830dd99124500ffb77339124dab80066619`; полный исходник доступен через Git parent миграции.

Локальный `main` до миграции `11a0c0d` чистый и опережает GitHub `main=de9ef4b` на пять commit: `496c59d`, `d3e5e8a`, `f8e44a8`, `5c29390`, `11a0c0d`. Они содержат export-plan reuse, local wall time для generic FFprobe `creation_time` и явный GUI `join` без date/time overlay. Исторический полный gate для последнего изменения: 333 PASS, 31 skipped; focused 14 PASS. Release Stage 15 `implemented_unverified`: ранее 340 PASS, 12 skipped, scanners/lock PASS; обязательный независимый semantic security review без high findings не проведён. Stage 16 packaging и Stage 17 experiments остаются blocked, `LICENSE` не утверждена, FFmpeg redistribution требует review. Последние пять commits локально объединены, но по этому снимку не опубликованы и не released. Отдельный `ffmpeg/` upstream Git root и `ffmpeg1/` не затронуты.

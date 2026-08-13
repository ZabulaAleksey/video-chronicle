# Этап 16 — Windows packaging и release candidate

## Цель и release gate

Создать воспроизводимую Windows-сборку с явной стратегией Python/Qt,
FFmpeg/FFprobe/metadata tools, лицензий, обновления и диагностики на чистой машине.

## Зависимости и контекст

- Этап 15 завершён без high security findings; release feature set заморожен.
- Прочитать system/feature SPEC, architecture, dependency/licensing decisions,
  TESTING/SECURITY, supported Windows matrix. Создать release `AI_PLAN`.

## Scope / non-goals

- Выбранный packager, signed/hashed artifacts where available, bundled-or-
  discovered tool policy, licenses/notices, clean-machine install/run/export.
- Не публиковать и не push artifacts без прямого разрешения пользователя;
  не добавлять auto-update без отдельной SPEC/security model.

## Области и контракты

- Разрешены: packaging config/scripts, assets, manifests, license notices,
  release tests/docs, минимальные runtime fixes.
- Запрещено включать локальные `ffmpeg/`/`ffmpeg1/` целиком без license/size
  decision и provenance.

## Tests и gates

- Reproducible build; clean supported Windows VM; GUI launch, dependency
  discovery, mixed-media export, Unicode path, cancel/resume if included;
  uninstall/upgrade and antivirus false-positive notes.
- Release review, security review and license inventory обязательны.

## DoD / artifacts / rollback

- Versioned RC artifact, checksums, notices, install/run/export report и known
  limitations готовы; публикация ожидает отдельного разрешения.
- Rollback — предыдущий подписанный/проверенный artifact; packaging не меняет
  project/cache schema без migration plan.

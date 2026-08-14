# INTEROP-001 — Optional OTIO interchange и scene suggestions

- Статус: утверждён и реализован на этапе 12
- Версия: 1.1
- Родительская SPEC: `timeline-builder.spec.md`
- Зависимости: EDIT-001, EXEC-001, system path/process invariants

## 1. Решение continue

Эксперимент продолжается в двух удаляемых adapters:

1. native OpenTimelineIO JSON `.otio` через optional
   `opentimelineio==0.18.1` (Apache-2.0);
2. scene suggestions через уже используемый FFmpeg 9.0.1 filter `scdet`, без
   новой ML/runtime зависимости.

CMX3600 отклонён из-за внешнего/default rate и frame/timecode-loss. FCPXML
отклонён из-за Apple-specific XML/resource/URL surface и plugin dependency.
PySceneDetect 0.7.x остаётся только challenger: NumPy/OpenCV и отдельный
version/license surface не оправданы до измеренного провала `scdet`.

Adapters не входят в core project schema v2. Их удаление не требует migration.

## 2. Feature flags и fallback

- `VIDEO_CHRONICLE_EXPERIMENTAL_OTIO=1` включает OTIO actions; default `0`.
- `VIDEO_CHRONICLE_EXPERIMENTAL_SCENE=ffmpeg-scdet` включает detector; default
  `off`.
- Без flag или optional OTIO dependency application/CLI/GUI сохраняют EDIT-001
  поведение; import/export/detection возвращают явное unavailable состояние.
- Никакие модели, plugins или binaries не скачиваются автоматически.

## 3. Adapter-neutral contracts

Qt-free DTO `InterchangeTimeline` содержит только project ID/revision,
ordered clips (`item_id`, local source path, integer `in_us/out_us`, optional
group ID) и warnings. Он не содержит executable, argv, output/cache root или
OTIO objects.

`TimelineInterchangePort`:

```text
export_timeline(InterchangeTimeline) -> bytes
import_timeline(bytes, known_project) -> ImportResult
```

Import всегда возвращает proposal. Он не изменяет `ProjectState`; пользователь
отдельно подтверждает применение через существующие EDIT-001 operations.
Unknown/missing project item ID не создаёт новый source автоматически.

`SceneSuggestionPort.detect(source, resolved_trim) -> tuple[CutSuggestion, ...]`.
Suggestion содержит `item_id`, `timestamp_us`, finite `score`, detector/version,
threshold и settings digest. Он не является trim/group edit и не применяется
автоматически.

## 4. Утверждённый OTIO subset

Разрешено ровно:

`Timeline.1 → Stack.1 → один Track.1(kind=Video) → Clip.2`,
`ExternalReference.1`, `TimeRange.1`, `RationalTime.1`.

Запрещены Gap, Transition, nesting, effects, markers, generators, audio tracks,
multiple media references и plugin schemas. `target_url` — только local `file:`
reference, нормализуемая к existing known source; remote schemes, UNC/device,
relative traversal и symlink/reparse targets отвергаются.

Экспорт использует `rate=1_000_000` и integer `value`, поэтому native project µs
представимы точно. Import требует finite `rate > 0`, `value >= 0` и positive
duration, преобразует через `Decimal` и отвергает ошибку представления больше
0.5 µs, negative values, invalid trim/min-frame и conflicting Video Chronicle
metadata. Foreign bounded metadata даёт warning и отбрасывается; lossless
foreign round-trip не обещается.

Identity resolution выполняется детерминированно: trusted
`metadata.video_chronicle.item_id` используется только при точном совпадении
project ID/revision. Иначе canonical local `ExternalReference.target_url`
связывается ровно с одним known source текущего проекта. Ноль или несколько
совпадений дают warning/unmapped proposal и никогда не auto-bind. Foreign OTIO
без Video Chronicle metadata поддерживается только через этот exact-path match.

OTIO dependency импортируется лениво только внутри adapter. Core modules,
schema v2 и default install не импортируют OTIO types.

## 5. Parser/resource limits

До вызова OTIO parser выполняется bounded JSON preflight:

- UTF-8 file не более 32 MiB, top-level object, NaN/Infinity запрещены;
- глубина до 32, до 262144 рекурсивно посчитанных JSON scalar/container nodes,
  до 4096 clips;
- строка до 4096 chars;
- metadata до 64 KiB, depth 8 и 1024 entries;
- только утверждённые schema names/versions и structural fields;
- никакого filesystem/tool access до полного structural validation.

Ошибка лимита/структуры возвращает diagnostics и не меняет project/source.

Лимиты 32 MiB/262144 nodes уточнены по принятому golden на 4096 clips:
native OTIO занимает 2 834 552 bytes и 131 101 рекурсивно посчитанный node.
Первоначальные 4 MiB/8192 nodes противоречили `INTEROP-AC-001`; отдельные
ограничения depth/string/metadata/clip count сохраняют bounded preflight.

## 6. Scene detector `ffmpeg-scdet-v1`

Adapter запускает trusted selected FFmpeg list-argv/no-shell в существующем
managed process tree и применяет `scdet=threshold=10.0`. Читаются только bounded
`lavfi.scd.score` и `lavfi.scd.time`; timestamps переводятся в integer µs и
ограничиваются resolved trim. Timeout/output-limit/cancel используют EXEC-001.

`CutSuggestion.timestamp_us` всегда source-relative. Если detector получает
rebased trimmed stream, canonical mapping: `source_us = trim.in_us + filtered_us`.
Значения `<= trim.in_us` или `>= trim.out_us` отвергаются как endpoints, а не
clamp; non-zero trim обязателен в tests.

Detector version: `ffmpeg-scdet-v1`; threshold 10.0 входит в settings digest.
Изменение source fingerprint, trim, tool identity или threshold инвалидирует
suggestions. Scene suggestions не входят в normalized clip cache.

## 7. Benchmark corpus и метрики

Checked-in generator создаёт deterministic low-resolution synthetic corpus с
manifest SHA-256 и exact ground truth:

- CFR 24, 25, 30000/1001 и 60 FPS;
- hard color cuts, fade/dissolve, flash и no-cut negatives;
- минимум 20 секунд media и 12 hard-cut boundaries.

One-to-one maximum matching использует tolerance `max(one decoded frame, 50ms)`.
Отчёт включает precision/recall/F1 hard cuts, FP/min negatives, p95 boundary
error, wall/media ratio и 3-run timestamp determinism.

Continue criteria на документированном FFmpeg 9.0.1 baseline:

- precision ≥ 0.95, recall ≥ 0.90, F1 ≥ 0.92;
- negative false positives ≤ 0.20/min;
- p95 error ≤ one decoded frame;
- identical suggestions 3/3;
- aggregate runtime ≤ `max(0.75 × media duration, 5 s)`.

Если критерии не достигнуты, scene adapter и flag удаляются. PySceneDetect
исследуется только если улучшает F1 минимум на 0.05 без нарушения performance,
dependency и license gates.

Принятый Windows baseline FFmpeg 9.0.1 дал precision/recall/F1 `1.0/1.0/1.0`,
`0` negative FP/min, p95 `0 µs`, одинаковые timestamps `3/3` и wall/media
`0.080509`. Решение этапа 12 — **CONTINUE** для `ffmpeg-scdet-v1` за default-off
feature flag.

## 8. Критерии приёмки

- **INTEROP-AC-001.** Golden OTIO export→import→export сохраняет semantic order,
  IDs, local refs и exact µs для 0/1/4096 clips; rates 24, 25, 30000/1001, 60 и
  1_000_000 импортируются с документированным rounding/error contract. Foreign
  OTIO без VC metadata связывается exact-path; zero/duplicate/path conflicts
  остаются unmapped warnings.
- **INTEROP-AC-002.** Каждый forbidden schema/field, NaN/Inf, remote/traversal,
  bad bounds, oversized/deep/node/metadata payload отвергается до I/O/mutation.
- **INTEROP-AC-003.** Import возвращает immutable proposal/warnings; explicit
  apply создаёт новую project revision, old preview становится stale; cancel или
  отказ оставляет project byte-identical.
- **SCENE-AC-001.** Synthetic benchmark достигает численных continue criteria и
  сохраняет JSON/Markdown report с environment/tool identity.
- **SCENE-AC-002.** Suggestions deterministic, bounded, связаны с item/trim и не
  применяются автоматически; non-zero trim подтверждает source-relative mapping,
  malformed/noisy output/timeout/cancel безопасны.
- **OPTIONAL-AC-001.** Без flags/dependency default tests и package entrypoints
  работают; import graph core не содержит OTIO, а удаление adapters не меняет
  project schema/migration.
- **LICENSE-AC-001.** Optional extra фиксирует OTIO 0.18.1/Apache-2.0. FFmpeg
  остаётся отдельно устанавливаемым executable; redistribution и отсутствие
  project LICENSE блокируют release до этапов 15–16.

## 9. Rollback/drop

Удаляются optional extra, adapter modules, flags и GUI actions. Project schema
v2, cache и exports остаются читаемыми без migration. Imported proposals и
scene suggestions не являются persisted authority и могут быть отброшены.

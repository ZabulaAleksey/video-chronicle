# EDIT-001 — Неразрушающее редактирование timeline

- Статус: утверждённый feature contract этапа 11
- Версия: 1.0
- Родительская SPEC: `timeline-builder.spec.md`
- Зависимости: MODEL-001, GUI-APP-001, OVERLAY-001, MODE-001, EXEC-001, CACHE-001

## 1. Цель и границы

Пользователь может менять порядок, задавать in/out trim, объединять соседние
элементы в именованные группы и применять versioned render presets. Эти
операции изменяют только проект и immutable export snapshot: исходные файлы не
переименовываются, не перемещаются и не перезаписываются.

Не входят: multi-track NLE, transitions, effects graph, nested groups,
collaboration/cloud, arbitrary FFmpeg expressions, общий event sourcing и
general undo/redo stack.

## 2. Термины и единицы

- `Timeline` — date-sorted каталог известных источников MODEL-001; он остаётся
  baseline и не переписывается ручным reorder.
- `TimelineLayout` — точная ручная перестановка всех `Timeline.item_ids` плюс
  edits/group membership.
- `source_duration_us` — effective длительность в целых микросекундах. Видео
  получает её из первого экспортируемого `0:v:0` stream: сначала
  `duration_ts × time_base`, затем bounded fallback
  `format.duration`, с `Decimal` и округлением вниз. Фото имеет 2_000_000 µs.
- `TrimRange` — полуоткрытый интервал `[in_us, out_us)`. Persisted full-source
  identity — `{in_us: 0, out_us: null}`; runtime snapshot всегда содержит
  разрешённый integer `out_us`.
- Один целевой кадр равен 16_667 µs. Пользовательский trim короче одного кадра
  недопустим.

## 3. Domain contract

### EDIT-001 — Layout и reorder

`TimelineLayout.entries` является точной перестановкой `Timeline.item_ids`: без
пропусков, дублей и неизвестных ID. `move_items(item_ids, before_item_id)`
сохраняет взаимный порядок переносимых и остальных элементов. Каждая операция
возвращает новый immutable state и увеличивает `project.revision` ровно на один.

### EDIT-002 — Trim

- Видео: `0 <= in_us < out_us <= source_duration_us`.
- Фото: `in_us == 0`, `16_667 <= out_us <= 2_000_000`.
- `out_us=null` означает полный источник. Пользовательский trim для элемента с
  неизвестной duration отвергается до preview/export.
- Runtime применяет точный video `trim/atrim + setpts/asetpts`; keyframe seek не
  является источником истины. Фото получает эффективную `-t` длительность.
- Изменение trim не меняет source path/fingerprint и не записывает source.

### EDIT-003 — Groups

Группа — именованный непрерывный блок минимум из двух элементов. Один item
может входить не более чем в одну группу; nesting и пересечения запрещены.
Перемещение группы сохраняет её внутренний порядок. Отдельный item нельзя
вынести из группы без `ungroup`. Group влияет на UI и reorder, но не меняет
нормализованные bytes и cache identity.

### EDIT-004 — Versioned presets

`RenderPreset` содержит stable `preset_id`, положительную монотонную `version`,
непустое имя и полные `RenderSettings`: `mode`, `overlay`, `crf` и
`encoder_preset`. Изменение создаёт новую immutable версию; старые snapshots
остаются воспроизводимыми.

Input/output, FFmpeg/FFprobe paths, overwrite, cache и `keep_work` в preset не
входят. Export фиксирует одновременно `PresetRef` и resolved settings; поздний
lookup во время выполнения запрещён. Новая версия/имя при тех же resolved
settings не меняет normalized cache identity.

### EDIT-005 — Immutable editing export snapshot

Snapshot версии 2 содержит:

- `project_id` и `project_revision`;
- ordered clips: `item_id`, resolved `{in_us, out_us}`, optional `group_id`;
- определения групп;
- `PresetRef` и resolved `RenderSettings`;
- output MP4 и overwrite policy.

`plan-v2-*` вычисляется как SHA-256 canonical sorted-field UTF-8 JSON всех
полей, кроме самого `plan_id`. Executable paths, argv и cache root не входят.
Runtime `ExportPlan` содержит effective reordered `MediaItem` и тот же snapshot;
третья timeline/plan модель не создаётся.

`apply_project_state(analyzed_plan, project_state)` связывает сохранённые IDs с
текущим inspection, разрешает trims/settings и создаёт snapshot. Новые файлы не
добавляются молча; отсутствующие/повреждённые известные источники остаются
диагностикой, но edits не теряются.

## 4. Preview/export/cache parity

- Preview и `execute_plan` получают один объект с одним `plan_id`.
- Любой reorder/trim/group/preset edit создаёт новый snapshot и делает старый
  preview stale; export блокируется до актуального preview.
- Representative preview использует первый effective item и кадр на `in_us`.
- Full-source trim сохраняет `clip-v1`/manifest-v1/`normalize-v1` reuse.
  Реальный trim использует `clip-v2`/manifest-v2/`normalize-v2` и включает
  resolved `{in_us,out_us}`. Manifest v2 сохраняет тот же path-free exact-field
  contract, но имеет `version=2` и key prefix `clip-v2-`.
- Reorder, group ID/name, output, overwrite и сам `PresetRef` cache не
  инвалидируют. Изменившиеся resolved mode/overlay/CRF/encoder settings —
  инвалидируют через существующую identity.
- Cache enumeration, actual-byte accounting, interprocess lock, retention и
  protected purge одинаково охватывают `clip-v1-*` и `clip-v2-*`. Reader
  выбирает strict schema по key prefix/version; смешение prefix/version и extra
  fields отвергаются. Старые cache v1 entries остаются читаемыми;
  несовместимость означает clean miss/fallback, а не ошибочный reuse.

## 5. Persistence schema v2

`video-chronicle-project` версии 2 расширяет строгую MODEL-001 schema:

- `project.revision` — неотрицательный optimistic-concurrency counter;
- `timeline.items[].media_kind` — `photo`, `video` либо `null` для мигрированного
  v1 до повторного analysis; `source_duration_us` — positive integer либо `null`;
- `layout.entries[]` — `item_id`, exact trim и optional `group_id`;
- `layout.groups[]` — stable `group_id` и name;
- immutable список всех `presets` и `active_preset`;
- tagged `current_plan.snapshot_version`: исторический v1 либо новый v2.

Неизвестная version, extra/missing fields, invalid ID/path/trim/group/preset,
revision conflict или рассогласованный digest отвергаются без записи и без
выполнения команд. Schema-level validation применяет photo-specific rule, когда
`media_kind=photo`; для мигрированного `null` разрешён только full-source trim.
После нового inspection `apply_project_state` обязан связать kind/duration и
повторить все media-specific bounds до preview/export.

### EDIT-006 — Миграция v1 → v2

Чистая миграция создаёт chronological identity layout, full-source trims,
пустые groups, `media_kind/source_duration_us=null`, `revision=0` и `legacy-default/v1`
из существующих CRF/encoder preset плюс legacy Chronicle/overlay defaults.
Исторический plan/job сохраняет v1 ID и семантику через tagged snapshot.

Первый durable save мигрированного v1 обязан сохранить исходные v1 bytes как
backup до публикации v2.

### EDIT-007 — Durable JSON repository и rollback

`ProjectRepository` эволюционирует явно: `save(state, *, expected_revision)`
возвращает опубликованный state с `revision=expected_revision+1`; `get`,
`list_project_ids` и `restore_backup(project_id, *, expected_revision)` входят в
тот же port. `JsonProjectRepository` является durable adapter.
Операция save под per-project OS lock:

1. strict-read текущей версии и проверка `expected_revision`;
2. canonical UTF-8 v2 во временный private regular file;
3. flush/fsync и повторная strict deserialize;
4. атомарная публикация предыдущих bytes как `.bak`;
5. атомарная replace project file и fsync directory.

Сбой до commit сохраняет текущий файл. `restore_backup` под тем же lock сначала
валидирует backup, мигрирует его в v2 при необходимости, сохраняет текущую
версию как rollback artifact и публикует восстановленное содержимое как новую
v2 revision `expected_revision+1`. Revision никогда не уменьшается, поэтому
stale writer после rollback отвергается. Symlink/reparse/UNC/device roots и
files запрещены. `InMemoryProjectRepository` остаётся reference adapter с той
же revision policy.

## 6. GUI contract

- После analysis редактор показывает effective order и per-item duration/trim.
- Доступны move up/down, group/ungroup, trim start/end и save/apply versioned preset.
- Save/Open работают вне UI thread и показывают conflict/migration/rollback error.
- Изменение layout/settings инвалидирует representative preview и export.
- Project save не требует export и не меняет source bytes.
- Legacy GUI/CLI без открытого проекта используют прежний date-sorted план и
  legacy settings; новые project/edit CLI flags в этом этапе не вводятся.

## 7. Безопасность и ошибки

- Все пользовательские edits валидируются до FFmpeg.
- Длительность повторно связывается с актуальным inspected item; source
  fingerprint продолжает проверяться у каждого tool boundary.
- Project payload не содержит argv и не может выбирать executable/cache/output
  вне явных UI/CLI полей текущей операции.
- Ошибка отдельного edited item следует существующей partial-success policy;
  invalid project/layout целиком отклоняется до workspace.
- Persistence locks имеют bounded wait/cancel; backup/rollback не следуют
  symlink/reparse и не удаляют неподтверждённые каталоги.

## 8. Критерии приёмки

- **EDIT-AC-001 (EDIT-001).** Property tests подтверждают exact permutation,
  стабильность move и deterministic `plan_id`.
- **EDIT-AC-002 (EDIT-002).** Table tests покрывают `0:v:0` duration extraction,
  trim bounds/null-kind/unknown duration/photo policy и exact µs round-trip;
  real FFmpeg
  длительность соответствует snapshot с допуском один target frame.
- **EDIT-AC-003 (EDIT-003).** Group create/move/ungroup сохраняют contiguity;
  overlap/nesting/partial move отвергаются; flattened export order совпадает.
- **EDIT-AC-004 (EDIT-004/005).** Preset revisions immutable/monotonic; preview
  и export имеют один `plan_id`; любая edit mutation делает preview stale.
- **EDIT-AC-005 (EDIT-006/007).** Strict v1 load → v2 migration → save/reopen
  не теряет IDs/jobs; fault injection сохраняет current bytes; backup и rollback
  воспроизводимы как монотонная новая revision; stale expected revision не
  перезаписывает save или rollback.
- **EDIT-AC-006 (EDIT-002/005).** Старый full-source cache v1 даёт hit; trim
  change даёт v2 miss, повтор даёт v2 hit, resolved preset change инвалидирует,
  reorder/group не дают miss; mixed v1/v2 prune/purge/accounting безопасны, а
  clean/resumed outputs эквивалентны.
- **EDIT-AC-007 (SYS-NFR-001, SYS-COMP-001).** Legacy CLI/MVP characterization
  зелёная; source SHA-256/size/mtime неизменны после edit/save/preview/export,
  failure и cancel.

## 9. Rollback

- Editor/runtime binding включается только при наличии валидного project v2;
  отсутствие проекта оставляет прежний MVP path.
- Schema v1 всегда читается; v2 migration не публикуется без backup.
- В случае regression GUI может скрыть editing controls, сохранив v2 payload и
  не меняя legacy export. Cache v2 entries можно игнорировать/очистить независимо.

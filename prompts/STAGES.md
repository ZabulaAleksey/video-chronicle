# Канонические этапы video-chronicle  Единый источник stage-prompts. Ниже сохранено полное содержание ранее существовавших этапов.

## 01-discovery-baseline
# Р­С‚Р°Рї 01 вЂ” Discovery Рё baseline

## РќР°Р·РЅР°С‡РµРЅРёРµ Рё Р·Р°РїСѓСЃРє

Р—Р°РІРµСЂС€РёС‚СЊ characterization baseline СЌС‚Р°Р»РѕРЅРЅРѕРіРѕ `join_media.py`. Р—Р°РїСѓСЃРєР°С‚СЊ РїРѕ
РєРѕРјР°РЅРґРµ `РќР°С‡РёРЅР°Р№ СЌС‚Р°Рї 01` С‡РµСЂРµР· `$implement-stage`. РўРµРєСѓС‰РёР№ РёСЃРїРѕР»РЅСЏРµРјС‹Р№ СЃСЂРµР·
СѓР¶Рµ РЅР°С…РѕРґРёС‚СЃСЏ РІ `docs/AI_PLAN.md`.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё Рё РєРѕРЅС‚РµРєСЃС‚

- Р­С‚Р°Рї 00 Рё GUI-001 Р·Р°РІРµСЂС€РµРЅС‹.
- РџСЂРѕС‡РёС‚Р°С‚СЊ: `specs/system.spec.md`, `FR-011`/`AC-008` feature SPEC,
  `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `docs/SECURITY.md`,
  `join_media.py`, `tests/`, `docs/AI_STATUS.md`.
- РќРµ Р·Р°РіСЂСѓР¶Р°С‚СЊ РґСЂСѓРіРёРµ stage prompts.

## Scope / non-goals

- Р—Р°С„РёРєСЃРёСЂРѕРІР°С‚СЊ РґР°С‚С‹, СЃРѕСЂС‚РёСЂРѕРІРєСѓ, С„РёР»СЊС‚СЂС‹, argv, РѕС€РёР±РєРё, partial success,
  РІСЂРµРјРµРЅРЅСѓСЋ РѕР±Р»Р°СЃС‚СЊ Рё С„РёРЅР°Р»РёР·Р°С†РёСЋ.
- Р”РѕР±Р°РІРёС‚СЊ РєРѕСЂРѕС‚РєРёР№ СЃРёРЅС‚РµС‚РёС‡РµСЃРєРёР№ FFmpeg/FFprobe smoke-test Рё РїСЂРѕРІРµСЂРµРЅРЅСѓСЋ
  РјРёРЅРёРјР°Р»СЊРЅСѓСЋ РІРµСЂСЃРёСЋ.
- РќРµ РјРµРЅСЏС‚СЊ РїСѓР±Р»РёС‡РЅС‹Р№ CLI, РјРµРґРёР°РїРѕР»РёС‚РёРєСѓ, GUI, package layout, РѕС‡РµСЂРµРґСЊ РёР»Рё РєСЌС€.
- РќРµ РёР·РјРµРЅСЏС‚СЊ `ffmpeg/` Рё `ffmpeg1/`.

## РљРѕРЅС‚СЂР°РєС‚С‹ Рё РѕР±Р»Р°СЃС‚Рё С„Р°Р№Р»РѕРІ

- РРЅРІР°СЂРёР°РЅС‚С‹: read-only inputs, list argv, explicit overwrite, atomic publish.
- Р Р°Р·СЂРµС€РµРЅС‹: `tests/`, СѓР·РєР°СЏ С‚РµСЃС‚РёСЂСѓРµРјРѕСЃС‚СЊ РІ `join_media.py`, testing/SPEC/status.
- РР·РјРµРЅРµРЅРёРµ РЅР°Р±Р»СЋРґР°РµРјРѕРіРѕ РїРѕРІРµРґРµРЅРёСЏ С‚СЂРµР±СѓРµС‚ СЃРЅР°С‡Р°Р»Р° СЂРµС€РµРЅРёСЏ РІ SPEC.

## РџСЂРѕРІРµСЂРєРё Рё quality gates

- `pytest`, synthetic media smoke, `compileall`, CLI `--help`, `git diff --check`.
- РўСЂР°СЃСЃРёСЂРѕРІРєР°: `SYS-AC-001/003/005`, `AC-008/010` в†’ tests в†’ implementation.
- РќРµРґРѕСЃС‚СѓРїРЅС‹Р№ FFmpeg РґРѕРїСѓСЃРєР°РµС‚ С‚РѕР»СЊРєРѕ СЏРІРЅС‹Р№ skip СЃ РїСЂРёС‡РёРЅРѕР№; СЌС‚Р°Рї РЅРµ СЃС‡РёС‚Р°РµС‚СЃСЏ
  РїРѕР»РЅРѕСЃС‚СЊСЋ Р·Р°РІРµСЂС€С‘РЅРЅС‹Рј Р±РµР· РІРѕСЃРїСЂРѕРёР·РІРѕРґРёРјРѕРіРѕ smoke РЅР° РґРѕСЃС‚СѓРїРЅРѕРј runtime.

## DoD, Р°СЂС‚РµС„Р°РєС‚С‹ Рё РѕС‚РєР°С‚

- РњР°С‚СЂРёС†Р° baseline Рё РІРµСЂСЃРёСЏ РёРЅСЃС‚СЂСѓРјРµРЅС‚РѕРІ Р·Р°РїРёСЃР°РЅС‹ РІ `docs/TESTING.md`.
- Characterization Рё smoke tests РїСЂРѕС…РѕРґСЏС‚; product behavior РЅРµ СЂР°СЃС€РёСЂРµРЅРѕ.
- `AI_STATUS` РѕР±РЅРѕРІР»С‘РЅ, `AI_PLAN` РїРµСЂРµРєР»СЋС‡С‘РЅ РЅР° СЌС‚Р°Рї 02.
- РџСЂРё РЅРµРѕРґРЅРѕР·РЅР°С‡РЅРѕР№ РїРѕР»РёС‚РёРєРµ РѕСЃС‚Р°РЅРѕРІРёС‚СЊСЃСЏ РґРѕ РёР·РјРµРЅРµРЅРёСЏ РєРѕРґР°; additions С‚РµСЃС‚РѕРІ
  РѕС‚РєР°С‚С‹РІР°СЋС‚СЃСЏ РЅРµР·Р°РІРёСЃРёРјРѕ, РєРѕСЂСЂРµРєС‚РЅС‹Рµ С‚РµСЃС‚С‹ РЅРµ РѕСЃР»Р°Р±Р»СЏСЋС‚СЃСЏ.


## 02-package-foundation
# Р­С‚Р°Рї 02 вЂ” Package foundation

## Р¦РµР»СЊ

РЎРѕР·РґР°С‚СЊ СѓСЃС‚Р°РЅР°РІР»РёРІР°РµРјСѓСЋ СЃС‚СЂСѓРєС‚СѓСЂСѓ Python-РїР°РєРµС‚Р°, РµРґРёРЅС‹Рµ entry points,
РєРѕРЅС„РёРіСѓСЂР°С†РёСЋ Рё Р»РѕРіРёСЂРѕРІР°РЅРёРµ, СЃРѕС…СЂР°РЅРёРІ РїРѕРІРµРґРµРЅРёРµ legacy CLI Рё GUI-001.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё Рё РєРѕРЅС‚РµРєСЃС‚

- Р­С‚Р°Рї 01 РїРѕР»РЅРѕСЃС‚СЊСЋ Р·Р°РІРµСЂС€С‘РЅ, baseline Рё FFmpeg smoke Р·РµР»С‘РЅС‹Рµ.
- РџСЂРѕС‡РёС‚Р°С‚СЊ system SPEC, `FR-011`/`AC-008`, architecture, decisions, testing,
  С‚РµРєСѓС‰РёРµ entry points Рё `AI_STATUS`.
- РџРµСЂРµРґ СЂРµР°Р»РёР·Р°С†РёРµР№ Р·Р°РјРµРЅРёС‚СЊ `docs/AI_PLAN.md` РѕРіСЂР°РЅРёС‡РµРЅРЅС‹Рј РїР»Р°РЅРѕРј СЌС‚Р°РїР° 02.

## Scope / non-goals

- `pyproject.toml`, package layout, dependency groups, logging/config boundary,
  console Рё GUI entry points, РїРµСЂРµРЅРѕСЃ С‚РµСЃС‚РѕРІ Р±РµР· РїРѕС‚РµСЂРё РїРѕРєСЂС‹С‚РёСЏ.
- РћСЃС‚Р°РІРёС‚СЊ СЃРѕРІРјРµСЃС‚РёРјС‹Р№ Р·Р°РїСѓСЃРє `python join_media.py` Р»РёР±Рѕ РґРѕРєСѓРјРµРЅС‚РёСЂРѕРІР°С‚СЊ С‚РѕРЅРєРёР№
  compatibility shim.
- РќРµ РёР·РІР»РµРєР°С‚СЊ РјРµРґРёР°Р»РѕРіРёРєСѓ, РЅРµ РјРµРЅСЏС‚СЊ РґР°С‚С‹/FFmpeg argv/UI Рё РЅРµ РїР°РєРµС‚РёСЂРѕРІР°С‚СЊ EXE.

## РћР±Р»Р°СЃС‚Рё С„Р°Р№Р»РѕРІ Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: package/entry modules, manifests, tests, README, architecture,
  decisions, status/plan.
- Р—Р°РїСЂРµС‰РµРЅС‹: `ffmpeg/`, `ffmpeg1/`, РЅРѕРІР°СЏ Р‘Р” Рё РїРѕРІРµРґРµРЅС‡РµСЃРєРёРµ РёР·РјРµРЅРµРЅРёСЏ.
- РљРѕРЅС‚СЂР°РєС‚: РїСЂРµР¶РЅРёРµ Р°СЂРіСѓРјРµРЅС‚С‹, defaults, exit codes Рё overwrite semantics.

## Tests Рё quality gates

- Р’СЃРµ tests СЌС‚Р°РїР° 01; import/install test РІ С‡РёСЃС‚РѕРј venv; РѕР±Р° entry points;
  dependency check, compileall, `git diff --check`.
- CLI parity РїРѕРґС‚РІРµСЂР¶РґР°РµС‚СЃСЏ С‚РµРј Р¶Рµ characterization-РЅР°Р±РѕСЂРѕРј, РЅРµ РєРѕРїРёРµР№ С‚РµСЃС‚РѕРІ.

## DoD / acceptance artifacts / rollback

- Package СѓСЃС‚Р°РЅР°РІР»РёРІР°РµС‚СЃСЏ РёР· Р»РѕРєР°Р»СЊРЅРѕРіРѕ checkout, CLI Рё GUI Р·Р°РїСѓСЃРєР°СЋС‚СЃСЏ.
- РђСЂС…РёС‚РµРєС‚СѓСЂР° Рё СЂРµС€РµРЅРёРµ package layout Р·Р°С„РёРєСЃРёСЂРѕРІР°РЅС‹; `AI_PLAN` РїРµСЂРµРІРµРґС‘РЅ РЅР° 03.
- РћС‚РєР°С‚: compatibility shims РїРѕР·РІРѕР»СЏСЋС‚ РІРµСЂРЅСѓС‚СЊ СЃС‚Р°СЂС‹Р№ layout РѕРґРЅРёРј commit;
  РїСЂРё РёР·РјРµРЅРµРЅРёРё CLI РѕСЃС‚Р°РЅРѕРІРёС‚СЊСЃСЏ Рё СЃРѕРіР»Р°СЃРѕРІР°С‚СЊ РјРёРіСЂР°С†РёСЋ РґРѕ РїСЂРѕРґРѕР»Р¶РµРЅРёСЏ.


## 03-core-extraction
# Р­С‚Р°Рї 03 вЂ” Core extraction

## Р¦РµР»СЊ

РР·РІР»РµС‡СЊ РёР· legacy-РјРѕРґСѓР»СЏ С‚РµСЃС‚РёСЂСѓРµРјС‹Рµ domain/application РіСЂР°РЅРёС†С‹ Р±РµР· РёР·РјРµРЅРµРЅРёСЏ
РЅР°Р±Р»СЋРґР°РµРјРѕРіРѕ CLI/GUI-РїРѕРІРµРґРµРЅРёСЏ Рё Р±РµР· РІС‚РѕСЂРѕРіРѕ РјРµРґРёР°РєРѕРЅРІРµР№РµСЂР°.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё Рё РєРѕРЅС‚РµРєСЃС‚

- Р­С‚Р°Рї 02 Р·Р°РІРµСЂС€С‘РЅ; package Рё compatibility entry points СЃС‚Р°Р±РёР»СЊРЅС‹.
- РџСЂРѕС‡РёС‚Р°С‚СЊ system SPEC, `FR-011`, `NFR-001`, `AC-008`, architecture,
  security/testing, baseline tests Рё С‚РµРєСѓС‰РёР№ package.
- РЎРѕР·РґР°С‚СЊ С‚РµРєСѓС‰РёР№ `AI_PLAN` СЃ РїРѕСЃР»РµРґРѕРІР°С‚РµР»СЊРЅС‹РјРё РјР°Р»РµРЅСЊРєРёРјРё extraction-Р±Р»РѕРєР°РјРё.

## Scope / non-goals

- Р§РёСЃС‚С‹Рµ РјРѕРґРµР»Рё/С„СѓРЅРєС†РёРё, ports РґР»СЏ probe/process/filesystem Рё application
  service РґР»СЏ plan/execute boundary.
- CLI Рё РїРµСЂРµС…РѕРґРЅС‹Р№ GUI РґРѕР»Р¶РЅС‹ РёСЃРїРѕР»СЊР·РѕРІР°С‚СЊ РѕРґРёРЅ production path.
- РќРµ СѓС‚РІРµСЂР¶РґР°С‚СЊ РЅРѕРІСѓСЋ metadata policy, РѕС‡РµСЂРµРґСЊ, persistence, cancel РёР»Рё cache.
- РќРµ РїРµСЂРµРїРёСЃС‹РІР°С‚СЊ РІСЃС‘ РѕРґРЅРёРј Р±РѕР»СЊС€РёРј РёР·РјРµРЅРµРЅРёРµРј.

## РћР±Р»Р°СЃС‚Рё Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: package core/application/adapters, legacy shims, tests, architecture.
- Р—Р°РїСЂРµС‰РµРЅС‹: РІРЅРµС€РЅРёРµ Р±РёРЅР°СЂРЅРёРєРё, UI redesign, РЅРѕРІС‹Рµ РїСЂРѕРґСѓРєС‚РѕРІС‹Рµ СЂРµР¶РёРјС‹.
- РљРѕРЅС‚СЂР°РєС‚С‹: deterministic inputs/outputs, typed public boundaries, list argv,
  atomic publish Рё РїСЂРµР¶РЅРёРµ codes/messages РІ РїСЂРµРґРµР»Р°С… СѓС‚РІРµСЂР¶РґС‘РЅРЅРѕР№ СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚Рё.

## Tests Рё gates

- Р”Рѕ РєР°Р¶РґРѕРіРѕ extraction С€Р°РіР° СЃСѓС‰РµСЃС‚РІСѓРµС‚ characterization test.
- Unit tests С‡РёСЃС‚РѕРіРѕ core, adapter contract tests, CLI/GUI parity, FFmpeg smoke,
  compileall Рё diff check.
- Reviewer РѕР±СЏР·Р°С‚РµР»РµРЅ; security review вЂ” РґР»СЏ subprocess/filesystem boundary.

## DoD / artifacts / rollback

- `join_media.py` СЃС‚Р°Р» С‚РѕРЅРєРёРј entry/compatibility layer; РјРµРґРёР°Р»РѕРіРёРєР° РЅРµ
  РґСѓР±Р»РёСЂСѓРµС‚СЃСЏ; architecture РѕС‚СЂР°Р¶Р°РµС‚ ports/adapters.
- Р’СЃРµ baseline tests Р·РµР»С‘РЅС‹Рµ, `AI_PLAN` РїРµСЂРµРєР»СЋС‡С‘РЅ РЅР° 04.
- РљР°Р¶РґС‹Р№ extraction block РѕР±СЂР°С‚РёРј РѕС‚РґРµР»СЊРЅС‹Рј commit; РїСЂРё parity regression
  РѕС‚РєР°С‚РёС‚СЊ РїРѕСЃР»РµРґРЅРёР№ Р±Р»РѕРє, Р° РЅРµ РѕСЃР»Р°Р±Р»СЏС‚СЊ characterization.


## 04-metadata-date-engine
# Р­С‚Р°Рї 04 вЂ” Metadata/date engine

## Р¦РµР»СЊ

РЎРґРµР»Р°С‚СЊ РІС‹Р±РѕСЂ РґР°С‚С‹ РѕР±СЉСЏСЃРЅРёРјС‹Рј Рё РґРµС‚РµСЂРјРёРЅРёСЂРѕРІР°РЅРЅС‹Рј: РїРѕР»РёС‚РёРєР° РїСЂРёРѕСЂРёС‚РµС‚РѕРІ,
provenance, timezone Рё Р°РґР°РїС‚РµСЂС‹ РёСЃС‚РѕС‡РЅРёРєРѕРІ РјРµС‚Р°РґР°РЅРЅС‹С….

## РџСЂРµРґРІР°СЂРёС‚РµР»СЊРЅС‹Р№ decision gate

Feature SPEC РїРѕРєР° СЃРѕРґРµСЂР¶РёС‚ РѕС‚РєСЂС‹С‚С‹Рµ РІРѕРїСЂРѕСЃС‹. Р”Рѕ production-РєРѕРґР° РїРѕРґРіРѕС‚РѕРІРёС‚СЊ Рё
РїРѕР»СѓС‡РёС‚СЊ СѓС‚РІРµСЂР¶РґРµРЅРёРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РґР»СЏ РїСЂРёРѕСЂРёС‚РµС‚Р° metadata/EXIF/filename,
РїРѕРІРµРґРµРЅРёСЏ missing/conflict Рё timezone. Р•СЃР»Рё СЂРµС€РµРЅРёСЏ РЅРµС‚ вЂ” Р·Р°РІРµСЂС€РёС‚СЊ С‚РѕР»СЊРєРѕ
SPEC/ADR/РїР»Р°РЅРёСЂРѕРІР°РЅРёРµ Рё РѕСЃС‚Р°РЅРѕРІРёС‚СЊСЃСЏ.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё Рё РєРѕРЅС‚РµРєСЃС‚

- Р­С‚Р°Рї 03 Р·Р°РІРµСЂС€С‘РЅ; metadata port РІС‹РґРµР»РµРЅ.
- РџСЂРѕС‡РёС‚Р°С‚СЊ `FR-002вЂ“FR-004`, `NFR-001`, `AC-002`, system invariants,
  metadata sections architecture/testing/security Рё РїСЂРѕС„РёР»СЊ
  `.codex/agents/metadata_forensics_specialist.toml` С‚РѕР»СЊРєРѕ РїСЂРё РЅРµРѕР±С…РѕРґРёРјРѕСЃС‚Рё.

## Scope / non-goals

- Typed result СЃ РІС‹Р±СЂР°РЅРЅРѕР№ РґР°С‚РѕР№, origin, raw value/conflict diagnostics Рё
  СЏРІРЅРѕР№ timezone policy; adapters С‚РµРєСѓС‰РµРіРѕ FFprobe Рё СѓС‚РІРµСЂР¶РґС‘РЅРЅС‹С… РёСЃС‚РѕС‡РЅРёРєРѕРІ.
- РќРµ РґРѕР±Р°РІР»СЏС‚СЊ РїРѕР»СЊР·РѕРІР°С‚РµР»СЊСЃРєРѕРµ СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёРµ timeline, SQLite, ML Рё OTIO.
- ExifTool РґРѕР±Р°РІР»СЏС‚СЊ С‚РѕР»СЊРєРѕ РїРѕСЃР»Рµ РѕС‚РґРµР»СЊРЅРѕРіРѕ dependency/licensing decision.

## РћР±Р»Р°СЃС‚Рё Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: metadata/date core, adapters, tests, feature SPEC, decisions/docs.
- Р—Р°РїСЂРµС‰РµРЅРѕ: РјРѕР»С‡Р°Р»РёРІРѕРµ timezone conversion Рё СЃРєСЂС‹С‚РёРµ РєРѕРЅС„Р»РёРєС‚РѕРІ.

## Tests Рё gates

- Table/property tests: metadata keys/casing, invalid values, equal dates,
  filename Unicode, timezone-aware/naive, conflicts Рё deterministic ordering.
- Adapter contract Рё regression smoke; SPEC validation РґР»СЏ `AC-002`.

## DoD / artifacts / rollback

- РЈС‚РІРµСЂР¶РґС‘РЅРЅР°СЏ policy Р·Р°РїРёСЃР°РЅР° РІ SPEC/DECISIONS; provenance РґРѕСЃС‚СѓРїРµРЅ consumers.
- Р”РІР°Р¶РґС‹ РІС‹РїРѕР»РЅРµРЅРЅС‹Р№ РЅР°Р±РѕСЂ РґР°С‘С‚ РѕРґРёРЅ СЂРµР·СѓР»СЊС‚Р°С‚ Рё РѕР±СЉСЏСЃРЅРµРЅРёРµ; `AI_PLAN` в†’ 05.
- РќРѕРІС‹Рµ adapters feature-gated; РїСЂРё РЅРµСЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚Рё fallback вЂ” РїСЂРѕРІРµСЂРµРЅРЅС‹Р№
  FFprobe/filename path Р±РµР· РёР·РјРµРЅРµРЅРёСЏ СЃРѕС…СЂР°РЅС‘РЅРЅС‹С… raw values.


## 05-project-queue-model
# Р­С‚Р°Рї 05 вЂ” Project/queue model

## Р¦РµР»СЊ

РЎРѕР·РґР°С‚СЊ РЅРµР·Р°РІРёСЃРёРјС‹Рµ РѕС‚ UI РјРѕРґРµР»Рё timeline, export plan Рё Р¶РёР·РЅРµРЅРЅРѕРіРѕ С†РёРєР»Р°
РґРѕР»РіРѕРіРѕ Р·Р°РґР°РЅРёСЏ, РЅР° РєРѕС‚РѕСЂС‹Рµ СЃРјРѕРіСѓС‚ РѕРїРµСЂРµС‚СЊСЃСЏ GUI, progress/cancel Рё resume.

## РџСЂРµРґРІР°СЂРёС‚РµР»СЊРЅС‹Р№ decision gate

Р”Рѕ РІС‹Р±РѕСЂР° SQLite РёР»Рё РґСЂСѓРіРѕРіРѕ persistence РѕРїРёСЃР°С‚СЊ РєРѕРЅС‚СЂР°РєС‚ РјРѕРґРµР»Рё, СЃРѕСЃС‚РѕСЏРЅРёСЏ Рё
РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёСЏ. РҐСЂР°РЅРёР»РёС‰Рµ РЅРµ СѓС‚РІРµСЂР¶РґР°С‚СЊ РїРѕ СѓРїРѕРјРёРЅР°РЅРёСЋ РІ roadmap; СЂРµС€РµРЅРёРµ
С„РёРєСЃРёСЂСѓРµС‚СЃСЏ РІ SPEC/DECISIONS РїРѕСЃР»Рµ СЃСЂР°РІРЅРµРЅРёСЏ in-memory/file/SQLite РІР°СЂРёР°РЅС‚РѕРІ.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё Рё РєРѕРЅС‚РµРєСЃС‚

- Р­С‚Р°Рї 04 Р·Р°РІРµСЂС€С‘РЅ; metadata/date result СЃС‚Р°Р±РёР»РµРЅ.
- РџСЂРѕС‡РёС‚Р°С‚СЊ `FR-004/005/009/010`, `AC-002/006/007`, architecture, security Рё
  testing. РћР±РЅРѕРІРёС‚СЊ `AI_PLAN` С‚РѕР»СЊРєРѕ РЅР° СЃРѕРіР»Р°СЃРѕРІР°РЅРЅС‹Р№ СЃСЂРµР· СЌС‚Р°РїР° 05.

## Scope / non-goals

- Timeline items, stable identifiers/order, export plan snapshot, job states Рё
  РґРѕРїСѓСЃС‚РёРјС‹Рµ transitions; СЃРЅР°С‡Р°Р»Р° in-memory reference implementation.
- РќРµ СЃС‚СЂРѕРёС‚СЊ GUI, РЅРµ Р·Р°РїСѓСЃРєР°С‚СЊ FFmpeg РёР· РјРѕРґРµР»Рё, РЅРµ СЂРµР°Р»РёР·РѕРІС‹РІР°С‚СЊ resume/cache.
- РќРµ РґРѕР±Р°РІР»СЏС‚СЊ СЃРµС‚СЊ, server queue РёР»Рё multi-user semantics.

## РћР±Р»Р°СЃС‚Рё Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: domain/application models, repository port, tests, SPEC/ADR/docs.
- Р—Р°РїСЂРµС‰РµРЅС‹: widgets imports РІ РјРѕРґРµР»Рё Рё РєРѕРјР°РЅРґС‹/paths РёР· РЅРµРґРѕРІРµСЂРµРЅРЅРѕРіРѕ state.
- РЎРѕСЃС‚РѕСЏРЅРёСЏ РґРѕР»Р¶РЅС‹ СЂР°Р·Р»РёС‡Р°С‚СЊ planned/running/succeeded/failed/cancel-requested,
  РЅРµ РІС‹РґР°РІР°СЏ incomplete output Р·Р° РіРѕС‚РѕРІС‹Р№.

## Tests Рё gates

- State-transition/table tests, stable ordering/IDs, serialization round-trip
  С‚РѕР»СЊРєРѕ РґР»СЏ СѓС‚РІРµСЂР¶РґС‘РЅРЅРѕРіРѕ С„РѕСЂРјР°С‚Р°, invalid/corrupt state rejection.
- РќРёРєР°РєРёС… РІРЅРµС€РЅРёС… РїСЂРѕС†РµСЃСЃРѕРІ РІ domain tests; full regression suite РѕСЃС‚Р°С‘С‚СЃСЏ Р·РµР»С‘РЅС‹Рј.

## DoD / artifacts / rollback

- UI-РЅРµР·Р°РІРёСЃРёРјС‹Рµ РєРѕРЅС‚СЂР°РєС‚С‹ Рё storage decision Р·Р°РґРѕРєСѓРјРµРЅС‚РёСЂРѕРІР°РЅС‹; migrations,
  РµСЃР»Рё РїРѕСЏРІРёР»РёСЃСЊ, РёРјРµСЋС‚ forward/backward test; `AI_PLAN` в†’ 06.
- Persistence adapter Р·Р°РјРµРЅСЏРµРј; rollback РІРѕР·РІСЂР°С‰Р°РµС‚ in-memory adapter Р±РµР·
  РёР·РјРµРЅРµРЅРёСЏ domain API Рё Р±РµР· РїРѕС‚РµСЂРё РёСЃС…РѕРґРЅРёРєРѕРІ/РіРѕС‚РѕРІС‹С… СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ.


## 06-gui-application-services
# Р­С‚Р°Рї 06 вЂ” GUI РїРѕРІРµСЂС… application services

## Р¦РµР»СЊ

Р—Р°РјРµРЅРёС‚СЊ РїРµСЂРµС…РѕРґРЅС‹Р№ Р·Р°РїСѓСЃРє whole CLI РЅР° application-service boundary Рё РґР°С‚СЊ
РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ РїСЂРѕРІРµСЂРєСѓ СЃРѕСЃС‚Р°РІР° Рё РїРѕСЂСЏРґРєР° РґРѕ СЌРєСЃРїРѕСЂС‚Р°, СЃРѕС…СЂР°РЅРёРІ РѕС‚Р·С‹РІС‡РёРІРѕСЃС‚СЊ UI.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё Рё РєРѕРЅС‚РµРєСЃС‚

- Р­С‚Р°Рї 05 Р·Р°РІРµСЂС€С‘РЅ; timeline/export plan/job model СЃС‚Р°Р±РёР»СЊРЅС‹.
- РџСЂРѕС‡РёС‚Р°С‚СЊ `FR-001/004/005/012`, `NFR-003/004`, `AC-001/002/009/010`,
  system SPEC, architecture, design, security/testing Рё СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёР№ PySide6 GUI.
- РџРµСЂРµРґ implementation РѕР±РЅРѕРІРёС‚СЊ `AI_PLAN`; РµСЃР»Рё РїРѕРІРµРґРµРЅРёРµ preview РЅРµ
  СѓС‚РІРµСЂР¶РґРµРЅРѕ, СЃРЅР°С‡Р°Р»Р° СѓС‚РѕС‡РЅРёС‚СЊ feature SPEC.

## Scope / non-goals

- РђСЃРёРЅС…СЂРѕРЅРЅС‹Р№ Р°РЅР°Р»РёР· РїР°РїРєРё, СЃРїРёСЃРѕРє accepted/skipped/error items, РІС‹Р±СЂР°РЅРЅР°СЏ РґР°С‚Р°
  Рё РїРѕСЂСЏРґРѕРє, export plan summary, loading/empty/error states.
- РџРµСЂРµРІРµСЃС‚Рё GUI СЃ whole-CLI adapter РЅР° application services Р±РµР· РґСѓР±Р»РёСЂРѕРІР°РЅРёСЏ.
- РќРµ РґРѕР±Р°РІР»СЏС‚СЊ СЂСѓС‡РЅРѕР№ reorder/trim, overlay editor, cancel, cache РёР»Рё persistence UI.

## РћР±Р»Р°СЃС‚Рё Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: GUI presenters/view models/widgets, application adapters, tests,
  design/architecture/status.
- Р—Р°РїСЂРµС‰РµРЅР° РјРµРґРёР°СЂР°Р±РѕС‚Р° РІ UI thread Рё РїСЂСЏРјРѕР№ FFmpeg orchestration РІ widgets.
- Р—Р°РєСЂС‹С‚РёРµ/worker lifecycle СЏРІРЅС‹; paths РѕСЃС‚Р°СЋС‚СЃСЏ list values Р±РµР· shell.

## Tests Рё gates

- GUI tests loading/empty/error/populated, responsiveness, Unicode paths,
  РїРѕРІС‚РѕСЂРЅС‹Р№ Р·Р°РїСѓСЃРє Рё cleanup; application contract tests; legacy CLI parity.
- Visual QA РЅР° Windows, keyboard/focus Рё light/dark system palette.

## DoD / artifacts / rollback

- РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РІРёРґРёС‚ СЃРѕСЃС‚Р°РІ Рё РїРѕСЂСЏРґРѕРє РґРѕ Р·Р°РїСѓСЃРєР°; GUI Рё CLI РёСЃРїРѕР»СЊР·СѓСЋС‚ РѕРґРёРЅ
  application path; РїРµСЂРµС…РѕРґРЅС‹Р№ adapter РјРѕР¶РЅРѕ СѓРґР°Р»РёС‚СЊ Р±РµР· РїРѕС‚РµСЂРё РїРѕРІРµРґРµРЅРёСЏ.
- DESIGN/ARCHITECTURE РѕС‚СЂР°Р¶Р°СЋС‚ С„Р°РєС‚РёС‡РµСЃРєРёР№ UI, `AI_PLAN` в†’ 07.
- Feature flag/adapter boundary РїРѕР·РІРѕР»СЏРµС‚ РІСЂРµРјРµРЅРЅРѕ РІРµСЂРЅСѓС‚СЊ GUI-001 РїСЂРё
  СЂРµРіСЂРµСЃСЃРёРё, РЅРµ СЃРѕР·РґР°РІР°СЏ РІС‚РѕСЂРѕР№ core.


## 07-overlay-editor
# Р­С‚Р°Рї 07 вЂ” Overlay editor

## Р¦РµР»СЊ

Р”Р°С‚СЊ РµРґРёРЅСѓСЋ РєРѕРЅС„РёРіСѓСЂР°С†РёСЋ РїРѕРґРїРёСЃРё РґР°С‚С‹ Рё Р±С‹СЃС‚СЂС‹Р№ РїСЂРµРґРїСЂРѕСЃРјРѕС‚СЂ, РїСЂРёРјРµРЅСЏРµРјС‹Рµ
РѕРґРёРЅР°РєРѕРІРѕ Рє РїР»Р°РЅСѓ, preview Рё С„РёРЅР°Р»СЊРЅРѕРјСѓ СЌРєСЃРїРѕСЂС‚Сѓ.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё, decision gate Рё РєРѕРЅС‚РµРєСЃС‚

- Р­С‚Р°Рї 06 Р·Р°РІРµСЂС€С‘РЅ.
- РЈС‚РІРµСЂРґРёС‚СЊ РІ feature SPEC С„РѕСЂРјР°С‚, РІРєР»СЋС‡РµРЅРёРµ, РїРѕР·РёС†РёСЋ, font fallback, С†РІРµС‚Р°,
  РіСЂР°РЅРёС†С‹ РґРѕРїСѓСЃС‚РёРјС‹С… Р·РЅР°С‡РµРЅРёР№ Рё РїРѕРІРµРґРµРЅРёРµ РїСЂРё РѕС‚СЃСѓС‚СЃС‚РІСѓСЋС‰РµРј С€СЂРёС„С‚Рµ.
- РџСЂРѕС‡РёС‚Р°С‚СЊ `FR-002/007`, `AC-004`, design, architecture, security/testing,
  С‚РµРєСѓС‰РёР№ `make_video_filter` Рё export-plan contract.

## Scope / non-goals

- Typed overlay config, UI controls, representative frame preview Рё РµРґРёРЅС‹Р№
  adapter Рє FFmpeg filter generation.
- РќРµ РґРµР»Р°С‚СЊ РїРѕР»РЅРѕС†РµРЅРЅС‹Р№ video editor, animation/keyframes, templates marketplace
  РёР»Рё РїСЂРѕРёР·РІРѕР»СЊРЅС‹Рµ FFmpeg expressions.

## РћР±Р»Р°СЃС‚Рё Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: overlay domain/config, preview service, PySide6 controls, tests,
  SPEC/DESIGN/DECISIONS.
- РћРґРёРЅ config object РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ preview Рё export; РїРѕР»СЊР·РѕРІР°С‚РµР»СЊСЃРєРёР№ С‚РµРєСЃС‚ Рё
  paths СЌРєСЂР°РЅРёСЂСѓСЋС‚СЃСЏ РІ adapter, Р° РЅРµ РІ widgets.

## Tests Рё gates

- Unit tests config/escaping/defaults; golden/screenshot checks representative
  preview; integration test overlay on/off; Unicode font/path negatives.
- Visual QA: scaling, keyboard, contrast Рё loading/error preview.

## DoD / artifacts / rollback

- `AC-004` РїСЂРѕСЃР»РµР¶РёРІР°РµС‚СЃСЏ РґРѕ config, preview Рё synthetic export test.
- DESIGN С„РёРєСЃРёСЂСѓРµС‚ controls/tokens/states, `AI_PLAN` в†’ 08.
- Overlay РјРѕР¶РЅРѕ РІС‹РєР»СЋС‡РёС‚СЊ Р±РµР· РёР·РјРµРЅРµРЅРёСЏ РёСЃС…РѕРґРЅРёРєРѕРІ Рё pipeline; РЅРѕРІС‹Р№ preview
  adapter removable Р±РµР· РёР·РјРµРЅРµРЅРёСЏ export plan schema.


## 08-join-chronicle-modes
# Р­С‚Р°Рї 08 вЂ” Join Рё Chronicle modes

## Р¦РµР»СЊ

РЎРґРµР»Р°С‚СЊ РґРІР° РїРѕРЅСЏС‚РЅС‹С… СЂРµР¶РёРјР° РїРѕРІРµСЂС… РѕРґРЅРѕРіРѕ РјРµРґРёР°РєРѕРЅРІРµР№РµСЂР°: СЃРѕРІРјРµСЃС‚РёРјС‹Р№ Join Рё
Chronicle СЃ РґР°С‚Р°РјРё/overlay, Р±РµР· СЂР°СЃС…РѕР¶РґРµРЅРёСЏ core semantics.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё, decision gate Рё РєРѕРЅС‚РµРєСЃС‚

- Р­С‚Р°Рї 07 Р·Р°РІРµСЂС€С‘РЅ.
- Р’ feature SPEC СѓС‚РІРµСЂРґРёС‚СЊ СЂР°Р·Р»РёС‡РёСЏ СЂРµР¶РёРјРѕРІ, defaults, migration CLI Рё
  РґРѕРїСѓСЃС‚РёРјС‹Рµ СЃРѕС‡РµС‚Р°РЅРёСЏ РїР°СЂР°РјРµС‚СЂРѕРІ.
- РџСЂРѕС‡РёС‚Р°С‚СЊ `FR-006/007/011`, `AC-003/004/008`, system compatibility,
  architecture/design/testing Рё С‚РµРєСѓС‰РёРµ plan/overlay contracts.

## Scope / non-goals

- РЇРІРЅС‹Р№ mode enum/config, РµРґРёРЅС‹Р№ plan builder СЃ mode-specific policy,
  GUI selector Рё СЃРѕРІРјРµСЃС‚РёРјРѕРµ CLI representation.
- РќРµ РґСѓР±Р»РёСЂРѕРІР°С‚СЊ normalize/concat, РЅРµ РґРѕР±Р°РІР»СЏС‚СЊ trim/reorder/cache Рё РЅРµ РјРµРЅСЏС‚СЊ
  codecs Р±РµР· РѕС‚РґРµР»СЊРЅРѕРіРѕ С‚СЂРµР±РѕРІР°РЅРёСЏ.

## РћР±Р»Р°СЃС‚Рё Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: mode config/policy, application/CLI/GUI adapters, tests, docs/SPEC.
- Legacy invocation СЃРѕС…СЂР°РЅСЏРµС‚ РїСЂРµР¶РЅРёР№ СЂРµР·СѓР»СЊС‚Р°С‚ Р»РёР±Рѕ РїРѕР»СѓС‡Р°РµС‚ СѓС‚РІРµСЂР¶РґС‘РЅРЅСѓСЋ
  migration; СЂРµР¶РёРј СЏРІР»СЏРµС‚СЃСЏ РґР°РЅРЅС‹РјРё РїР»Р°РЅР°, РЅРµ РІРµС‚РІР»РµРЅРёРµРј widgets.

## Tests Рё gates

- Matrix tests mode Г— overlay Г— media type; CLI compatibility; same-plan
  determinism; mixed-media smoke РґР»СЏ РѕР±РѕРёС… СЂРµР¶РёРјРѕРІ.
- РћС‚СЃСѓС‚СЃС‚РІРёРµ duplicated FFmpeg pipeline РїРѕРґС‚РІРµСЂР¶РґР°РµС‚СЃСЏ review.

## DoD / artifacts / rollback

- РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РїРѕРЅРёРјР°РµС‚ СЂР°Р·Р»РёС‡РёСЏ РґРѕ СЌРєСЃРїРѕСЂС‚Р°, РѕР±Р° СЂРµР¶РёРјР° РїСЂРѕС…РѕРґСЏС‚ РѕРґРёРЅ core;
  migration Рё defaults Р·Р°РґРѕРєСѓРјРµРЅС‚РёСЂРѕРІР°РЅС‹; `AI_PLAN` в†’ 09.
- РќРѕРІС‹Р№ mode policy РѕР±СЂР°С‚РёРј, СЃС‚Р°СЂС‹Р№ Join РѕСЃС‚Р°С‘С‚СЃСЏ Р±РµР·РѕРїР°СЃРЅС‹Рј fallback.


## 09-export-progress-cancel
# Р­С‚Р°Рї 09 вЂ” Export, progress Рё safe cancel

## Р¦РµР»СЊ

Р РµР°Р»РёР·РѕРІР°С‚СЊ СЃС‚СЂСѓРєС‚СѓСЂРёСЂРѕРІР°РЅРЅС‹Р№ export lifecycle СЃ РїСЂРѕРІРµСЂРєРѕР№ РїР»Р°РЅР°, РЅР°Р±Р»СЋРґР°РµРјС‹Рј
РїСЂРѕРіСЂРµСЃСЃРѕРј, Р±РµР·РѕРїР°СЃРЅРѕР№ РѕС‚РјРµРЅРѕР№ РІСЃРµРіРѕ process tree Рё Р°С‚РѕРјР°СЂРЅРѕР№ С„РёРЅР°Р»РёР·Р°С†РёРµР№.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё, decision gate Рё РєРѕРЅС‚РµРєСЃС‚

- Р­С‚Р°Рї 08 Р·Р°РІРµСЂС€С‘РЅ.
- Р”Рѕ РєРѕРґР° СѓС‚РІРµСЂРґРёС‚СЊ СЃРµРјР°РЅС‚РёРєСѓ РїСЂРѕС†РµРЅС‚Р°, timeout/escalation cancel Рё cleanup.
- РџСЂРѕС‡РёС‚Р°С‚СЊ `FR-005/006/008/009/012`, `AC-003/005/006/009/010`, system
  security, job model, architecture, testing/security Рё platform process rules.

## Scope / non-goals

- Preflight tools/paths/space where feasible, structured progress events,
  cancellation token/process-tree termination, terminal states Рё cleanup.
- GUI progress/cancel Рё CLI-compatible diagnostics.
- РќРµ СЂРµР°Р»РёР·РѕРІС‹РІР°С‚СЊ resume/cache, background service РёР»Рё parallel exports.

## РћР±Р»Р°СЃС‚Рё Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: export application service, subprocess adapter, job states,
  GUI/CLI consumers, integration tests, security/architecture/SPEC.
- Р—Р°РїСЂРµС‰РµРЅРѕ СЃС‡РёС‚Р°С‚СЊ kill РѕРґРЅРѕРіРѕ Python-РїСЂРѕС†РµСЃСЃР° Р±РµР·РѕРїР°СЃРЅРѕР№ РѕС‚РјРµРЅРѕР№ РЅР° Windows.
- Final output СЃСѓС‰РµСЃС‚РІСѓРµС‚ С‚РѕР»СЊРєРѕ РїРѕСЃР»Рµ success; existing output Р·Р°С‰РёС‰С‘РЅ.

## Tests Рё gates

- Integration tests normal/failure/cancel before/during encode/during concat,
  orphan-process check, collision/permissions/Unicode Рё bounded cancel time.
- GUI event-loop responsiveness; security review РѕР±СЏР·Р°С‚РµР»РµРЅ.

## DoD / artifacts / rollback

- `AC-003/005/006/009/010` РїРѕРґС‚РІРµСЂР¶РґРµРЅС‹ Р°РІС‚РѕРјР°С‚РёРєРѕР№ РёР»Рё СЏРІРЅС‹Рј platform test;
  РѕС‚РјРµРЅР° РЅРµ РјРµРЅСЏРµС‚ inputs/result Рё РЅРµ РѕСЃС‚Р°РІР»СЏРµС‚ Р¶РёРІРѕР№ FFmpeg; `AI_PLAN` в†’ 10.
- Feature flag РїРѕР·РІРѕР»СЏРµС‚ РѕС‚РєР»СЋС‡РёС‚СЊ cancel UI; fallback вЂ” РґРѕР¶РґР°С‚СЊСЃСЏ Р·Р°РІРµСЂС€РµРЅРёСЏ,
  Р° РЅРµ РЅРµР±РµР·РѕРїР°СЃРЅРѕ СѓР±РёРІР°С‚СЊ С‚РѕР»СЊРєРѕ СЂРѕРґРёС‚РµР»СЏ.


## 10-resume-cache
# Р­С‚Р°Рї 10 вЂ” Resume Рё cache

## Р¦РµР»СЊ

Р—Р°РІРµСЂС€РёС‚СЊ MVP СЃРѕРІРјРµСЃС‚РёРјС‹Рј РІРѕР·РѕР±РЅРѕРІР»РµРЅРёРµРј: РїРѕРІС‚РѕСЂРЅРѕ РёСЃРїРѕР»СЊР·РѕРІР°С‚СЊ С‚РѕР»СЊРєРѕ
РїСЂРѕРІРµСЂРµРЅРЅС‹Рµ РїСЂРѕРјРµР¶СѓС‚РѕС‡РЅС‹Рµ РґР°РЅРЅС‹Рµ, СЃРІСЏР·Р°РЅРЅС‹Рµ СЃ РІС…РѕРґР°РјРё, РїР»Р°РЅРѕРј Рё РёРЅСЃС‚СЂСѓРјРµРЅС‚Р°РјРё.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё, decision gate Рё РєРѕРЅС‚РµРєСЃС‚

- Р­С‚Р°Рї 09 Р·Р°РІРµСЂС€С‘РЅ; export/cancel state machine СЃС‚Р°Р±РёР»РµРЅ.
- РЈС‚РІРµСЂРґРёС‚СЊ identity/key schema, versioning, retention, integrity Рё cleanup.
- РџСЂРѕС‡РёС‚Р°С‚СЊ `FR-010`, `AC-007`, `SEC-005`, job/project model, architecture,
  security/testing Рё СЂРµС€РµРЅРёРµ persistence СЌС‚Р°РїР° 05.

## Scope / non-goals

- Content/metadata identity, parameter/tool-version key, cache manifest,
  validation/invalidation, safe resume Рё explicit purge.
- РќРµ РґРѕРІРµСЂСЏС‚СЊ cache paths/commands, РЅРµ РёСЃРїРѕР»СЊР·РѕРІР°С‚СЊ partial final РєР°Рє success.
- РќРµ РґРѕР±Р°РІР»СЏС‚СЊ cloud sync, distributed cache РёР»Рё ML artifacts.

## РћР±Р»Р°СЃС‚Рё Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: cache/resume domain and storage adapter, migrations, export
  integration, GUI status, tests, security/architecture/SPEC.
- Cache СЏРІР»СЏРµС‚СЃСЏ РѕРїС‚РёРјРёР·Р°С†РёРµР№: РїРѕР»РЅС‹Р№ clean export РѕСЃС‚Р°С‘С‚СЃСЏ fallback.

## Tests Рё gates

- Resume after interruption; input/content/mtime/parameters/tool-version change;
  corrupt/tampered/old manifest; permissions/space; purge and clean fallback.
- Property tests stable keys; integration parity resumed vs clean output;
  security review РѕР±СЏР·Р°С‚РµР»РµРЅ.

## DoD / artifacts / rollback

- `AC-007` РїРѕРґС‚РІРµСЂР¶РґС‘РЅ; incompatible state rejected before reuse; MVP 02вЂ“10
  РѕС‚РјРµС‡РµРЅ Р·Р°РІРµСЂС€С‘РЅРЅС‹Рј С‚РѕР»СЊРєРѕ РїРѕСЃР»Рµ full mixed-media regression.
- `AI_STATUS` С„РёРєСЃРёСЂСѓРµС‚ MVP, `AI_PLAN` СЃРѕР·РґР°С‘С‚СЃСЏ РґР»СЏ СѓС‚РІРµСЂР¶РґС‘РЅРЅРѕРіРѕ СЌС‚Р°РїР° 11 РёР»Рё
  РґР»СЏ release hardening РїРѕ СЂРµС€РµРЅРёСЋ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ.
- Cache РјРѕР¶РЅРѕ РїРѕР»РЅРѕСЃС‚СЊСЋ РѕС‚РєР»СЋС‡РёС‚СЊ Р±РµР· РїРѕС‚РµСЂРё С„СѓРЅРєС†РёРѕРЅР°Р»СЊРЅРѕСЃС‚Рё РёР»Рё РґР°РЅРЅС‹С….


## 11-nondestructive-editing
# Р­С‚Р°Рї 11 вЂ” РќРµСЂР°Р·СЂСѓС€Р°СЋС‰РµРµ СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёРµ timeline

## Р¦РµР»СЊ Рё specification gate

Р”РѕР±Р°РІРёС‚СЊ reorder, trim, grouping Рё presets РєР°Рє РёР·РјРµРЅРµРЅРёСЏ РїСЂРѕРµРєС‚Р°, Р° РЅРµ
РёСЃС…РѕРґРЅС‹С… С„Р°Р№Р»РѕРІ. РўРµРєСѓС‰Р°СЏ feature SPEC РЅРµ РѕРїСЂРµРґРµР»СЏРµС‚ СЌС‚Рё РєРѕРЅС‚СЂР°РєС‚С‹: СЃРЅР°С‡Р°Р»Р°
СЃРѕР·РґР°С‚СЊ/СѓС‚РІРµСЂРґРёС‚СЊ РѕС‚РґРµР»СЊРЅСѓСЋ feature SPEC Рё РєСЂРёС‚РµСЂРёРё; Р±РµР· СѓС‚РІРµСЂР¶РґРµРЅРёСЏ РєРѕРґ РЅРµ РїРёСЃР°С‚СЊ.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё Рё РєРѕРЅС‚РµРєСЃС‚

- MVP 02вЂ“10 Р·Р°РІРµСЂС€С‘РЅ Рё СЃС‚Р°Р±РёР»РµРЅ.
- РџСЂРѕС‡РёС‚Р°С‚СЊ system invariants, timeline/export/cache contracts, DESIGN,
  SECURITY/TESTING Рё С‚РѕР»СЊРєРѕ РЅРѕРІСѓСЋ editing SPEC РїРѕСЃР»Рµ РµС‘ СЃРѕР·РґР°РЅРёСЏ.
- РћР±РЅРѕРІРёС‚СЊ `AI_PLAN` СЃРЅР°С‡Р°Р»Р° РЅР° specification slice, Р·Р°С‚РµРј РЅР° implementation.

## Scope / non-goals

- Stable reorder, non-destructive in/out trim, groups Рё versioned presets;
  preview/export РёСЃРїРѕР»СЊР·СѓСЋС‚ РѕРґРёРЅ project model.
- РќРµ РёР·РјРµРЅСЏС‚СЊ/РїРµСЂРµРёРјРµРЅРѕРІС‹РІР°С‚СЊ inputs; РЅРµ РґРµР»Р°С‚СЊ multi-track NLE, effects graph,
  collaboration РёР»Рё cloud storage.

## РћР±Р»Р°СЃС‚Рё Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: project/timeline domain, persistence migrations, GUI editor,
  application services, tests, SPEC/DESIGN/DECISIONS.
- Trim bounds Рё ordering РІР°Р»РёРґРёСЂСѓСЋС‚СЃСЏ РґРѕ export; cache keys СѓС‡РёС‚С‹РІР°СЋС‚ edits.

## Tests Рё gates

- Model/property tests reorder/trim/group; undoable state transitions РµСЃР»Рё
  СѓС‚РІРµСЂР¶РґРµРЅС‹; migration, cache invalidation, preview/export parity Рё GUI QA.
- Regression MVP Рё immutable-input checks РѕР±СЏР·Р°С‚РµР»СЊРЅС‹.

## DoD / artifacts / rollback

- РЈС‚РІРµСЂР¶РґС‘РЅРЅР°СЏ editing SPEC СЃРІСЏР·Р°РЅР° СЃ tests; РїСЂРѕРµРєС‚ РїРѕРІС‚РѕСЂРЅРѕ РѕС‚РєСЂС‹РІР°РµС‚СЃСЏ Р±РµР·
  РїРѕС‚РµСЂРё edits; РёСЃС…РѕРґРЅРёРєРё РїРѕР±Р°Р№С‚РЅРѕ РЅРµРёР·РјРµРЅРЅС‹; `AI_PLAN` в†’ РІС‹Р±СЂР°РЅРЅС‹Р№ СЌС‚Р°Рї 12.
- Migration РёРјРµРµС‚ backup/rollback Р»РёР±Рѕ РЅРѕРІР°СЏ СЃС…РµРјР° feature-gated.


## 12-timeline-interchange-scene
# Р­С‚Р°Рї 12 вЂ” Optional timeline interchange Рё scene analysis

## Р¦РµР»СЊ Рё experiment gate

РџСЂРѕРІРµСЂРёС‚СЊ РїРѕР»РµР·РЅРѕСЃС‚СЊ РёРјРїРѕСЂС‚Р°/СЌРєСЃРїРѕСЂС‚Р° timeline Рё Р°РЅР°Р»РёР·Р° СЃС†РµРЅ Р·Р° Р°РґР°РїС‚РµСЂР°РјРё.
Р”Рѕ РєРѕРґР° РЅСѓР¶РЅС‹ РѕС‚РґРµР»СЊРЅР°СЏ feature SPEC, С„РѕСЂРјР°С‚С‹/РІРµСЂСЃРёРё, benchmark corpus, РјРµС‚СЂРёРєРё
С‚РѕС‡РЅРѕСЃС‚Рё Рё fallback. OTIO/scene libraries РЅРµ СЃС‡РёС‚Р°СЋС‚СЃСЏ РІС‹Р±СЂР°РЅРЅС‹РјРё Р·Р°СЂР°РЅРµРµ.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё Рё РєРѕРЅС‚РµРєСЃС‚

- Р­С‚Р°Рї 11 Р·Р°РІРµСЂС€С‘РЅ Р»РёР±Рѕ СЏРІРЅРѕ РёСЃРєР»СЋС‡С‘РЅ СЂРµС€РµРЅРёРµРј РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ; project/timeline
  model СЃС‚Р°Р±РёР»РµРЅ.
- РџСЂРѕС‡РёС‚Р°С‚СЊ relevant SPEC, architecture, security/testing, dependency/license
  constraints Рё compatibility decision. РЎРѕР·РґР°С‚СЊ РѕРіСЂР°РЅРёС‡РµРЅРЅС‹Р№ `AI_PLAN`.

## Scope / non-goals

- РћРґРёРЅ СѓС‚РІРµСЂР¶РґС‘РЅРЅС‹Р№ interchange format С‡РµСЂРµР· port/adapter; optional scene
  detector, РїСЂРµРѕР±СЂР°Р·СѓСЋС‰РёР№ СЂРµР·СѓР»СЊС‚Р°С‚ РІ РїСЂРµРґР»РѕР¶РµРЅРёСЏ, Р° РЅРµ РЅРµРѕР±СЂР°С‚РёРјС‹Рµ edits.
- РќРµ РІРЅРµРґСЂСЏС‚СЊ С„РѕСЂРјР°С‚ РІ core model, РЅРµ СЃРєР°С‡РёРІР°С‚СЊ РјРѕРґРµР»Рё РјРѕР»С‡Р°, РЅРµ РІРєР»СЋС‡Р°С‚СЊ
  auto-edit РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ Рё РЅРµ РѕР±РµС‰Р°С‚СЊ lossless round-trip Р±РµР· С‚РµСЃС‚Р°.

## РћР±Р»Р°СЃС‚Рё Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: optional adapters, feature flag, fixtures/benchmarks, SPEC/ADR.
- Unknown fields/timebase/rates РѕР±СЂР°Р±Р°С‚С‹РІР°СЋС‚СЃСЏ СЏРІРЅРѕ; РЅРµРґРѕРІРµСЂРµРЅРЅС‹Рµ С„Р°Р№Р»С‹ РёРјРµСЋС‚
  size/structure limits.

## Tests Рё gates

- Golden round-trip fixtures, malformed/large input negatives, timebase tests,
  scene benchmark Рё clean fallback Р±РµР· optional dependency.
- Security/license review РґР»СЏ dependency Рё parser.

## DoD / artifacts / rollback

- РњРµС‚СЂРёРєРё СѓСЃРїРµС…Р° РґРѕСЃС‚РёРіРЅСѓС‚С‹ РЅР° corpus; adapter РјРѕР¶РЅРѕ СѓРґР°Р»РёС‚СЊ/РІС‹РєР»СЋС‡РёС‚СЊ Р±РµР·
  РёР·РјРµРЅРµРЅРёСЏ project schema; СЂРµС€РµРЅРёРµ continue/drop Р·Р°С„РёРєСЃРёСЂРѕРІР°РЅРѕ.
- Р•СЃР»Рё РєСЂРёС‚РµСЂРёРё РЅРµ РґРѕСЃС‚РёРіРЅСѓС‚С‹, СЂРµР·СѓР»СЊС‚Р°С‚ СЌС‚Р°РїР° вЂ” РґРѕРєСѓРјРµРЅС‚РёСЂРѕРІР°РЅРЅС‹Р№ РѕС‚РєР°Р·, Р° РЅРµ
  РїРѕСЃС‚РѕСЏРЅРЅР°СЏ Р·Р°РІРёСЃРёРјРѕСЃС‚СЊ.


## 13-local-transcription
# Р­С‚Р°Рї 13 вЂ” Optional Р»РѕРєР°Р»СЊРЅР°СЏ С‚СЂР°РЅСЃРєСЂРёРїС†РёСЏ

## Р¦РµР»СЊ Рё model gate

Р”РѕР±Р°РІРёС‚СЊ Р»РѕРєР°Р»СЊРЅСѓСЋ С‚СЂР°РЅСЃРєСЂРёРїС†РёСЋ РєР°Рє optional adapter СЃ provenance РјРѕРґРµР»Рё Рё
СЏРІРЅС‹РјРё resource/privacy constraints. Р”Рѕ РєРѕРґР° СѓС‚РІРµСЂРґРёС‚СЊ feature SPEC, СЏР·С‹РєРё,
С„РѕСЂРјР°С‚ СЂРµР·СѓР»СЊС‚Р°С‚Р°, РјРѕРґРµР»СЊ/Р»РёС†РµРЅР·РёСЋ, СЂР°Р·РјРµСЂ Р·Р°РіСЂСѓР·РєРё Рё РєСЂРёС‚РµСЂРёРё РєР°С‡РµСЃС‚РІР°.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё Рё РєРѕРЅС‚РµРєСЃС‚

- Project/timeline model Рё optional-adapter boundary СЃС‚Р°Р±РёР»СЊРЅС‹.
- РџСЂРѕС‡РёС‚Р°С‚СЊ РЅРѕРІСѓСЋ transcription SPEC, architecture, security/testing,
  dependency/model provenance rules; РѕР±РЅРѕРІРёС‚СЊ `AI_PLAN`.

## Scope / non-goals

- Extraction Р°СѓРґРёРѕ, Р»РѕРєР°Р»СЊРЅС‹Р№ inference adapter, timestamped transcript,
  provenance/version Рё СЂСѓС‡РЅРѕРµ РІРєР»СЋС‡РµРЅРёРµ.
- РќРµ РѕС‚РїСЂР°РІР»СЏС‚СЊ РјРµРґРёР° РІ cloud, РЅРµ Р·Р°РіСЂСѓР¶Р°С‚СЊ РјРѕРґРµР»СЊ Р±РµР· СЃРѕРіР»Р°СЃРёСЏ, РЅРµ СЃС‡РёС‚Р°С‚СЊ
  transcript РґРѕСЃС‚РѕРІРµСЂРЅС‹Рј Р±РµР· confidence/limitations.

## РћР±Р»Р°СЃС‚Рё Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: optional AI adapter, model manifest/cache, project attachments,
  GUI states, benchmarks/tests, SECURITY/SPEC/ADR.
- Transcript РЅРµ СЃС‚Р°РЅРѕРІРёС‚СЃСЏ РєРѕРјР°РЅРґРѕР№/РїСѓС‚С‘Рј; cache СЃРІСЏР·Р°РЅ СЃ input/model identity.

## Tests Рё gates

- Golden short-audio corpus, timestamps/language/error/cancel, corrupt model,
  offline mode, memory/time benchmark Рё privacy review.
- РџСЂРёР»РѕР¶РµРЅРёРµ РїРѕР»РЅРѕСЃС‚СЊСЋ СЂР°Р±РѕС‚Р°РµС‚ Р±РµР· РјРѕРґРµР»Рё/dependency.

## DoD / artifacts / rollback

- Model provenance, license, resource envelope Рё quality metrics РІРёРґРёРјС‹;
  optional feature РґРѕСЃС‚РёРіР°РµС‚ СѓС‚РІРµСЂР¶РґС‘РЅРЅРѕРіРѕ threshold.
- Feature flag Рё СѓРґР°Р»СЏРµРјС‹Р№ model cache РѕР±РµСЃРїРµС‡РёРІР°СЋС‚ Р±РµР·РѕРїР°СЃРЅС‹Р№ rollback.


## 14-hardware-quality
# Р­С‚Р°Рї 14 вЂ” Hardware capabilities Рё quality metrics

## Р¦РµР»СЊ Рё decision gate

Р”РѕР±Р°РІРёС‚СЊ РѕР±РЅР°СЂСѓР¶РµРЅРёРµ Р°РїРїР°СЂР°С‚РЅС‹С… РІРѕР·РјРѕР¶РЅРѕСЃС‚РµР№, РїСЂРѕРІРµСЂСЏРµРјРѕРµ СѓСЃРєРѕСЂРµРЅРёРµ Рё РјРµС‚СЂРёРєРё
РєР°С‡РµСЃС‚РІР° СЃ РѕР±СЏР·Р°С‚РµР»СЊРЅС‹Рј software fallback. Р”Рѕ РєРѕРґР° СѓС‚РІРµСЂРґРёС‚СЊ РїРѕРґРґРµСЂР¶РёРІР°РµРјС‹Рµ
backends, РєР°С‡РµСЃС‚РІРѕ, benchmark machines Рё РїСЂРµРґРµР»С‹ СЂРµРіСЂРµСЃСЃРёРё.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё Рё РєРѕРЅС‚РµРєСЃС‚

- Export pipeline Рё resume/cache СЃС‚Р°Р±РёР»СЊРЅС‹; optional ML adapters СѓС‡РёС‚С‹РІР°СЋС‚СЃСЏ,
  С‚РѕР»СЊРєРѕ РµСЃР»Рё СѓС‚РІРµСЂР¶РґРµРЅС‹.
- РџСЂРѕС‡РёС‚Р°С‚СЊ `NFR-005`, architecture, testing/security, FFmpeg capability
  outputs Рё РЅРѕРІСѓСЋ performance/quality SPEC; СЃРѕР·РґР°С‚СЊ `AI_PLAN`.

## Scope / non-goals

- Capability probe, explicit backend selection, deterministic fallback,
  benchmark harness Рё output quality/compatibility checks.
- РќРµ РІРєР»СЋС‡Р°С‚СЊ hardware path С‚РѕР»СЊРєРѕ РїРѕ РЅР°Р»РёС‡РёСЋ СѓСЃС‚СЂРѕР№СЃС‚РІР°; РЅРµ СѓС…СѓРґС€Р°С‚СЊ quality
  РёР»Рё portability РјРѕР»С‡Р°; РЅРµ РїРѕРґРґРµСЂР¶РёРІР°С‚СЊ РІСЃРµ GPU vendors Р±РµР· evidence.

## РћР±Р»Р°СЃС‚Рё Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: capability/performance adapters, export policy, benchmarks,
  fixtures, SPEC/ADR/docs.
- Probe failure Р±РµР·РѕРїР°СЃРµРЅ; cache key РІРєР»СЋС‡Р°РµС‚ backend/tool version.

## Tests Рё gates

- Capability matrix available/unavailable/broken driver; software parity;
  reproducible speed/quality benchmark; representative playback checks.
- Performance review РѕР±СЏР·Р°С‚РµР»РµРЅ, security review вЂ” РґР»СЏ driver/tool boundary.

## DoD / artifacts / rollback

- Hardware backend РІРєР»СЋС‡Р°РµС‚СЃСЏ С‚РѕР»СЊРєРѕ РїРѕСЃР»Рµ probe Рё РїСЂРѕС…РѕРґРёС‚ thresholds;
  benchmark report/ADR Р·Р°РїРёСЃР°РЅС‹; software fallback РІСЃРµРіРґР° С‚РµСЃС‚РёСЂСѓРµС‚СЃСЏ.
- Feature flags РїРѕР·РІРѕР»СЏСЋС‚ РѕС‚РєР»СЋС‡РёС‚СЊ Р»СЋР±РѕР№ backend Р±РµР· migration РґР°РЅРЅС‹С….


## 15-security-hardening
# Р­С‚Р°Рї 15 вЂ” Security hardening

## Р¦РµР»СЊ

РџСЂРѕРІРµСЃС‚Рё release-oriented Р°СѓРґРёС‚ РЅРµРґРѕРІРµСЂРµРЅРЅС‹С… РјРµРґРёР°, subprocess, РїСѓС‚РµР№,
permissions, cache/state Рё supply chain; СѓСЃС‚СЂР°РЅРёС‚СЊ РїРѕРґС‚РІРµСЂР¶РґС‘РЅРЅС‹Рµ СЂРёСЃРєРё РґРѕ
Windows-РїР°РєРµС‚РёСЂРѕРІР°РЅРёСЏ.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё Рё РєРѕРЅС‚РµРєСЃС‚

- Р’СЃРµ РІС‹Р±СЂР°РЅРЅС‹Рµ v1-С„СѓРЅРєС†РёРё СЂРµР°Р»РёР·РѕРІР°РЅС‹; feature set РґР»СЏ release Р·Р°РјРѕСЂРѕР¶РµРЅ.
- РџСЂРѕС‡РёС‚Р°С‚СЊ system/feature SPEC, full architecture/data boundaries,
  `docs/SECURITY.md`, tests, dependency manifests Рё packaging assumptions.
- РћР±РЅРѕРІРёС‚СЊ `AI_PLAN` РЅР° threat-model в†’ fixes в†’ verification, РЅРµ РЅР° redesign.

## Scope / non-goals

- Threat model, input/resource limits, process tree, path/symlink/reparse-point
  handling, atomic publish, cache tampering, log disclosure, dependency audit.
- РќРµ РґРѕР±Р°РІР»СЏС‚СЊ РЅРѕРІС‹Рµ РїСЂРѕРґСѓРєС‚РѕРІС‹Рµ С„СѓРЅРєС†РёРё Рё РЅРµ РѕР±РµС‰Р°С‚СЊ sandbox, РєРѕС‚РѕСЂРѕРіРѕ РЅРµС‚.

## РћР±Р»Р°СЃС‚Рё Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: boundary validation, adapters, limits/config, negative tests,
  SECURITY/DECISIONS/release docs.
- РСЃС‚РѕС‡РЅРёРєРё immutable; custom executable СЏРІР»СЏРµС‚СЃСЏ trusted-code decision;
  cleanup РѕРіСЂР°РЅРёС‡РµРЅ РёР·РІРµСЃС‚РЅРѕР№ work/cache РѕР±Р»Р°СЃС‚СЊСЋ.

## Tests Рё gates

- Corpus corrupt/large/pathological media; Unicode/quotes/long paths;
  permissions/space/collision/cancel; tampered state/cache; orphan processes;
  dependency/license/vulnerability audit.
- РќРµР·Р°РІРёСЃРёРјС‹Р№ security review РѕР±СЏР·Р°С‚РµР»РµРЅ; high findings Р±Р»РѕРєРёСЂСѓСЋС‚ СЌС‚Р°Рї 16.

## DoD / artifacts / rollback

- Threat model Рё residual risks РґРѕРєСѓРјРµРЅС‚РёСЂРѕРІР°РЅС‹, high findings Р·Р°РєСЂС‹С‚С‹,
  negative suite Р°РІС‚РѕРјР°С‚РёР·РёСЂРѕРІР°РЅ; `AI_PLAN` в†’ 16.
- РљР°Р¶РґС‹Р№ hardening change РёРјРµРµС‚ compatibility test Рё РѕС‚РґРµР»СЊРЅСѓСЋ С‚РѕС‡РєСѓ РѕС‚РєР°С‚Р°.


## 16-windows-packaging
# Р­С‚Р°Рї 16 вЂ” Windows packaging Рё release candidate

## Р¦РµР»СЊ Рё release gate

РЎРѕР·РґР°С‚СЊ РІРѕСЃРїСЂРѕРёР·РІРѕРґРёРјСѓСЋ Windows-СЃР±РѕСЂРєСѓ СЃ СЏРІРЅРѕР№ СЃС‚СЂР°С‚РµРіРёРµР№ Python/Qt,
FFmpeg/FFprobe/metadata tools, Р»РёС†РµРЅР·РёР№, РѕР±РЅРѕРІР»РµРЅРёСЏ Рё РґРёР°РіРЅРѕСЃС‚РёРєРё РЅР° С‡РёСЃС‚РѕР№ РјР°С€РёРЅРµ.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё Рё РєРѕРЅС‚РµРєСЃС‚

- Р­С‚Р°Рї 15 Р·Р°РІРµСЂС€С‘РЅ Р±РµР· high security findings; release feature set Р·Р°РјРѕСЂРѕР¶РµРЅ.
- РџСЂРѕС‡РёС‚Р°С‚СЊ system/feature SPEC, architecture, dependency/licensing decisions,
  TESTING/SECURITY, supported Windows matrix. РЎРѕР·РґР°С‚СЊ release `AI_PLAN`.

## Scope / non-goals

- Р’С‹Р±СЂР°РЅРЅС‹Р№ packager, signed/hashed artifacts where available, bundled-or-
  discovered tool policy, licenses/notices, clean-machine install/run/export.
- РќРµ РїСѓР±Р»РёРєРѕРІР°С‚СЊ Рё РЅРµ push artifacts Р±РµР· РїСЂСЏРјРѕРіРѕ СЂР°Р·СЂРµС€РµРЅРёСЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ;
  РЅРµ РґРѕР±Р°РІР»СЏС‚СЊ auto-update Р±РµР· РѕС‚РґРµР»СЊРЅРѕР№ SPEC/security model.

## РћР±Р»Р°СЃС‚Рё Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: packaging config/scripts, assets, manifests, license notices,
  release tests/docs, РјРёРЅРёРјР°Р»СЊРЅС‹Рµ runtime fixes.
- Р—Р°РїСЂРµС‰РµРЅРѕ РІРєР»СЋС‡Р°С‚СЊ Р»РѕРєР°Р»СЊРЅС‹Рµ `ffmpeg/`/`ffmpeg1/` С†РµР»РёРєРѕРј Р±РµР· license/size
  decision Рё provenance.

## Tests Рё gates

- Reproducible build; clean supported Windows VM; GUI launch, dependency
  discovery, mixed-media export, Unicode path, cancel/resume if included;
  uninstall/upgrade and antivirus false-positive notes.
- Release review, security review and license inventory РѕР±СЏР·Р°С‚РµР»СЊРЅС‹.

## DoD / artifacts / rollback

- Versioned RC artifact, checksums, notices, install/run/export report Рё known
  limitations РіРѕС‚РѕРІС‹; РїСѓР±Р»РёРєР°С†РёСЏ РѕР¶РёРґР°РµС‚ РѕС‚РґРµР»СЊРЅРѕРіРѕ СЂР°Р·СЂРµС€РµРЅРёСЏ.
- Rollback вЂ” РїСЂРµРґС‹РґСѓС‰РёР№ РїРѕРґРїРёСЃР°РЅРЅС‹Р№/РїСЂРѕРІРµСЂРµРЅРЅС‹Р№ artifact; packaging РЅРµ РјРµРЅСЏРµС‚
  project/cache schema Р±РµР· migration plan.


## 17-experimental-adapters
# Р­С‚Р°Рї 17 вЂ” Experimental adapters

## Р¦РµР»СЊ Рё РѕР±СЏР·Р°С‚РµР»СЊРЅС‹Р№ experiment gate

РСЃСЃР»РµРґРѕРІР°С‚СЊ С‚РѕР»СЊРєРѕ РѕРґРЅСѓ РїРѕРґС‚РІРµСЂР¶РґС‘РЅРЅСѓСЋ РїСЂРѕР±Р»РµРјСѓ, РєРѕС‚РѕСЂСѓСЋ РЅРµР»СЊР·СЏ СЂР°Р·СѓРјРЅРѕ СЂРµС€РёС‚СЊ
СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёРј core. Р”Рѕ Р»СЋР±РѕРіРѕ РєРѕРґР° РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ СѓС‚РІРµСЂР¶РґР°РµС‚ hypothesis, dataset,
РјРµС‚СЂРёРєРё СѓСЃРїРµС…Р°, time/resource budget, feature flag, fallback Рё РєСЂРёС‚РµСЂРёР№ СѓРґР°Р»РµРЅРёСЏ.

## Р—Р°РІРёСЃРёРјРѕСЃС‚Рё Рё РєРѕРЅС‚РµРєСЃС‚

- Stable v1/RC СЃСѓС‰РµСЃС‚РІСѓРµС‚; СЌРєСЃРїРµСЂРёРјРµРЅС‚ РЅРµ Р±Р»РѕРєРёСЂСѓРµС‚ РѕСЃРЅРѕРІРЅРѕР№ РїСЂРѕРґСѓРєС‚.
- РЎРѕР·РґР°С‚СЊ РѕС‚РґРµР»СЊРЅСѓСЋ draft feature SPEC/ADR Рё `AI_PLAN` С‚РѕР»СЊРєРѕ РґР»СЏ РѕРґРЅРѕРіРѕ
  СЌРєСЃРїРµСЂРёРјРµРЅС‚Р°. РќРµ Р·Р°РіСЂСѓР¶Р°С‚СЊ РѕСЃС‚Р°Р»СЊРЅС‹Рµ optional prompts Р±РµР· РЅРµРѕР±С…РѕРґРёРјРѕСЃС‚Рё.

## Scope / non-goals

- РћРґРёРЅ adapter/ML/scene/timeline hypothesis Р·Р° port Рё feature flag;
  РІРѕСЃРїСЂРѕРёР·РІРѕРґРёРјС‹Р№ benchmark Рё СЃСЂР°РІРЅРёС‚РµР»СЊРЅС‹Р№ baseline.
- РќРµ РјРµРЅСЏС‚СЊ canonical project schema, default export РёР»Рё privacy boundary РґРѕ
  РґРѕРєР°Р·Р°С‚РµР»СЊСЃС‚РІР°; РЅРµ РґРѕР±Р°РІР»СЏС‚СЊ dependency В«РЅР° Р±СѓРґСѓС‰РµРµВ».

## РћР±Р»Р°СЃС‚Рё Рё РєРѕРЅС‚СЂР°РєС‚С‹

- Р Р°Р·СЂРµС€РµРЅС‹: isolated adapter, fixtures/benchmark, flag/config, SPEC/ADR/report.
- Р—Р°РїСЂРµС‰РµРЅС‹: silent downloads/network, РѕР±СЏР·Р°С‚РµР»СЊРЅР°СЏ РјРѕРґРµР»СЊ/GPU, РІС‚РѕСЂРѕР№ pipeline
  Рё РёСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ benchmark data Р±РµР· provenance/license.

## Tests Рё gates

- Functional fallback/off-path, resource limits, deterministic benchmark where
  applicable, security/privacy/license review Рё comparison with baseline.

## DoD / acceptance / rollback

- Р РµР·СѓР»СЊС‚Р°С‚ вЂ” РѕРґРЅРѕ РёР·: promote СЃ СѓС‚РІРµСЂР¶РґС‘РЅРЅРѕР№ production SPEC; РѕСЃС‚Р°РІРёС‚СЊ
  disabled experiment СЃ owner/date; СѓРґР°Р»РёС‚СЊ РєР°Рє РЅРµ РґРѕСЃС‚РёРіС€РёР№ metrics.
- РћС‚РєР»СЋС‡РµРЅРёРµ flag РїРѕР»РЅРѕСЃС‚СЊСЋ РІРѕР·РІСЂР°С‰Р°РµС‚ stable v1; experimental state/cache РЅРµ
  С‚СЂРµР±СѓРµС‚СЃСЏ РґР»СЏ РѕС‚РєСЂС‹С‚РёСЏ РѕР±С‹С‡РЅРѕРіРѕ РїСЂРѕРµРєС‚Р°.

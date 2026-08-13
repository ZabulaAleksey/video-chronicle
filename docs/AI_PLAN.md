# Текущий план для AI

## Срез

- Этап: **03 — Core extraction**
- Статус: выполняется по прямой команде пользователя
- Prompt: `prompts/stages/03-core-extraction.md`
- Зависимости: этапы 01 и 02 завершены; package, entry points и baseline зелёные
- Требования: `SYS-FR-001`, `SYS-FR-002`, `SYS-COMP-001`, `FR-011`, `NFR-001`
- Критерии: `SYS-AC-001`, `SYS-AC-002`, `AC-008`, `GUI-AC-001–003`

## Цель

Извлечь медиаконвейер из root-level legacy-модуля в тестируемые package-границы
без изменения CLI/GUI-поведения и без появления второго production path.

## Последовательность

1. Зафиксировать чистые модели и ports для subprocess/filesystem boundary.
2. Перенести неизменённую медиалогику в package core/application modules.
3. Переключить package CLI и legacy `join_media.py` на единый application path.
4. Подтвердить characterization, GUI contract и реальный FFmpeg smoke.
5. Провести обязательные review и security review границ subprocess/filesystem.

## Non-goals

- новая metadata/date policy;
- project persistence, очередь, cancel или cache;
- изменение FFmpeg argv, кодов выхода, сообщений или форматов результата;
- UI redesign и новые пользовательские режимы.

## Quality gates и DoD

- `join_media.py` является тонким compatibility entry point;
- медиалогика существует в одном production path;
- публичные package-границы типизированы и тестируемы без Qt;
- argv всегда передаются списком, исходники read-only, публикация атомарна;
- все baseline/package/GUI tests и FFmpeg smoke зелёные;
- compileall, package build и `git diff --check` проходят;
- после commit `AI_STATUS` и `AI_PLAN` переключены на этап 04.

## Откат

Этап фиксируется отдельным commit. При regression откатывается extraction-блок,
а не ослабляются characterization-тесты.

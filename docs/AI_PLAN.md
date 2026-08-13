# Текущий план для AI

## Срез

- Этап: **01 — Discovery и baseline**
- Статус: готов к реализации после явной команды пользователя
- Prompt: `prompts/stages/01-discovery-baseline.md`
- Зависимости: этап 00 и GUI-001 завершены
- Основные требования: `SYS-FR-001`, `SYS-FR-003`, `SYS-FR-004`,
  `SYS-NFR-001`, `SYS-SEC-001`, `SYS-SEC-002`, `SYS-COMP-001`, `FR-011`
- Критерии: `SYS-AC-001`, `SYS-AC-003`, `SYS-AC-005`, `AC-008`, `AC-010`

## Цель

Завершить воспроизводимый baseline `join_media.py` до дальнейшего
пакетирования и извлечения core: описать наблюдаемое поведение, закрыть
characterization-тестами критические ветви и добавить короткий синтетический
FFmpeg/FFprobe smoke-test с зафиксированной минимальной версией инструментов.

## Контекст для загрузки

1. `AGENTS.md`;
2. `specs/system.spec.md` и требования совместимости из
   `specs/features/timeline-builder.spec.md`;
3. `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `docs/SECURITY.md`;
4. `join_media.py`, `tests/` и текущий diff;
5. компактный `docs/AI_STATUS.md`.

Не загружать остальные stage prompts, optional v1/ML-материалы и полную
историю `docs/LEARNING_LOG.md`.

## Scope

- матрица входов, выходов, кодов завершения и диагностик legacy CLI;
- тесты граничных случаев дат, сортировки, фильтров и FFmpeg argv;
- тесты пустого входа, повреждения, частичного успеха и коллизий;
- синтетические короткие фото/видео fixtures, создаваемые командами FFmpeg;
- определение и документирование проверенной минимальной версии FFmpeg/FFprobe.

## Non-goals

- новая GUI-функциональность;
- package layout или извлечение production-кода;
- изменение политики дат, параметров кодирования или CLI;
- очередь, отмена, кэш, SQLite, ExifTool, Pydantic или OTIO;
- изменение каталогов `ffmpeg/` и `ffmpeg1/`.

## Области файлов

- Разрешены: `tests/`, `join_media.py` только для узкой тестируемости или
  подтверждённого исправления инварианта, `docs/TESTING.md`, `README.md`,
  соответствующие SPEC/status/plan.
- Запрещены без нового решения: медиапараметры и публичный CLI-контракт,
  `ffmpeg/`, `ffmpeg1/`, будущие GUI/application-service модули.

## Исполняемые шаги

1. Сопоставить ветви `join_media.py` с `SYS-AC-001/003/005` и `AC-008/010`.
2. Добавить недостающие characterization/unit-тесты без рефакторинга поведения.
3. Добавить детерминированный smoke-test с синтетическими медиа и skip с
   явной причиной, если инструменты недоступны.
4. Зафиксировать реально проверенную версию и ограничения FFmpeg/FFprobe.
5. Выполнить tests → SPEC validation → review и обновить фактический статус.

## Quality gates и DoD

- релевантный pytest-набор и smoke-test проходят;
- входные fixtures не меняются, процессы получают list argv без shell;
- `python -m compileall`, `join_media.py --help`, `git diff --check` проходят;
- каждое затронутое AC связано с тестом или явным ограничением;
- `docs/AI_STATUS.md` отражает факт, `docs/AI_PLAN.md` переключён на этап 02;
- итоговый commit создан; merge выполняется только после разрешения пользователя.

## Acceptance artifacts

- characterization tests и синтетический smoke-test;
- таблица проверенных сценариев/версий в `docs/TESTING.md`;
- отчёт `SPEC → AC → tests → implementation`;
- обновлённые `AI_STATUS` и следующий `AI_PLAN`.

## Условия остановки и откат

Остановиться до изменения поведения, если baseline выявил неоднозначность SPEC
или платформенную несовместимость. Тестовые additions откатываются независимо;
нельзя ослаблять корректный тест ради сохранения случайного legacy-дефекта.

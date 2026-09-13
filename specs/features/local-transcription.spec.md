# TRANSCRIBE-001 — Optional локальная транскрипция

- Статус: утверждён прямой командой пользователя для этапа 13
- Версия: 1.0
- Зависимости: SYS-NFR-001–003, SYS-SEC-001, EXEC-001, MODEL-001

## 1. Цель и принятые defaults

Видео с аудиодорожкой может быть явно передано локальному `whisper.cpp`
adapter и получить timestamped transcript без сетевой передачи media. Adapter
выключен по умолчанию. Автоматическая загрузка executable или модели запрещена.

Поддерживаются `auto` и нормализованный ISO-639 language tag. Результат —
immutable typed segments в integer microseconds и strict UTF-8 JSON sidecar.
Transcript является вспомогательным attachment и не меняет timeline/export.

## 2. Provenance и privacy

- Manifest модели фиксирует model ID/version, SHA-256, bytes, license, source
  URL, заявленные languages и engine compatibility.
- Перед inference проверяются local regular executable/model/source, отсутствие
  symlink/reparse/UNC/device path, bounded size и SHA-256 модели.
- Media не отправляется в сеть. Runtime не содержит download path.
- Output фиксирует source/model/engine identity и limitations; transcript не
  считается достоверной расшифровкой без внешней проверки.

## 3. Runtime contract

- FFmpeg создаёт private mono PCM 16 kHz WAV через list argv, затем
  `whisper-cli --output-json-full` запускается тем же managed command runner.
- Source/model/tool identity проверяется до и после; общий deadline 30 минут,
  JSON не более 8 MiB, не более 20 000 segments, text segment не более 4096
  Unicode code points, duration не более 12 часов.
- Timestamps монотонны, `0 <= start < end <= source duration`; malformed,
  oversized, non-finite или overlapping result отклоняется целиком.
- Cancel/timeout/process-safety не превращаются в partial success. Temporary
  WAV/JSON удаляются во всех terminal states.

## 4. Availability и fallback

Feature доступен только при `VIDEO_CHRONICLE_TRANSCRIPTION=whisper-cpp` и явных
local paths к FFmpeg, whisper-cli, model и manifest. Missing/corrupt component
даёт typed unavailable/error без влияния на основной GUI/CLI export.

## 5. Acceptance

- **TRANSCRIBE-AC-001.** Disabled/offline path не импортирует ML dependency, не
  создаёт files и не выполняет command.
- **TRANSCRIBE-AC-002.** Golden runner подтверждает exact extraction/inference
  argv, language, timestamps, provenance и atomic sidecar round-trip.
- **TRANSCRIBE-AC-003.** Negative tests покрывают model hash/license/size,
  malformed/oversized/overlapping JSON, source/model replacement, timeout,
  cancel и cleanup.
- **TRANSCRIBE-AC-004.** Основной application/GUI/CLI полностью работает без
  whisper.cpp и model; optional entry point выдаёт понятную диагностику.

## 6. Quality gate и ограничения

Contract benchmark использует лицензированный короткий golden WAV и ожидаемый
segment envelope. Реальная WER/CER конкретной модели остаётся environment-bound
и должна быть опубликована до заявления release-quality transcription. До
такого evidence функция маркируется optional/beta и не влияет на этап 16.

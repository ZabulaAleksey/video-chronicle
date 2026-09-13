# HW-001 — Hardware capabilities и quality gate

- Статус: утверждён прямой командой пользователя для этапа 14
- Версия: 1.0
- Зависимости: SYS-NFR-001/002, SYS-SEC-001, CACHE-001, EXEC-001

## Требования

- **HW-001 — Probe.** Явно выбранный local FFmpeg опрашивается managed argv
  `-version`, `-encoders` и `-hwaccels`; parser распознаёт только утверждённые
  H.264 backends `libx264`, `h264_nvenc`, `h264_qsv`, `h264_amf`.
- **HW-002 — Selection.** Default всегда `software/libx264`. Hardware никогда
  не включается только по факту наличия. Явный unavailable/broken backend
  детерминированно возвращает software fallback с видимой причиной.
- **HW-003 — Args.** Каждый backend имеет фиксированное typed argv mapping;
  arbitrary codec/options от пользователя запрещены.
- **HW-004 — Benchmark.** Promotion требует один и тот же bounded source,
  software reference, SSIM не ниже 0.95 и не хуже reference более чем на 0.01,
  а wall time hardware — не более 110% software. Tool/platform/probe identity и
  raw metrics сохраняются в JSON report.
- **HW-005 — Cache identity.** Backend/tool identity обязаны входить в cache
  identity до использования hardware в production export. Пока promotion
  evidence отсутствует, основной export остаётся software и cache schema не
  меняется.

## Acceptance

- **HW-AC-001.** Matrix tests покрывают available/unavailable/malformed probe и
  отсутствие shell/ambient driver execution.
- **HW-AC-002.** Selection tests подтверждают software default, explicit
  hardware и deterministic fallback.
- **HW-AC-003.** Benchmark parser/threshold tests покрывают pass/drop,
  non-finite/отсутствующий SSIM и reproducible JSON.
- **HW-AC-004.** Без подтверждённого machine benchmark default export и cache
  остаются byte-compatible software path.

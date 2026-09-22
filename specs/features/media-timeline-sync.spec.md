# MEDIA-SYNC-001 — Согласованная media timeline

- Статус: утверждён прямым запросом пользователя
- Версия: 1.1
- Зависимости: SYS-AC-001, AC-010

## Требования

- **MEDIA-SYNC-001 — Source timestamps.** PTS/DTS и соответствующий
  `time_base` исходных streams являются источником времени. Запрещено
  восстанавливать timestamps только как `frame_index / nominal_fps`, если
  source содержит собственную timeline.
- **MEDIA-SYNC-002 — Rational rates.** Rates `30000/1001`, `60000/1001` и
  `24000/1001` сохраняются как рациональные значения и не округляются до 30,
  60 или 24 при вычислении времени.
- **MEDIA-SYNC-003 — Explicit CFR.** Product output остаётся явно заданным CFR
  60. Преобразование CFR/VFR source детерминированно использует source PTS,
  сохраняет общую продолжительность и rescale'ит timestamps между input,
  filter, encoder и output stream time bases.
- **MEDIA-SYNC-004 — Frame integrity.** Overlay/normalization не должны
  терять, дублировать, генерировать или переставлять frames иначе, чем требует
  явное CFR 60 преобразование. Проверка использует timestamps; frame count сам
  по себе недостаточен для VFR.
- **MEDIA-SYNC-005 — Continuous audio encode.** Нормализованные сегменты могут
  содержать независимо закодированный AAC, но финальный output не должен
  stream-copy concatenated AAC access units. Финальная сборка сохраняет H.264
  video через stream copy, а audio всех сегментов декодирует и кодирует ровно
  один раз как AAC 48 kHz stereo на общей непрерывной timeline. Если concat
  demuxer сохраняет между decoded audio frames положительный PTS gap, этот
  интервал должен быть материализован как PCM silence до финального encode;
  отсутствие samples не должно переноситься в output как разрыв audio clock.
- **MEDIA-SYNC-006 — No masking.** Запрещены произвольный audio delay,
  `-itsoffset`, изменение скорости audio и недокументированная посткомпенсация.
  Bounded `aresample=48000:async=1000:min_hard_comp=0.001:first_pts=0`
  разрешён только на финальной concat-границе для доказанного случая: заполнить
  реальные положительные PTS gaps PCM silence и начать общую audio timeline с
  нуля. Это не разрешает подбирать коэффициент скорости или offset.
- **MEDIA-SYNC-007 — Mux continuity.** Output audio/video packet timestamps
  монотонны, корректно rescale'нуты в stream time bases и описывают ту же
  продолжительность с учётом codec priming, padding, skip/discard metadata и
  container edit lists.

## Acceptance

- **MEDIA-SYNC-AC-001.** Regression corpus покрывает CFR 30,
  `30000/1001`, `60000/1001`, smartphone-like VFR, различные audio/video
  stream time bases и output продолжительностью несколько минут с множеством
  concat-границ.
- **MEDIA-SYNC-AC-002.** Для input и output сохраняется FFprobe evidence:
  format/start/duration, stream codec/time base/duration, rational frame rates,
  frame count где доступен, sample rate и packet/frame timestamps в начале,
  середине и конце.
- **MEDIA-SYNC-AC-003.** Video frame timestamps монотонны; output frame count
  соответствует детерминированному CFR 60 преобразованию source durations без
  недокументированных drops/duplicates.
- **MEDIA-SYNC-AC-004.** После учёта codec skip/discard metadata разница между
  числом декодированных audio samples и packet timeline не превышает один AAC
  access unit: 1024 samples при 48 kHz (`21.333... ms`) на всём output.
- **MEDIA-SYNC-AC-005.** A/V timeline проверяется в начале, середине и конце;
  расхождение между checkpoint'ами не растёт более чем на один AAC access unit.
  Проверка одной только близости stream/container durations не является
  достаточным evidence.
- **MEDIA-SYNC-AC-006.** Детерминированный multi-segment test доказывает, что
  final video остаётся stream-copy compatible, audio кодируется один раз, а
  произвольный offset и изменение FPS/скорости отсутствуют.
- **MEDIA-SYNC-AC-007.** Real-like normalized segment с video duration около
  `3.233333 s` и decoded audio duration `3.221333 s` повторяется не менее 60
  раз. До correction output содержит 59 положительных decoded-frame PTS gaps
  по 576 samples (`0.708 s` суммарно); после correction число/net gap и рост
  decoded-content clock error proxy между checkpoint'ами не превышает один AAC
  access unit. Signed oracle также не допускает накопления отрицательных
  overlaps более одного AAC access unit.
- **MEDIA-SYNC-AC-008.** Offline PCM/PTS evidence доказывает устранение
  structural clock deficit, но не подменяет semantic playback verification.
  До root-cause closure/release полный diagnostic candidate должен пройти
  непрерывное воспроизведение без accumulated A/V drift во встроенном
  Android-плеере `7.30.50.106`; seek проверяется отдельно как diagnostic step.

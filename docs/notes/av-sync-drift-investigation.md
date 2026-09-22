# Расследование накопительного A/V drift

## ROOT CAUSE

Накопительный drift создаёт не округление FPS и не постоянный audio offset, а
финальный stream-copy concat независимо закодированных AAC-сегментов. На границе
каждого нормализованного клипа muxer сокращает packet duration до границы видео,
но AAC access unit по-прежнему декодируется в полный блок из 1024 PCM samples.
Последовательный decoder поэтому потребляет больше audio samples, чем описывает
packet timeline; ошибка повторяется для 361 независимо закодированного сегмента
на 360 joins и накапливается.

Видео при этом имеет согласованную временную модель: итог — exact CFR 60 с
`time_base=1/60000`, а число кадров совпадает с суммой
`round(source_duration * 60)` для видео и 120 кадров для каждой фотографии.
Следовательно, обнаруженные VFR-like/rate-mismatch исходники не являются
механизмом данного drift.

## EVIDENCE

Реальный обработанный `07.mp4`:

- video: 94 883 frames, exact CFR `60/1`, `time_base=1/60000`,
  `start_time=0.021333`, `duration=1581.383333`;
- audio: AAC, 48 kHz, `time_base=1/48000`, `start_time=0`,
  `duration=1581.399312`, 74 329 packets;
- video/audio packet PTS и DTS непрерывны, поэтому обычная проверка container
  timestamps не показывает разрыв;
- `74329 * 1024 = 76112896` decoded AAC samples, тогда как сумма packet
  durations равна 75 907 167 samples;
- surplus: `205729 samples / 48000 = 4.286020833 s`;
- относительная скорость накопления:
  `4.286020833 / 1581.399312 = 0.00271027`, то есть около 2.71 ms/s.

Сопоставление длительности декодируемого AAC payload с packet PTS timeline
подтверждает линейное накопление: `0.441 s` при `158.129 s`, `1.149 s` при
`395.267 s`, `2.322 s` при `790.510 s`, `3.323 s` при `1185.925 s`,
`3.798 s` при `1423.295 s` и `4.286 s` при `1581.378 s`. Измеренные
`0.271%` отличаются от `30/29.97 - 1 ≈ 0.100%`, поэтому NTSC FPS mismatch
не объясняет наблюдаемую скорость drift.

Корпус состоит из 361 item: 344 video и 17 photo. У всех 344 video
`time_base=1/90000`; 335 классифицированы как rate-mismatch/VFR-like.
`r_frame_rate` включает `60/1`, `60000/1001`, `30/1` и `120/1`, но output
frame count в точности соответствует явному CFR 60 преобразованию. Это
опровергает гипотезу о фактической подмене `60000/1001` на `60/1` как причине
измеренного drift.

Детерминированный repro на 361 сегменте дал:

- stream-copy AAC: surplus `9.124125 s` на timeline `445.254542 s`;
- однократное финальное AAC-перекодирование при copy video: остаток
  `0.014792 s`, то есть меньше одного AAC access unit (`0.021333... s`).

## WHY SEEK FIXES IT

При непрерывном воспроизведении Android decoder последовательно выдаёт PCM из
полных AAC access units, включая samples за сокращёнными packet durations. Его
audio clock всё дальше отстаёт от video timeline.

Seek очищает decoder queues и выбирает новую точку через container index и
ближайший video keyframe. Плеер заново привязывает audio/video clocks к PTS этой
позиции, поэтому накопленная до seek decoder-state ошибка исчезает. После
последовательного прохождения следующих границ AAC-сегментов surplus снова
накапливается. Версия встроенного Android-плеера, на которой наблюдался симптом:
`7.30.50.106`.

## FIX

Минимальное исправление находится на финальной concat/mux границе:

1. Сохранять H.264 video через stream copy: нормализованные сегменты уже имеют
   общий CFR 60 профиль и непрерывную video timeline.
2. На финальном concat декодировать audio всех сегментов в одну непрерывную
   timeline и закодировать AAC ровно один раз в 48 kHz stereo.
3. Сохранить непрерывные timestamps и общую продолжительность audio/video;
   корректно rescale timestamps в output stream time bases.
4. Не добавлять произвольный delay, `-itsoffset`, изменение скорости,
   `aresample=async` или дополнительное принудительное CFR-преобразование.

Source timestamps остаются источником истины до явно заданного,
детерминированного преобразования output в CFR 60. Рациональные rates
`30000/1001` и `60000/1001` нельзя округлять до целого FPS при расчёте времени.

## REGRESSION

Автоматический media regression corpus должен включать:

- CFR 30;
- `30000/1001`;
- `60000/1001`;
- smartphone-like VFR;
- несколько минут и много concat-границ;
- различные video/audio stream time bases.

Для начала, середины и конца output проверяются packet continuity и расхождение
audio/video timelines. Основной oracle — не только container duration, но и
число фактически декодированных audio samples после учёта codec skip/discard
metadata относительно суммы packet durations. На всём output допустим остаток
не более одного AAC access unit: 1024 samples при 48 kHz
(`21.333... ms`), без линейного роста между checkpoint'ами.

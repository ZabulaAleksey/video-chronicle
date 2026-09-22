# Расследование накопительного A/V drift — v2

## Статус прежней гипотезы

Гипотеза из v1 **частично подтверждена**, но не является полным root cause.
Commit `fed1309` правильно устранил stream-copy независимо закодированных AAC
access units: final audio действительно декодируется и кодируется один раз.
Однако реальный экспорт `D:\output.mp4`, созданный этим pipeline, всё ещё
воспроизводит drift. Однократный encode сам по себе не заполняет интервалы, в
которых concat input содержит video timeline, но не содержит decoded PCM.

## ROOT CAUSE

Доказан root cause структурного decoded-content clock deficit и сложной MP4
audio timing table. Его достаточность как объяснения слышимого Android symptom
остаётся условной до обязательной проверки diagnostic candidate на устройстве.

Нормализованные clips имеют duration, заданную CFR 60 video. У части clips
decoded audio payload короче video span. Например, первый video clip реального
корпуса имеет `3.233333 s` video и `3.221333 s` decoded audio: отсутствуют 578
samples относительно video timeline. Concat demuxer сохраняет следующий audio
frame на PTS следующего segment, поэтому между decoded audio frames остаётся
положительный PTS gap.

Финальный AAC encode из `fed1309` сохраняет эти timestamps, но не создаёт PCM
samples внутри gaps. В `D:\output.mp4` найдено 343 положительных gaps. В
последовательности есть 343 boundaries после video items и 17 boundaries после
photo items. Равенство первых counts само по себе не доказывает one-to-one:
консервативная реконструкция absolute PTS дала 119 точных совпадений gap с
video boundary, 0 совпадений после photo, а остальные связи не доказаны из-за
cumulative rounding и соседних overlaps. Суммарный net gap равен 167 263
samples, или `3.484645833 s`. Artifact описывает presentation timeline длиной
`1581.3993125 s`, но содержит только 75 739 904 decoded samples
(`1577.914667 s`) звукового материала.

Video PTS при этом непрерывны. В последовательной sample-count модели
video progress минус cumulative decoded PCM даёт end clock-deficit proxy
`3.468667 s`, slope `2193.44 ppm` (`0.219344%`). Это не является прямым
измерением семантического смещения звукового события: timestamp-aware player
может выдержать gap как silence и остаться синхронным. Proxy количественно
согласуется с накопленным PCM deficit и не совпадает с
`60 / (60000/1001) - 1`, поэтому ошибка `59.94 → 60` не объясняет структуру.

## EVIDENCE

Реальный post-`fed1309` artifact `D:\output.mp4`:

- video timeline: continuous CFR 60 PTS, без accumulated frame-time gap;
- audio presentation: 75 907 167 samples / 48 kHz = `1581.3993125 s`;
- decoded audio: 75 739 904 samples / 48 kHz = `1577.914667 s`;
- positive decoded-frame PTS gaps: 343;
- net gaps: 167 263 samples = `3.484645833 s`;
- decoded-content clock-deficit proxy в конце: `3.468667 s`;
- slope proxy: `2193.44 ppm` = `0.219344%`.

Детерминированный real-FFmpeg repro нормализует source с video duration около
`3.226111 s` и audio duration около `3.199958 s`. Полученный segment имеет
`3.233333 s` video, 154 624 decoded audio samples (`3.221333 s`) и deficit 576
samples. Это synthetic fixture; измеренный deficit первого real clip равен
578 samples. 60 synthetic повторов на pipeline `fed1309` дают 59 gaps по 576
samples:
33 984 samples, или `0.708 s`, на output около 194 seconds. Это RED на том же
механизме, что и реальный artifact, а не только проверка container duration.

### Segment-boundary correlation

- positive decoded-frame gaps: 343;
- boundaries после video items: 343;
- boundaries после photo items: 17;
- exact conservative absolute-PTS matches с video boundaries: 119;
- exact matches после photo: 0.

Остальные 224 gaps нельзя честно назначить конкретным boundary только по
реконструкции: накопленное округление time bases и отрицательные overlaps
сдвигают absolute positions. Поэтому evidence подтверждает video-boundary
association, но не утверждает недоказанное точное соответствие 343/343.

### Container boxes и edit lists

Оба MP4 используют movie timescale `240000`. У проблемного файла video `elst`
содержит пустой интервал `5120/240000 s`, затем `media_time=2000`; diagnostic
candidate сохраняет ту же video edit list. Проблемный audio `elst` начинается с
`media_time=0`, candidate — с `media_time=1024`. Эти offsets ограничены началом
track и постоянны: они могут объяснить initial offset порядка одного AAC unit,
но не накопительный drift.

Главное различие находится в audio `stts`: проблемный box занимает 23 064
bytes и содержит variable sample durations от `768/1023/1024` до `2027`, тогда
как candidate имеет 32-byte `stts`. Это согласуется с continuous decoded PCM в
candidate и сохраняет variable-timing structure как Android-specific trigger
hypothesis, а не как доказанный renderer algorithm.

### Mux interleaving

Длинных runs одного stream не обнаружено: максимум 3 последовательных video
packets (около `0.100001 s`), максимум 1 audio packet (около `0.042229 s`),
максимальный PTS lead — `0.100001 s`. Следовательно, starvation из-за грубого
packet interleaving не соответствует многосекундному накоплению.

### Differential experiments

| Variant | Изменение | Decoded discontinuities | Вывод |
| --- | --- | ---: | --- |
| A | Current `fed1309`, video copy + один AAC encode | 59 gaps, net `0.707937 s` | Дефект сохраняется после единственного encode |
| B | Re-encode audio + video | те же 59 / `0.707937 s` | Video stream-copy не является причиной |
| C | Video copy + PCM в MKV | те же 59 / около `0.708 s` | Дефект не создаётся AAC encoder или MP4 muxer |
| D | Video copy + Opus | те же 59 / около `0.7075 s` | Дефект не специфичен для AAC codec payload |
| E | `asetpts` regenerate | gaps закрыты, semantic timeline сокращена | Невалидно: отбрасывает source timing |
| F | default soft `aresample=async=1` | residual около `0.072 s` | Soft compensation недостаточна |
| G | `async=1000:min_hard_comp=0.001` | 0 gaps; decoded `194.009312 s`; residual `0.0120035 s` | Материализует gaps в PCM |
| H | `async=1:min_hard_comp=0.001` | 0 gaps | Hard threshold, а не значение 1000, закрывает fixture gaps |

На полном real corpus вариант с `async=1:min_hard_comp=0.001` также дал
75 907 168 decoded samples и 0 positive gaps/overlaps. Production использует
вариант G; experiment H показывает, что результат не основан на подобранном
global speed coefficient.

## DRIFT TYPE

Доказанный artifact defect является stepwise. Структурно
PCM deficit добавляется на segment boundaries; на длинном корпусе много малых
steps выглядят почти линейным drift. Container audio PTS продолжают описывать
правильные presentation positions, но decoded PCM последовательность содержит
пропуски, поэтому проверка только packet monotonicity или stream duration
дефект не обнаруживает. Связь этого defect с конкретным направлением
семантического A/V offset зависит от renderer: compliant timestamp-aware path
может вставить/выдержать silence и не накопить semantic drift.

## WHY SEEK FIXES IT

Точный механизм renderer встроенного Android-плеера `7.30.50.106` и направление
его внутренней clock correction локально не наблюдаемы. Поэтому seek-effect
остаётся evidence-supported гипотезой, а не доказанным decoder algorithm.

Проблемный MP4 содержит необычно сложную audio timing table: box `stts` имеет
размер 23 064 bytes, а sample durations варьируются (`768`, `1023`, `1024` и
значения до `2027`). Рабочая гипотеза: sequential Android path некорректно
обрабатывает эту переменную AAC schedule и сохраняет ошибочное decoder/render
state. Seek отбрасывает предыдущее state и reanchor'ит playback на текущие PTS,
поэтому симптом временно исчезает. Исправленный diagnostic candidate имеет
audio `stts` размером 32 bytes и continuous decoded PCM, то есть удаляет
структурный trigger этой гипотезы. Это ещё не заменяет Android-проверку.

## FIX

Минимальная correction находится на единственной финальной audio decode/encode
границе. Перед AAC encoder применяется:

```text
aresample=48000:async=1000:min_hard_comp=0.001:first_pts=0
```

Filter использует существующие PTS как source of truth и материализует
положительные intervals как PCM silence. Он не меняет video: H.264 остаётся
stream-copy. Не добавляются `itsoffset`, подобранный delay, `atempo` или FPS
correction. Diagnostic export с этим filter имел ноль decoded-frame PTS gaps.

## REGRESSION

`test_final_concat_materializes_real_segment_audio_gaps_as_pcm_silence`
создаёт real-like mismatched source, прогоняет production normalization,
повторяет segment 60 раз и анализирует итоговый artifact через ffprobe. Test:

- подтверждает исходный 576-sample PCM deficit;
- проверяет continuous CFR 60 video PTS;
- считает count и net decoded-audio PTS gaps;
- считает signed discontinuities и не допускает накопления отрицательных
  overlaps;
- сравнивает decoded PCM content с video end;
- измеряет accumulated error на 10%, 50%, 75% и 100%;
- допускает не более одного AAC access unit (`1024 / 48000 s`) без роста.

На `fed1309` test падает с 59 gaps / 33 984 samples (`0.708 s`). После bounded
gap materialization output содержит 0 positive gaps, 9 312 447 decoded samples
(`194.0093125 s`) при video end `194.021316667 s`; end difference
`0.012004167 s` меньше одного AAC access unit. Прежний рациональный FPS/VFR
regression также остаётся зелёным.

## VERIFICATION

Полный long diagnostic candidate
`D:\output-avsync-v2-diagnostic.mp4`, собранный исправленным pipeline из
реального июльского корпуса:

- decoded audio: 75 907 168 samples / 48 kHz = `1581.399333 s`;
- positive decoded-frame PTS gaps: 0;
- net gap: 0 samples;
- negative overlaps: 0; проблемный artifact имел 1097 overlaps по 1 sample;
- video end минус decoded audio end: `0.005333 s`;
- checkpoint error остаётся около `-0.021333 s` и не растёт по timeline.

Отдельный manual fixture со start times video `0.500000 s` и audio
`0.478667 s`, повторённый 20 раз, после correction дал 0 positive gaps и net
gap 0. Это подтверждает, что `first_pts=0` не оставляет accumulated defect при
non-zero source start, но не заменяет semantic playback check.

Таким образом, накопительный компонент устранён и на synthetic repro, и на
полном реальном artifact; остаток ограничен одним AAC access unit и является
постоянным, а не decoded-content clock drift. Семантический A/V sync на Android
этими offline измерениями ещё не доказан.

Проверки в корректном user-profile temp окружении:

- `tests/test_cli_characterization.py` + полный `tests/test_ffmpeg_smoke.py`:
  `41 passed in 41.53s`, включая cache scenario;
- полный project suite: `342 passed, 21 skipped, 3 failed in 101.12s`.

Три full-suite failure environment/baseline-sensitive и не затрагивают media
timeline diff: GUI test ожидает literal `ffmpeg`, но discovery находит
установленный absolute full-build path; wheel test запускает base Python без
`setuptools.build_meta`; scene golden закрепляет essentials-build identity, а
окружение обнаруживает установленный full-build FFmpeg.

Desktop playback coverage ограничено: `ffplay` установлен, но объективное
семантическое A/V наблюдение локально не автоматизировано; VLC и mpv
недоступны. Механизм renderer Android `7.30.50.106` локально не инспектируется.

## NEXT HUMAN CHECKPOINT

До полного закрытия root cause и release необходимо открыть именно
`D:\output-avsync-v2-diagnostic.mp4` во встроенном Android-плеере
`7.30.50.106` и непрерывно воспроизвести достаточно длинный интервал, включая
начало, середину и участок ближе к концу. Нужно проверить, накапливается ли
слышимое semantic A/V смещение без seek, затем выполнить seek и сравнить
поведение. Только отсутствие накопительного drift на этом файле подтвердит,
что устранение variable `stts`/PCM gaps убирает Android-specific trigger.

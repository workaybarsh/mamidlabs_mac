"""Ses hazirligi: herhangi bir ses/video dosyasini 16 kHz mono PCM WAV'a cevirir.

PyAV kullanilir (ffmpeg ikilisi gerekmez). Uzun kayitlar (lite tier; chunk_minutes>0) `wave` modulu ile
parcalara bolunur; boylece 16 GB sistem RAM'i sismez.
"""
from __future__ import annotations

import os
import wave

SAMPLE_RATE = 16000


def to_wav16k_mono(src: str, dst: str | None = None) -> str:
    """src -> 16 kHz mono s16le WAV. dst verilmezse src ile ayni klasorde uretir."""
    if dst is None:
        base, _ = os.path.splitext(src)
        dst = base + '.16k.wav'
    import av
    from av.audio.resampler import AudioResampler

    with av.open(src) as container:
        if not container.streams.audio:
            raise ValueError('Ses akisi bulunamadi: %s' % src)
        stream = container.streams.audio[0]
        resampler = AudioResampler(format='s16', layout='mono', rate=SAMPLE_RATE)
        with av.open(dst, 'w', format='wav') as out:
            out_stream = out.add_stream('pcm_s16le', rate=SAMPLE_RATE)
            out_stream.layout = 'mono'
            for frame in container.decode(stream):
                for resampled in resampler.resample(frame):
                    for packet in out_stream.encode(resampled):
                        out.mux(packet)
            for resampled in resampler.resample(None):
                for packet in out_stream.encode(resampled):
                    out.mux(packet)
    return dst


def duration_seconds(wav_path: str) -> float:
    with wave.open(wav_path, 'rb') as w:
        return w.getnframes() / float(w.getframerate() or SAMPLE_RATE)


def probe_duration_seconds(path: str) -> float | None:
    """Herhangi bir ses/video dosyasinin suresini (saniye) TAM COZMEDEN tahmin eder.

    Cihaz/swap plani icin kullanilir (kisa/uzun karari); tam WAV'a cevirmek gerekmez.
    Okunamazsa None doner.
    """
    try:
        import av

        with av.open(path) as container:
            if container.duration is not None:
                return float(container.duration) / float(av.time_base)
            for stream in container.streams:
                if stream.duration is not None and stream.time_base is not None:
                    return float(stream.duration * stream.time_base)
    except Exception:
        return None
    return None


def read_mono_float32(wav_path: str):
    """16 kHz mono WAV'i [-1, 1] float32 numpy dizisine okur (VAD icin)."""
    import numpy as np

    with wave.open(wav_path, 'rb') as w:
        assert w.getframerate() == SAMPLE_RATE, 'VAD 16 kHz bekler'
        frames = w.readframes(w.getnframes())
    data = np.frombuffer(frames, dtype='<i2').astype('float32') / 32768.0
    return data


def split_wav(wav_path: str, minutes: int) -> list[tuple[str, float]]:
    """WAV'i `minutes` dilimlerine boler. [(parca_yolu, baslangic_saniye), ...] doner.

    minutes <= 0 ise ya da kayit kisaysa tek parca [(wav_path, 0.0)] doner.
    """
    if minutes <= 0:
        return [(wav_path, 0.0)]
    with wave.open(wav_path, 'rb') as w:
        params = w.getparams()
        total = w.getnframes()
        rate = w.getframerate() or SAMPLE_RATE
    per_chunk = int(minutes * 60 * rate)
    if total <= per_chunk:
        return [(wav_path, 0.0)]
    chunks: list[tuple[str, float]] = []
    base, _ = os.path.splitext(wav_path)
    with wave.open(wav_path, 'rb') as w:
        index = 0
        offset = 0
        while True:
            frames = w.readframes(per_chunk)
            if not frames:
                break
            chunk_path = '%s.part%02d.wav' % (base, index)
            with wave.open(chunk_path, 'wb') as out:
                out.setparams(params)
                out.writeframes(frames)
            chunks.append((chunk_path, offset / float(rate)))
            index += 1
            offset += len(frames) // (params.sampwidth * params.nchannels)
    return chunks

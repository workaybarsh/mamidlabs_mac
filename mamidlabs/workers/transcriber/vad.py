"""Silero VAD: konusma araliklarini bulur (sessizlikte uydurma metni azaltir).

faster-whisper'in paketledigi silero VAD kullanilir (ayri model indirmek gerekmez).
ASR tarafinda `vad_filter=True` zaten kullanilir; buradaki fonksiyon olay hattinin
konusma disi pencereleri ayirmasi ve raporlama icindir.
"""
from __future__ import annotations

DEFAULT_MIN_SILENCE_MS = 500


def speech_ranges(wav_path: str, min_silence_ms: int = DEFAULT_MIN_SILENCE_MS) -> list[tuple[float, float]]:
    """(baslangic, bitis) saniye cinsinden konusma araliklari. Hata olursa bos liste."""
    try:
        from faster_whisper.vad import VadOptions, get_speech_timestamps
    except Exception:
        return []
    from . import audio

    samples = audio.read_mono_float32(wav_path)
    options = VadOptions(min_silence_duration_ms=min_silence_ms)
    try:
        stamps = get_speech_timestamps(samples, options)
    except Exception:
        return []
    return [(t['start'] / float(audio.SAMPLE_RATE), t['end'] / float(audio.SAMPLE_RATE)) for t in stamps]


def is_speech(start: float, end: float, ranges: list[tuple[float, float]], min_overlap: float = 0.2) -> bool:
    """Aralik, konusma araliklariyla en az `min_overlap` oraninda ortusuyor mu?"""
    span = max(end - start, 1e-6)
    for a, b in ranges:
        overlap = min(end, b) - max(start, a)
        if overlap > 0 and overlap / span >= min_overlap:
            return True
    return False

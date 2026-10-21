"""Speaker diarisation (pyannote). Silently skipped when there is no token or it is not installed.

Used to add a "Speaker 1 / Speaker 2" label to the lines of multi-person recordings.
pyannote/speaker-diarization-3.1 requires an acceptance (token) on Hugging Face.
"""
from __future__ import annotations

import os

_PIPELINE_CACHE: dict = {}
DEFAULT_MODEL = 'pyannote/speaker-diarization-3.1'


def resolve_token(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    for name in ('MAMIDLABS_HF_TOKEN', 'HUGGINGFACE_TOKEN', 'HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN'):
        value = os.environ.get(name)
        if value:
            return value
    return None


def _load_pipeline(token: str, device: str):
    from pyannote.audio import Pipeline

    key = (DEFAULT_MODEL, device)
    if key not in _PIPELINE_CACHE:
        import inspect
        params = inspect.signature(Pipeline.from_pretrained).parameters
        if 'use_auth_token' in params:
            pipeline = Pipeline.from_pretrained(DEFAULT_MODEL, use_auth_token=token)
        else:
            pipeline = Pipeline.from_pretrained(DEFAULT_MODEL, token=token)
        pipeline.to(__import__('torch').device('cuda' if (device or '').lower() == 'cuda' else 'cpu'))
        _PIPELINE_CACHE[key] = pipeline
    return _PIPELINE_CACHE[key]


def unload_pipeline():
    _PIPELINE_CACHE.clear()
    try:
        import gc
        gc.collect()
    except Exception:
        pass
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def diarize(wav_path: str, token: str | None = None, device: str = 'cuda') -> list[dict]:
    """[{start, end, speaker}, ...]. Returns [] when there is no token or pyannote is not installed."""
    token = resolve_token(token)
    if not token:
        return []
    try:
        pipeline = _load_pipeline(token, device)
        annotation = pipeline(wav_path)
    except Exception:
        return []
    turns: list[dict] = []
    # Newer pyannote versions may return a DiarizeOutput instead of an Annotation.
    it = annotation
    if hasattr(annotation, 'speaker_diarization'):
        it = annotation.speaker_diarization
    try:
        for segment, _, speaker in it.itertracks(yield_label=True):
            turns.append({'start': round(segment.start, 2), 'end': round(segment.end, 2), 'speaker': str(speaker)})
    except Exception:
        return []
    return turns

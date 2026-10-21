"""Non-speech sound events (AudioSet/AST). Labels are turned into readable phrases.

Important design decision: speech labels ("Speech", "Male/Female speech" ...) are filtered out,
otherwise an unnecessary "(speech sound)" is added next to every speech line. Events below the
confidence threshold and consecutive repeats are cleaned up.

Limitation: AST works in ~10 s windows; the event time is window-accurate, not second-accurate.
Sliding windows (hop) improve this but it is not exact.
"""
from __future__ import annotations

_EVENT_MODEL_CACHE: dict = {}

# AST's speech-related labels: not counted as events.
SPEECH_LABELS = {
    'speech', 'male speech, man speaking', 'female speech, woman speaking',
    'child speech, kid speaking', 'conversation', 'narration, monologue',
    'speech synthesizer', 'whoosh, swoosh, swish', 'silence',
    'inside, small room', 'inside, large room or hall', 'outside, urban or manmade',
    'outside, rural or natural', 'music',  # 'music' may be noise; filtered by the threshold
}

# AudioSet label -> readable phrase (common events). Anything else keeps the raw label.
LABEL_TR = {
    'walk, footsteps': 'footsteps',
    'footsteps': 'footsteps',
    'door': 'door sound',
    'doorbell': 'doorbell',
    'knock': 'knocking sound',
    'knock, knock': 'knocking sound',
    'slam': 'door slam',
    'applause': 'applause',
    'laughter': 'laughter',
    'giggle': 'giggling',
    'cough': 'cough',
    'sneeze': 'sneeze',
    'sigh': 'sigh',
    'breathing': 'breathing',
    'crying, sobbing': 'crying',
    'shout': 'shouting',
    'screaming': 'scream',
    'whispering': 'whispering',
    'glass': 'glass sound',
    'shatter': 'breaking glass',
    'thump, thud': 'thump',
    'bang': 'bang',
    'beep, bleep': 'beep',
    'ringtone': 'ringtone',
    'telephone': 'telephone ring',
    'typing': 'typing',
    'writing': 'writing',
    'printer': 'printer',
    'water': 'water',
    'pouring water': 'pouring water',
    'tap': 'tap',
    'dishes, pots, and pans': 'kitchenware',
    'paper rustling': 'rustling paper',
    'crackle': 'crackle',
    'engine': 'engine',
    'car': 'car',
    'vehicle': 'vehicle',
    'air conditioner': 'air conditioner',
    'vacuum cleaner': 'vacuum cleaner',
    'dog': 'dog',
    'bark': 'barking',
    'cat': 'cat',
    'meow': 'meow',
    'bird': 'bird',
    'crowd': 'crowd',
    'chatter': 'chatter',
    'noise': 'noise',
    'white noise': 'white noise',
    'static': 'static',
    'hum': 'hum',
    'cacophony': 'cacophony',
    'environmental noise': 'environmental noise',
    'background noise': 'background noise',
    'wind': 'wind',
    'rain': 'rain',
    'thunder': 'thunder',
    'alarm': 'alarm',
    'siren': 'siren',
    'fireworks': 'fireworks',
    'gunshot, gunfire': 'gunshot',
}


def _translate(label: str) -> str:
    key = label.strip().lower()
    if key in LABEL_TR:
        return LABEL_TR[key]
    # Look for a known pattern (for comma-separated labels like "walk, footsteps").
    for aset, tr in LABEL_TR.items():
        if aset in key:
            return tr
    return label


def _load_events_model(profile):
    from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

    key = profile.events_model
    if key not in _EVENT_MODEL_CACHE:
        extractor = AutoFeatureExtractor.from_pretrained(key)
        model = AutoModelForAudioClassification.from_pretrained(key)
        model.eval()
        _EVENT_MODEL_CACHE[key] = (extractor, model)
    return _EVENT_MODEL_CACHE[key]


def unload_events_model():
    _EVENT_MODEL_CACHE.clear()
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


def tag(wav_path: str, profile, device: str = 'cuda', threshold: float = 0.3,
        window: float = 10.0, hop: float = 5.0, top_k: int = 3, offset: float = 0.0) -> list[dict]:
    """Label the sound event windows. Returns an empty list when there are no events/dependencies."""
    if not profile.events or profile.events_model in (None, '', 'none'):
        return []
    try:
        import numpy as np
        import torch
        from . import audio
    except Exception:
        return []

    # If the AST model cannot be loaded (e.g. a missing HF cache: HF_HOME is not set and the model
    # is not in the default cache) the WHOLE transcript MUST NOT FAIL; events are skipped. Otherwise
    # audio input failed completely (see tests/test_transcriber.py).
    try:
        extractor, model = _load_events_model(profile)
    except Exception:
        return []
    use_cuda = (device or '').lower() == 'cuda' and torch.cuda.is_available()
    if use_cuda:
        model = model.to('cuda')

    samples = audio.read_mono_float32(wav_path)
    rate = audio.SAMPLE_RATE
    win = int(window * rate)
    step = max(int(hop * rate), 1)
    id2label = model.config.id2label

    raw: list[dict] = []
    for start in range(0, max(len(samples) - win + step, step), step):
        chunk = samples[start:start + win]
        if len(chunk) < rate:  # skip a window shorter than 1 s
            continue
        try:
            inputs = extractor(chunk, sampling_rate=rate, return_tensors='pt')
            if use_cuda:
                inputs = {k: v.to('cuda') for k, v in inputs.items()}
            with torch.no_grad():
                logits = model(**inputs).logits
            probs = torch.sigmoid(logits)[0].detach().cpu().numpy()
        except Exception:
            continue
        order = np.argsort(probs)[::-1]
        picked = 0
        for idx in order:
            if picked >= top_k:
                break
            score = float(probs[idx])
            if score < threshold:
                break
            label = str(id2label.get(int(idx), '')).strip()
            if not label or label.lower() in SPEECH_LABELS:
                continue
            raw.append({
                'start': round(start / rate + offset, 1),
                'end': round(min(start + win, len(samples)) / rate + offset, 1),
                'label': label,
                'text': _translate(label),
                'score': round(score, 3),
            })
            picked += 1

    if use_cuda:
        try:
            model.to('cpu')
        except Exception:
            pass
    return _merge_repeats(raw)


def _merge_repeats(events: list[dict], gap: float = 6.0) -> list[dict]:
    """Collapse the same label repeated in consecutive windows into a single event."""
    events = sorted(events, key=lambda e: e['start'])
    merged: list[dict] = []
    for event in events:
        if merged and merged[-1]['label'] == event['label'] and event['start'] - merged[-1]['end'] <= gap:
            merged[-1]['end'] = max(merged[-1]['end'], event['end'])
            merged[-1]['score'] = max(merged[-1]['score'], event['score'])
        else:
            merged.append(dict(event))
    return merged

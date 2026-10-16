"""Konusma disi ses olaylari (AudioSet/AST). Etiketler Turkce ifadeye cevrilir.

Onemli tasarim karari: konusma etiketleri ("Speech", "Male/Female speech" ...) elenir,
yoksa her konusma satirinin yanina gereksiz "(konusma sesi)" eklenir. Guven esiginin
altindaki olaylar ve ardisik tekrarlar temizlenir.

Sinir: AST ~10 sn'lik pencerelerle calisir; olay zamani saniye degil pencere
hassasiyetindedir. Pencereler kaydirilarak (hop) iyilestirilir ama tam hassas olmaz.
"""
from __future__ import annotations

_EVENT_MODEL_CACHE: dict = {}

# AST'nin konusma ile ilgili etiketleri: olay sayilmaz.
SPEECH_LABELS = {
    'speech', 'male speech, man speaking', 'female speech, woman speaking',
    'child speech, kid speaking', 'conversation', 'narration, monologue',
    'speech synthesizer', 'whoosh, swoosh, swish', 'silence',
    'inside, small room', 'inside, large room or hall', 'outside, urban or manmade',
    'outside, rural or natural', 'music',  # 'music' gurultu olabilir; esikle filtrelenir
}

# AudioSet etiketi -> Turkce ifade (sik gecen olaylar). Yoksa etiket oldugu gibi kalir.
LABEL_TR = {
    'walk, footsteps': 'ayak sesleri',
    'footsteps': 'ayak sesleri',
    'door': 'kapı sesi',
    'doorbell': 'kapı zili',
    'knock': 'kapı vurma sesi',
    'knock, knock': 'kapı vurma sesi',
    'slam': 'kapı çarpma sesi',
    'applause': 'alkış',
    'laughter': 'gülüşme',
    'giggle': 'kıkırdama',
    'cough': 'öksürük',
    'sneeze': 'hapşırma',
    'sigh': 'iç çekme',
    'breathing': 'nefes sesi',
    'crying, sobbing': 'ağlama',
    'shout': 'bağırma',
    'screaming': 'çığlık',
    'whispering': 'fısıltı',
    'glass': 'cam sesi',
    'shatter': 'cam kırılması',
    'thump, thud': 'gümlü ses',
    'bang': 'patlama sesi',
    'beep, bleep': 'bip sesi',
    'ringtone': 'zil sesi',
    'telephone': 'telefon sesi',
    'typing': 'klavye sesi',
    'writing': 'yazma sesi',
    'printer': 'yazıcı sesi',
    'water': 'su sesi',
    'pouring water': 'su dökme sesi',
    'tap': 'musluk sesi',
    'dishes, pots, and pans': 'mutfak eşyası sesi',
    'paper rustling': 'kağıt hışırtısı',
    'crackle': 'çıtırtı',
    'engine': 'motor sesi',
    'car': 'araba sesi',
    'vehicle': 'araç sesi',
    'air conditioner': 'klima sesi',
    'vacuum cleaner': 'süpürge sesi',
    'dog': 'köpek sesi',
    'bark': 'köpek havlaması',
    'cat': 'kedi sesi',
    'meow': 'miyavlama',
    'bird': 'kuş sesi',
    'crowd': 'kalabalık sesi',
    'chatter': 'konuşma uğultusu',
    'noise': 'gürültü',
    'white noise': 'beyaz gürültü',
    'static': 'parazit',
    'hum': 'uğultu',
    'cacophony': 'uğultu',
    'environmental noise': 'ortam gürültüsü',
    'background noise': 'arka plan gürültüsü',
    'wind': 'rüzgar sesi',
    'rain': 'yağmur sesi',
    'thunder': 'gök gürültüsü',
    'alarm': 'alarm sesi',
    'siren': 'siren sesi',
    'fireworks': 'havai fişek',
    'gunshot, gunfire': 'silah sesi',
}


def _translate(label: str) -> str:
    key = label.strip().lower()
    if key in LABEL_TR:
        return LABEL_TR[key]
    # Bilinen kalibi ara ("walk, footsteps" gibi virgullu etiketler icin).
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
    """Ses olayi pencerelerini etiketler. Olay yoksa/bagimlilik yoksa bos liste doner."""
    if not profile.events or profile.events_model in (None, '', 'none'):
        return []
    try:
        import numpy as np
        import torch
        from . import audio
    except Exception:
        return []

    # AST modeli yuklenemezse (or. HF onbellegi eksik: HF_HOME ayarlanmamis ve varsayilan
    # onbellekte model yok) TUM dökum DUSMEMELI; olaylar atlanir. Aksi halde sesli giris
    # tamamen hata veriyordu (bkz. tests/test_transcriber.py).
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
        if len(chunk) < rate:  # 1 sn'den kisa pencereyi atla
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
    """Ayni etiket ardisik pencerelerde tekrar ederse tek olaya indirir."""
    events = sorted(events, key=lambda e: e['start'])
    merged: list[dict] = []
    for event in events:
        if merged and merged[-1]['label'] == event['label'] and event['start'] - merged[-1]['end'] <= gap:
            merged[-1]['end'] = max(merged[-1]['end'], event['end'])
            merged[-1]['score'] = max(merged[-1]['score'], event['score'])
        else:
            merged.append(dict(event))
    return merged

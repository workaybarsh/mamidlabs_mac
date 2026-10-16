"""Ses dökum iscisi: `transcriber` paketini cagirir.

Motor: faster-whisper large-v3-tr (Turkce). Ses olaylari (AST) ve konusmaci ayrimi
(pyannote) varsayilan aciktir. Cikti bicimi kronolojik, zaman damgasiz:

    (ayak sesleri)
    Konusmaci: Geldin mi?
    (kapi sesi)
    Konusmaci: Evet, biraz geciktim.

Arayuz/isci sozlesmesi: stdin'den JSON alir, stdout'a JSON yazar.
    istek: {"action":"transcribe","path":...,"device":"auto|cuda|cpu","need_swap":bool,"profile":"lite|pro","language":"tr", ...}
    istek: {"action":"plan","local_model_loaded":bool,"profile":"lite|pro"}   -> {"device":..,"need_swap":..}
    istek: {"action":"unload"}   -> yuklu modelleri bellekten cikarir (VRAM/RAM iadesi)
    yanit: {"text":..., "model":..., "chars":..., "events":N, "diarized":bool} ya da {"error":...}

SICAK (kalici) isci: `--serve` ile tek seferlik stdin yerine 127.0.0.1 uzerinde surekli
calisir ve modelleri SÜREÇ İÇİNDE tutar. Boylece her ses turunda tekrarlanan sabit
maliyet (Python baslatma + torch/transformers/faster-whisper importlari; ölçüldü ~10 sn,
ilk/disk sogukken ~25 sn) oturumda BIR kez odenir; dil modeli VRAM'i gerektiginde cagiran
`{"action":"unload"}` ile ses modellerini bosaltir (surec yasamaya devam eder).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

# transcriber paketi bu dosyanin yanindaki alt klasordedir (<kok>/agent/transcriber).
AGENT_DIR = pathlib.Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from transcriber import config, main as transcriber_main  # noqa: E402


def _profile(req: dict):
    """Ses hatti tier'i SECILI profil adindan gelir: 'lite', 'pro' ('max'/'flash'), ya da
    eski adlar 'pc1'/'pc2'. Ad yoksa/taninmiyorsa tier'i makinenin toplam VRAM'i belirler
    (bkz. config.select_profile_for)."""
    language = str(req.get('language') or '').strip()
    overrides = {}
    if language and language != 'auto':
        overrides['language'] = language
    name = req.get('profile')
    if name:
        return config.select_profile_for(name, **overrides)
    return config.select_profile(**overrides) if overrides else config.select_profile()


def transcribe(req: dict) -> dict:
    # 'auto' oldugu gibi gecirilir; cihazi transcriber paketi kaydin suresine gore secer.
    device = str(req.get('device') or 'auto').lower()
    if device == 'gpu':
        device = 'cuda'
    # need_swap: yerel 27B saglayicida dil modeli VRAM swap maliyeti oldugunu isciye bildir.
    # Alan yoksa None birak (paket guvenli varsayilani uygular).
    need_swap = req.get('need_swap')
    if need_swap is not None:
        need_swap = bool(need_swap)
    profile = _profile(req)
    payload = transcriber_main.run(
        str(req.get('path') or ''),
        profile=profile,
        device=device,
        need_swap=need_swap,
        initial_prompt=req.get('initial_prompt'),
        events=req.get('events'),
        diarize_enabled=req.get('diarize'),
        token=req.get('token'),
        include_timestamps=False,
        out_base=req.get('out_base'),
        keep_wav=False,
    )
    return {
        'text': payload['text'],
        'model': os.path.basename(profile.whisper_model),
        'vad': 'silero',
        'chars': len(payload['text']),
        'language': payload['language'],
        'profile': profile.name,
        'events': len(payload['events']),
        'diarized': payload['diarized'],
    }


def plan(req: dict) -> dict:
    """Ses isi baslamadan once (cihaz, swap) planini doner (bkz. config.choose_plan).

    Oncelik: (1) dil modeliyle birlikte bos VRAM'e sigarsa GPU + swap yok; (2) sigmazsa ve
    kayit KISAYSA (swap maliyeti kazanci asar) CPU'da RAM'e sigiyorsa CPU + swap yok;
    (3) aksi halde (uzun kayit ya da RAM yetmiyor) GPU + mecburi swap. Kaydin suresi
    `path`ten cozmeden tahmin edilir.
    Isci bu plani arayuz/isci katmanina bildirir; dil modeli YALNIZCA swap gerektiginde
    bosaltilir.
    """
    profile = _profile(req)
    local = req.get('local_model_loaded')
    local = True if local is None else bool(local)
    vram = config.free_vram_mib()
    ram = config.available_ram_mib()
    # Kaydin suresi (kisa -> CPU, uzun -> GPU ekonomisi icin). Dosyayi cozmeden tahmin edilir.
    duration = None
    path = str(req.get('path') or '')
    if path:
        try:
            from transcriber import audio
            duration = audio.probe_duration_seconds(path)
        except Exception:
            duration = None
    device, need_swap = config.choose_plan(
        profile, duration_seconds=duration, vram_free_mib=vram, ram_free_mib=ram,
        local_model_loaded=local)
    return {
        'device': device,
        'need_swap': need_swap,
        'profile': profile.name,
        'duration_seconds': duration,
        'free_vram_mib': vram,
        'free_ram_mib': ram,
    }


def unload(_req: dict | None = None) -> dict:
    """Yuklu ASR/AST/konusmaci modellerini bellekten cikarir (VRAM/RAM iadesi).

    Kalici (sicak) isci modelleri surec icinde tutar; dil modeli VRAM'e geri yuklenmeden
    ONCE ses modellerinin bosaltilmasi icin cagrilir (bkz. mamidlabs-inference.ps1). Surec
    YASAMAYA DEVAM EDER (yalnizca modeller atilir): importlar/onbellekler sicak kalir.
    """
    from transcriber import asr, diarize, events
    for fn in (getattr(asr, 'unload_model', None),
               getattr(events, 'unload_events_model', None),
               getattr(diarize, 'unload_pipeline', None)):
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
    return {'ok': True, 'unloaded': True}


ACTIONS = {'transcribe': transcribe, 'plan': plan, 'unload': unload}


def _dispatch(req: dict) -> dict:
    """Tek bir istegi isler ve yanit sozlugunu doner (tek-atimlik main + serve ORTAK)."""
    action = req.get('action')
    if action == 'ping':
        return {'ok': True, 'pid': os.getpid()}
    handler = ACTIONS.get(action)
    if not handler:
        return {'error': 'bilinmeyen islem'}
    try:
        return handler(req)
    except Exception as exc:
        return {'error': '%s: %s' % (type(exc).__name__, exc)}


def _write_state(state_file: str, data: dict) -> None:
    """Durum dosyasini ATOMIK yazar (istemci yarim/bozuk JSON okumasin)."""
    tmp = state_file + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh)
    os.replace(tmp, state_file)


def _parent_gone(parent_pid: int) -> bool:
    """Ust surec (uygulama) kapandi mi? Kapanmissa sunucu kendini bitirir (sizinti yok)."""
    if not parent_pid:
        return False
    if os.name == 'nt':
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(parent_pid))
            if not handle:
                return True
            try:
                code = ctypes.c_ulong()
                ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
                return bool(ok) and code.value != STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(int(parent_pid), 0)
        return False
    except ProcessLookupError:
        return True
    except Exception:
        return False


def _serve_client(conn) -> None:
    """Tek istemci baglantisini isler: bir satir JSON istegi -> bir satir JSON yaniti."""
    stream = conn.makefile('rwb')
    try:
        line = stream.readline()
        if not line:
            return
        try:
            req = json.loads(line.decode('utf-8') or '{}')
        except Exception as exc:
            resp = {'error': 'gecersiz istek: %s' % exc}
        else:
            resp = _dispatch(req)
        stream.write((json.dumps(resp, ensure_ascii=False) + '\n').encode('utf-8'))
        stream.flush()
    finally:
        try:
            stream.close()
        except Exception:
            pass


def serve(state_file: str, parent_pid: int = 0, idle_timeout: float = 600.0) -> int:
    """Kalici (sicak) isci: modelleri SÜREÇ İÇİNDE tutar, istekleri 127.0.0.1 uzerinden alir.

    Amac: her ses turunda tekrarlanan sabit maliyeti (Python baslatma + torch/transformers/
    faster-whisper importlari) oturumda BIR kez odemek. Dil modeli VRAM'i gerektiginde
    cagiran taraf `{"action":"unload"}` ile ses modellerini bosaltir; surec yasamaya devam
    eder ve sonraki turda yalnizca model YUKLEME maliyeti kalir.

    Guvenlik: `parent_pid` (uygulama) kapaninca ya da `idle_timeout` sn boyunca istek
    gelmezse surec kendini bitirir; boylece artik (orphan) surec/VRAM/RAM sizintisi olmaz.
    """
    import socket
    import time

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('127.0.0.1', 0))
    server.listen(8)
    port = server.getsockname()[1]
    server.settimeout(1.0)
    try:
        _write_state(state_file, {'pid': os.getpid(), 'port': port, 'started': time.time()})
    except Exception:
        pass
    last = time.time()
    try:
        while True:
            try:
                conn, _ = server.accept()
            except socket.timeout:
                if _parent_gone(parent_pid) or (idle_timeout > 0 and time.time() - last > idle_timeout):
                    break
                continue
            except OSError:
                break
            try:
                _serve_client(conn)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            last = time.time()
            if _parent_gone(parent_pid):
                break
    finally:
        try:
            server.close()
        except Exception:
            pass
        try:
            if os.path.isfile(state_file):
                os.remove(state_file)
        except Exception:
            pass
    return 0


def main() -> None:
    argv = sys.argv[1:]
    if '--serve' in argv:
        parser = argparse.ArgumentParser(description='Kalici (sicak) ses dokum iscisi')
        parser.add_argument('--serve', action='store_true')
        parser.add_argument('--state-file', required=True)
        parser.add_argument('--parent-pid', type=int, default=0)
        parser.add_argument('--idle-timeout', type=float, default=600.0)
        args = parser.parse_args(argv)
        raise SystemExit(serve(args.state_file, args.parent_pid, args.idle_timeout))
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stdin.reconfigure(encoding='utf-8')
    except Exception:
        pass
    try:
        req = json.loads(sys.stdin.read() or '{}')
    except Exception as exc:
        print(json.dumps({'error': 'gecersiz istek: %s' % exc}, ensure_ascii=False))
        return
    print(json.dumps(_dispatch(req), ensure_ascii=False))


if __name__ == '__main__':
    main()

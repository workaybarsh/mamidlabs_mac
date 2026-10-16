"""Video yardimcilari: kare cikarma, bilgi okuma, kucuk resim.

imagegen venv'i ile calisir (PyAV kurulu). stdin'den JSON alir, stdout'a JSON yazar.
"""
import json
import os
import pathlib
import sys


MAX_VIDEO_FILE_BYTES = 512 * 1024 * 1024
MAX_VIDEO_DURATION_SECONDS = 600
# Kurulum kokunu ortam degiskeninden oku (bkz. _root.py).
from _root import install_root

OUTPUT_ROOT = (install_root() / 'outputs')


def _open(path):
    if os.path.getsize(path) > MAX_VIDEO_FILE_BYTES:
        raise ValueError('Video boyutu guvenlik sinirini asti.')
    import av
    return av.open(path)


def _validate_duration(container):
    if container.duration and container.duration / 1000000.0 > MAX_VIDEO_DURATION_SECONDS:
        raise ValueError('Video suresi guvenlik sinirini asti.')


def _output_path(value):
    candidate = pathlib.Path(value).resolve()
    try:
        candidate.relative_to(OUTPUT_ROOT)
    except ValueError:
        raise ValueError('Video kare cikisi outputs klasoru icinde olmali.')
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def video_info(req):
    with _open(req['path']) as container:
        _validate_duration(container)
        stream = container.streams.video[0]
        fps = float(stream.average_rate) if stream.average_rate else 0.0
        duration = float(container.duration) / 1000000.0 if container.duration else 0.0
        return {
            'width': stream.codec_context.width,
            'height': stream.codec_context.height,
            'fps': round(fps, 3),
            'duration': round(duration, 3),
            'frames': stream.frames or 0,
        }


def video_frame(req):
    """which = 'first' | 'last' -> PNG olarak kaydeder."""
    which = req.get('which', 'first')
    out = _output_path(req['out'])
    with _open(req['path']) as container:
        _validate_duration(container)
        stream = container.streams.video[0]
        stream.thread_type = 'AUTO'
        picked = None
        for frame in container.decode(stream):
            picked = frame
            if which == 'first':
                break
        if picked is None:
            return {'error': 'videodan kare okunamadi'}
        image = picked.to_image()
        max_side = int(req.get('max_side', 1280))
        if max(image.size) > max_side:
            scale = max_side / float(max(image.size))
            image = image.resize((max(8, int(image.size[0] * scale)), max(8, int(image.size[1] * scale))))
        image.save(str(out))
        return {'out': str(out), 'width': image.size[0], 'height': image.size[1]}


ACTIONS = {'video_info': video_info, 'video_frame': video_frame}


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stdin.reconfigure(encoding='utf-8')
    except Exception:
        pass
    req = json.loads(sys.stdin.read() or '{}')
    handler = ACTIONS.get(req.get('action'))
    if not handler:
        print(json.dumps({'error': 'bilinmeyen islem'}, ensure_ascii=False))
        return
    try:
        print(json.dumps(handler(req), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'error': '%s: %s' % (type(exc).__name__, exc)}, ensure_ascii=False))


if __name__ == '__main__':
    main()

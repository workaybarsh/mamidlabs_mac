"""Hugging Face access without writing a plaintext token into the Hub cache."""
import hashlib
import json
import os
import pathlib
import shutil
import sys

# Hub/xet onbellegi kullanici profiline (~/.cache/huggingface) degil kurulum kokune
# yazilir; kaldirmada kokle birlikte silinir. Import'tan once ayarlanmalidir.
from _root import install_root

os.environ.setdefault('HF_HOME', str(install_root() / 'tools' / 'hf-home'))
from huggingface_hub import HfApi, hf_hub_download
from mtp_inject import ensure_mtp, has_mtp

def emit(kind, text):
    print(json.dumps(dict(kind=kind, text=text), ensure_ascii=False), flush=True)

def safe_repo_path(name):
    # Windows ayraclarini depo ici POSIX yoluna cevirir.
    name = pathlib.PureWindowsPath(str(name)).as_posix()
    parts = pathlib.PurePosixPath(name).parts
    if pathlib.PurePosixPath(name).is_absolute() or '..' in parts or ':' in name:
        raise ValueError('Geçerli bir depo içi dosya yolu gir.')
    return name

def prune_empty(folder, stop):
    """Indirme sonrasi geride kalan bos depo alt klasorlerini temizler."""
    folder = pathlib.Path(folder)
    while folder != stop and folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
        folder = folder.parent

def sha256_file(path, chunk=1024 * 1024):
    """Dosyanin SHA256 ozetini parca parca hesaplar (52 GB'lik model icin bellek dostu)."""
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(chunk), b''):
            digest.update(block)
    return digest.hexdigest()

_sha_cache = {}

def lookup_sha256(item, token):
    """Katalogda sha256 yoksa Hugging Face'in LFS ozetini sorar (depo basina bir kez).

    Ozlu bir depoda, ag yokken ya da saglayici ozet vermiyorsa None doner; indirme
    boyut dogrulamasiyla surer. Sert hata degildir: ozet yalnizca ek guvencedir.
    """
    repo = item.get('repo') or ''
    name = safe_repo_path(item.get('filename') or '')
    if not repo or not name:
        return None
    revision = item.get('revision') or 'main'
    key = (repo, revision)
    if key not in _sha_cache:
        mapping = {}
        try:
            info = HfApi(token=token).model_info(repo_id=repo, revision=revision, files_metadata=True)
            for sibling in (info.siblings or []):
                lfs = getattr(sibling, 'lfs', None)
                if isinstance(lfs, dict):
                    sha = lfs.get('sha256')
                elif lfs is not None:
                    sha = getattr(lfs, 'sha256', None)
                else:
                    sha = None
                if sha:
                    mapping[sibling.rfilename] = str(sha).lower()
        except Exception:
            mapping = {}
        _sha_cache[key] = mapping
    return _sha_cache[key].get(name)

def incomplete_bytes(target, name):
    """Bu dosyaya ait yarim indirmenin boyutu.

    hf_hub_download parcali indirmeyi `local_dir/.cache/huggingface/download`
    altinda saklar ve sonraki cagrida HTTP Range ile kaldigi yerden surer.
    """
    cache = pathlib.Path(target).parent / '.cache' / 'huggingface' / 'download'
    if not cache.is_dir():
        return 0
    base = pathlib.PurePosixPath(name).name
    total = 0
    for path in cache.rglob('*.incomplete'):
        if not path.name.startswith(base):
            continue
        try:
            total += path.stat().st_size
        except OSError:
            pass
    return total

def verify_sha256(target, expected, label):
    """Ozeti dogrular; uyusmazsa bozuk dosyayi siler ve net hata verir."""
    actual = sha256_file(target)
    if actual == expected:
        emit('status', f'{label}: SHA256 doğrulandı.')
        return
    pathlib.Path(target).unlink(missing_ok=True)
    raise ValueError(
        f'{label}: indirilen dosyanın SHA256 özeti beklenenle uyuşmuyor '
        f'({actual} != {expected}). Dosya bozuk kabul edildi ve silindi; tekrar indir.')

def _mtp_config(item):
    """MTP yapilandirmasini tek bicime indirger (katalog `mtp` sozlugu ya da `mtpRepo`)."""
    cfg = item.get('mtp')
    if isinstance(cfg, str):
        cfg = {'repo': cfg} if cfg else None
    if not cfg and item.get('mtpRepo'):
        cfg = {'repo': item['mtpRepo']}
    return cfg or None

def fetch(item, token, index, total):
    name = safe_repo_path(item['filename'])
    label = item.get('label') or pathlib.PurePosixPath(name).name
    target = pathlib.Path(item['target']).resolve()
    expected_bytes = int(item.get('bytes') or 0)
    pinned_sha = (item.get('sha256') or '').strip().lower() or None
    mtp_cfg = _mtp_config(item)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not item.get('force'):
        # MTP enjeksiyonu dosyayi buyuttugu icin, MTP'li dosyada boyut kontrolu atlanir.
        if mtp_cfg and has_mtp(str(target)):
            emit('status', f'[{index}/{total}] {label} zaten var (MTP dahil), atlandı.')
            emit('artifact', str(target))
            return
        if expected_bytes and target.stat().st_size != expected_bytes:
            raise ValueError(
                f'{label}: diskteki dosya boyutu beklenenle uyuşmuyor '
                f'({target.stat().st_size} != {expected_bytes} bayt). Yarım/bozuk indirme olabilir; '
                'dosyayı silip tekrar indir.')
        if pinned_sha:
            # Katalogda sabit ozet varsa cevrimdisi de dogrulanir; uyusmazlikta
            # mevcut dosya sessizce silinmez (kullaniciya net hata verilir).
            if sha256_file(target) != pinned_sha:
                raise ValueError(
                    f'{label}: diskteki dosyanın SHA256 özeti katalogdakiyle uyuşmuyor. '
                    'Dosyayı silip tekrar indir.')
        if mtp_cfg:
            # Var olan (MTP'siz) modeli yeniden indirmeden basliga MTP ekle.
            ensure_mtp(str(target), mtp_cfg, token, lambda text: emit('status', f'{label}: {text}'))
            emit('artifact', str(target))
            return
        emit('status', f'[{index}/{total}] {label} zaten var, atlandı.')
        emit('artifact', str(target))
        return
    pending = incomplete_bytes(target, name)
    if pending:
        emit('status', f'[{index}/{total}] {label}: yarım indirme bulundu '
                       f'({pending // (1024 * 1024)} MB), kaldığı yerden sürülecek.')
    emit('status', f'[{index}/{total}] {label} indiriliyor…')
    # local_dir hedef klasorun kendisidir; boylece dosya ayni diskte iner ve
    # tasima islemi kopyalama olmadan tamamlanir (10 GB'lik dosyalar icin onemli).
    path = pathlib.Path(hf_hub_download(
        repo_id=item['repo'], filename=name, revision=item.get('revision') or 'main',
        local_dir=str(target.parent), token=token))
    if path != target:
        os.replace(path, target)
        prune_empty(path.parent, target.parent)
    if expected_bytes and target.stat().st_size != expected_bytes:
        actual = target.stat().st_size
        target.unlink(missing_ok=True)
        raise ValueError(
            f'{label}: indirilen dosya boyutu beklenenle uyuşmuyor ({actual} != {expected_bytes} bayt). '
            'Dosya bozuk kabul edildi ve silindi; tekrar indir.')
    expected_sha = pinned_sha or lookup_sha256(item, token)
    if expected_sha:
        # MTP enjeksiyonundan ONCE dogrulanir: enjeksiyon dosyayi degistirir.
        verify_sha256(target, expected_sha, label)
    if mtp_cfg:
        # MTP basligi donusturucuden dusen modeller icin indirme sonrasi eklenir.
        ensure_mtp(str(target), mtp_cfg, token, lambda text: emit('status', f'{label}: {text}'))
    emit('artifact', str(target))

def run(job):
    token = job.get('apiKey') or os.environ.get('HF_TOKEN') or None
    if token:
        user = HfApi(token=token).whoami()
        emit('status', 'Hugging Face bağlantısı doğrulandı: ' + user.get('name', 'hesap'))
    else:
        # Katalogdaki depolar herkese aciktir; token yalnizca kisitli depolar icin gerekir.
        emit('status', 'Token kayıtlı değil; yalnızca herkese açık depolar indirilebilir.')
    if job.get('action') != 'download':
        return
    files = job.get('files')
    if not files:
        # Hugging Face penceresinden gelen tek dosyalik eski bicim.
        name = safe_repo_path(job['filename'])
        destination = pathlib.Path(job['destination']).resolve()
        files = [dict(repo=job['repo'], filename=name, revision=job.get('revision'),
                      target=str(destination / pathlib.PurePosixPath(name).name))]
    total = len(files)
    for index, item in enumerate(files, 1):
        fetch(item, token, index, total)
    emit('status', f'{total} dosya hazır.')

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdin.reconfigure(encoding='utf-8')
    job = json.load(sys.stdin)
    try:
        run(job)
    except Exception as exc:
        message = str(exc).replace(job.get('apiKey') or '\0', '[gizli]')
        emit('error', message[:800])

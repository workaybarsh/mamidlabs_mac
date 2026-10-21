"""Hugging Face access without writing a plaintext token into the Hub cache."""
import hashlib
import json
import os
import pathlib
import shutil
import sys

# The Hub/xet cache is written under the install root instead of the user profile
# (~/.cache/huggingface), so uninstalling removes it together with the root. It
# must be set before the import.
from _root import install_root

os.environ.setdefault('HF_HOME', str(install_root() / 'tools' / 'hf-home'))
from huggingface_hub import HfApi, hf_hub_download
from mtp_inject import ensure_mtp, has_mtp

def emit(kind, text):
    print(json.dumps(dict(kind=kind, text=text), ensure_ascii=False), flush=True)

def safe_repo_path(name):
    # Convert Windows separators to a POSIX path inside the repository.
    name = pathlib.PureWindowsPath(str(name)).as_posix()
    parts = pathlib.PurePosixPath(name).parts
    if pathlib.PurePosixPath(name).is_absolute() or '..' in parts or ':' in name:
        raise ValueError('Enter a valid file path inside the repository.')
    return name

def prune_empty(folder, stop):
    """Remove empty repository subfolders left behind after a download."""
    folder = pathlib.Path(folder)
    while folder != stop and folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
        folder = folder.parent

def sha256_file(path, chunk=1024 * 1024):
    """Compute a file's SHA256 digest chunk by chunk (memory-friendly for a 52 GB model)."""
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(chunk), b''):
            digest.update(block)
    return digest.hexdigest()

_sha_cache = {}

def lookup_sha256(item, token):
    """Ask Hugging Face for the LFS digest when the catalog has no sha256 (once per repo).

    Returns None for a private repo, when offline or when the provider does not
    supply a digest; the download then proceeds with size verification only. This
    is not a hard error: the digest is an extra guarantee.
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
    """Size of the partial download for this file.

    hf_hub_download keeps a chunked download under `local_dir/.cache/huggingface/download`
    and resumes it with an HTTP Range request on the next call.
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
    """Verify the digest; on a mismatch delete the corrupt file and fail clearly."""
    actual = sha256_file(target)
    if actual == expected:
        emit('status', f'{label}: SHA256 verified.')
        return
    pathlib.Path(target).unlink(missing_ok=True)
    raise ValueError(
        f'{label}: the downloaded file\'s SHA256 digest does not match the expected one '
        f'({actual} != {expected}). The file was treated as corrupt and deleted; download it again.')

def _mtp_config(item):
    """Normalise the MTP configuration (catalog `mtp` dict or `mtpRepo`)."""
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
        # MTP injection grows the file, so the size check is skipped for an MTP file.
        if mtp_cfg and has_mtp(str(target)):
            emit('status', f'[{index}/{total}] {label} already present (MTP included), skipped.')
            emit('artifact', str(target))
            return
        if expected_bytes and target.stat().st_size != expected_bytes:
            raise ValueError(
                f'{label}: the file size on disk does not match the expected one '
                f'({target.stat().st_size} != {expected_bytes} bytes). It may be a partial/corrupt '
                'download; delete the file and download it again.')
        if pinned_sha:
            # With a pinned digest in the catalog the check also works offline; a
            # mismatch does not silently delete the existing file (the user gets a
            # clear error).
            if sha256_file(target) != pinned_sha:
                raise ValueError(
                    f'{label}: the SHA256 digest of the file on disk does not match the catalog. '
                    'Delete the file and download it again.')
        if mtp_cfg:
            # Add MTP to the header of an existing (non-MTP) model without re-downloading.
            ensure_mtp(str(target), mtp_cfg, token, lambda text: emit('status', f'{label}: {text}'))
            emit('artifact', str(target))
            return
        emit('status', f'[{index}/{total}] {label} already present, skipped.')
        emit('artifact', str(target))
        return
    pending = incomplete_bytes(target, name)
    if pending:
        emit('status', f'[{index}/{total}] {label}: partial download found '
                       f'({pending // (1024 * 1024)} MB), resuming from where it stopped.')
    emit('status', f'[{index}/{total}] {label} downloading…')
    # local_dir is the target folder itself, so the file lands on the same disk and
    # the move completes without copying (important for 10 GB files).
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
            f'{label}: the downloaded file size does not match the expected one ({actual} != {expected_bytes} bytes). '
            'The file was treated as corrupt and deleted; download it again.')
    expected_sha = pinned_sha or lookup_sha256(item, token)
    if expected_sha:
        # Verified BEFORE MTP injection: the injection changes the file.
        verify_sha256(target, expected_sha, label)
    if mtp_cfg:
        # The MTP header is added after the download for models that lost it during conversion.
        ensure_mtp(str(target), mtp_cfg, token, lambda text: emit('status', f'{label}: {text}'))
    emit('artifact', str(target))

def run(job):
    token = job.get('apiKey') or os.environ.get('HF_TOKEN') or None
    if token:
        user = HfApi(token=token).whoami()
        emit('status', 'Hugging Face connection verified: ' + user.get('name', 'account'))
    else:
        # The catalog repositories are public; a token is only needed for restricted repos.
        emit('status', 'No token is stored; only public repositories can be downloaded.')
    if job.get('action') != 'download':
        return
    files = job.get('files')
    if not files:
        # Legacy single-file format coming from the Hugging Face window.
        name = safe_repo_path(job['filename'])
        destination = pathlib.Path(job['destination']).resolve()
        files = [dict(repo=job['repo'], filename=name, revision=job.get('revision'),
                      target=str(destination / pathlib.PurePosixPath(name).name))]
    total = len(files)
    for index, item in enumerate(files, 1):
        fetch(item, token, index, total)
    emit('status', f'{total} files ready.')

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdin.reconfigure(encoding='utf-8')
    job = json.load(sys.stdin)
    try:
        run(job)
    except Exception as exc:
        message = str(exc).replace(job.get('apiKey') or '\0', '[redacted]')
        emit('error', message[:800])

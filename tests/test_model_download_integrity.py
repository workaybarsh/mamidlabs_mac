"""Model download integrity: SHA256 verification + resumable downloads.

``hf-hub.py`` is a worker script (file name has a dash), so it is loaded by path
for unit-testing its pure helpers and the fetch guard logic.
"""

from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import sys

import pytest

WORKERS = pathlib.Path(__file__).resolve().parents[1] / "mamidlabs" / "workers"


def _load_hfhub():
    # hf-hub.py does ``from _root import ...`` and ``from mtp_inject import ...``,
    # so the workers directory has to be importable.
    sys.path.insert(0, str(WORKERS))
    spec = importlib.util.spec_from_file_location("hfhub_under_test", WORKERS / "hf-hub.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def hfhub():
    return _load_hfhub()


# --- sha256 ------------------------------------------------------------------
def test_sha256_file_matches_hashlib(tmp_path, hfhub):
    path = tmp_path / "blob.bin"
    payload = b"mamidlabs" * 5000
    path.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()
    assert hfhub.sha256_file(path) == expected


# --- mtp config normalisation ------------------------------------------------
def test_mtp_config_accepts_dict(hfhub):
    assert hfhub._mtp_config({"mtp": {"repo": "a/b"}}) == {"repo": "a/b"}


def test_mtp_config_accepts_string(hfhub):
    assert hfhub._mtp_config({"mtp": "a/b"}) == {"repo": "a/b"}


def test_mtp_config_accepts_legacy_mtprepo(hfhub):
    assert hfhub._mtp_config({"mtpRepo": "a/b"}) == {"repo": "a/b"}


def test_mtp_config_empty_is_none(hfhub):
    assert hfhub._mtp_config({}) is None
    assert hfhub._mtp_config({"mtp": "", "mtpRepo": ""}) is None


# --- incomplete (resume) size ------------------------------------------------
def test_incomplete_bytes_sums_matching_partials(tmp_path, hfhub):
    target = tmp_path / "model.gguf"
    target.write_bytes(b"")
    cache = target.parent / ".cache" / "huggingface" / "download"
    cache.mkdir(parents=True)
    (cache / "model.gguf.incomplete").write_bytes(b"x" * 4096)
    (cache / "other.gguf.incomplete").write_bytes(b"y" * 9999)
    assert hfhub.incomplete_bytes(target, "model.gguf") == 4096


def test_incomplete_bytes_without_cache_is_zero(tmp_path, hfhub):
    assert hfhub.incomplete_bytes(tmp_path / "model.gguf", "model.gguf") == 0


# --- verify: delete on mismatch ---------------------------------------------
def test_verify_sha256_passes_on_match(tmp_path, hfhub, monkeypatch):
    path = tmp_path / "ok.bin"
    path.write_bytes(b"hello")
    digest = hashlib.sha256(b"hello").hexdigest()
    monkeypatch.setattr(hfhub, "emit", lambda *a, **k: None)
    hfhub.verify_sha256(path, digest, "label")  # must not raise
    assert path.exists()


def test_verify_sha256_deletes_on_mismatch(tmp_path, hfhub, monkeypatch):
    path = tmp_path / "bad.bin"
    path.write_bytes(b"hello")
    monkeypatch.setattr(hfhub, "emit", lambda *a, **k: None)
    with pytest.raises(ValueError):
        hfhub.verify_sha256(path, "deadbeef", "label")
    assert not path.exists()  # broken file never stays on disk


# --- fetch guard: existing files --------------------------------------------
def _events(hfhub, monkeypatch):
    collected: list[tuple[str, str]] = []
    monkeypatch.setattr(hfhub, "emit", lambda kind, text: collected.append((kind, text)))
    return collected


def test_fetch_skips_existing_file_with_correct_size(tmp_path, hfhub, monkeypatch):
    target = tmp_path / "model.gguf"
    target.write_bytes(b"12345")
    events = _events(hfhub, monkeypatch)
    hfhub.fetch({"repo": "a/b", "filename": "model.gguf", "target": str(target),
                 "bytes": 5}, None, 1, 1)
    assert any(kind == "artifact" for kind, _ in events)


def test_fetch_existing_wrong_size_raises(tmp_path, hfhub, monkeypatch):
    target = tmp_path / "model.gguf"
    target.write_bytes(b"12345")
    _events(hfhub, monkeypatch)
    with pytest.raises(ValueError):
        hfhub.fetch({"repo": "a/b", "filename": "model.gguf", "target": str(target),
                     "bytes": 999}, None, 1, 1)


def test_fetch_existing_pinned_sha_mismatch_does_not_delete(tmp_path, hfhub, monkeypatch):
    target = tmp_path / "model.gguf"
    target.write_bytes(b"12345")
    _events(hfhub, monkeypatch)
    with pytest.raises(ValueError):
        hfhub.fetch({"repo": "a/b", "filename": "model.gguf", "target": str(target),
                     "bytes": 5, "sha256": "deadbeef"}, None, 1, 1)
    # Unlike a fresh download, an existing file is not silently removed.
    assert target.exists()


def test_fetch_existing_with_mtp_header_is_skipped(tmp_path, hfhub, monkeypatch):
    target = tmp_path / "model.gguf"
    target.write_bytes(b"whatever-size")
    monkeypatch.setattr(hfhub, "has_mtp", lambda path: True)
    events = _events(hfhub, monkeypatch)
    hfhub.fetch({"repo": "a/b", "filename": "model.gguf", "target": str(target),
                 "bytes": 5, "mtp": {"repo": "a/b"}}, None, 1, 1)
    assert any("MTP" in text for _, text in events)


def test_fetch_download_verifies_sha_before_mtp(tmp_path, hfhub, monkeypatch):
    target = tmp_path / "model.gguf"
    payload = b"model-bytes"
    digest = hashlib.sha256(payload).hexdigest()

    def fake_download(**kwargs):
        target.write_bytes(payload)
        return str(target)

    monkeypatch.setattr(hfhub, "hf_hub_download", fake_download)
    monkeypatch.setattr(hfhub, "lookup_sha256", lambda item, token: digest)
    injected: list[str] = []
    monkeypatch.setattr(hfhub, "ensure_mtp",
                        lambda path, cfg, token, notify: injected.append(path))
    events = _events(hfhub, monkeypatch)
    hfhub.fetch({"repo": "a/b", "filename": "model.gguf", "target": str(target),
                 "bytes": len(payload), "mtp": {"repo": "a/b"}}, None, 1, 1)
    assert any("doğrulandı" in text for _, text in events)  # verified
    assert injected == [str(target)]  # MTP injected after verification


def test_fetch_download_mismatch_is_deleted_and_raises(tmp_path, hfhub, monkeypatch):
    target = tmp_path / "model.gguf"
    payload = b"corrupt-bytes"

    def fake_download(**kwargs):
        target.write_bytes(payload)
        return str(target)

    monkeypatch.setattr(hfhub, "hf_hub_download", fake_download)
    monkeypatch.setattr(hfhub, "lookup_sha256", lambda item, token: "deadbeef")
    _events(hfhub, monkeypatch)
    with pytest.raises(ValueError):
        hfhub.fetch({"repo": "a/b", "filename": "model.gguf", "target": str(target),
                     "bytes": len(payload)}, None, 1, 1)
    assert not target.exists()

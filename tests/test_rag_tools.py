"""Local RAG: offline BM25 search in the bound folder (``search_folder``).

The worker is a standalone script (its file name has a dash), so it is exercised
through a real child process — the same contract the app uses.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

from mamidlabs.core.paths import Paths
from mamidlabs.core.runner import WorkerRunner
from mamidlabs.core.settings import SecretStore, Settings
from mamidlabs.core.tools import ToolRegistry

WORKER = pathlib.Path(__file__).resolve().parents[1] / "mamidlabs" / "workers" / "rag-tools.py"


def _call(request: dict, cwd: pathlib.Path) -> dict:
    completed = subprocess.run(
        [sys.executable, str(WORKER)],
        input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
        capture_output=True, cwd=str(cwd), check=False)
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    return json.loads(completed.stdout.decode("utf-8"))


def _corpus(tmp_path: pathlib.Path) -> pathlib.Path:
    # The index store lives OUTSIDE the searched folder (the app keeps it in
    # <root>/tools/rag while the bound folder is elsewhere); otherwise the store
    # file would itself be indexed and change the signature on every run.
    root = tmp_path / "corpus"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "notlar.txt").write_text(
        "Elma ve armut meyvedir.\n"
        "Armut özellikle sulu olur.\n"
        "Kayısı da bir meyvedir.\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text(
        "def elma_isle():\n    return 'armutlu kod'\n", encoding="utf-8")
    # Skipped: dependency folder.
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / "node_modules" / "pkg" / "index.js").write_text(
        "karpuzgizli kelimesi sadece burada\n", encoding="utf-8")
    # Skipped: binary content in a text extension.
    (root / "bin").mkdir()
    (root / "bin" / "fake.txt").write_bytes(b"\x00\x01\x02kavun\x00")
    return root


def test_search_finds_chunk_with_path_and_line(tmp_path):
    root = _corpus(tmp_path)
    store = tmp_path / "rag" / "bound-abc.json"
    result = _call({"action": "search", "root": str(root), "query": "armut",
                    "top": 5, "store": str(store)}, tmp_path)
    assert result["hits"], result
    top = result["hits"][0]
    assert top["path"] == "docs/notlar.txt"
    assert top["line"] >= 1
    assert "armut" in top["text"].lower()
    assert store.is_file()


def test_search_skips_dependency_folders(tmp_path):
    root = _corpus(tmp_path)
    result = _call({"action": "search", "root": str(root), "query": "karpuzgizli"},
                   tmp_path)
    assert result["hits"] == []


def test_search_skips_binary_files(tmp_path):
    root = _corpus(tmp_path)
    result = _call({"action": "search", "root": str(root), "query": "kavun"}, tmp_path)
    assert result["hits"] == []


def test_index_is_reused_until_files_change(tmp_path):
    root = _corpus(tmp_path)
    store = tmp_path / "rag" / "bound-abc.json"
    first = _call({"action": "search", "root": str(root), "query": "elma",
                   "store": str(store)}, tmp_path)
    assert first["cached"] is False
    second = _call({"action": "search", "root": str(root), "query": "elma",
                    "store": str(store)}, tmp_path)
    assert second["cached"] is True
    # A new file invalidates the signature and rebuilds the index.
    (root / "docs" / "yeni.txt").write_text("elma taze bilgi\n", encoding="utf-8")
    third = _call({"action": "search", "root": str(root), "query": "elma",
                   "store": str(store)}, tmp_path)
    assert third["cached"] is False


def test_index_action_reports_counts(tmp_path):
    root = _corpus(tmp_path)
    result = _call({"action": "index", "root": str(root),
                    "store": str(tmp_path / "rag" / "index.json")}, tmp_path)
    assert result["files"] >= 2
    assert result["chunks"] >= 2


def test_missing_root_is_a_clean_error(tmp_path):
    result = _call({"action": "search", "root": str(tmp_path / "yok"),
                    "query": "x"}, tmp_path)
    assert "error" in result


def test_unknown_action_is_a_clean_error(tmp_path):
    root = _corpus(tmp_path)
    result = _call({"action": "wat", "root": str(root)}, tmp_path)
    assert "error" in result


# --- gating: offered only with the agent chip, hidden on audio turns ---------
def _registry(tmp_path) -> ToolRegistry:
    secrets = SecretStore()
    secrets._keyring = None
    secrets.backend = "file"
    settings = Settings(Paths(tmp_path), secrets=secrets)
    return ToolRegistry(Paths(tmp_path), settings,
                        WorkerRunner(Paths(tmp_path), settings))


def _names(registry, **kwargs):
    return [d["function"]["name"] for d in registry.definitions(**kwargs)]


def test_search_folder_requires_agent_chip(tmp_path):
    reg = _registry(tmp_path)
    assert "search_folder" in _names(reg, chips={"agent": True})
    assert "search_folder" not in _names(reg, chips={"agent": False})


def test_search_folder_hidden_on_audio_turn(tmp_path):
    reg = _registry(tmp_path)
    assert "search_folder" not in _names(reg, chips={"agent": True}, has_audio=True,
                                        message="bu sesi özetle")


def test_search_folder_shown_on_audio_turn_with_file_intent(tmp_path):
    reg = _registry(tmp_path)
    names = _names(reg, chips={"agent": True}, has_audio=True,
                   message="ses dosyasını klasörde ara")
    assert "search_folder" in names


def test_search_folder_spec_requires_query(tmp_path):
    reg = _registry(tmp_path)
    spec = reg.get("search_folder")
    assert spec is not None
    definition = spec.definition()["function"]
    assert definition["name"] == "search_folder"
    assert "query" in definition["parameters"]["required"]

"""Model manager: memory gate, MTP detection, argument bundles, process selection."""

from __future__ import annotations

import pytest

from mamidlabs.core import manage
from mamidlabs.core.manage import (MemoryError_, Proc, app_gpu_workers, comfy_processes,
                                   gguf_has_mtp, managed_servers, memory_budget, server_args)
from mamidlabs.core.paths import Paths
from mamidlabs.core.settings import SecretStore, Settings


def _settings(tmp_path, **values):
    secrets = SecretStore()
    secrets._keyring = None
    secrets.backend = "file"
    settings = Settings(Paths(tmp_path), secrets=secrets)
    settings.update(values)
    return settings


def _fake_gguf(path, content=b"GGUF\x00" + b"\x00" * 64):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_gguf_has_mtp_true(tmp_path):
    model = _fake_gguf(tmp_path / "m.gguf", b"GGUF" + b"blk.64.nextn.eh_proj.weight" + b"\x00" * 8)
    assert gguf_has_mtp(model) is True


def test_gguf_has_mtp_false(tmp_path):
    model = _fake_gguf(tmp_path / "m.gguf", b"GGUF" + b"\x00" * 64)
    assert gguf_has_mtp(model) is False


def test_memory_budget_raises_for_max(tmp_path):
    model = _fake_gguf(tmp_path / "m.gguf", b"\x00" * (10 * 1024 * 1024))
    with pytest.raises(MemoryError_):
        memory_budget(model, "max", None, free_mib=9)  # 10 MiB model + 750 overhead


def test_memory_budget_warns_between_thresholds(tmp_path):
    # LITE has a 1024 MiB tolerance: free may sit below the estimate (spill to
    # CPU) and still load, with a warning instead of a refusal.
    model = _fake_gguf(tmp_path / "m.gguf", b"\x00" * (10 * 1024 * 1024))
    warning = memory_budget(model, "lite", None, free_mib=200)
    assert warning and "CPU" in warning


def test_memory_budget_ok_when_enough(tmp_path):
    model = _fake_gguf(tmp_path / "m.gguf", b"\x00" * (10 * 1024 * 1024))
    assert memory_budget(model, "max", None, free_mib=2000) is None


def test_memory_budget_lite_tolerates_spill(tmp_path):
    model = _fake_gguf(tmp_path / "m.gguf", b"\x00" * (10 * 1024 * 1024))
    # lite: 10 MiB + 300 overhead; a small deficit warns rather than refusing.
    assert "CPU" in memory_budget(model, "lite", None, free_mib=100)


def test_memory_budget_lite_raises_when_far_below(tmp_path):
    model = _fake_gguf(tmp_path / "m.gguf", b"\x00" * (6000 * 1024 * 1024))
    with pytest.raises(MemoryError_):
        memory_budget(model, "lite", None, free_mib=1000)


def test_memory_budget_skipped_without_nvidia(tmp_path):
    model = _fake_gguf(tmp_path / "m.gguf", b"\x00" * (10 * 1024 * 1024))
    assert memory_budget(model, "max", None, free_mib=None) is None


def test_server_args_max_locked(tmp_path):
    settings = _settings(tmp_path, mtp=True)
    paths = Paths(tmp_path)
    model = _fake_gguf(tmp_path / "m.gguf", b"GGUF" + b"nextn" + b"\x00" * 32)
    args = server_args(paths, settings, "max", model, tmp_path / "mmproj.gguf",
                       "qwen3.8-27b-max")
    joined = " ".join(args)
    for fragment in ("--ctx-size 32768", "--predict 8192", "--gpu-layers 99",
                     "--reasoning-effort xhigh", "--no-mmproj-offload",
                     "--image-min-tokens 1024", "--spec-type draft-mtp", "--no-context-shift"):
        assert fragment in joined


def test_server_args_flash_effort_low(tmp_path):
    settings = _settings(tmp_path)
    args = server_args(Paths(tmp_path), settings, "flash",
                       _fake_gguf(tmp_path / "m.gguf", b"GGUF"), tmp_path / "p.gguf", "a")
    assert "--reasoning-effort low" in " ".join(args)


def test_server_args_lite_uses_settings_context(tmp_path):
    settings = _settings(tmp_path, liteContext=16384)
    model = _fake_gguf(tmp_path / "m.gguf", b"GGUF")
    args = server_args(Paths(tmp_path), settings, "lite", model, tmp_path / "p.gguf", "a")
    joined = " ".join(args)
    assert "--ctx-size 16384" in joined
    assert "--image-min-tokens 512" in joined
    assert "--batch-size 256" in joined


def test_server_args_mtp_disabled(tmp_path):
    settings = _settings(tmp_path, mtp=False)
    model = _fake_gguf(tmp_path / "m.gguf", b"GGUF" + b"nextn")
    args = server_args(Paths(tmp_path), settings, "max", model, tmp_path / "p.gguf", "a")
    assert "--spec-type" not in args


def test_server_args_custom_bundle(tmp_path):
    settings = _settings(tmp_path)
    args = server_args(Paths(tmp_path), settings, "max",
                       _fake_gguf(tmp_path / "m.gguf"), None, "custom-id", custom=True)
    joined = " ".join(args)
    assert "--ctx-size 8192" in joined
    assert "--predict 4096" in joined
    assert "--reasoning-effort" not in joined


def test_process_selection_by_root(tmp_path):
    root = tmp_path / "root"
    server = root / "llama.cpp" / "b10998" / "llama-server"
    procs = [
        Proc(1, 0, f"{server} --model {root}/models/x.gguf --port 8080 --alias a"),
        Proc(2, 0, "/usr/bin/other --port 8080"),
        Proc(3, 0, f"/usr/bin/python {root}/ComfyUI/main.py"),
        Proc(4, 0, f"{root}/venv/asr/bin/python {root}/mamidlabs/workers/whisper-tools.py --serve"),
    ]
    assert [p.pid for p in managed_servers(procs, server)] == [1]
    assert [p.pid for p in comfy_processes(procs, root)] == [3]
    assert [p.pid for p in app_gpu_workers(procs, root)] == [4]


def test_comfy_instance_roots_pairs(tmp_path):
    procs = [Proc(10, 1, "comfy launcher"), Proc(11, 10, "comfy child")]
    roots = manage._comfy_instance_roots(procs)
    assert [r.pid for r in roots] == [10]
    assert manage._comfy_under_root(procs, 11, 10) is True
    assert manage._comfy_under_root(procs, 10, 99) is False


def test_available_memory_env_override(monkeypatch):
    monkeypatch.setenv("MAMIDLABS_FREE_MEM_MIB", "12345")
    assert manage.available_memory_mib() == 12345


def test_macos_available_memory_parses_vm_stat(monkeypatch):
    import subprocess

    class _Result:
        def __init__(self, stdout):
            self.stdout = stdout

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["sysctl", "-n"] and cmd[2] == "hw.pagesize":
            return _Result("16384\n")
        if cmd[0] == "vm_stat":
            return _Result(
                "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
                "Pages free:                            1000.\n"
                "Pages active:                          9999.\n"
                "Pages inactive:                        2000.\n"
                "Pages speculative:                      500.\n"
                "Pages purgeable:                        250.\n"
            )
        return _Result("")

    monkeypatch.setattr(subprocess, "run", fake_run)
    # free + inactive + speculative + purgeable = 3750 pages * 16384 B
    assert manage._macos_available_mib() == (3750 * 16384) // (1024 * 1024)


def test_available_memory_prefers_macos_branch(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.delenv("MAMIDLABS_FREE_MEM_MIB", raising=False)
    monkeypatch.setattr(manage, "_macos_available_mib", lambda: 4242)
    assert manage.available_memory_mib() == 4242


def test_memory_error_message_mentions_unified_memory_on_macos(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    model = _fake_gguf(tmp_path / "m.gguf", b"\x00" * (10 * 1024 * 1024))
    with pytest.raises(MemoryError_) as excinfo:
        memory_budget(model, "max", None, free_mib=9)
    assert "unified memory" in str(excinfo.value)

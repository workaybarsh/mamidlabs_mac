"""Hardware measurement and profile recommendation (macOS).

macOS has **no separate VRAM**: llama.cpp runs on Metal and the model lives in
the Mac's *unified memory*, so the recommendation is driven by total RAM and the
CPU family rather than by ``nvidia-smi``:

* Apple Silicon (M series) with ≥ 32 GB unified memory → **PRO** (Qwen3.8 27B);
* Apple Silicon with ≥ 16 GB → **LITE** (Qwen3.5 9B);
* anything else (Intel Mac, or less memory) → **own** (use an API provider),
  because local inference would be painfully slow.

Same split as the Linux edition so the wizard code is shared: **pure parsers and
thresholds** (testable without the host) and **probes** that run ``sysctl`` /
``system_profiler`` and degrade gracefully when a tool is missing.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: Unified memory (MiB) at or above which the 27B profile fits.
PRO_RAM_MIB = 32 * 1024

#: Unified memory (MiB) at or above which the 9B profile fits.
LITE_RAM_MIB = 16 * 1024

#: Free disk (GiB) we recommend before downloading a profile's models.
PRO_DISK_GIB = 64.0
LITE_DISK_GIB = 48.0


@dataclass
class Gpu:
    """Kept for parity with the Linux edition; holds the chip name only."""

    name: str = ""
    vram_mib: int = 0
    driver: str = ""


@dataclass
class Report:
    """Everything the wizard shows on the hardware page."""

    gpus: list[Gpu] = field(default_factory=list)
    ram_mib: int = 0
    cpu: str = ""
    cores: int = 0
    distro: str = ""
    free_gib: float = 0.0
    apple_silicon: bool = False
    model: str = ""

    @property
    def gpu_name(self) -> str:
        if self.gpus:
            return self.gpus[0].name
        return self.cpu

    @property
    def vram_mib(self) -> int:
        """Kept for parity with the Linux report (macOS uses unified memory)."""
        return max((gpu.vram_mib for gpu in self.gpus), default=0)


def recommend(report: Report) -> str:
    """Pick a profile id: ``flash`` (PRO), ``lite`` or ``own``."""
    if not report.apple_silicon:
        return "own"
    if report.ram_mib >= PRO_RAM_MIB:
        return "flash"
    if report.ram_mib >= LITE_RAM_MIB:
        return "lite"
    return "own"


def warnings(report: Report) -> list[str]:
    """Translation keys for the notes under the recommendation."""
    notes: list[str] = []
    if not report.apple_silicon:
        notes.append("wizard.report.no_apple_silicon")
    elif report.ram_mib < PRO_RAM_MIB:
        notes.append("wizard.report.low_ram")
    profile = recommend(report)
    if profile != "own":
        need = PRO_DISK_GIB if profile == "flash" else LITE_DISK_GIB
        if report.free_gib and report.free_gib < need:
            notes.append("wizard.report.low_disk")
    return notes


# --- pure parsers ------------------------------------------------------------


def mib_from_bytes(value: str | int) -> int:
    """``sysctl -n hw.memsize`` (bytes) → MiB."""
    try:
        return int(str(value).strip()) // (1024 * 1024)
    except (TypeError, ValueError):
        return 0


def is_apple_silicon(machine: str, arm64_flag: str = "") -> bool:
    """True on Apple Silicon (``arm64`` machine or ``hw.optional.arm64 = 1``)."""
    return machine == "arm64" or str(arm64_flag).strip() == "1"


# --- probes ------------------------------------------------------------------


def _sysctl(name: str) -> str:
    try:
        done = subprocess.run(["sysctl", "-n", name], capture_output=True, text=True,
                              timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (done.stdout or "").strip()


def _sw_vers() -> str:
    try:
        done = subprocess.run(["sw_vers", "-productVersion"], capture_output=True,
                              text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (done.stdout or "").strip()


def measure(root: Path | str | None = None) -> Report:
    """Measure the host; never raises, degrades to an empty report."""
    report = Report()
    report.ram_mib = mib_from_bytes(_sysctl("hw.memsize"))
    report.cpu = _sysctl("machdep.cpu.brand_string") or _sysctl("hw.model")
    report.model = _sysctl("hw.model")
    report.apple_silicon = is_apple_silicon(platform.machine(), _sysctl("hw.optional.arm64"))
    try:
        report.cores = int(_sysctl("hw.ncpu") or 0)
    except ValueError:
        report.cores = 0
    report.distro = f"macOS {_sw_vers()}".strip() if _sw_vers() else "macOS"
    if report.cpu:
        report.gpus = [Gpu(name=report.cpu)]
    try:
        usage = shutil.disk_usage(str(root or Path.home()))
        report.free_gib = usage.free / (1024 ** 3)
    except OSError:
        report.free_gib = 0.0
    return report


def has_display() -> bool:
    """macOS always has a desktop session for a GUI app."""
    return sys.platform == "darwin"

"""Runtime profile: turns the SELECTED language-model profile ('lite' / 'pro') into an audio-pipeline tier.

One codebase, two profiles. The only difference: Whisper's compute_type and whether the models are
loaded at the same time (in parallel) or one after another.

- pro (MAX/FLASH): float16, models in memory at the same time.
- lite: int8_float16, models one after another; long recordings are split.

The UI passes the SELECTED profile to the worker (`select_profile_for`), so LITE and PRO behave
differently. On the CLI, when no profile name is given, the tier is determined by the machine's
total VRAM (`select_profile`). The device/swap decision is still made from the REAL free VRAM and
system RAM (`choose_plan`).
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, replace

# macOS has no CUDA and CTranslate2 has no Metal backend, so transcription always
# runs on the CPU here; the device choosers below short-circuit to 'cpu'.
IS_MACOS = sys.platform == 'darwin'

# Tier names are now the same as the SELECTED profile: 'lite' and 'pro'. The old hardware names
# ('pc1'/'pc2') and the UI profile names ('max'/'flash') are synonymous aliases, so old callers
# (CLI `--profile pc2`) keep working.
PC1 = 'lite'
PC2 = 'pro'
VRAM_THRESHOLD_MIB = 14000
# UI profile name -> tier. The profile NAME decides the tier; VRAM is only a fallback when the
# name is missing.
TIER_ALIASES = {
    'lite': PC1, 'pc1': PC1,
    'pro': PC2, 'max': PC2, 'flash': PC2, 'pc2': PC2,
}

# --- Automatic device selection (CPU / GPU) -----------------------------------
# When transcribing on the GPU the local language model is evicted from VRAM and then loaded back
# (swap). That swap has a fixed cost; transcribing on the CPU is slower than the GPU but has NO
# swap cost. For short recordings the swap cost exceeds the transcription gain:
#
#     GPU_transcription + swap_cost > CPU_transcription  =>  CPU is chosen.
#
# The threshold is a DURATION, kept in the constant below; if the measurement changes only this
# line is updated (or it is overridden per profile with `Profile.cpu_max_seconds`).
#
# R&D measurement (RTX 5060 Ti 16 GB, Whisper large-v3-tr):
#   CPU(d)  = 5.0  + 0.908*d   (model load 5 s; transcription ~real time)
#   GPU(d)  = 14.0 + 3.3 + 0.079*d   (swap = evict 3 + reload 11; model load 3.3)
#   Intersection: d = (14 + 3.3 - 5.0) / (0.908 - 0.079) ~= 15 s
# 20 s was chosen for the safety margin + the first-job CUDA warm-up (pro; old name PC2). LITE's
# swap was measured shorter (evict 3 + reload 6 = ~9 s) and the 9B model loads in ~6 s on LITE, so
# the threshold is kept a little lower (Profile.cpu_max_seconds = 15; see PROFILES). On both
# profiles the "short -> CPU, long -> GPU + swap" logic holds.
DEFAULT_CPU_MAX_SECONDS = 20.0

# LITE (8 GB card) CPU/GPU threshold. LITE's swap was measured shorter (~9-14 s); the cut-off is
# d = (swap - 1.7) / 0.831 ~= 9-15 s. 15 s was chosen with a safety margin. When the measurement
# agent that gives the numeric verdict has not returned, the existing R&D value is used; the safe
# range is 15-20 s.
LITE_CPU_MAX_SECONDS = 15.0

# Single engine: the Turkish fine-tuned CTranslate2 (float16) build of Whisper large-v3.
DEFAULT_WHISPER_MODEL = 'oguzhangokboru/whisper-large-v3-tr'
# AudioSet-based sound event model (AST). Disabled with 'none'.
DEFAULT_EVENTS_MODEL = 'MIT/ast-finetuned-audioset-10-10-0.4593'

# --- Audio pipeline memory requirements (MiB) --------------------------------
# The device/swap decision is NOT based on the PROFILE NAME but on the REAL free VRAM and system RAM
# measured when the audio job starts (see choose_plan). The LITE profile is used on both 8 GB (the
# target machine) and 16 GB cards, so the profile name alone is not enough.
#
# `audio_vram_mib`: the worst-case headroom needed for Whisper large-v3 + AST + the torch/CUDA
# context. Measured: int8_float16 large-v3 ~1.5-2.5 GB, AST (fp32) ~0.4 GB, torch/CUDA context
# ~0.3-0.5 GB; on pro (old name PC2) Whisper in float16 grows to ~2.9 GB.
DEFAULT_AUDIO_VRAM_MIB = 4096
# `audio_ram_mib`: on the CPU path (no swap) the worst-case headroom the audio pipeline keeps in
# system RAM: Whisper int8 (~2 GB) + AST (fp32 ~0.4 GB) + torch/Python (~0.8 GB) + chunk/decode
# buffers (30 min float32 ~0.15 GB; chunked transcription).
DEFAULT_AUDIO_RAM_MIB = 5120

# LITE (8 GB card) CPU co-resident audio pipeline RAM threshold. TWO MEASUREMENTS CONFLICTED; the
# more CONCLUSIVE one (measurement-2, which actually ran LM + ASR on the CPU TOGETHER) concluded:
# co-resident **DOES NOT FIT**. Physical RAM 15.25 GB; with the LM loaded the requirement is ~16.1 GB
# (zero/negative margin; peak ~15,127/15,611 MB, only ~489 MB free). Even without an OOM, the LM's
# ~6.1 GB model pages are evicted from the reclaimable cache and re-read from disk on the NEXT chat
# turn (slowdown). So LITE uses the SAME safe gate as PRO: threshold **5,120 MiB** (although the
# real ASR requirement is ~3.8 GB, ~16 GB is needed TOGETHER with the language model, which is why
# this is the safe gate). With the LM loaded (on this machine) choose_plan does not choose the CPU
# branch -> GPU + swap; on a machine with plenty of RAM a short recording can still be CPU
# co-resident.
LITE_AUDIO_RAM_MIB = DEFAULT_AUDIO_RAM_MIB


@dataclass(frozen=True)
class Profile:
    name: str
    compute_type: str      # faster-whisper compute_type ('float16' | 'int8_float16')
    load_mode: str         # 'parallel' | 'sequential'
    chunk_minutes: int     # split long recordings; 0 = no split
    whisper_model: str
    events_model: str      # 'ast' | 'none'
    language: str
    events: bool
    diarize: bool
    auto_device: bool = True          # pick the device automatically from the recording duration
    cpu_max_seconds: float | None = None  # CPU for recordings shorter than this (None -> DEFAULT_CPU_MAX_SECONDS)
    audio_vram_mib: int = DEFAULT_AUDIO_VRAM_MIB  # free VRAM the audio pipeline wants alongside the language model
    audio_ram_mib: int = DEFAULT_AUDIO_RAM_MIB    # system RAM the audio pipeline wants on the CPU path


PROFILES = {
    PC2: Profile(
        name=PC2, compute_type='float16', load_mode='parallel', chunk_minutes=0,
        whisper_model=DEFAULT_WHISPER_MODEL, events_model=DEFAULT_EVENTS_MODEL,
        language='tr', events=True, diarize=True,
    ),
    PC1: Profile(
        name=PC1, compute_type='int8_float16', load_mode='sequential', chunk_minutes=30,
        whisper_model=DEFAULT_WHISPER_MODEL, events_model=DEFAULT_EVENTS_MODEL,
        language='tr', events=True, diarize=True,
        # LITE ASR policy: CPU co-resident is chosen ONLY when the recording is SHORTER than
        # `cpu_max_seconds` AND system RAM suffices (the language model stays in VRAM, the audio
        # model runs on the CPU/in system RAM; NO swap). For a long recording or insufficient RAM,
        # GPU + mandatory swap (although the swap costs ~9-14 s, the GPU transcription is so much
        # faster that the total is shorter; see choose_plan). Threshold LITE_CPU_MAX_SECONDS (15 s);
        # the system RAM required for the CPU branch is LITE_AUDIO_RAM_MIB (5,120 MiB; measurement-2:
        # co-resident TOGETHER with the LM DOES NOT FIT -> in practice GPU + swap on this machine).
        cpu_max_seconds=LITE_CPU_MAX_SECONDS,
        audio_ram_mib=LITE_AUDIO_RAM_MIB,
    ),
}


def _macos_total_mib() -> int:
    """Total unified memory on macOS (MiB). 0 when it cannot be read."""
    try:
        out = subprocess.run(['sysctl', '-n', 'hw.memsize'], capture_output=True,
                             text=True, timeout=10).stdout.strip()
        return int(out) // (1024 * 1024) if out.isdigit() else 0
    except Exception:
        return 0


def _macos_available_mib() -> int:
    """Reclaimable unified memory on macOS (MiB): free+inactive+speculative+purgeable."""
    try:
        pagesize = int(subprocess.run(['sysctl', '-n', 'hw.pagesize'], capture_output=True,
                                      text=True, timeout=10).stdout.strip() or 4096)
    except Exception:
        pagesize = 4096
    try:
        out = subprocess.run(['vm_stat'], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return 0
    wanted = ('Pages free', 'Pages inactive', 'Pages speculative', 'Pages purgeable')
    pages = 0
    for line in out.splitlines():
        stripped = line.strip()
        for key in wanted:
            if stripped.startswith(key + ':'):
                digits = ''.join(ch for ch in stripped.split(':', 1)[-1] if ch.isdigit())
                if digits:
                    pages += int(digits)
    return (pages * pagesize) // (1024 * 1024)


def total_vram_mib() -> int:
    """Total VRAM of the largest card (MiB). 0 when there is none (-> lite (old name PC1) profile).

    macOS has no separate VRAM; the whole unified memory is the hardware budget, so
    `hw.memsize` is returned (it provides a reasonable threshold for profile selection).
    """
    if IS_MACOS:
        return _macos_total_mib()
    try:
        out = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.total', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except Exception:
        return 0
    values = [int(x) for x in out.replace(',', ' ').split() if x.strip().isdigit()]
    return max(values) if values else 0


def free_vram_mib() -> int:
    """FREE VRAM of the largest card (MiB). 0 when there is none.

    On macOS the reclaimable pages of unified memory are returned.
    """
    if IS_MACOS:
        return _macos_available_mib()
    try:
        out = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.free', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except Exception:
        return 0
    values = [int(x) for x in out.replace(',', ' ').split() if x.strip().isdigit()]
    return max(values) if values else 0


def available_ram_mib() -> int:
    """Available (free) system RAM in MiB. 0 when it cannot be read."""
    if IS_MACOS:
        return _macos_available_mib()
    if os.name == 'nt':
        try:
            import ctypes

            class _MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ('dwLength', ctypes.c_ulong),
                    ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong),
                    ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong),
                    ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong),
                    ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
                ]

            status = _MemoryStatusEx()
            status.dwLength = ctypes.sizeof(_MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys // (1024 * 1024))
        except Exception:
            return 0
        return 0
    try:
        with open('/proc/meminfo', encoding='utf-8') as fh:
            for line in fh:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 0


def select_profile(total_mib: int | None = None, **overrides) -> Profile:
    """Select a profile by total VRAM (only when no profile name is given / CLI fallback)."""
    total = total_vram_mib() if total_mib is None else int(total_mib)
    profile = PROFILES[PC2] if total >= VRAM_THRESHOLD_MIB else PROFILES[PC1]
    clean = {k: v for k, v in overrides.items() if v is not None and hasattr(profile, k)}
    return replace(profile, **clean) if clean else profile


def resolve_tier(name: str | None) -> str | None:
    """Turn a profile name into a tier key ('lite'/'pro'); None when unrecognised."""
    return TIER_ALIASES.get((name or '').strip().lower())


def select_profile_for(name: str | None, **overrides) -> Profile:
    """Select the tier for the application's SELECTED profile name; the name takes priority.

    'lite' -> LITE, 'pro'/'max'/'flash' -> PRO. When the name is unrecognised (or empty) it falls
    back to `select_profile`, where the machine's total VRAM decides the tier.
    """
    tier = resolve_tier(name)
    if tier is None:
        return select_profile(**overrides)
    profile = PROFILES[tier]
    clean = {k: v for k, v in overrides.items() if v is not None and hasattr(profile, k)}
    return replace(profile, **clean) if clean else profile


def choose_device(duration_seconds: float | None, profile: Profile, need_swap: bool,
                  cpu_max_seconds: float | None = None) -> str:
    """Choose 'cuda' or 'cpu' from the recording duration.

    Rule (see DEFAULT_CPU_MAX_SECONDS):
      - need_swap=False: no VRAM swap cost (e.g. an API provider or LITE; the language model fits
        together with the audio pipeline) -> always 'cuda'.
      - need_swap=True: a GPU transcription evicts the language model and loads it back (swap). If
        the recording is SHORTER than `threshold` seconds the swap cost exceeds the transcription
        gain, so 'cpu'; otherwise 'cuda'.

    Threshold: `cpu_max_seconds` when given, else `profile.cpu_max_seconds`, else
    `DEFAULT_CPU_MAX_SECONDS`. When the duration cannot be read (None) the safe default is 'cuda'.

    NOTE: the application path (UI/worker) makes the device/swap decision with `choose_plan`; this
    function is kept only for the CLI's `--device auto` flow.
    """
    if IS_MACOS:
        return 'cpu'
    if not need_swap:
        return 'cuda'
    threshold = cpu_max_seconds
    if threshold is None:
        threshold = profile.cpu_max_seconds
    if threshold is None:
        threshold = DEFAULT_CPU_MAX_SECONDS
    if duration_seconds is not None and duration_seconds <= threshold:
        return 'cpu'
    return 'cuda'


def choose_plan(profile: Profile, duration_seconds: float | None = None,
                vram_free_mib: int | None = None, ram_free_mib: int | None = None,
                local_model_loaded: bool = True,
                cpu_max_seconds: float | None = None) -> tuple[str, bool]:
    """Return the (device, need_swap) plan for the audio pipeline, in order of PREFERENCE.

    The tier (`profile`) comes from the SELECTED profile name (lite/pro); the device/swap decision
    is made from the tier's memory thresholds + the REAL free VRAM + system RAM and the recording
    DURATION:

      1) If Whisper + AST fit into free VRAM TOGETHER with the local language model
         (`audio_vram_mib`) -> ('cuda', False): GPU transcription, NO swap (fastest, free).
      2) If they do not fit and CPU co-resident conditions are met -> ('cpu', False): the language
         model STAYS in VRAM, the audio model runs on the CPU/in system RAM (NO swap; it is slow).
         Condition: the recording is SHORTER than `threshold` seconds **AND** the audio pipeline
         fits into system RAM (`audio_ram_mib`; LITE and PRO 5,120 MiB).
         On a short recording the swap cost exceeds the transcription gain. Threshold:
         `cpu_max_seconds` / `profile.cpu_max_seconds` / `DEFAULT_CPU_MAX_SECONDS` (LITE 15 s, PRO 20 s).
      3) Otherwise (a LONG recording or not enough RAM) -> ('cuda', True): GPU transcription. The
         language model is MANDATORILY evicted/reloaded (swap); on a long recording the GPU gain
         exceeds the swap cost, and if RAM is short it is unavoidable anyway.

    When the duration is unknown (duration_seconds=None) a swap is NOT FORCED; only the memory rule
    applies (CPU if RAM suffices, mandatory swap otherwise). This avoids an unnecessary language
    model evict/reload for a single recording.

    When the local language model is not loaded (API provider) the GPU is already free ->
    ('cuda', False). The CPU path is never MANDATORY: if the chosen device fails the worker layer
    falls back to the CPU; if there is no GPU at all (no CUDA/nvidia-smi) the CPU remains the last
    resort. When `vram_free_mib`/`ram_free_mib` are not given they are read from the machine (0 when
    unmeasurable -> the safe side: treated as not fitting).
    """
    if IS_MACOS:
        # No CUDA: always CPU, no language-model swap (there is nothing to free).
        return 'cpu', False
    if not local_model_loaded:
        return 'cuda', False
    if vram_free_mib is None:
        vram_free_mib = free_vram_mib()
    if ram_free_mib is None:
        ram_free_mib = available_ram_mib()
    if vram_free_mib >= profile.audio_vram_mib:
        return 'cuda', False
    ram_ok = ram_free_mib >= profile.audio_ram_mib
    threshold = cpu_max_seconds
    if threshold is None:
        threshold = profile.cpu_max_seconds
    if threshold is None:
        threshold = DEFAULT_CPU_MAX_SECONDS
    # CPU co-resident ONLY when the recording is SHORTER than the threshold AND RAM suffices. When
    # the duration is unknown a swap is not forced (memory rule): no unnecessary language-model swap
    # for a single recording.
    if ram_ok and (duration_seconds is None or duration_seconds <= threshold):
        return 'cpu', False
    return 'cuda', True

"""Profile catalog and model registry (port of ``agent/profiles.json`` +
``agent/model-registry.ps1``).

A *profile* is a (language model + projector + media assets) bundle tuned for a
class of hardware:

* ``max``   — Qwen3.8 27B, deep reasoning (32 GB unified memory)
* ``flash`` — the same 27B files, shorter reasoning effort
* ``lite``  — Huihui-Qwen3.5 9B, for 16 GB unified memory

``max`` and ``flash`` share the same files, so the catalog presents them as one
"Qwen3.8 27B" entry to the user (see :func:`catalog_for_display`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .paths import Paths

#: Server ``--alias`` per profile. Must stay in sync with ``manage.py``.
PROFILE_ALIASES: dict[str, str] = {
    "max": "qwen3.8-27b-max",
    "flash": "qwen3.8-27b-flash",
    "lite": "qwen3.5-9b-lite",
}

PROFILE_IDS = ("max", "flash", "lite")


@dataclass(frozen=True)
class CatalogFile:
    label: str
    target: str  # path relative to the install root
    repo: str
    revision: str
    filename: str
    bytes: int
    #: Optional pinned SHA256 for offline verification (see ``hf-hub.py``); when
    #: empty the downloader asks the Hub for the LFS digest instead.
    sha256: str = ""
    #: Optional MTP header source (see ``mtp_inject.py``); only the LITE GGUF
    #: loses its ``nextn`` block during conversion and needs it re-injected.
    mtp_repo: str = ""


@dataclass(frozen=True)
class Profile:
    id: str
    label: str
    hardware: str
    summary: str
    files: list[CatalogFile] = field(default_factory=list)

    @property
    def alias(self) -> str:
        return PROFILE_ALIASES[self.id]

    @property
    def total_bytes(self) -> int:
        return sum(item.bytes for item in self.files)

    def chat_files(self) -> list[CatalogFile]:
        """The language model + projector (everything under ``models/``)."""
        return [item for item in self.files if item.target.startswith("models/")]

    def media_files(self) -> list[CatalogFile]:
        """ComfyUI assets (image/video models)."""
        return [item for item in self.files if item.target.startswith("ComfyUI/")]

    def chat_files_present(self, paths: Paths) -> bool:
        """True when the language model is on disk (projector is optional for lite)."""
        for item in self.chat_files():
            if "mmproj" in item.filename and self.id == "lite":
                continue
            if not (paths.root / item.target).exists():
                return False
        return True


def _f(label: str, target: str, repo: str, revision: str, filename: str, size: int,
       mtp_repo: str = "", sha256: str = "") -> CatalogFile:
    return CatalogFile(label, target, repo, revision, filename, size, sha256, mtp_repo)


# --- language models ---------------------------------------------------------
_27B_GGUF = _f(
    "Language model (Qwen3.8 27B IQ4_XS)",
    "models/Qwen3.8-27B-Abliterated-IQ4_XS/Qwen3.8-27B-Abliterated-IQ4_XS.gguf",
    "windowsxp811203/Qwen3.8-27B-Abliterated-GGUF",
    "efb07baa690a1bc7beb53ee067b4b57c7025b5e7",
    "Qwen3.8-27B-Abliterated-IQ4_XS.gguf",
    15309039488,
)
_27B_MMPROJ = _f(
    "Vision projector (mmproj F16)",
    "models/Qwen3.8-27B-Abliterated-IQ4_XS/mmproj-Qwen3.8-27B-Abliterated-F16.gguf",
    "windowsxp811203/Qwen3.8-27B-Abliterated-GGUF",
    "efb07baa690a1bc7beb53ee067b4b57c7025b5e7",
    "mmproj-Qwen3.8-27B-Abliterated-F16.gguf",
    927607328,
)
_LITE_GGUF = _f(
    "Language model (Huihui-Qwen3.5 9B Q5_K_M)",
    "models/Huihui-Qwen3.5-9B-abliterated-i1-GGUF/Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf",
    "mradermacher/Huihui-Qwen3.5-9B-abliterated-i1-GGUF",
    "4cc15cd6f643e668e18902550f80e2274a212473",
    "Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf",
    6522005152,
    mtp_repo="huihui-ai/Huihui-Qwen3.5-9B-abliterated",
)
_LITE_MMPROJ = _f(
    "Vision projector (mmproj Q8_0)",
    "models/Huihui-Qwen3.5-9B-abliterated-i1-GGUF/Huihui-Qwen3.5-9B-abliterated.mmproj-Q8_0.gguf",
    "mradermacher/Huihui-Qwen3.5-9B-abliterated-GGUF",
    "9f646d7eda193ddf2348134f3bff3d49eed7a2c6",
    "Huihui-Qwen3.5-9B-abliterated.mmproj-Q8_0.gguf",
    624229760,
)

# --- shared media assets -----------------------------------------------------
_KREA2_FP8 = _f(
    "Krea-2 Turbo (image)",
    "ComfyUI/models/diffusion_models/krea2_turbo_fp8_scaled.safetensors",
    "Comfy-Org/Krea-2",
    "e5ea8b4dd7f38f348b138eb0fe29f92c0e367e96",
    "diffusion_models/krea2_turbo_fp8_scaled.safetensors",
    13141730784,
)
_KREA2_GGUF = _f(
    "Krea-2 Turbo GGUF Q4_K_M (image, requires the ComfyUI-GGUF custom node)",
    "ComfyUI/models/unet/krea2_turbo-Q4_K_M.gguf",
    "vantagewithai/Krea-2-Turbo-GGUF",
    "390847e2835c16bdf82303731e3d35b874760d89",
    "krea2_turbo-Q4_K_M.gguf",
    7486289184,
)
_QWEN3VL = _f(
    "Qwen3-VL 4B text encoder",
    "ComfyUI/models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors",
    "Comfy-Org/Krea-2",
    "e5ea8b4dd7f38f348b138eb0fe29f92c0e367e96",
    "text_encoders/qwen3vl_4b_fp8_scaled.safetensors",
    5242467968,
)
_QWEN_VAE = _f(
    "Qwen Image VAE",
    "ComfyUI/models/vae/qwen_image_vae.safetensors",
    "Comfy-Org/Krea-2",
    "e5ea8b4dd7f38f348b138eb0fe29f92c0e367e96",
    "vae/qwen_image_vae.safetensors",
    253806246,
)
_KREA2_STYLE = _f(
    "Krea-2 style reference LoRA (optional)",
    "ComfyUI/models/loras/krea2_style_reference.safetensors",
    "Comfy-Org/Krea-2",
    "e5ea8b4dd7f38f348b138eb0fe29f92c0e367e96",
    "loras/krea2_style_reference.safetensors",
    457111760,
)
_KREA2_REALISM = _f(
    "Krea-2 realism LoRA (only used when a realistic image is requested)",
    "ComfyUI/models/loras/krea2_realism_lora.safetensors",
    "gokaygokay/Krea-2-Realism-LoRA",
    "32f0436ac10e985134364e7555898c9f121a46ce",
    "krea2_realism_lora.safetensors",
    469288512,
)
_KREA2_IDENTITY = _f(
    "Krea 2 Identity Edit v1.2 LoRA (photo editing, identity preserved)",
    "ComfyUI/models/loras/krea2_identity_edit_v1_2.safetensors",
    "conradlocke/krea2-identity-edit",
    "89e9e7a09ee2e5c9331e952063d79b1b8a703280",
    "krea2_identity_edit_v1_2.safetensors",
    1828256432,
)
_WAN_MODEL = _f(
    "Wan 2.2 TI2V 5B (video)",
    "ComfyUI/models/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors",
    "Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
    "c4f60d30c55a624e35427060fdd217579a6c1d77",
    "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors",
    9999658848,
)
_UMT5 = _f(
    "UMT5 XXL text encoder",
    "ComfyUI/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    "Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
    "c4f60d30c55a624e35427060fdd217579a6c1d77",
    "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    6735906897,
)
_WAN_VAE = _f(
    "Wan 2.2 VAE",
    "ComfyUI/models/vae/wan2.2_vae.safetensors",
    "Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
    "c4f60d30c55a624e35427060fdd217579a6c1d77",
    "split_files/vae/wan2.2_vae.safetensors",
    1409400960,
)

_PRO_MEDIA = [_KREA2_FP8, _QWEN3VL, _QWEN_VAE, _KREA2_STYLE, _KREA2_REALISM,
              _KREA2_IDENTITY, _WAN_MODEL, _UMT5, _WAN_VAE]
#: LITE has no identity-edit LoRA (5 GB text encoder + 7.5 GB diffusion model
#: cannot coexist on 8 GB) and uses the GGUF diffusion model.
_LITE_MEDIA = [_KREA2_GGUF, _QWEN3VL, _QWEN_VAE, _KREA2_STYLE, _KREA2_REALISM,
               _WAN_MODEL, _UMT5, _WAN_VAE]

CATALOG: dict[str, Profile] = {
    "max": Profile(
        "max", "Qwen3.8 MAX", "32 GB unified memory",
        "Deep reasoning, 32K context, image understanding on. Fast on Metal with MTP enabled; "
        "the memory budget is measured from unified memory.",
        [_27B_GGUF, _27B_MMPROJ, *_PRO_MEDIA],
    ),
    "flash": Profile(
        "flash", "Qwen3.8 27B", "32 GB unified memory",
        "The same files as MAX, with a shorter reasoning effort. Fast on Metal with MTP enabled.",
        [_27B_GGUF, _27B_MMPROJ, *_PRO_MEDIA],
    ),
    "lite": Profile(
        "lite", "Qwen3.5 9B LITE", "16 GB unified memory",
        "A 9B language model for Macs with 16 GB of unified memory (32K context, image "
        "understanding with mmproj Q8_0), the quantized (Q4_K_M) GGUF build of Krea-2 Turbo for "
        "images, and a 480p / 3 s limit for video. ComfyUI runs in low-memory MPS mode; "
        "generation is noticeably slower than on the 27B profile.",
        [_LITE_GGUF, _LITE_MMPROJ, *_LITE_MEDIA],
    ),
}


def get_profile(profile_id: str) -> Profile:
    try:
        return CATALOG[profile_id]
    except KeyError:
        raise KeyError(f"Unknown profile: {profile_id}") from None


def profile_from_alias(alias: str) -> str:
    """Resolve a server-reported alias back to a profile id."""
    for name, value in PROFILE_ALIASES.items():
        if alias == value:
            return name
    if alias.endswith("-lite"):
        return "lite"
    if alias.endswith("-flash"):
        return "flash"
    return "max"


def catalog_for_display() -> list[Profile]:
    """Collapse ``max``/``flash`` (identical files) into a single entry."""
    return [CATALOG["max"], CATALOG["lite"]]


def unique_targets(profile_id: str) -> list[str]:
    """Targets used *only* by this profile (safe to delete with the profile)."""
    mine = {item.target for item in get_profile(profile_id).files}
    others: set[str] = set()
    for other in PROFILE_IDS:
        if other != profile_id:
            others |= {item.target for item in get_profile(other).files}
    return sorted(mine - others)


def missing_files(profile_id: str, paths: Paths) -> list[CatalogFile]:
    return [item for item in get_profile(profile_id).files
            if not (paths.root / item.target).exists()]


def model_path(paths: Paths, profile_id: str) -> Path:
    """Path of the language model GGUF for a profile."""
    for item in get_profile(profile_id).chat_files():
        if "mmproj" not in item.filename:
            return paths.root / item.target
    raise KeyError(f"no language model is defined for {profile_id}.")


def projector_path(paths: Paths, profile_id: str) -> Path | None:
    """Path of the vision projector (``None`` when the profile has none)."""
    for item in get_profile(profile_id).chat_files():
        if "mmproj" in item.filename:
            return paths.root / item.target
    return None

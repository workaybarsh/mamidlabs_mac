"""Profile catalog and registry."""

from __future__ import annotations

from mamidlabs.core.paths import Paths
from mamidlabs.core.profiles import (CATALOG, PROFILE_ALIASES, catalog_for_display,
                                     get_profile, missing_files, model_path,
                                     profile_from_alias, projector_path, unique_targets)


def test_aliases_locked():
    assert PROFILE_ALIASES == {"max": "qwen3.8-27b-max",
                               "flash": "qwen3.8-27b-flash",
                               "lite": "qwen3.5-9b-lite"}


def test_profile_from_alias_roundtrip():
    for name, alias in PROFILE_ALIASES.items():
        assert profile_from_alias(alias) == name
    assert profile_from_alias("something-lite") == "lite"
    assert profile_from_alias("something-flash") == "flash"
    assert profile_from_alias("unknown") == "max"


def test_max_and_flash_share_files():
    assert {f.target for f in CATALOG["max"].files} == {f.target for f in CATALOG["flash"].files}


def test_display_collapses_max_flash():
    ids = [p.id for p in catalog_for_display()]
    assert ids == ["max", "lite"]


def test_lite_has_no_identity_edit_lora():
    targets = {f.target for f in CATALOG["lite"].files}
    assert not any("identity_edit" in t for t in targets)
    assert any("identity_edit" in f.target for f in CATALOG["max"].files)


def test_unique_targets_only_profile_specific():
    lite_only = unique_targets("lite")
    # The shared Qwen3-VL encoder must never be deleted with the lite profile.
    assert not any("qwen3vl_4b" in t for t in lite_only)
    assert any("Huihui-Qwen3.5-9B" in t for t in lite_only)


def test_model_and_projector_paths(tmp_path):
    paths = Paths(tmp_path)
    model = model_path(paths, "max")
    assert model.name.endswith(".gguf") and "mmproj" not in model.name
    assert projector_path(paths, "max").name.startswith("mmproj")
    assert projector_path(paths, "lite").name.endswith("mmproj-Q8_0.gguf")


def test_missing_files(tmp_path):
    paths = Paths(tmp_path)
    missing = missing_files("lite", paths)
    assert len(missing) == len(get_profile("lite").files)

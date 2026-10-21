"""Hardware measurement and profile recommendation (macOS: unified memory)."""

from __future__ import annotations

import pytest

from mamidlabs.core import hwinfo


def test_mib_from_bytes():
    assert hwinfo.mib_from_bytes(17179869184) == 16384
    assert hwinfo.mib_from_bytes("68719476736") == 65536
    assert hwinfo.mib_from_bytes("") == 0
    assert hwinfo.mib_from_bytes("nonsense") == 0


@pytest.mark.parametrize("machine,flag,expected", [
    ("arm64", "", True),
    ("x86_64", "1", True),
    ("x86_64", "0", False),
    ("x86_64", "", False),
])
def test_is_apple_silicon(machine, flag, expected):
    assert hwinfo.is_apple_silicon(machine, flag) is expected


@pytest.mark.parametrize("ram_mib,silicon,expected", [
    (64 * 1024, True, "flash"),
    (32 * 1024, True, "flash"),
    (24 * 1024, True, "lite"),
    (16 * 1024, True, "lite"),
    (8 * 1024, True, "own"),
    (64 * 1024, False, "own"),   # Intel Mac: local inference would crawl
])
def test_recommend_uses_unified_memory_and_silicon(ram_mib, silicon, expected):
    report = hwinfo.Report(ram_mib=ram_mib, apple_silicon=silicon)
    assert hwinfo.recommend(report) == expected


def test_warnings_on_an_intel_mac_point_to_api_providers():
    report = hwinfo.Report(ram_mib=64 * 1024, apple_silicon=False)
    assert "wizard.report.no_apple_silicon" in hwinfo.warnings(report)


def test_warnings_flag_low_memory_on_apple_silicon():
    report = hwinfo.Report(ram_mib=16 * 1024, apple_silicon=True, free_gib=200.0)
    assert "wizard.report.low_ram" in hwinfo.warnings(report)


def test_warnings_flag_a_tight_disk_for_a_local_profile():
    report = hwinfo.Report(ram_mib=32 * 1024, apple_silicon=True, free_gib=10.0)
    assert "wizard.report.low_disk" in hwinfo.warnings(report)


def test_warning_keys_exist_in_the_catalogs():
    import json

    from mamidlabs.core import i18n

    for code in i18n.SUPPORTED:
        catalog = json.loads((i18n.LOCALES_DIR / f"{code}.json").read_text(encoding="utf-8"))
        for report in (hwinfo.Report(), hwinfo.Report(ram_mib=16 * 1024, apple_silicon=True,
                                                      free_gib=1.0)):
            for key in hwinfo.warnings(report):
                assert key in catalog, f"{code}.json is missing: {key}"


def test_measure_never_raises(tmp_path):
    report = hwinfo.measure(tmp_path)
    assert isinstance(report, hwinfo.Report)


def test_has_display_is_true_on_macos_only(monkeypatch):
    monkeypatch.setattr(hwinfo.sys, "platform", "darwin")
    assert hwinfo.has_display() is True
    monkeypatch.setattr(hwinfo.sys, "platform", "linux")
    assert hwinfo.has_display() is False

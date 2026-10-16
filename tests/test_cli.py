"""Headless CLI (``python -m mamidlabs ...``)."""

from __future__ import annotations

import json

from mamidlabs.__main__ import main


def test_version(capsys):
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    assert "MamidLabs" in capsys.readouterr().out


def test_profiles_json(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("MAMIDLABS_ROOT", str(tmp_path))
    assert main(["profiles", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    ids = [entry["id"] for entry in payload]
    assert ids == ["max", "lite"]
    assert all(entry["present"] is False for entry in payload)


def test_doctor_reports_missing(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("MAMIDLABS_ROOT", str(tmp_path))
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "Kurulum kökü" in out
    assert "YOK" in out

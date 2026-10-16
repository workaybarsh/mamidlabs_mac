"""The partial-web-failure fix: a turn with any successful call is not a failure."""

from __future__ import annotations

import json

from mamidlabs.core.tools import WebTracker, classify_web_result


def test_classify_error_dict_is_failure():
    assert classify_web_result({"error": "HTTP Error 403: Forbidden"}) is True


def test_classify_results_list_is_success():
    assert classify_web_result([{"title": "x"}]) is False


def test_classify_empty_is_failure():
    assert classify_web_result(None) is True
    assert classify_web_result({}) is True
    assert classify_web_result("") is True


def test_classify_json_string():
    assert classify_web_result(json.dumps({"error": "timed out"})) is True
    assert classify_web_result(json.dumps({"url": "u", "text": "body"})) is False


def test_classify_text_failure_markers():
    assert classify_web_result("Web aramasi basarisiz: No results found.") is True
    assert classify_web_result("urlopen error timed out") is True


def test_tracker_mixed_success_is_not_unavailable():
    tracker = WebTracker()
    for _ in range(4):
        tracker.record([{"title": "ok"}])
    for result in ({"error": "HTTP Error 403: Forbidden"},
                   {"error": "Web aramasi basarisiz: No results found."},
                   {"error": "urlopen error [WinError 10054]"}):
        tracker.record(result)
    assert tracker.fail_count == 3
    assert tracker.success is True
    assert tracker.unavailable is False
    assert tracker.should_lock_tools is False
    # The visible note must not be appended when a call succeeded.
    assert tracker.add_failure_note("Bugün Zonguldak 18°C.") == "Bugün Zonguldak 18°C."


def test_tracker_all_failed_is_unavailable():
    tracker = WebTracker()
    tracker.record({"error": "HTTP Error 403"})
    tracker.record({"error": "timed out"})
    assert tracker.unavailable is True
    assert tracker.should_lock_tools is True
    note = tracker.add_failure_note("Yanıt.")
    assert "başarısız" in note


def test_tracker_single_failure_locks_only_after_two():
    tracker = WebTracker()
    tracker.record({"error": "HTTP Error 403"})
    assert tracker.unavailable is True       # note predicate
    assert tracker.should_lock_tools is False  # lock predicate needs >= 2


def test_tracker_success_after_failure_clears_unavailable():
    tracker = WebTracker()
    tracker.record({"error": "HTTP Error 403"})
    tracker.record([{"title": "ok"}])
    assert tracker.unavailable is False
    assert tracker.add_failure_note("metin") == "metin"

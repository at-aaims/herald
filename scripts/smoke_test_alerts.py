"""
scripts/smoke_test_alerts.py — P6+ alert evaluator unit checks.

Tests the rule evaluation, cooldown logic, and firing using StubNotifier.
Does not hit Slack or the syslog store — the residual-rate query is
swapped out for a closure that returns fixed numbers.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.syslog.notifier import StubNotifier  # noqa: E402
from scripts.check_alerts import (  # noqa: E402
    evaluate_rules,
    fire,
    in_cooldown,
    rule_queue_backlog,
    rule_residual_rate,
)


@dataclass(frozen=True)
class FakeSettings:
    syslog_alert_queue_threshold: int = 20
    syslog_alert_residual_rate_per_min_threshold: int = 1000
    syslog_alert_residual_rate_window_minutes: int = 5
    syslog_alert_cooldown_minutes: int = 60


def test_rule_queue_backlog_thresholding():
    print("=== test 1: queue backlog rule ===")
    # Stub proposals_queue.summary() by monkey-patching the import.
    from src.syslog import proposals_queue
    original = proposals_queue.summary
    proposals_queue.summary = lambda: {"pending": 25}
    try:
        r = rule_queue_backlog(threshold=20)
        assert r.fired
        assert "25 pending items" in r.message
        proposals_queue.summary = lambda: {"pending": 5}
        r = rule_queue_backlog(threshold=20)
        assert not r.fired
        proposals_queue.summary = lambda: {"pending": 25}
        r = rule_queue_backlog(threshold=0)   # disabled
        assert not r.fired
    finally:
        proposals_queue.summary = original
    print("  ok — fires at/above threshold, suppressed below, threshold=0 disables")


def test_rule_residual_rate_thresholding():
    print("\n=== test 2: residual-rate rule ===")
    r = rule_residual_rate(
        threshold_per_min=1000,
        window_min=5,
        rate_provider=lambda w: (6000, 1200.0),
    )
    assert r.fired
    assert "1200" in r.message or "1200.0" in r.message
    r = rule_residual_rate(
        threshold_per_min=1000,
        window_min=5,
        rate_provider=lambda w: (3000, 600.0),
    )
    assert not r.fired
    r = rule_residual_rate(
        threshold_per_min=0,
        window_min=5,
        rate_provider=lambda w: (10000, 2000.0),
    )
    assert not r.fired, "threshold=0 should disable the rule entirely"
    print("  ok — fires above threshold; threshold=0 disables")


def test_cooldown_suppresses_repeat_fires():
    print("\n=== test 3: cooldown suppresses repeat fires ===")
    now = datetime.now(timezone.utc)
    state: dict = {}
    # First fire: not in cooldown
    assert not in_cooldown(state, "queue_backlog", cooldown_min=60, now=now)
    state["queue_backlog"] = {"last_fired_at": now.isoformat()}
    # Same minute: in cooldown
    assert in_cooldown(state, "queue_backlog", cooldown_min=60, now=now + timedelta(minutes=30))
    # After cooldown window: not in cooldown
    assert not in_cooldown(state, "queue_backlog", cooldown_min=60, now=now + timedelta(minutes=61))
    print("  ok — cooldown enforced; clears after window")


def test_fire_routes_to_notifier_and_updates_state():
    print("\n=== test 4: fire() sends to notifier and updates state ===")
    from src.syslog import proposals_queue
    original = proposals_queue.summary
    proposals_queue.summary = lambda: {"pending": 30}
    try:
        results = evaluate_rules(
            settings=FakeSettings(),
            residual_rate_provider=lambda w: (10000, 2000.0),
        )
        assert len(results) == 2
        assert all(r.fired for r in results)

        notifier = StubNotifier()
        state: dict = {}
        now = datetime.now(timezone.utc)
        fired, suppressed = fire(
            results, notifier=notifier, alert_state=state,
            cooldown_min=60, now=now,
        )
        assert fired == 2 and suppressed == 0
        assert len(notifier.sent) == 2
        assert "queue_backlog" in state
        assert "residual_rate" in state

        # Second invocation: both rules in cooldown
        fired, suppressed = fire(
            results, notifier=notifier, alert_state=state,
            cooldown_min=60, now=now + timedelta(minutes=10),
        )
        assert fired == 0 and suppressed == 2
        assert len(notifier.sent) == 2, "no new sends during cooldown"
    finally:
        proposals_queue.summary = original
    print("  ok — first run notifies both rules; second run suppresses both")


def main() -> int:
    test_rule_queue_backlog_thresholding()
    test_rule_residual_rate_thresholding()
    test_cooldown_suppresses_repeat_fires()
    test_fire_routes_to_notifier_and_updates_state()
    print("\nAll alert checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

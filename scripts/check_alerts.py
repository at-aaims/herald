"""
scripts/check_alerts.py — P6+ alert evaluator, cron-driven.

Two rules:

  queue_backlog       fires when proposals_queue.summary().pending >=
                      syslog_alert_queue_threshold
                      (operator hasn't reviewed in a while; proposals
                       are piling up)

  residual_rate       fires when residuals/min over the recent window
                      exceeds syslog_alert_residual_rate_per_min_threshold
                      (the system started emitting unmatched lines at a
                       clip that suggests a real change — firmware update,
                       new daemon, misconfigured rsyslog)

Each rule has a cooldown so a sustained condition doesn't page every tick.
Last-fired state persists at syslog_alert_state_path so cooldown survives
across script invocations.

Cron line (every 10 min):
  */10 * * * * cd /path/to/herald && \\
    .venv/bin/python scripts/check_alerts.py >> .data/alerts.log 2>&1

If syslog_alert_slack_webhook_url is empty (the default), this script
prints what it would have sent and exits — useful for dry-running the
thresholds before wiring a real webhook.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings  # noqa: E402
from src.syslog import proposals_queue  # noqa: E402
from src.syslog.notifier import Notifier, StubNotifier, get_notifier  # noqa: E402


# ── Rule definitions ──────────────────────────────────────────────────────


@dataclass(slots=True)
class RuleResult:
    name: str
    fired: bool
    severity: str
    message: str
    extra: dict


def rule_queue_backlog(threshold: int) -> RuleResult:
    summary = proposals_queue.summary()
    pending = summary["pending"]
    fired = threshold > 0 and pending >= threshold
    return RuleResult(
        name="queue_backlog",
        fired=fired,
        severity="warning",
        message=(
            f"HERALD proposal queue has {pending} pending items "
            f"(threshold {threshold}). Review at /syslog/proposals "
            f"or run scripts/review_proposals.py."
        ),
        extra={"pending": pending, "threshold": threshold},
    )


def rule_residual_rate(
    threshold_per_min: int,
    window_min: int,
    rate_provider: Callable[[int], tuple[int, float]],
) -> RuleResult:
    """`rate_provider(window_min) -> (count, rate_per_min)` so tests can stub it."""
    if threshold_per_min <= 0:
        return RuleResult("residual_rate", False, "info", "rule disabled", {})
    count, rate = rate_provider(window_min)
    fired = rate >= threshold_per_min
    return RuleResult(
        name="residual_rate",
        fired=fired,
        severity="warning",
        message=(
            f"HERALD residual rate {rate:.1f}/min over the last {window_min}m "
            f"(threshold {threshold_per_min}/min, {count} unmatched lines). "
            f"Possible firmware update, new daemon, or rsyslog misconfig. "
            f"Run scripts/propose_patterns.py to extract patterns."
        ),
        extra={"count": count, "rate_per_min": rate,
               "threshold_per_min": threshold_per_min, "window_min": window_min},
    )


# ── Cooldown state ────────────────────────────────────────────────────────


def load_alert_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_alert_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def in_cooldown(state: dict, rule_name: str, cooldown_min: int, now: datetime) -> bool:
    """True if the rule was last fired within cooldown_min minutes."""
    last = state.get(rule_name, {}).get("last_fired_at")
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return False
    delta_min = (now - last_dt).total_seconds() / 60
    return delta_min < cooldown_min


# ── Live residual rate (via the syslog store) ─────────────────────────────


def live_residual_rate(window_min: int) -> tuple[int, float]:
    """Query the configured store for residuals in the last `window_min` minutes."""
    from src.syslog import state as syslog_state
    store = syslog_state.syslog_store()
    sql = (
        f"SELECT COUNT(*) AS n FROM events "
        f"WHERE coalesce(event_type, '') = '' "
        f"AND ts >= now() - INTERVAL {int(window_min)} MINUTE"
    )
    raw = store.run_sql(sql)
    try:
        rows = json.loads(raw)
    except ValueError:
        return 0, 0.0
    if not rows:
        return 0, 0.0
    n = int(rows[0].get("n", 0) or 0)
    return n, n / max(window_min, 1)


# ── Evaluation and firing ─────────────────────────────────────────────────


def evaluate_rules(
    *,
    settings,
    residual_rate_provider: Callable[[int], tuple[int, float]],
) -> list[RuleResult]:
    return [
        rule_queue_backlog(settings.syslog_alert_queue_threshold),
        rule_residual_rate(
            settings.syslog_alert_residual_rate_per_min_threshold,
            settings.syslog_alert_residual_rate_window_minutes,
            residual_rate_provider,
        ),
    ]


def fire(
    results: list[RuleResult],
    *,
    notifier: Notifier,
    alert_state: dict,
    cooldown_min: int,
    now: datetime,
) -> tuple[int, int]:
    """Returns (fired_count, suppressed_by_cooldown_count)."""
    fired_count = 0
    suppressed = 0
    for r in results:
        if not r.fired:
            continue
        if in_cooldown(alert_state, r.name, cooldown_min, now):
            suppressed += 1
            continue
        notifier.send(r.message, severity=r.severity, extra=r.extra)
        alert_state[r.name] = {"last_fired_at": now.isoformat()}
        fired_count += 1
    return fired_count, suppressed


# ── CLI entry ────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be sent; don't actually notify and don't update state.")
    args = ap.parse_args()

    settings = get_settings()
    notifier: Notifier | None = get_notifier()
    if notifier is None:
        # No webhook configured — fall back to a stub so we can still
        # evaluate the rules and report findings to stdout.
        notifier = StubNotifier()
        no_backend = True
    else:
        no_backend = False
        if args.dry_run:
            notifier = StubNotifier()

    now = datetime.now(timezone.utc)
    results = evaluate_rules(
        settings=settings,
        residual_rate_provider=live_residual_rate,
    )
    state_path = Path(settings.syslog_alert_state_path)
    alert_state = load_alert_state(state_path)
    fired, suppressed = fire(
        results, notifier=notifier, alert_state=alert_state,
        cooldown_min=settings.syslog_alert_cooldown_minutes, now=now,
    )

    print(f"=== {now.isoformat()} alert evaluation ===")
    for r in results:
        status = "FIRED" if r.fired else "ok"
        print(f"  [{status}] {r.name}: {r.message}")
    print(f"\nNotified: {fired}  Suppressed by cooldown: {suppressed}")
    if no_backend:
        print("No notifier backend configured (syslog_alert_slack_webhook_url empty).")
        print("Set the webhook URL to actually deliver alerts.")
    if args.dry_run:
        print("(dry-run: state not persisted)")
    elif not no_backend:
        save_alert_state(state_path, alert_state)

    if isinstance(notifier, StubNotifier) and notifier.sent:
        print("\nMessages that would be sent:")
        for msg in notifier.sent:
            print(f"  - {msg['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

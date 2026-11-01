"""
src/syslog/notifier.py 

"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol


SEVERITY_PREFIX: dict[str, str] = {
    "critical": "[CRITICAL]",
    "error":    "[ERROR]",
    "warning":  "[WARNING]",
    "info":     "[INFO]",
}


class Notifier(Protocol):
    """Backend-agnostic notification surface."""

    def send(
        self,
        message: str,
        *,
        severity: str = "info",
        extra: dict[str, Any] | None = None,
    ) -> None: ...


@dataclass
class StubNotifier:
    """In-memory notifier for tests; .sent captures every send()."""
    sent: list[dict[str, Any]] = field(default_factory=list)

    def send(self, message, *, severity="info", extra=None):
        self.sent.append({
            "message": message, "severity": severity, "extra": extra or {},
        })


@dataclass
class SlackNotifier:
    """

    """
    webhook_url: str
    timeout: float = 5.0

    def send(self, message, *, severity="info", extra=None):
        prefix = SEVERITY_PREFIX.get(severity, "[INFO]")
        text = f"{prefix} {message}"
        if extra:
            text += "\n```" + json.dumps(extra, indent=2)[:1500] + "```"
        payload = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(
            self.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status >= 400:
                    raise RuntimeError(f"slack webhook returned HTTP {resp.status}")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"slack webhook unreachable: {exc}") from exc


def get_notifier() -> Notifier | None:
    """Returns the configured Notifier, or None if no backend is enabled.

    """
    from src.config import get_settings
    settings = get_settings()
    if settings.syslog_alert_slack_webhook_url:
        return SlackNotifier(settings.syslog_alert_slack_webhook_url)
    return None

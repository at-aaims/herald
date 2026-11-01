"""
HERALD syslog sub-system.

Streaming HPC syslog classifier + monitor backend. Mirrors the offline
two-stage parsing pipeline from the SC paper:
  - Stage 1 (offline, LLM): produces taxonomy + regex DB
  - Stage 2 (here, regex):  line-rate classification, no LLM in hot path

Modules:
  patterns    - LOG_PATTERNS + classify_log_line (ported from syslog_model)
  classifier  - StreamingClassifier with noise sampling and residual queue
  ringbuffer  - per-node 5s-binned in-memory event store
  ingest      - source adapters (CSV replay, parquet replay)
  service     - FastAPI router exposing /syslog/* endpoints
"""
from src.syslog.patterns import LOG_PATTERNS, classify_log_line, severity_for
from src.syslog.classifier import StreamingClassifier, ParsedEvent

__all__ = [
    "LOG_PATTERNS",
    "classify_log_line",
    "severity_for",
    "StreamingClassifier",
    "ParsedEvent",
]

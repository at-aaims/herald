"""
src/syslog/residuals.py 

"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

from openai import AsyncOpenAI


# ── Template extraction ───────────────────────────────────────────────────

# Order matters: more specific replacements first. Each turns a class of
# variable tokens into a stable placeholder so identical templates with
# different concrete values collapse to one cluster.

_IPV4_RE     = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_MAC_RE      = re.compile(r"\b[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}\b")
_TIMESTAMP_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[\.\d]+)?(?:Z|[+-]\d{2}:?\d{2})?\b")
_QUOTED_RE   = re.compile(r"\"[^\"]{0,200}\"|'[^']{0,200}'")
_HOSTNAME_RE = re.compile(r"\b(?:frontier|node|host|hsn|nid)[-_]?\d+\b", re.IGNORECASE)
_PATH_RE     = re.compile(r"(?:/[\w.\-+@%]+){2,}")
_HEX_PREFIX_RE = re.compile(r"\b0x[0-9a-fA-F]+\b")
_HEX_BARE_RE = re.compile(r"\b[0-9a-fA-F]{8,}\b")
_NUM_RE      = re.compile(r"\b\d+\b")


def normalize(line: str) -> str:
    """
    Replace variable tokens with placeholders to expose the underlying template.

    Two log lines that differ only in numbers, hex IDs, paths, IPs, MACs,
    quoted strings, or hostname-with-digit will normalize to the same string
    and so cluster together.
    """
    s = line
    s = _TIMESTAMP_RE.sub("<TS>", s)
    s = _IPV4_RE.sub("<IP>", s)
    s = _MAC_RE.sub("<MAC>", s)
    s = _HOSTNAME_RE.sub("<HOST>", s)
    s = _QUOTED_RE.sub("<STR>", s)
    s = _PATH_RE.sub("<PATH>", s)
    s = _HEX_PREFIX_RE.sub("<HEX>", s)
    s = _HEX_BARE_RE.sub("<HEX>", s)
    s = _NUM_RE.sub("<N>", s)
    return s.strip()


@dataclass
class Cluster:
    template: str            # normalized representative
    samples: list[str]       # up to max_samples original lines
    frequency: int           # total residuals hitting this template

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def cluster_residuals(
    lines: list[str],
    *,
    min_size: int = 5,
    max_samples_per_cluster: int = 5,
    max_clusters: int = 200,
) -> list[Cluster]:
    """
    Group residual log lines by normalized template.

    Returns clusters with frequency >= min_size, sorted by frequency desc,
    capped at max_clusters (high-frequency clusters are what the proposer
    cares about; long-tail residuals are typically genuine one-offs).
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for ln in lines:
        if ln:
            groups[normalize(ln)].append(ln)
    clusters = [
        Cluster(template=tmpl, samples=samples[:max_samples_per_cluster], frequency=len(samples))
        for tmpl, samples in groups.items()
        if len(samples) >= min_size
    ]
    clusters.sort(key=lambda c: -c.frequency)
    return clusters[:max_clusters]


# ── LLM proposer ──────────────────────────────────────────────────────────


@dataclass
class PatternProposal:
    template: str
    representative_samples: list[str]
    frequency: int
    proposed_event_type: str            # NEW_FOO_BAR or an existing label
    proposed_regex: str
    subsystem: str                      # NET / GPU / HW / FS / SYS / SVC / APP / SEC / STO / CTX
    severity: str                       # critical / error / warning / info
    description: str
    is_new_label: bool
    rationale: str
    ignorecase: bool = False

    proposed_upstream: list[dict[str, str]] = field(default_factory=list)
    proposed_downstream: list[dict[str, str]] = field(default_factory=list)
    # Filled in by validate_proposals(); not produced by the LLM:
    valid: bool = True
    validation_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PROPOSER_SYSTEM = """\
You analyze residual HPC syslog messages — lines that HERALD's regex
database could not classify. Each input cluster is a group of similar
unmatched lines sharing one template.

For each cluster you must propose ONE pattern. You may either:
  - Extend an existing 87-event-type label (preferred when the cluster
    clearly belongs to a known subsystem and severity), OR
  - Define a new label using the same naming convention:
    <SUBSYSTEM>_<SHORT_NAME>  (UPPER_SNAKE_CASE, max 6 segments).

Subsystems: NET / GPU / HW / FS / SYS / SVC / APP / SEC / STO / CTX
Severities: critical / error / warning / info

You should ALSO propose plausible causal edges if domain knowledge
supports them:
  - "proposed_upstream": event_types that likely PRECEDE this new label
    (causes / triggers). Each entry: {"label": "EXISTING_LABEL", "rationale": "..."}.
  - "proposed_downstream": event_types this new label likely PRECEDES
    (effects / consequences). Each entry: {"label": "EXISTING_LABEL", "rationale": "..."}.
  - Reference only labels from the known_labels list provided in user input.
    Unknown labels will be rejected by the loader.
  - Empty lists are fine when you're unsure. Don't fabricate.
  - These are educated guesses, not statistical evidence — they enter
    the graph with tier="Manual" and an operator gate. Be conservative.

Output a JSON object with a single key "proposals" whose value is an array,
ONE object per input cluster, in the same order:

{
  "proposals": [
    {
      "proposed_event_type": "FS_LUSTRE_NEW_PATTERN",
      "proposed_regex": "LustreError: .* something specific",
      "subsystem": "FS",
      "severity": "error",
      "description": "Short one-line operational meaning.",
      "is_new_label": true,
      "rationale": "Why this label and regex fit the cluster.",
      "ignorecase": false,
      "proposed_upstream": [
        {"label": "FS_LUSTRE_OST_ERR", "rationale": "OST errors precede this pattern"}
      ],
      "proposed_downstream": [
        {"label": "APP_INFRA_FAIL", "rationale": "Persistent Lustre errors fail the app"}
      ]
    }
  ]
}

Rules:
  - The regex MUST match the representative samples and SHOULD NOT match
    the existing taxonomy's well-known patterns.
  - Anchor on a stable substring; avoid over-broad patterns like '.*'
    that would swallow unrelated lines.
  - Be specific. If a cluster looks like noise (banners, hardware names,
    BIOS strings), prefer an INFO_NOISE-style label with severity=info.
  - Output JSON ONLY. No markdown fences, no commentary.
"""


_FENCE_RE = re.compile(r"```(?:json)?\s*(.+?)```", re.DOTALL | re.IGNORECASE)
_REASONING_TAG_RE = re.compile(
    # Capture the tag name so the back-reference matches the same close tag.
    r"<(think|thinking|scratchpad|reasoning|reflection)>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
_JSON_BLOCK_RE = re.compile(r"(\[.*\]|\{.*\})", re.DOTALL)


def _extract_json_payload(text: str) -> str:
    """Strip reasoning blocks, markdown fences, and any pre/post commentary,
    returning the raw JSON substring (or the cleaned text if no obvious JSON
    block is found — caller will report the parse error)."""
    # 1. Drop <think>...</think> and friends
    s = _REASONING_TAG_RE.sub("", text)
    # 2. Drop markdown fences
    m = _FENCE_RE.search(s)
    if m:
        s = m.group(1)
    s = s.strip()
    # 3. If there's leading/trailing commentary around a JSON block, isolate it
    m = _JSON_BLOCK_RE.search(s)
    if m:
        return m.group(1).strip()
    return s


# Back-compat alias for any caller that still imports the old name.
_strip_fences = _extract_json_payload


def _validate(p: PatternProposal) -> PatternProposal:
    """Compile the regex; mark invalid proposals so the human can fix or reject."""
    try:
        flags = re.IGNORECASE if p.ignorecase else 0
        compiled = re.compile(p.proposed_regex, flags)
    except re.error as e:
        p.valid = False
        p.validation_error = f"regex did not compile: {e}"
        return p
    # Sanity-check: at least one of the representative samples must match.
    if p.representative_samples and not any(
        compiled.search(s) for s in p.representative_samples
    ):
        p.valid = False
        p.validation_error = "regex matches none of the representative samples"
    return p


# ── Tiered auto-apply (P6+) ───────────────────────────────────────────────

CANONICAL_SUBSYSTEMS: frozenset[str] = frozenset({
    "NET", "GPU", "HW", "FS", "SYS", "SVC", "APP", "SEC", "STO", "CTX",
})
VALID_SEVERITIES: frozenset[str] = frozenset({"critical", "error", "warning", "info"})

# Regex starts that would over-broadly swallow events. Anchored to position 0
# of the proposed regex (after stripping any leading whitespace).
_OVERBROAD_PREFIXES: tuple[str, ...] = (
    ".*", ".+", "\\w+", "\\W+", "\\s*", "\\s+", "\\S+", "\\d+",
    "^.*", "^.+",
)


@dataclass(slots=True)
class ConfidenceVerdict:
    auto_approve: bool
    reason: str   # approved, or not


def score_proposal(
    p: PatternProposal,
    *,
    known_labels: set[str],
    min_frequency: int = 50,
) -> ConfidenceVerdict:
    """
    
    """
    if not p.valid:
        return ConfidenceVerdict(False, f"invalid: {p.validation_error}")
    if p.proposed_event_type in known_labels:
        return ConfidenceVerdict(
            False, f"label collision with existing {p.proposed_event_type!r}"
        )
    if p.subsystem not in CANONICAL_SUBSYSTEMS:
        return ConfidenceVerdict(False, f"non-canonical subsystem {p.subsystem!r}")
    if p.severity not in VALID_SEVERITIES:
        return ConfidenceVerdict(False, f"unknown severity {p.severity!r}")
    if p.frequency < min_frequency:
        return ConfidenceVerdict(
            False, f"frequency {p.frequency} < min_frequency {min_frequency}"
        )
    stripped = p.proposed_regex.lstrip()
    for prefix in _OVERBROAD_PREFIXES:
        if stripped.startswith(prefix):
            return ConfidenceVerdict(
                False, f"regex starts with over-broad token {prefix!r}"
            )
    return ConfidenceVerdict(True, "all criteria met")


async def propose_patterns(
    clusters: list[Cluster],
    *,
    client: AsyncOpenAI,
    model_name: str,
    known_labels: list[str],
    batch_size: int = 20,
    max_tokens: int = 8192,
    debug_sink: list[dict] | None = None,
) -> list[PatternProposal]:
    """
    Run the LLM proposer over clusters, in batches to keep prompts small.
    Returns a list of PatternProposals (validated; invalid ones still
    returned with .valid=False so the human can see what was attempted).

    If `debug_sink` is provided, each batch appends a record
    `{batch_index, raw_response, parse_error}` so callers can dump it to a
    debug file when nothing comes back. This is essential for diagnosing
    reasoning-model output that the JSON parser couldn't decode.
    """
    proposals: list[PatternProposal] = []
    for i in range(0, len(clusters), batch_size):
        batch = clusters[i : i + batch_size]
        user_payload = {
            "known_labels": known_labels,
            "clusters": [
                {"template": c.template, "samples": c.samples, "frequency": c.frequency}
                for c in batch
            ],
        }
        messages = [
            {"role": "system", "content": _PROPOSER_SYSTEM},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]
        # response_format={"type": "json_object"} forces the model to emit a
        # top-level JSON object (not an array) and works on OpenAI / vLLM /
        # most modern backends. Not all support it though, so retry plain
        # on rejection.
        try:
            response = await client.chat.completions.create(
                model=model_name, messages=messages,
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
            )
        except Exception:
            response = await client.chat.completions.create(
                model=model_name, messages=messages,
                max_tokens=max_tokens,
            )
        raw_response = response.choices[0].message.content or ""
        cleaned = _extract_json_payload(raw_response)
        parse_error: str | None = None
        decoded: object | None = None
        try:
            decoded = json.loads(cleaned)
        except json.JSONDecodeError as e:
            parse_error = f"json.JSONDecodeError: {e}"
        # response_format=json_object forces a TOP-LEVEL OBJECT, which means
        # the model can't legitimately emit a bare array — it'll wrap it in
        # something like {"proposals":[...]} or {"items":[...]}. Unwrap.
        if isinstance(decoded, dict):
            for k in ("proposals", "results", "items", "data", "patterns", "output"):
                if k in decoded and isinstance(decoded[k], list):
                    decoded = decoded[k]
                    break

        if debug_sink is not None:
            debug_sink.append({
                "batch_index": i // batch_size,
                "cluster_count": len(batch),
                "raw_response_chars": len(raw_response),
                "raw_response": raw_response,
                "cleaned_payload": cleaned,
                "parse_error": parse_error,
                "shape": type(decoded).__name__,
                "finish_reason": getattr(response.choices[0], "finish_reason", None),
            })

        if not isinstance(decoded, list):
            continue
        for cluster, item in zip(batch, decoded):
            if not isinstance(item, dict):
                continue
            proposal = PatternProposal(
                template=cluster.template,
                representative_samples=cluster.samples,
                frequency=cluster.frequency,
                proposed_event_type=str(item.get("proposed_event_type", "")).strip(),
                proposed_regex=str(item.get("proposed_regex", "")),
                subsystem=str(item.get("subsystem", "UNKNOWN")).upper(),
                severity=str(item.get("severity", "info")).lower(),
                description=str(item.get("description", "")).strip(),
                is_new_label=bool(item.get("is_new_label", False)),
                rationale=str(item.get("rationale", "")).strip(),
                ignorecase=bool(item.get("ignorecase", False)),
                proposed_upstream=_normalize_edges(item.get("proposed_upstream")),
                proposed_downstream=_normalize_edges(item.get("proposed_downstream")),
            )
            proposals.append(_validate(proposal))
    return proposals


def _normalize_edges(raw: Any) -> list[dict[str, str]]:
    """Accept either ['LABEL', ...] or [{'label': 'LABEL', 'rationale': '...'}, ...]
    and return the dict form. Drops malformed entries silently."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for e in raw:
        if isinstance(e, str) and e.strip():
            out.append({"label": e.strip(), "rationale": ""})
        elif isinstance(e, dict):
            label = str(e.get("label") or e.get("cause") or e.get("effect") or "").strip()
            rationale = str(e.get("rationale") or "").strip()
            if label:
                out.append({"label": label, "rationale": rationale})
    return out

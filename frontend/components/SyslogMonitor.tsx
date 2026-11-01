'use client'

/**
 * SyslogMonitor — live replay panel for HPC syslog events.
 *
 * Left: SSE-driven event table (auto-scrolls; capped at MAX_EVENTS).
 * Right: detail panel for the clicked event — DAG of upstream causes plus
 *        sample raw instances within the lookback window.
 *
 * Controls: source path, speed, node id, lookback seconds, residuals on/off.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import CauseDag from './CauseDag'
import OperatorActions from './OperatorActions'

type ParsedEvent = {
  ts: string
  node: string
  event_type: string | null
  raw: string
  severity: string
  subsystem: string
  pid: number | null
  identifier: string | null
  // Monotonic id assigned on arrival — a STABLE React key so rows don't remount
  // when the capped buffer slides (esp. in loop mode). Index-based keys churn on
  // every slice, which remounts cells and breaks the hover-to-pause handlers.
  _id?: number
}

type ExplainEdge = {
  cause: string
  effect: string
  tier: string
  num_methods: number
  detected_by: string[]
  instance_count: number
  instances: Array<{ ts: string; node: string; raw: string; severity: string }>
}

type CascadeNode = {
  event_type: string
  depth: number
  tier?: string
  num_methods?: number
  detected_by?: string[]
  instance_count?: number
  instances?: Array<{ ts: string; node: string; raw: string; severity: string }>
  upstream?: CascadeNode[]
  cycle_truncated?: boolean
}

type ExplainResponse = {
  independent: boolean
  clicked: { event_type: string; node: string; ts: string }
  edges_with_instances: ExplainEdge[]
  candidates_without_instances: Array<{ cause: string; tier: string; num_methods: number }>
  lookback_seconds: number
  subgraph: { nodes: any[]; edges: any[] }
  cascade_tree?: CascadeNode | null
  max_depth?: number
}

const MAX_EVENTS = 5000
// Default to the cascade demo JSONL built by scripts/build_demo_cascades.py.
// Relative, not an absolute host path: the backend resolves it against its
// own process cwd, which is the repo root whether it's running bare-metal
// (`make api`) or in the Docker container (entrypoint `cd /app` before
// exec'ing uvicorn) — an absolute host path like /Users/.../herald/... only
// resolves inside the container by coincidence of the bind-mount target
// matching the host path, and breaks the moment they differ (as they do
// here: bind-mounted to /app, not the host's actual directory name).
// Override in the UI to point at the legacy /Users/.../sample_data_logs.csv,
// a parquet dump, or any other JSONL — the backend dispatches by extension.
const DEFAULT_SOURCE = '.data/syslog_demo.jsonl'

// In dev, the Next.js rewrite buffers SSE responses (it re-compresses with
// gzip for browsers that send Accept-Encoding: gzip, which then accumulates
// frames until ~kB chunks land). Bypass the proxy and point EventSource
// straight at the FastAPI port — CORS for localhost:3000 is already
// allow-listed in src/server/api.py. In prod, set NEXT_PUBLIC_HERALD_API_URL
// to your reverse proxy that streams SSE without buffering (nginx with
// proxy_buffering off, etc.), or leave unset to use a same-origin path.
const STREAM_API_BASE =
  process.env.NEXT_PUBLIC_HERALD_API_URL ??
  (process.env.NODE_ENV === 'development' ? 'http://localhost:8000' : '')

const SEVERITY_STYLE: Record<string, string> = {
  critical: 'text-red-400 border-red-400/40 bg-red-400/10',
  error:    'text-orange-400 border-orange-400/40 bg-orange-400/10',
  warning:  'text-yellow-400 border-yellow-400/30 bg-yellow-400/10',
  info:     'text-herald-text-dim border-herald-border bg-herald-surface',
  residual: 'text-violet-400 border-violet-400/30 bg-violet-400/10',
}

// Operator-toggleable severity levels, ordered most→least urgent. The table
// shows only events whose severity is in the active set (client-side filter —
// the stream still carries every level, so toggling is instant and lossless).
const SEVERITY_LEVELS = ['critical', 'error', 'warning', 'info', 'residual'] as const

function SeverityBadge({ sev }: { sev: string }) {
  const cls = SEVERITY_STYLE[sev] ?? SEVERITY_STYLE.info
  return (
    <span className={`text-[10px] font-mono uppercase tracking-wider border rounded px-1 py-0.5 ${cls}`}>
      {sev}
    </span>
  )
}

// Minimal bar sparkline — plain divs, no charting lib, for a footprint this
// small (a handful of bars next to a stats-strip number). `values` is
// oldest-first, real time-bucketed counts from the backend (see
// src/syslog/store.py's bucketed_counts), not a client-side approximation.
function Sparkline({ values }: { values: number[] }) {
  const max = Math.max(1, ...values)
  return (
    <span className="inline-flex items-end gap-px h-3 align-middle" title="Volume trend over the same window, oldest to newest">
      {values.map((v, i) => (
        <span
          key={i}
          className="w-0.5 bg-herald-accent/70 rounded-[1px]"
          style={{ height: `${Math.max(v > 0 ? 15 : 4, (v / max) * 100)}%` }}
        />
      ))}
    </span>
  )
}

export default function SyslogMonitor() {
  const [source, setSource] = useState(DEFAULT_SOURCE)
  const [editingSource, setEditingSource] = useState(false)  // show basename until clicked
  // Portal target in the app sidebar (#syslog-sidebar-controls). The stream
  // controls render there so the monitor keeps all its state local while the
  // controls live in the shared sidebar. Falls back to inline if absent.
  const [controlsHost, setControlsHost] = useState<HTMLElement | null>(null)
  useEffect(() => {
    setControlsHost(document.getElementById('syslog-sidebar-controls'))
  }, [])
  const [speed, setSpeed] = useState(20)
  const [node, setNode] = useState('node-0')
  const [includeResiduals, setIncludeResiduals] = useState(true)
  const [loopSource, setLoopSource] = useState(false)
  // Active severity levels for the table view. Defaults to all on; toggling a
  // chip filters the rendered rows client-side without touching the stream.
  const [activeSeverities, setActiveSeverities] = useState<Set<string>>(
    () => new Set(SEVERITY_LEVELS),
  )
  const toggleSeverity = useCallback((sev: string) => {
    setActiveSeverities((prev) => {
      const next = new Set(prev)
      if (next.has(sev)) next.delete(sev)
      else next.add(sev)
      return next
    })
  }, [])
  // Severity filter lives behind a dropdown to keep the stats strip uncluttered.
  const [severityMenuOpen, setSeverityMenuOpen] = useState(false)
  const severityMenuRef = useRef<HTMLDivElement | null>(null)
  // 24h volume panel — same open/outside-click-close pattern as the
  // severity dropdown, but lists every event type seen in the window
  // (not just a top few crammed into the stats strip), scrollable.
  const [volumePanelOpen, setVolumePanelOpen] = useState(false)
  const volumePanelRef = useRef<HTMLDivElement | null>(null)
  // Hovering the Severity column freezes the table entirely — row
  // positions, counts, everything — so a row stays put long enough to
  // click (see pendingEventsRef: incoming events queue instead of landing
  // in `events` while this is true). Resumes (flushing the backlog, then
  // snapping to bottom) on leave.
  const [scrollPaused, setScrollPaused] = useState(false)
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState<ParsedEvent[]>([])
  const [selected, setSelected] = useState<ParsedEvent | null>(null)
  const [lookback, setLookback] = useState(60)
  const [maxDepth, setMaxDepth] = useState(5)
  const [explain, setExplain] = useState<ExplainResponse | null>(null)
  const [explainLoading, setExplainLoading] = useState(false)
  const [explainError, setExplainError] = useState<string | null>(null)
  const [showAllCandidates, setShowAllCandidates] = useState(false)
  // When the operator clicks a cause hop in the DAG, the Causes section
  // below switches to that hop's raw messages instead of the default
  // depth-1 fired-causes view. The selected event (header, DAG, advisory)
  // stays unchanged. Reset to null on every new event selection.
  const [focusedHop, setFocusedHop] = useState<string | null>(null)
  // Side-panel width is operator-resizable via the drag bar between the
  // event table and the detail panel. Persisted in localStorage so it
  // survives reloads.
  const [sidePanelWidth, setSidePanelWidth] = useState<number>(480)
  useEffect(() => {
    const stored = typeof window !== 'undefined'
      ? window.localStorage.getItem('herald.syslog.sidePanelWidth')
      : null
    if (stored) {
      const n = Number(stored)
      if (Number.isFinite(n) && n >= 320 && n <= 1200) setSidePanelWidth(n)
    }
  }, [])
  const tableRef = useRef<HTMLDivElement | null>(null)
  const esRef = useRef<EventSource | null>(null)
  const stickToBottomRef = useRef(true)
  const eventIdRef = useRef(0)  // monotonic id source for stable row keys
  // Mirrors scrollPaused for the onmessage closure below (a ref, not state,
  // so the handler set up once in connect() always sees the current value).
  const scrollPausedRef = useRef(false)
  // Events arriving while paused land here instead of in `events` — the
  // pause is meant to freeze the table (row positions, counts, everything)
  // so an operator can read/click a row without it sliding out from under
  // the cursor. Applying incoming events straight to state during pause
  // still evicts old rows off the top of the 500-cap buffer, which shifts
  // every remaining row up by one row-height per arrival — invisible to the
  // "stickToBottom" auto-scroll check (which only guards the jump-to-
  // bottom call) but very visible to the operator as constant drift.
  // Flushed in one batch on resume (see the scrollPaused effect below).
  const pendingEventsRef = useRef<ParsedEvent[]>([])
  const dividerDragRef = useRef<{ startX: number; startWidth: number } | null>(null)

  const onDividerMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    dividerDragRef.current = { startX: e.clientX, startWidth: sidePanelWidth }
    const onMove = (ev: MouseEvent) => {
      const d = dividerDragRef.current
      if (!d) return
      // Dragging left increases panel width (panel is on the right).
      const next = Math.max(320, Math.min(1200, d.startWidth + (d.startX - ev.clientX)))
      setSidePanelWidth(next)
    }
    const onUp = () => {
      dividerDragRef.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      try {
        window.localStorage.setItem('herald.syslog.sidePanelWidth', String(sidePanelWidth))
      } catch {}
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }
  // Persist the width whenever it settles after a drag.
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (dividerDragRef.current) return  // mid-drag — wait
    try {
      window.localStorage.setItem('herald.syslog.sidePanelWidth', String(sidePanelWidth))
    } catch {}
  }, [sidePanelWidth])

  const connect = useCallback(() => {
    esRef.current?.close()
    setEvents([])
    pendingEventsRef.current = []
    setSelected(null)
    setExplain(null)
    const qs = new URLSearchParams({
      source,
      speed: String(speed),
      node,
      include_residuals: String(includeResiduals),
      loop: String(loopSource),
    })
    // When a subset of levels is selected, narrow the stream server-side too
    // so the 500-event buffer fills with the levels of interest rather than
    // being dominated by high-volume INFO. All-on = omit (emit everything).
    // The backend still classifies/buffers/persists every event regardless.
    if (activeSeverities.size > 0 && activeSeverities.size < SEVERITY_LEVELS.length) {
      qs.set('severities', [...activeSeverities].join(','))
    }
    const es = new EventSource(`${STREAM_API_BASE}/api/syslog/stream?${qs.toString()}`)
    esRef.current = es
    es.onopen = () => setConnected(true)
    es.onerror = () => {
      // EventSource fires onerror both for transient blips (it auto-reconnects
      // ~every 3s) and for the clean end-of-file close from the backend. Only
      // treat CLOSED as a real disconnect — otherwise the button would flicker
      // each reconnect cycle.
      if (es.readyState === EventSource.CLOSED) setConnected(false)
    }
    // Backend emits `event: end` when the replay finishes (loop=off, EOF).
    // Close ourselves so the browser doesn't auto-reconnect and re-replay.
    es.addEventListener('end', () => {
      es.close()
      esRef.current = null
      setConnected(false)
    })
    es.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data) as ParsedEvent
        ev._id = eventIdRef.current++
        if (scrollPausedRef.current) {
          // Frozen — queue instead of touching `events` (see pendingEventsRef).
          // Capped defensively so an unusually long pause can't grow this
          // without bound; the same MAX_EVENTS sliding-window trim the main
          // buffer uses.
          const q = pendingEventsRef.current
          q.push(ev)
          if (q.length > MAX_EVENTS) q.splice(0, q.length - MAX_EVENTS)
          return
        }
        setEvents((prev) => {
          const next = prev.length >= MAX_EVENTS ? prev.slice(-MAX_EVENTS + 1) : prev.slice()
          next.push(ev)
          return next
        })
      } catch {
        // skip malformed frame
      }
    }
  }, [source, speed, node, includeResiduals, loopSource, activeSeverities])

  const disconnect = useCallback(() => {
    esRef.current?.close()
    esRef.current = null
    setConnected(false)
  }, [])

  useEffect(() => () => { esRef.current?.close() }, [])

  // Close the severity dropdown on outside-click or Escape.
  useEffect(() => {
    if (!severityMenuOpen) return
    const onDown = (e: MouseEvent) => {
      if (severityMenuRef.current && !severityMenuRef.current.contains(e.target as Node)) {
        setSeverityMenuOpen(false)
      }
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setSeverityMenuOpen(false) }
    window.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [severityMenuOpen])

  // Close the 24h volume panel on outside-click or Escape — same pattern
  // as the severity dropdown above.
  useEffect(() => {
    if (!volumePanelOpen) return
    const onDown = (e: MouseEvent) => {
      if (volumePanelRef.current && !volumePanelRef.current.contains(e.target as Node)) {
        setVolumePanelOpen(false)
      }
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setVolumePanelOpen(false) }
    window.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [volumePanelOpen])

  // Keep the ref in sync, and flush anything queued during the pause the
  // instant it lifts — one state update, so the table jumps straight to
  // caught-up instead of visibly replaying the backlog row by row.
  useEffect(() => {
    scrollPausedRef.current = scrollPaused
    if (scrollPaused) return
    const pending = pendingEventsRef.current
    if (pending.length === 0) return
    pendingEventsRef.current = []
    setEvents((prev) => {
      const next = prev.concat(pending)
      return next.length > MAX_EVENTS ? next.slice(next.length - MAX_EVENTS) : next
    })
  }, [scrollPaused])

  // Rows actually shown: every streamed event whose severity is toggled on.
  const visibleEvents = useMemo(
    () => events.filter((e) => activeSeverities.has(e.severity)),
    [events, activeSeverities],
  )

  // Auto-scroll to bottom when new events arrive, unless user scrolled up.
  useEffect(() => {
    const el = tableRef.current
    if (!el || !stickToBottomRef.current || scrollPaused) return
    el.scrollTop = el.scrollHeight
  }, [visibleEvents, scrollPaused])

  const onScroll = () => {
    const el = tableRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24
    stickToBottomRef.current = atBottom
  }

  // Pause auto-scroll when the pointer is over the sev (col 1) or event (col 2)
  // column. We key off the pointer's COLUMN, computed on mousemove, rather than
  // per-cell onMouseEnter: programmatic auto-scroll moves rows under a stationary
  // cursor without reliably firing mouseenter, which made pausing racy. The
  // column is an X-position fact that vertical scrolling never changes, so the
  // pause stays correct even while the mouse is still and content scrolls.
  const PAUSE_COLS = new Set([1, 2]) // ts=0, sev=1, event=2, raw=3
  const onTableMouseMove = (e: React.MouseEvent) => {
    const cell = (e.target as HTMLElement).closest('td,th') as HTMLTableCellElement | null
    setScrollPaused(!!cell && PAUSE_COLS.has(cell.cellIndex))
  }

  const fetchExplain = useCallback(async (ev: ParsedEvent, lookbackSec: number, depth: number) => {
    if (!ev.event_type) {
      setExplain({
        independent: true,
        clicked: { event_type: 'RESIDUAL', node: ev.node, ts: ev.ts },
        edges_with_instances: [],
        candidates_without_instances: [],
        lookback_seconds: lookbackSec,
        subgraph: { nodes: [{ id: 'RESIDUAL', kind: 'effect' }], edges: [] },
      })
      return
    }
    setExplainLoading(true)
    setExplainError(null)
    try {
      const res = await fetch('/api/syslog/explain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_type: ev.event_type,
          node: ev.node,
          ts: ev.ts,
          lookback_seconds: lookbackSec,
          max_depth: depth,
        }),
      })
      if (!res.ok) {
        const body = await res.text()
        setExplainError(`${res.status}: ${body}`)
        setExplain(null)
      } else {
        const data = (await res.json()) as ExplainResponse
        setExplain(data)
      }
    } catch (err) {
      setExplainError(String(err))
      setExplain(null)
    } finally {
      setExplainLoading(false)
    }
  }, [])

  const onRowClick = (ev: ParsedEvent) => {
    setSelected(ev)
    setFocusedHop(null)
    fetchExplain(ev, lookback, maxDepth)
  }

  // Walk the cascade tree to find a node by event_type. The tree may visit
  // the same event at multiple depths via different paths; we return the
  // shallowest occurrence (it carries the canonical instance list since
  // layoutCascade also uses min-depth).
  const findCascadeNode = useCallback(
    (tree: CascadeNode | null | undefined, et: string): CascadeNode | null => {
      if (!tree) return null
      let best: CascadeNode | null = null
      const visit = (n: CascadeNode) => {
        if (n.event_type === et && (best === null || n.depth < best.depth)) best = n
        for (const c of n.upstream ?? []) visit(c)
      }
      visit(tree)
      return best
    },
    [],
  )

  const focusedNode = useMemo(
    () => (focusedHop ? findCascadeNode(explain?.cascade_tree, focusedHop) : null),
    [focusedHop, explain, findCascadeNode],
  )

  // Re-fetch when lookback OR depth changes for the currently selected event.
  useEffect(() => {
    if (selected) fetchExplain(selected, lookback, maxDepth)
  }, [lookback, maxDepth, selected, fetchExplain])

  const stats = useMemo(() => {
    const byType = new Map<string, number>()
    let residuals = 0
    for (const e of visibleEvents) {
      if (e.event_type) byType.set(e.event_type, (byType.get(e.event_type) ?? 0) + 1)
      else residuals++
    }
    const top = [...byType.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4)
    return { total: visibleEvents.length, hidden: events.length - visibleEvents.length, residuals, top }
  }, [events, visibleEvents])

  // True cumulative counts over the persisted store for the last 24h —
  // distinct from `stats` above, which is only ever computed from the
  // capped MAX_EVENTS ring buffer currently held in the browser. Polled
  // (not derived from the SSE stream) since it reflects everything
  // written to the store, including by other connections/workers, not
  // just what this tab has seen.
  const [sinceCounts, setSinceCounts] = useState<Record<string, number> | null>(null)
  // Per-type time-bucketed counts for the same top types as sinceCounts —
  // powers the sparklines. A real query (src/syslog/store.py's
  // bucketed_counts), not a client-side approximation from whatever's in
  // the ring buffer.
  const [sinceBuckets, setSinceBuckets] = useState<Record<string, number[]> | null>(null)
  // Types whose recent rate is way above their peers right now (see
  // src/syslog/service.py's _flag_high_frequency) — a dynamic counterpart
  // to the classifier's static noise allowlist: this catches ANY type
  // spiking, known-noisy or not, relative to current conditions rather
  // than a fixed pre-approved list.
  const [rateFlags, setRateFlags] = useState<Array<{ event_type: string; rate_per_sec: number; median_rate_per_sec: number; ratio: number }>>([])
  useEffect(() => {
    if (!connected) return
    let cancelled = false
    const poll = async () => {
      try {
        const res = await fetch(`${STREAM_API_BASE}/api/syslog/stats?since_hours=24`)
        if (!res.ok || cancelled) return
        const data = await res.json()
        if (!cancelled) {
          setSinceCounts(data.since_counts ?? null)
          setSinceBuckets(data.since_buckets ?? null)
          setRateFlags(data.rate_flags ?? [])
        }
      } catch {
        // transient — next poll will retry
      }
    }
    poll()
    const id = setInterval(poll, 5000)
    return () => { cancelled = true; clearInterval(id) }
  }, [connected])
  const rateFlagMap = useMemo(
    () => new Map(rateFlags.map((f) => [f.event_type, f])),
    [rateFlags],
  )

  // Every type seen in the window, sorted by volume — the panel shows all
  // of it (scrollable), not just a handful crammed into the stats strip.
  const sinceAll = useMemo(() => {
    if (!sinceCounts) return []
    return Object.entries(sinceCounts).sort((a, b) => b[1] - a[1])
  }, [sinceCounts])
  const sinceTotal = useMemo(() => sinceAll.reduce((sum, [, n]) => sum + n, 0), [sinceAll])

  // Stream controls — rendered vertically (portaled into the app sidebar).
  const controls = (
    <div className="space-y-3 text-xs">
      {/* Source */}
      <div className="space-y-1">
        <p className="px-0.5 text-[10px] uppercase tracking-wider text-herald-muted">Source</p>
        {editingSource ? (
          <input
            autoFocus
            value={source}
            onChange={(e) => setSource(e.target.value)}
            onBlur={() => setEditingSource(false)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === 'Escape') setEditingSource(false) }}
            className="w-full bg-herald-bg border border-herald-accent/60 rounded px-2 py-1 font-mono text-herald-text"
          />
        ) : (
          <button
            onClick={() => setEditingSource(true)}
            title={`Source: ${source}\nClick to edit. Accepts .jsonl / .csv / .parquet. Applies on next Connect.`}
            className="w-full flex items-center gap-1.5 bg-herald-bg border border-herald-border rounded px-2 py-1 hover:border-herald-accent/60"
          >
            <span className="font-mono text-herald-text truncate flex-1 text-left">{source.split('/').pop() || source}</span>
            <span className="text-herald-muted text-[10px]">edit</span>
          </button>
        )}
      </div>

      {/* Playback — applies on next Connect */}
      <div className="space-y-1.5">
        <p className="px-0.5 text-[10px] uppercase tracking-wider text-herald-muted">Playback · on connect</p>
        <label className="flex items-center justify-between gap-2" title="Replay rate in events per second. File timestamps are preserved; this only changes emission cadence.">
          <span className="text-herald-text-dim">Speed</span>
          <span className="flex items-center gap-1">
            <input type="number" min={1} max={10000} value={speed}
              onChange={(e) => setSpeed(Math.max(1, Number(e.target.value) || 1))}
              className="w-16 bg-herald-bg border border-herald-border rounded px-2 py-1 text-herald-text" />
            <span className="text-herald-muted">eps</span>
          </span>
        </label>
        <label className="flex items-center justify-between gap-2" title="Synthetic node id used only when the source file does not carry a node column.">
          <span className="text-herald-text-dim">Node</span>
          <input value={node} onChange={(e) => setNode(e.target.value)}
            className="w-28 bg-herald-bg border border-herald-border rounded px-2 py-1 font-mono text-herald-text" />
        </label>
        <div className="flex items-center gap-4 pt-0.5">
          <label className="flex items-center gap-1 text-herald-text-dim" title="Include LLM-fallback parsed lines the regex bank did not classify.">
            <input type="checkbox" checked={includeResiduals} onChange={(e) => setIncludeResiduals(e.target.checked)} />
            residuals
          </label>
          <label className="flex items-center gap-1 text-herald-text-dim" title="When the source file is exhausted, restart from the top instead of stopping.">
            <input type="checkbox" checked={loopSource} onChange={(e) => setLoopSource(e.target.checked)} />
            loop
          </label>
        </div>
      </div>

      {/* Analysis — re-applies live to the selected event */}
      <div className="space-y-1.5">
        <p className="px-0.5 text-[10px] uppercase tracking-wider text-herald-muted">Analysis · live</p>
        <label className="flex items-center justify-between gap-2" title="Click-walker time window: scans this node's ringbuffer this many seconds back for upstream-cause instances.">
          <span className="text-herald-text-dim">Lookback</span>
          <span className="flex items-center gap-1">
            <input type="number" min={1} max={3600} value={lookback}
              onChange={(e) => setLookback(Math.max(1, Number(e.target.value) || 1))}
              className="w-16 bg-herald-bg border border-herald-border rounded px-2 py-1 text-herald-text" />
            <span className="text-herald-muted">s</span>
          </span>
        </label>
        <label className="flex items-center justify-between gap-2" title="How many causal-graph hops to walk upstream from the clicked event. 1 = direct causes; 5 = full cascade.">
          <span className="text-herald-text-dim">Depth</span>
          <span className="flex items-center gap-2">
            <input type="range" min={1} max={5} step={1} value={maxDepth}
              onChange={(e) => setMaxDepth(Math.max(1, Math.min(5, Number(e.target.value) || 1)))}
              className="accent-herald-accent w-24" />
            <span className="font-mono text-herald-text w-3 text-right">{maxDepth}</span>
          </span>
        </label>
      </div>

      {/* Connect / Disconnect */}
      {connected ? (
        <button onClick={disconnect} title="Close the SSE stream."
          className="w-full px-3 py-1.5 rounded border border-red-400/40 text-red-400 hover:bg-red-400/10">
          Disconnect
        </button>
      ) : (
        <button onClick={connect} title="Open the SSE stream with the current Source / Playback settings."
          className="w-full px-3 py-1.5 rounded border border-herald-accent text-herald-accent hover:bg-herald-accent hover:text-white">
          Connect
        </button>
      )}
    </div>
  )

  return (
    <div className="flex flex-col h-full">
      {/* Stream controls — portaled into the app sidebar (#syslog-sidebar-controls).
          Falls back to an inline bar if that host isn't present. */}
      {controlsHost
        ? createPortal(controls, controlsHost)
        : <div className="px-4 py-2 border-b border-herald-border bg-herald-surface">{controls}</div>}

      {/* Stats strip */}
      <div className="flex items-center gap-4 px-4 py-1.5 border-b border-herald-border text-[11px] text-herald-text-dim">
        <span>{connected ? '● live' : '○ idle'}</span>
        {scrollPaused && connected && (
          <span className="text-herald-accent" title="Auto-scroll paused while hovering the Severity column.">
            ⏸ scroll paused
          </span>
        )}
        <span title={`Live view only — capped at ${MAX_EVENTS} rows for render performance. Not the total volume; see "24h" further right for the real cumulative count.`}>
          {stats.total} shown (last {MAX_EVENTS})
        </span>
        {stats.hidden > 0 && (
          <span className="text-herald-muted">({stats.hidden} hidden by filter)</span>
        )}
        <span>{stats.residuals} residuals</span>
        <span className="text-herald-muted">|</span>
        {/* Severity filter — checkbox dropdown. Toggling a level filters the
            table immediately; on the next Connect it also narrows the stream
            server-side (the backend still classifies/stores every level). */}
        <div className="relative" ref={severityMenuRef}>
          <button
            onClick={() => setSeverityMenuOpen((o) => !o)}
            aria-haspopup="true"
            aria-expanded={severityMenuOpen}
            title="Choose which severity levels appear in the table. Takes effect immediately on the events already received. On the next Connect, the selection also narrows the stream server-side (the backend still classifies and stores every level)."
            className="flex items-center gap-1.5 border border-herald-border rounded px-2 py-0.5 hover:bg-herald-surface text-herald-text-dim"
          >
            <span>Severity</span>
            <span className="font-mono text-herald-text">
              {activeSeverities.size === SEVERITY_LEVELS.length
                ? 'all'
                : `${activeSeverities.size}/${SEVERITY_LEVELS.length}`}
            </span>
            <span className="text-herald-muted text-[9px]">▾</span>
          </button>
          {severityMenuOpen && (
            <div className="absolute z-30 mt-1 left-0 min-w-[176px] border border-herald-border rounded bg-herald-bg shadow-lg p-1">
              {SEVERITY_LEVELS.map((sev) => {
                const on = activeSeverities.has(sev)
                return (
                  <label
                    key={sev}
                    className="flex items-center gap-2 px-2 py-1 rounded hover:bg-herald-surface cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={() => toggleSeverity(sev)}
                      className="accent-herald-accent"
                    />
                    <span
                      className={`font-mono uppercase tracking-wider border rounded px-1 py-0.5 text-[10px] ${
                        SEVERITY_STYLE[sev] ?? SEVERITY_STYLE.info
                      }`}
                    >
                      {sev}
                    </span>
                  </label>
                )
              })}
              <div className="flex items-center justify-between border-t border-herald-border mt-1 pt-1 px-2 text-[10px]">
                <button
                  onClick={() => setActiveSeverities(new Set(SEVERITY_LEVELS))}
                  className="text-herald-accent hover:underline"
                >
                  select all
                </button>
                <button
                  onClick={() => setActiveSeverities(new Set())}
                  className="text-herald-accent hover:underline"
                >
                  clear
                </button>
              </div>
            </div>
          )}
        </div>
        <span className="text-herald-muted">|</span>
        <span
          className="text-herald-muted"
          title={`Top event types in the currently-shown last ${MAX_EVENTS} rows — drifts as the window slides, not a running total.`}
        >
          window:
        </span>
        {stats.top.map(([t, n]) => (
          <span key={t} className="font-mono">
            {t}: <span className="text-herald-text">{n}</span>
          </span>
        ))}
        {sinceAll.length > 0 && (
          <>
            <span className="text-herald-muted">|</span>
            <div className="relative" ref={volumePanelRef}>
              <button
                onClick={() => setVolumePanelOpen((o) => !o)}
                aria-haspopup="true"
                aria-expanded={volumePanelOpen}
                title="True cumulative counts from the persisted store for the last 24h — everything written, not just what's currently rendered. Refreshes every 5s."
                className="flex items-center gap-1.5 hover:text-herald-text"
              >
                <span className="text-herald-muted">24h:</span>
                <span className="font-mono text-herald-text">{sinceTotal.toLocaleString()}</span>
                <span className="text-herald-muted">({sinceAll.length} types)</span>
                {rateFlags.length > 0 && (
                  <span
                    className="text-amber-400 text-[10px] font-mono"
                    title={`${rateFlags.length} type(s) running well above their usual rate right now`}
                  >
                    ⚠ {rateFlags.length}
                  </span>
                )}
                <span className="text-herald-muted text-[9px]">▾</span>
              </button>
              {volumePanelOpen && (
                <div className="absolute z-30 mt-1 right-0 w-[420px] max-h-80 overflow-y-auto border border-herald-border rounded bg-herald-bg shadow-lg p-1">
                  {sinceAll.map(([t, n]) => {
                    const flag = rateFlagMap.get(t)
                    return (
                      <div key={t} className="flex items-center justify-between gap-2 px-2 py-1 rounded hover:bg-herald-surface">
                        <span className="flex items-center gap-1.5 min-w-0">
                          {flag && (
                            <span
                              className="text-amber-400 text-[10px] flex-shrink-0"
                              title={`Current rate ${flag.rate_per_sec}/s is ${flag.ratio}x the median (${flag.median_rate_per_sec}/s) across active types right now`}
                            >
                              ⚠
                            </span>
                          )}
                          <span className="font-mono text-herald-text truncate">{t}</span>
                        </span>
                        <span className="flex items-center gap-2 flex-shrink-0">
                          <span className="font-mono text-herald-text-dim">{n.toLocaleString()}</span>
                          {sinceBuckets?.[t] && <Sparkline values={sinceBuckets[t]} />}
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* Split: event table + detail panel */}
      <div className="flex-1 flex overflow-hidden">
        {/* Event table */}
        <div
          ref={tableRef}
          onScroll={onScroll}
          // Column-based pause (see onTableMouseMove). Resume on leaving the
          // table is the stable backstop — it always fires even if a hovered
          // row unmounted mid-stream.
          onMouseMove={onTableMouseMove}
          onMouseLeave={() => setScrollPaused(false)}
          className="flex-1 min-w-0 overflow-y-auto"
        >
          <table className="w-full text-xs font-mono">
            <thead className="sticky top-0 bg-herald-bg text-herald-text-dim border-b border-herald-border">
              <tr>
                <th className="text-left px-3 py-1.5 font-normal w-44">ts</th>
                <th
                  className="text-left px-2 py-1.5 font-normal w-20"
                  title="Hover the severity or event column to pause auto-scroll; move off the table to resume."
                >
                  sev
                </th>
                <th className="text-left px-2 py-1.5 font-normal w-44">event</th>
                <th className="text-left px-2 py-1.5 font-normal">raw</th>
              </tr>
            </thead>
            <tbody>
              {visibleEvents.map((ev, i) => {
                const isSelected = selected && selected.ts === ev.ts && selected.raw === ev.raw
                return (
                  <tr
                    key={ev._id ?? i}
                    onClick={() => onRowClick(ev)}
                    className={`cursor-pointer border-b border-herald-border/40 hover:bg-herald-surface ${
                      isSelected ? 'bg-herald-surface' : ''
                    }`}
                  >
                    <td className="px-3 py-1 text-herald-text-dim whitespace-nowrap">
                      {ev.ts.replace(/\.\d+/, '').replace('T', ' ').replace(/\+.*/, '')}
                    </td>
                    <td className="px-2 py-1">
                      <SeverityBadge sev={ev.severity} />
                    </td>
                    <td className="px-2 py-1 text-herald-text whitespace-nowrap">
                      {ev.event_type ?? <span className="text-violet-400">(residual)</span>}
                    </td>
                    <td className="px-2 py-1 text-herald-text-dim truncate max-w-0">
                      {ev.raw}
                    </td>
                  </tr>
                )
              })}
              {visibleEvents.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-herald-text-dim">
                    {events.length > 0
                      ? 'No events match the selected severity levels.'
                      : connected
                        ? 'Waiting for events…'
                        : 'Press Connect to start the replay.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Draggable divider between table and detail panel */}
        <div
          onMouseDown={onDividerMouseDown}
          title="Drag to resize panel"
          className="w-1 cursor-col-resize bg-herald-border hover:bg-herald-accent transition-colors flex-shrink-0"
        />

        {/* Detail panel */}
        <aside
          style={{ width: `${sidePanelWidth}px` }}
          className="flex-shrink-0 border-l border-herald-border overflow-y-auto bg-herald-bg">
          {!selected ? (
            <div className="p-6 text-xs text-herald-text-dim leading-relaxed">
              <p className="mb-2 font-medium text-herald-text">Click any event row.</p>
              <p>
                The walker queries the tier1+tier2 causal graph for upstream causes,
                then scans this node&apos;s last <span className="font-mono">{lookback}s</span> for matching instances.
                Independent events are flagged when no upstream causes fired.
              </p>
            </div>
          ) : (
            <div className="p-4 space-y-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <SeverityBadge sev={selected.severity} />
                  <span className="font-mono text-sm text-herald-text">
                    {selected.event_type ?? '(residual)'}
                  </span>
                </div>
                <div className="text-[10px] text-herald-text-dim font-mono">
                  {selected.ts} · {selected.node} · {selected.subsystem}
                </div>
                <div className="mt-2 text-xs text-herald-text-dim border-l-2 border-herald-border pl-2 break-words">
                  {selected.raw}
                </div>
              </div>

              {explainLoading && (
                <div className="text-xs text-herald-text-dim">Walking causal graph…</div>
              )}
              {explainError && (
                <div className="text-xs text-red-400 border border-red-400/40 bg-red-400/10 rounded p-2">
                  {explainError}
                </div>
              )}

              {explain && (
                <>
                  <CauseDag
                    subgraph={explain.subgraph}
                    independent={explain.independent}
                    cascadeTree={explain.cascade_tree ?? null}
                    maxDepth={explain.max_depth ?? maxDepth}
                    onCauseClick={setFocusedHop}
                    focusedEventType={focusedHop}
                  />

                  {!explain.independent && (
                    <OperatorActions
                      clicked={explain.clicked}
                      edges_with_instances={explain.edges_with_instances}
                      candidates_without_instances={explain.candidates_without_instances}
                      lookback_seconds={explain.lookback_seconds}
                    />
                  )}

                  {focusedNode ? (
                    /* Focused-hop view: messages at the DAG box the operator clicked. */
                    <div className="space-y-2">
                      <div className="flex items-center justify-between gap-3">
                        <h3 className="text-xs font-semibold text-herald-text">
                          Messages at hop
                          <span className="ml-2 font-mono text-herald-text">{focusedNode.event_type}</span>
                          <span className="ml-2 font-normal text-herald-text-dim">
                            depth {focusedNode.depth}
                            {focusedNode.tier ? ` · ${focusedNode.tier}` : ''}
                            {' · '}
                            {focusedNode.instance_count ?? focusedNode.instances?.length ?? 0} instance{(focusedNode.instance_count ?? focusedNode.instances?.length ?? 0) === 1 ? '' : 's'}
                          </span>
                        </h3>
                        <button
                          onClick={() => setFocusedHop(null)}
                          className="text-[11px] text-herald-accent hover:underline"
                        >
                          ← back to causes
                        </button>
                      </div>
                      <div className="border border-herald-border rounded bg-herald-surface px-2 py-2 space-y-1">
                        {(focusedNode.instances ?? []).map((inst, i) => (
                          <div key={i} className="text-[11px] text-herald-text-dim font-mono break-words border-l border-herald-border pl-2">
                            <span className="text-herald-muted">{inst.ts}</span>
                            {' '}
                            <span className="text-herald-text">[{inst.node}]</span>
                            {' '}
                            {inst.raw}
                          </div>
                        ))}
                        {(focusedNode.instances ?? []).length === 0 && (
                          <div className="text-[11px] text-herald-text-dim">
                            No instances captured for this hop in the current lookback window.
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (explain.edges_with_instances.length > 0 ||
                    explain.candidates_without_instances.length > 0) && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between gap-3">
                        <h3 className="text-xs font-semibold text-herald-text">
                          Causes
                          <span className="ml-2 font-normal text-herald-text-dim">
                            {explain.edges_with_instances.length} fired ·{' '}
                            {explain.candidates_without_instances.length} did not fire
                          </span>
                        </h3>
                        <label className="flex items-center gap-1.5 text-[11px] text-herald-text-dim cursor-pointer">
                          <input
                            type="checkbox"
                            checked={showAllCandidates}
                            onChange={(e) => setShowAllCandidates(e.target.checked)}
                          />
                          Show causes that did not fire
                        </label>
                      </div>

                      {/* Fired causes — collapsible, raw lines inside */}
                      {explain.edges_with_instances.map((e) => (
                        <details
                          key={`fired-${e.cause}`}
                          className="border border-herald-border rounded bg-herald-surface"
                          open
                        >
                          <summary className="cursor-pointer px-2 py-1.5 text-xs font-mono text-herald-text flex items-center gap-2">
                            <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400" />
                            <span>{e.cause}</span>
                            <span className="text-herald-text-dim">×{e.instance_count}</span>
                            <span className="ml-auto text-[10px] text-herald-text-dim">{e.tier}</span>
                          </summary>
                          <div className="px-2 pb-2 space-y-1">
                            {e.instances.map((inst, i) => (
                              <div key={i} className="text-[11px] text-herald-text-dim font-mono break-words border-l border-herald-border pl-2">
                                <span className="text-herald-muted">{inst.ts}</span>
                                {' '}
                                <span className="text-herald-text">[{inst.node}]</span>
                                {' '}
                                {inst.raw}
                              </div>
                            ))}
                          </div>
                        </details>
                      ))}

                      {/* Did-not-fire causes — flat rows, hidden behind toggle */}
                      {showAllCandidates && explain.candidates_without_instances.map((c) => (
                        <div
                          key={`unfired-${c.cause}`}
                          className="border border-herald-border/50 rounded bg-herald-bg px-2 py-1.5 text-xs font-mono text-herald-text-dim flex items-center gap-2 opacity-70"
                        >
                          <span className="inline-block w-1.5 h-1.5 rounded-full bg-herald-muted" />
                          <span>{c.cause}</span>
                          <span className="text-herald-muted text-[10px]">did not fire</span>
                          <span className="ml-auto text-[10px]">{c.tier}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

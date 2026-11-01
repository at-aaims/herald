'use client'

/**
 * OperatorActions — renders the LLM-generated operator advisory.
 *
 * Called after the DAG renders so the UI shows the cause subgraph fast and
 * the LLM result streams in below. Cached responses come back ~instantly;
 * fresh ones take a model round-trip.
 */

import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

type ExplainEdge = {
  cause: string
  effect: string
  tier: string
  num_methods: number
  detected_by: string[]
  instance_count: number
  instances: Array<{ ts: string; node: string; raw: string; severity: string }>
}

type Props = {
  clicked: { event_type: string; node: string; ts: string }
  edges_with_instances: ExplainEdge[]
  candidates_without_instances: Array<{ cause: string; tier: string; num_methods: number }>
  lookback_seconds: number
}

type ActionsResponse = {
  actions?: string
  cached?: boolean
  model?: string
  error?: string
}

// Turn a raw backend/model error into a calm, operator-friendly line. The
// cascade + causes above don't need the LLM, so we frame this as "advisory
// unavailable", not a hard failure.
function friendlyError(raw: string): string {
  const s = raw.toLowerCase()
  if (s.includes('public access is disabled') || s.includes('private endpoint') || s.includes('403'))
    return 'Advisory model unreachable — endpoint access is blocked (check the VPN / private endpoint).'
  if (s.includes('502') || s.includes('modelhttperror') || s.includes('timeout') ||
      s.includes('connection') || s.includes('connect'))
    return 'Advisory model is currently unreachable. The cascade and causes above are unaffected.'
  return 'Could not generate the operator advisory.'
}

export default function OperatorActions(props: Props) {
  const [data, setData] = useState<ActionsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  // Re-fetch when the cause set or clicked event changes.
  const cacheTag = [
    props.clicked.event_type,
    ...props.edges_with_instances.map((e) => e.cause).sort(),
    props.lookback_seconds,
  ].join('|')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setData(null)
    fetch('/api/syslog/actions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        clicked: props.clicked,
        edges_with_instances: props.edges_with_instances,
        candidates_without_instances: props.candidates_without_instances,
        lookback_seconds: props.lookback_seconds,
      }),
    })
      .then(async (res) => {
        const body = await res.json().catch(() => ({}))
        if (cancelled) return
        if (!res.ok) {
          setError(body?.error ?? `HTTP ${res.status}`)
        } else {
          setData(body as ActionsResponse)
        }
      })
      .catch((err) => {
        if (!cancelled) setError(String(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheTag, reloadKey])

  // Status hint shown alongside the title so the operator can tell, without
  // expanding, whether the advisory is ready / cached / errored / still loading.
  const status = error
    ? 'error'
    : loading
      ? '…'
      : data?.cached
        ? 'cached'
        : data?.actions
          ? 'fresh'
          : ''

  return (
    <details className="group border border-herald-border rounded bg-herald-surface">
      <summary
        className="flex items-center justify-between px-3 py-1.5 cursor-pointer list-none select-none [&::-webkit-details-marker]:hidden"
        title="Click to expand the LLM-generated diagnosis and operator actions."
      >
        <span className="text-xs font-semibold text-herald-text flex items-center gap-2">
          <span className="text-herald-text-dim transition-transform group-open:rotate-90 inline-block w-2">
            ▸
          </span>
          Operator advisory
        </span>
        <span className="text-[10px] text-herald-text-dim font-mono flex items-center gap-2">
          {error && <span className="text-red-400">{status}</span>}
          {!error && status && <span>{status}</span>}
          {data?.model && <span>{data.model}</span>}
        </span>
      </summary>
      <div className="p-3 text-xs text-herald-text border-t border-herald-border">
        {loading && <p className="text-herald-text-dim">Generating recommendation…</p>}
        {error && (
          <div className="border border-herald-border bg-herald-bg rounded p-2 space-y-1.5">
            <p className="text-amber-400">{friendlyError(error)}</p>
            <p className="text-[10px] text-herald-muted font-mono break-words">{error}</p>
            <button
              onClick={() => setReloadKey((k) => k + 1)}
              className="text-[11px] text-herald-accent hover:underline"
            >
              Retry
            </button>
          </div>
        )}
        {data?.actions && (
          <div className="prose prose-invert prose-sm max-w-none syslog-actions">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.actions}</ReactMarkdown>
          </div>
        )}
      </div>
    </details>
  )
}

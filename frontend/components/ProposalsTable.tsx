'use client'

/**
 * ProposalsTable — pending LLM-proposed regex extensions for human review.
 *
 * Pulls /api/syslog/proposals on mount. Each row can be expanded for full
 * details. Approve appends to the extension JSONL (server restart picks
 * it up). Reject appends to the rejected JSONL so the proposal stops
 * appearing here even after future proposer runs that re-emit it.
 */

import { useCallback, useEffect, useState } from 'react'

type Proposal = {
  key: string
  file: string
  index: number
  template: string
  representative_samples: string[]
  frequency: number
  proposed_event_type: string
  proposed_regex: string
  subsystem: string
  severity: string
  description: string
  is_new_label: boolean
  rationale: string
  ignorecase: boolean
  proposer_generated_at?: string
  proposer_model?: string
}

type Summary = {
  pending: number
  approved_total: number
  rejected_total: number
  proposal_files: string[]
}

const SEVERITY_STYLE: Record<string, string> = {
  critical: 'text-red-400 border-red-400/40 bg-red-400/10',
  error: 'text-orange-400 border-orange-400/40 bg-orange-400/10',
  warning: 'text-yellow-400 border-yellow-400/30 bg-yellow-400/10',
  info: 'text-herald-text-dim border-herald-border bg-herald-surface',
}

function Sev({ s }: { s: string }) {
  const cls = SEVERITY_STYLE[s] ?? SEVERITY_STYLE.info
  return (
    <span className={`text-[10px] font-mono uppercase tracking-wider border rounded px-1 py-0.5 ${cls}`}>
      {s}
    </span>
  )
}

export default function ProposalsTable() {
  const [pending, setPending] = useState<Proposal[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [restartHint, setRestartHint] = useState<boolean>(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await fetch('/api/syslog/proposals')
      if (!r.ok) throw new Error(`${r.status}`)
      const data = await r.json()
      setPending(data.pending ?? [])
      setSummary(data.summary ?? null)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const action = useCallback(
    async (kind: 'approve' | 'reject', p: Proposal) => {
      setBusyKey(p.key)
      try {
        const body: Record<string, unknown> = { file: p.file, index: p.index }
        if (kind === 'reject') body.reason = null
        const r = await fetch(`/api/syslog/proposals/${kind}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        if (!r.ok) {
          const err = await r.text()
          throw new Error(`${r.status} ${err}`)
        }
        if (kind === 'approve') setRestartHint(true)
        await refresh()
      } catch (e) {
        setError(String(e))
      } finally {
        setBusyKey(null)
      }
    },
    [refresh],
  )

  return (
    <div className="flex flex-col h-full">
      {/* Top stats strip */}
      <div className="flex items-center gap-4 px-4 py-2 border-b border-herald-border bg-herald-surface text-xs text-herald-text-dim">
        <span className="text-herald-text font-medium">{summary?.pending ?? 0} pending</span>
        <span>{summary?.approved_total ?? 0} approved · {summary?.rejected_total ?? 0} rejected</span>
        <span className="text-herald-muted">|</span>
        <span>files: {summary?.proposal_files?.length ?? 0}</span>
        <div className="flex-1" />
        <button
          onClick={refresh}
          className="px-2 py-1 rounded border border-herald-border hover:bg-herald-bg"
        >
          Refresh
        </button>
      </div>

      {restartHint && (
        <div className="px-4 py-2 bg-emerald-400/10 border-b border-emerald-400/40 text-xs text-emerald-300">
          Approval recorded. <strong>Restart the API</strong> (Ctrl-C make api, then make api)
          for the new pattern to take effect in the live classifier.
        </div>
      )}

      {error && (
        <div className="px-4 py-2 bg-red-400/10 border-b border-red-400/40 text-xs text-red-300 break-all">
          {error}
        </div>
      )}

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {loading && (
          <div className="p-6 text-xs text-herald-text-dim">Loading proposals…</div>
        )}
        {!loading && pending.length === 0 && !error && (
          <div className="p-6 text-xs text-herald-text-dim leading-relaxed">
            <p className="mb-2 font-medium text-herald-text">No pending proposals.</p>
            <p>
              Run <code className="font-mono text-herald-text">.venv/bin/python scripts/propose_patterns.py</code>
              {' '}to generate a new batch from accumulated residuals. Approved entries are at
              {' '}<code className="font-mono">.data/syslog_patterns_extension.jsonl</code>;
              {' '}rejected at <code className="font-mono">.data/syslog_proposals_rejected.jsonl</code>.
            </p>
          </div>
        )}
        {pending.map((p) => {
          const isExpanded = expanded === p.key
          const isBusy = busyKey === p.key
          return (
            <div
              key={p.key}
              className="border-b border-herald-border/40 px-4 py-3 hover:bg-herald-surface"
            >
              <div className="flex items-start gap-3 text-xs">
                <button
                  onClick={() => setExpanded(isExpanded ? null : p.key)}
                  className="text-herald-text-dim hover:text-herald-text font-mono mt-0.5 w-4"
                  aria-label={isExpanded ? 'collapse' : 'expand'}
                >
                  {isExpanded ? '▾' : '▸'}
                </button>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <Sev s={p.severity} />
                    <span className="font-mono text-sm text-herald-text">{p.proposed_event_type}</span>
                    <span className="text-herald-text-dim">×{p.frequency}</span>
                    {p.is_new_label && (
                      <span className="text-[10px] uppercase tracking-wider text-violet-400 border border-violet-400/30 rounded px-1 py-0.5">
                        new label
                      </span>
                    )}
                    <span className="text-[10px] text-herald-muted ml-auto">
                      {p.proposer_model ?? ''} · {p.file}
                    </span>
                  </div>
                  <div className="text-herald-text-dim font-mono break-words mb-1">
                    template: {p.template}
                  </div>
                  <div className="text-herald-text-dim font-mono break-words">
                    regex: <span className="text-herald-text">{p.proposed_regex}</span>
                  </div>
                  {isExpanded && (
                    <div className="mt-2 space-y-2 border-l border-herald-border pl-3">
                      <div>
                        <div className="text-[10px] uppercase tracking-wider text-herald-muted mb-1">
                          {p.subsystem} / {p.severity} · {p.description}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase tracking-wider text-herald-muted mb-1">
                          rationale
                        </div>
                        <div className="text-herald-text-dim break-words">{p.rationale}</div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase tracking-wider text-herald-muted mb-1">
                          representative samples ({p.representative_samples.length})
                        </div>
                        <div className="space-y-0.5 font-mono text-[11px]">
                          {p.representative_samples.map((s, i) => (
                            <div key={i} className="text-herald-text-dim break-words">
                              {s}
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
                <div className="flex flex-col gap-1 flex-shrink-0">
                  <button
                    disabled={isBusy}
                    onClick={() => action('approve', p)}
                    className="px-3 py-1 rounded border border-emerald-400/40 text-emerald-400 hover:bg-emerald-400/10 disabled:opacity-40"
                  >
                    {isBusy ? '…' : 'Approve'}
                  </button>
                  <button
                    disabled={isBusy}
                    onClick={() => action('reject', p)}
                    className="px-3 py-1 rounded border border-red-400/40 text-red-400 hover:bg-red-400/10 disabled:opacity-40"
                  >
                    Reject
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

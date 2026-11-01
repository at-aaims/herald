'use client'
import { useEffect, useState } from 'react'
import AppShell from '@/components/AppShell'

type LargeType = 'anthropic' | 'openai' | 'vllm-ollama' | 'vllm-hosted'

interface Status {
  configured: boolean
  large_model_type: string | null
  large_model_name: string | null
  sub_agents_configured: boolean
}

const fieldCls =
  'w-full bg-herald-bg border border-herald-border rounded px-2.5 py-1.5 text-sm text-herald-text ' +
  'placeholder:text-herald-text-dim focus:outline-none focus:border-herald-accent/60'
const labelCls = 'block text-[11px] uppercase tracking-wider text-herald-muted mb-1'

// ── Azure OpenAI fields: resource name (the common case — matches what the
// Azure portal actually shows you: endpoint + deployment, separately) or a
// pasted full URL for anything non-standard (Gov cloud, a pinned
// api-version, a private endpoint) the simple form can't express. ──────────

interface AzureCfg {
  deployment: string
  useFullUrl: boolean
  resource: string
  fullUrl: string
  key: string
}
const emptyAzure = (deployment: string): AzureCfg =>
  ({ deployment, useFullUrl: false, resource: '', fullUrl: '', key: '' })

function azureUrl(cfg: AzureCfg, suffix: string): string {
  if (cfg.useFullUrl) return cfg.fullUrl
  return `https://${cfg.resource}.openai.azure.com/openai/deployments/${cfg.deployment}${suffix}?api-version=2025-01-01-preview`
}

function AzureFields({ cfg, onChange, suffix, keyNote }: {
  cfg: AzureCfg
  onChange: (cfg: AzureCfg) => void
  suffix: string
  keyNote?: string
}) {
  const set = (patch: Partial<AzureCfg>) => onChange({ ...cfg, ...patch })
  return (
    <div className="grid grid-cols-2 gap-2">
      <div>
        <label className={labelCls}>Deployment name</label>
        <input value={cfg.deployment} onChange={(e) => set({ deployment: e.target.value })} className={fieldCls} />
      </div>
      <div className="flex items-end pb-2">
        <label className="flex items-center gap-1.5 text-xs text-herald-text-dim cursor-pointer">
          <input type="checkbox" checked={cfg.useFullUrl} onChange={(e) => set({ useFullUrl: e.target.checked })} />
          Paste full URL instead
        </label>
      </div>
      {cfg.useFullUrl ? (
        <div className="col-span-2">
          <label className={labelCls}>Full endpoint URL</label>
          <input
            value={cfg.fullUrl}
            onChange={(e) => set({ fullUrl: e.target.value })}
            className={fieldCls}
            placeholder="https://<resource>.openai.azure.com/openai/deployments/<deployment>...?api-version=..."
          />
        </div>
      ) : (
        <div className="col-span-2">
          <label className={labelCls}>Azure resource name</label>
          <input
            value={cfg.resource}
            onChange={(e) => set({ resource: e.target.value })}
            className={fieldCls}
            placeholder="the <x> in https://<x>.openai.azure.com"
          />
          {/* Catches pasting a full URL here by mistake -- the template below
              wraps it in ANOTHER https://…azure.com/…, producing a doubled,
              unreachable URL that only ever surfaces later as a cryptic
              "Connection error" with no indication why. */}
          {/[:/]/.test(cfg.resource) && (
            <p className="text-xs text-amber-300 mt-1">
              This looks like a full URL, not just the resource name (the bare
              &lt;x&gt; in https://&lt;x&gt;.openai.azure.com — no https://, dots, or
              slashes). Either remove everything but that part, or check
              &quot;Paste full URL instead&quot; above and put the full URL there.
            </p>
          )}
        </div>
      )}
      <div className="col-span-2">
        <label className={labelCls}>Azure OpenAI key</label>
        <input type="password" value={cfg.key} onChange={(e) => set({ key: e.target.value })} className={fieldCls} />
        {keyNote && <p className="text-xs text-herald-text-dim mt-1">{keyNote}</p>}
      </div>
    </div>
  )
}

// ── One sub-agent slot (RAG+jobpred, or SQL): Azure or local vLLM/Ollama. ──

interface SubSlot {
  type: 'openai' | 'vllm'
  azure: AzureCfg
  localName: string
  localUrl: string
}
const emptySubSlot = (): SubSlot =>
  ({ type: 'openai', azure: emptyAzure('gpt-4o'), localName: 'llama3.1:8b', localUrl: 'http://localhost:11434/v1' })

function subModelPayload(slot: SubSlot) {
  if (slot.type === 'openai') {
    return { type: 'openai', name: slot.azure.deployment, url: azureUrl(slot.azure, '/chat/completions'), key: slot.azure.key }
  }
  return { type: 'vllm', name: slot.localName, url: slot.localUrl }
}

function SubAgentFields({ slot, onChange, idPrefix }: {
  slot: SubSlot
  onChange: (s: SubSlot) => void
  idPrefix: string
}) {
  const set = (patch: Partial<SubSlot>) => onChange({ ...slot, ...patch })
  return (
    <div className="space-y-2">
      <div className="flex gap-3">
        <label className="flex items-center gap-1.5 text-sm text-herald-text">
          <input type="radio" name={`${idPrefix}-type`} checked={slot.type === 'openai'} onChange={() => set({ type: 'openai' })} />
          Azure OpenAI
        </label>
        <label className="flex items-center gap-1.5 text-sm text-herald-text">
          <input type="radio" name={`${idPrefix}-type`} checked={slot.type === 'vllm'} onChange={() => set({ type: 'vllm' })} />
          Local vLLM/Ollama
        </label>
      </div>
      {slot.type === 'openai' ? (
        <AzureFields cfg={slot.azure} onChange={(azure) => set({ azure })} suffix="/chat/completions" />
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className={labelCls}>Model name</label>
            <input value={slot.localName} onChange={(e) => set({ localName: e.target.value })} className={fieldCls} />
          </div>
          <div>
            <label className={labelCls}>Server URL</label>
            <input value={slot.localUrl} onChange={(e) => set({ localUrl: e.target.value })} className={fieldCls} />
          </div>
        </div>
      )}
    </div>
  )
}

export default function SetupPage() {
  const [status, setStatus] = useState<Status | null>(null)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // True once a /api/setup/status attempt has failed (backend not reachable
  // yet — most commonly first boot, still downloading RAG's ML models before
  // it can respond to anything at all). Distinct from status===null's plain
  // "Loading…", which otherwise looks identical to a page that's just plain
  // broken, with no indication anything is happening or will resolve itself.
  const [backendUnreachable, setBackendUnreachable] = useState(false)

  // Orchestrator fields
  const [largeType, setLargeType] = useState<LargeType>('anthropic')
  const [anthropicKey, setAnthropicKey] = useState('')
  const [largeAzure, setLargeAzure] = useState<AzureCfg>(emptyAzure('gpt-5.5'))
  const [ollamaModel, setOllamaModel] = useState('llama3.1:8b')
  const [vllmName, setVllmName] = useState('Hermes-4-70B')
  const [vllmUrl, setVllmUrl] = useState('http://localhost:8082/v1')

  // Sub-agent fields (SQL / RAG / job prediction) — independent by design
  // (e.g. SQLcoder-8B for SQL vs. a general chat model for RAG/jobpred is a
  // real, intentional combination), defaulting to "same" since that's the
  // common case and the simpler path.
  const [configureSubAgents, setConfigureSubAgents] = useState(false)
  const [sameSubModel, setSameSubModel] = useState(true)
  const [ragSlot, setRagSlot] = useState<SubSlot>(emptySubSlot())
  const [sqlSlot, setSqlSlot] = useState<SubSlot>(emptySubSlot())

  useEffect(() => {
    let cancelled = false
    const poll = () => {
      fetch('/api/setup/status')
        .then((r) => {
          if (!r.ok) throw new Error(`status ${r.status}`)
          return r.json()
        })
        .then((s: Status) => {
          if (cancelled) return
          setStatus(s)
          setEditing(!s.configured)
          setBackendUnreachable(false)
        })
        .catch(() => {
          // Backend not up yet (most commonly: first boot, still downloading
          // RAG's models before the server can respond at all). Keep retrying
          // instead of giving up after one attempt — the alternative is a
          // page that renders its title/subtitle and then silently nothing
          // else forever, with no indication it'll ever resolve itself.
          if (cancelled) return
          setBackendUnreachable(true)
          setTimeout(poll, 3000)
        })
    }
    poll()
    return () => { cancelled = true }
  }, [])

  const submit = async () => {
    setSaving(true)
    setError(null)
    try {
      const body: Record<string, unknown> = { configure_sub_agents: configureSubAgents }

      if (largeType === 'anthropic') {
        body.large_model_type = 'anthropic'
        body.large_model_name = 'claude-opus-4-7'
        body.large_model_key = anthropicKey
      } else if (largeType === 'openai') {
        body.large_model_type = 'openai'
        body.large_model_name = largeAzure.deployment
        body.large_model_url = azureUrl(largeAzure, '')
        body.large_model_key = largeAzure.key
      } else if (largeType === 'vllm-ollama') {
        body.large_model_type = 'vllm'
        body.large_model_name = ollamaModel
        body.large_model_url = 'http://localhost:11434/v1'
      } else {
        body.large_model_type = 'vllm'
        body.large_model_name = vllmName
        body.large_model_url = vllmUrl
      }

      if (configureSubAgents) {
        body.small_model = subModelPayload(ragSlot)
        body.sql_model = sameSubModel ? subModelPayload(ragSlot) : subModelPayload(sqlSlot)
      }

      const res = await fetch('/api/setup/configure', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(await res.text())
      setSaved(true)
      setEditing(false)
      fetch('/api/setup/status').then((r) => r.json()).then(setStatus)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  if (status === null) {
    return (
      <AppShell title="Setup">
        <div className="max-w-xl mx-auto p-6 text-sm">
          {backendUnreachable ? (
            <div className="border border-herald-border rounded-lg p-4 bg-herald-surface space-y-2">
              <p className="text-herald-text font-medium">HERALD&apos;s backend is still starting up…</p>
              <p className="text-herald-text-dim">
                On first run, it downloads a few GB of ML models for documentation
                search before it can respond to anything — this can take a couple
                of minutes up to ~20 minutes depending on your network. Every run
                after this one is fast (seconds), since the models are cached.
              </p>
              <p className="text-herald-text-dim">This page is retrying automatically — no need to refresh.</p>
            </div>
          ) : (
            <p className="text-herald-text-dim">Loading…</p>
          )}
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell title="Setup">
      <div className="max-w-xl mx-auto p-6 space-y-6 overflow-y-auto h-full">
        <div>
          <h1 className="text-lg font-bold text-herald-text">HERALD setup</h1>
          <p className="text-sm text-herald-text-dim mt-1">
            Pick a model backend — no .env editing, takes effect immediately, no restart.
          </p>
        </div>

        {!editing && status.configured && (
          <div className="border border-herald-border rounded-lg p-4 bg-herald-surface space-y-3">
            <p className="text-sm text-herald-text">
              Configured: <span className="font-mono text-herald-accent">{status.large_model_type}</span> /{' '}
              <span className="font-mono">{status.large_model_name}</span>
            </p>
            <p className="text-sm text-herald-text-dim">
              Sub-agents (SQL/RAG/job prediction): {status.sub_agents_configured ? 'configured' : 'not configured'}
            </p>
            <button
              onClick={() => { setEditing(true); setSaved(false) }}
              className="text-sm px-3 py-1.5 rounded border border-herald-border text-herald-text hover:border-herald-accent/60"
            >
              Reconfigure
            </button>
          </div>
        )}

        {saved && !editing && (
          <div className="border border-emerald-500/40 bg-emerald-500/10 rounded-lg p-3 text-sm text-emerald-300">
            Saved — try the <a href="/" className="underline">chat</a> now, no restart needed.
          </div>
        )}

        {editing && (
          <div className="space-y-5">
            <section className="space-y-3">
              <p className="text-sm font-semibold text-herald-text">Orchestrator model (the one you chat with)</p>

              <div className="space-y-2">
                {([
                  ['anthropic', 'Anthropic Claude', 'Simplest, no GPU'],
                  ['openai', 'Azure OpenAI', 'Needs a resource (or full URL) + deployment + key'],
                  ['vllm-ollama', 'Local Ollama', 'Free, needs Ollama running'],
                  ['vllm-hosted', 'Self-hosted vLLM', 'Needs a running vLLM server'],
                ] as [LargeType, string, string][]).map(([val, label, hint]) => (
                  <label
                    key={val}
                    className={`flex items-start gap-2.5 p-2.5 rounded border cursor-pointer ${
                      largeType === val ? 'border-herald-accent/60 bg-herald-accent/5' : 'border-herald-border'
                    }`}
                  >
                    <input
                      type="radio"
                      name="largeType"
                      checked={largeType === val}
                      onChange={() => setLargeType(val)}
                      className="mt-0.5"
                    />
                    <span>
                      <span className="block text-sm text-herald-text">{label}</span>
                      <span className="block text-xs text-herald-text-dim">{hint}</span>
                    </span>
                  </label>
                ))}
              </div>

              {largeType === 'anthropic' && (
                <div>
                  <label className={labelCls}>Anthropic API key</label>
                  <input type="password" value={anthropicKey} onChange={(e) => setAnthropicKey(e.target.value)} className={fieldCls} placeholder="sk-ant-…" />
                </div>
              )}

              {largeType === 'openai' && (
                <AzureFields cfg={largeAzure} onChange={setLargeAzure} suffix="" />
              )}

              {largeType === 'vllm-ollama' && (
                <div>
                  <label className={labelCls}>Ollama model tag</label>
                  <input value={ollamaModel} onChange={(e) => setOllamaModel(e.target.value)} className={fieldCls} />
                  <p className="text-xs text-herald-text-dim mt-1">Make sure you&apos;ve run: ollama pull {ollamaModel}</p>
                </div>
              )}

              {largeType === 'vllm-hosted' && (
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className={labelCls}>Served model name</label>
                    <input value={vllmName} onChange={(e) => setVllmName(e.target.value)} className={fieldCls} />
                  </div>
                  <div>
                    <label className={labelCls}>vLLM server URL</label>
                    <input value={vllmUrl} onChange={(e) => setVllmUrl(e.target.value)} className={fieldCls} />
                  </div>
                </div>
              )}
            </section>

            <section className="space-y-3 border-t border-herald-border pt-4">
              <label className="flex items-center gap-2.5 cursor-pointer">
                <input type="checkbox" checked={configureSubAgents} onChange={(e) => setConfigureSubAgents(e.target.checked)} />
                <span className="text-sm font-semibold text-herald-text">Configure SQL / RAG / job-prediction sub-agents</span>
              </label>
              <p className="text-xs text-herald-text-dim">
                These need a separate OpenAI-compatible endpoint (Azure or vLLM/Ollama) — Anthropic only covers the orchestrator above.
                Leave unchecked to disable these tools.
              </p>

              {configureSubAgents && (
                <div className="space-y-3 pl-1">
                  <label className="flex items-center gap-2.5 cursor-pointer">
                    <input type="checkbox" checked={sameSubModel} onChange={(e) => setSameSubModel(e.target.checked)} />
                    <span className="text-sm text-herald-text">Same model for SQL and RAG/job-prediction</span>
                  </label>
                  <p className="text-xs text-herald-text-dim">
                    Uncheck for e.g. a specialized text-to-SQL model (SQLcoder-8B) alongside a general chat model for RAG/job-prediction.
                  </p>

                  {sameSubModel ? (
                    <SubAgentFields slot={ragSlot} onChange={setRagSlot} idPrefix="shared" />
                  ) : (
                    <>
                      <p className="text-xs font-semibold text-herald-muted uppercase tracking-wider pt-1">RAG + job-prediction</p>
                      <SubAgentFields slot={ragSlot} onChange={setRagSlot} idPrefix="rag" />
                      <p className="text-xs font-semibold text-herald-muted uppercase tracking-wider pt-2">SQL</p>
                      <SubAgentFields slot={sqlSlot} onChange={setSqlSlot} idPrefix="sql" />
                    </>
                  )}
                </div>
              )}
            </section>

            {error && (
              <div className="border border-red-500/40 bg-red-500/10 rounded p-2.5 text-sm text-red-300">{error}</div>
            )}

            <div className="flex gap-2">
              <button
                onClick={submit}
                disabled={saving}
                className="px-4 py-2 rounded bg-herald-accent hover:bg-herald-accent-hover text-white text-sm font-medium disabled:opacity-50"
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
              {status.configured && (
                <button
                  onClick={() => setEditing(false)}
                  className="px-4 py-2 rounded border border-herald-border text-herald-text-dim hover:text-herald-text text-sm"
                >
                  Cancel
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  )
}

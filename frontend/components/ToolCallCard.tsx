'use client'
import { useEffect, useState } from 'react'
import { TOOL_COLORS, TOOL_LABELS, TOOL_REGISTRY_NAME } from '@/lib/tools'
import SqlResultTable from './SqlResultTable'
import PlotlyChart from './PlotlyChart'

/**
 * In AI SDK v5, tool invocations arrive as message parts with shape:
 *   {
 *     type: `tool-${toolName}`,
 *     state: 'input-streaming' | 'input-available' | 'output-available' | 'output-error',
 *     input?: unknown,
 *     output?: unknown,
 *     errorText?: string,
 *     toolCallId: string,
 *   }
 */
interface ToolPart {
  type: string
  state: 'input-streaming' | 'input-available' | 'output-available' | 'output-error'
  input?: unknown
  output?: unknown
  errorText?: string
  toolCallId?: string
}

interface Props {
  part: ToolPart
}

export default function ToolCallCard({ part }: Props) {
  const [expanded, setExpanded] = useState(false)

  const toolName = part.type.replace(/^tool-/, '')
  const registryName = TOOL_REGISTRY_NAME[toolName] ?? ''
  const color = TOOL_COLORS[registryName] ?? 'text-herald-text border-herald-border bg-herald-border/10'
  const label = TOOL_LABELS[toolName] ?? toolName

  const isRunning = part.state === 'input-streaming' || part.state === 'input-available'
  const isError = part.state === 'output-error'
  const isDone = part.state === 'output-available'

  // The tool returns a JSON string; parse for structured rendering
  let parsed: Record<string, any> | null = null
  if (isDone && typeof part.output === 'string') {
    try { parsed = JSON.parse(part.output) } catch { /* render raw */ }
  } else if (isDone && typeof part.output === 'object' && part.output !== null) {
    parsed = part.output as Record<string, any>
  }

  const slimSqlRows = parsed?.query_result as Record<string, unknown>[] | undefined
  const fullToken = parsed?.full_result_token as string | undefined
  const truncated = !!parsed?.truncated

  // When the tool result is truncated for the LLM, fetch the full rows from
  // the backend side-channel so the chart can plot everything.
  const [fullRows, setFullRows] = useState<Record<string, unknown>[] | null>(null)
  useEffect(() => {
    if (!fullToken || !truncated) return
    let cancelled = false
    fetch(`/api/sql-result/${fullToken}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d?.query_result && !cancelled) setFullRows(d.query_result) })
      .catch(() => { /* fall back to slim rows */ })
    return () => { cancelled = true }
  }, [fullToken, truncated])

  const sqlRows = fullRows ?? slimSqlRows
  const hasSqlResult = Array.isArray(sqlRows) && sqlRows.length > 0
  const predResults = parsed?.results as Record<string, unknown>[] | undefined
  const hasPredResult = Array.isArray(predResults) && predResults.length > 0
  const ragImages = parsed?.images as { url: string; caption?: string; distance?: number }[] | undefined
  const hasImages = Array.isArray(ragImages) && ragImages.length > 0
  const ragSources = parsed?.sources as { title: string; source?: string }[] | undefined
  const hasSources = Array.isArray(ragSources) && ragSources.length > 0
  const ragContext = parsed?.context as { text: string; source?: string }[] | undefined
  const hasContext = Array.isArray(ragContext) && ragContext.length > 0
  const hasError = isError || !!parsed?.error

  return (
    <div className={`rounded-lg border text-xs my-2 overflow-hidden ${color}`}>
      <button
        onClick={() => !isRunning && setExpanded((v) => !v)}
        disabled={isRunning}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:opacity-80 transition-opacity"
      >
        <span
          className={[
            'w-1.5 h-1.5 rounded-full flex-shrink-0',
            isRunning ? 'bg-current animate-pulse' : hasError ? 'bg-red-400' : 'bg-current',
          ].join(' ')}
        />

        <span className="font-medium">{label}</span>

        {isRunning && <span className="text-herald-muted ml-1">running…</span>}
        {hasError && <span className="text-red-400 ml-1">failed</span>}
        {isDone && hasSqlResult && (
          <span className="text-herald-muted ml-1">
            {(parsed!.row_count as number)?.toLocaleString() ?? sqlRows!.length} rows
          </span>
        )}

        {isDone && hasContext && (
          <span className="text-herald-muted ml-1">{ragContext!.length} passage{ragContext!.length === 1 ? '' : 's'}</span>
        )}

        {isDone && hasImages && (
          <span className="text-herald-muted ml-1">{ragImages!.length} image{ragImages!.length === 1 ? '' : 's'}</span>
        )}

        {!isRunning && (
          <span className="ml-auto text-herald-muted">{expanded ? '▲' : '▼'}</span>
        )}
      </button>

      {/* Relevant images — always visible (not gated by expand) so they read as
          part of the answer. Click to open the full-size image. */}
      {isDone && hasImages && (
        <div className="px-3 pb-3 pt-2 flex flex-wrap gap-3 border-t border-current/20">
          {ragImages!.map((img, i) => (
            <a
              key={i}
              href={img.url}
              target="_blank"
              rel="noreferrer"
              title={img.caption ?? 'open image'}
              className="block"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={img.url}
                alt={img.caption ?? 'related image'}
                className="h-28 rounded border border-herald-border object-cover hover:opacity-90 transition-opacity"
              />
              {img.caption && (
                <div className="text-[10px] text-herald-text-dim mt-0.5 max-w-[180px] truncate">
                  {img.caption}
                </div>
              )}
            </a>
          ))}
        </div>
      )}

      {/* Citations — which source documents the answer drew from. */}
      {isDone && hasSources && (
        <div className="px-3 pb-2 pt-2 text-[10px] text-herald-text-dim border-t border-current/20">
          <span className="uppercase tracking-wider">Sources:</span>{' '}
          <span className="text-herald-text">{ragSources!.map((s) => s.title).join(' · ')}</span>
        </div>
      )}

      {expanded && !isRunning && (
        <div className="px-3 pb-3 border-t border-current/20">
          {hasError && (
            <p className="mt-2 text-red-400 font-mono">
              {String(parsed?.error ?? part.errorText ?? 'Unknown error')}
            </p>
          )}

          {hasSqlResult && (
            <>
              <SqlResultTable
                query={String(parsed!.query ?? '')}
                rows={sqlRows!}
                rowCount={(parsed!.row_count as number) ?? sqlRows!.length}
                truncated={!!parsed!.truncated}
              />
              <PlotlyChart rows={sqlRows!} />
            </>
          )}

          {hasPredResult && (
            <SqlResultTable
              query=""
              rows={predResults!.map((r: any) => ({ ...r, ...(r.prediction ?? {}) }))}
              rowCount={predResults!.length}
              truncated={false}
            />
          )}

          {isDone && !hasSqlResult && !hasPredResult && !hasError && (
            <pre className="mt-2 text-herald-text-dim font-mono whitespace-pre-wrap text-xs max-h-48 overflow-y-auto scroll-area">
              {typeof part.output === 'string'
                ? part.output
                : JSON.stringify(part.output, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

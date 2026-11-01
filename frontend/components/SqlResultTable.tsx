'use client'
import { useState } from 'react'

interface Props {
  query: string
  rows: Record<string, unknown>[]
  rowCount: number
  truncated: boolean
}

export default function SqlResultTable({ query, rows, rowCount, truncated }: Props) {
  const [showQuery, setShowQuery] = useState(false)
  if (!rows.length) return null
  const columns = Object.keys(rows[0])

  return (
    <div className="mt-3 rounded-lg border border-herald-border overflow-hidden text-xs">
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-2 bg-herald-surface border-b border-herald-border">
        <span className="text-tool-sql font-medium">
          SQL result — {rowCount.toLocaleString()} row{rowCount !== 1 ? 's' : ''}
          {truncated && <span className="ml-1 text-herald-muted">(showing first {rows.length})</span>}
        </span>
        <button
          onClick={() => setShowQuery((v) => !v)}
          className="text-herald-muted hover:text-herald-text transition-colors"
        >
          {showQuery ? 'hide query' : 'show query'}
        </button>
      </div>

      {/* SQL query */}
      {showQuery && (
        <pre className="px-3 py-2 bg-herald-bg border-b border-herald-border font-mono text-xs text-blue-300 overflow-x-auto whitespace-pre-wrap">
          {query}
        </pre>
      )}

      {/* Table */}
      <div className="overflow-x-auto max-h-72 scroll-area">
        <table className="w-full text-left">
          <thead className="sticky top-0 bg-herald-surface">
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  className="px-3 py-2 font-medium text-herald-text-dim border-b border-herald-border whitespace-nowrap"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={i}
                className="border-b border-herald-border/50 hover:bg-herald-surface/60 transition-colors"
              >
                {columns.map((col) => (
                  <td key={col} className="px-3 py-1.5 text-herald-text whitespace-nowrap">
                    {String(row[col] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

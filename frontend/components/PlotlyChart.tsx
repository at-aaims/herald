'use client'
import dynamic from 'next/dynamic'
import { useMemo, useState, useEffect } from 'react'
import { ArrowLeftRight, Sliders } from 'lucide-react'

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false, loading: () => (
  <div className="h-64 flex items-center justify-center text-herald-muted text-sm">Loading chart…</div>
)})

// L3 advanced editor — lazy import to keep the default bundle lean.
const PlotlyChartAdvanced = dynamic(() => import('./PlotlyChartAdvanced'), {
  ssr: false,
  loading: () => (
    <div className="h-[400px] flex items-center justify-center text-herald-muted text-sm">
      Loading advanced editor…
    </div>
  ),
})

interface Props {
  rows: Record<string, unknown>[]
}

type ChartType = 'bar' | 'line' | 'scatter' | 'pie'
type Agg = 'sum' | 'mean' | 'count' | 'none'

function isNumericCol(rows: Record<string, unknown>[], col: string): boolean {
  for (const r of rows) {
    const v = r[col]
    if (v === null || v === undefined || v === '') continue
    return typeof v === 'number' || (typeof v === 'string' && !isNaN(Number(v)))
  }
  return false
}

function coerceCell(v: unknown): string | number {
  if (typeof v === 'number') return v
  if (typeof v === 'string' && v !== '' && !isNaN(Number(v))) return Number(v)
  return String(v ?? '')
}

function aggregate(rows: Record<string, unknown>[], xCol: string, yCol: string, agg: Agg): { x: (string | number)[]; y: (string | number)[] } {
  if (agg === 'none') {
    return {
      x: rows.map((r) => coerceCell(r[xCol])),
      y: rows.map((r) => coerceCell(r[yCol])),
    }
  }
  const groups = new Map<string, number[]>()
  for (const r of rows) {
    const key = String(r[xCol])
    const val = Number(r[yCol])
    if (!groups.has(key)) groups.set(key, [])
    if (!isNaN(val)) groups.get(key)!.push(val)
  }
  const x: string[] = []
  const y: number[] = []
  for (const [k, vals] of groups) {
    x.push(k)
    if (agg === 'count') y.push(vals.length)
    else if (agg === 'sum') y.push(vals.reduce((a, b) => a + b, 0))
    else if (agg === 'mean') y.push(vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0)
  }
  return { x, y }
}

export default function PlotlyChart({ rows }: Props) {
  const cols = useMemo(() => (rows.length ? Object.keys(rows[0]) : []), [rows])

  // Default picks: first string col on X, first numeric col on Y (matches old heuristic)
  const defaultX = useMemo(
    () => cols.find((c) => !isNumericCol(rows, c)) ?? cols[0] ?? '',
    [cols, rows],
  )
  const defaultY = useMemo(
    () => cols.find((c) => isNumericCol(rows, c)) ?? cols[1] ?? cols[0] ?? '',
    [cols, rows],
  )

  const [xCol, setXCol] = useState(defaultX)
  const [yCol, setYCol] = useState(defaultY)
  const [chartType, setChartType] = useState<ChartType>('bar')
  const [agg, setAgg] = useState<Agg>('none')
  const [advanced, setAdvanced] = useState(false)

  // Reset axes when the underlying data shape changes
  useEffect(() => { setXCol(defaultX) }, [defaultX])
  useEffect(() => { setYCol(defaultY) }, [defaultY])

  const xIsCategory = !isNumericCol(rows, xCol)
  const effectiveAgg: Agg = xIsCategory && agg !== 'none' ? agg : 'none'

  const { data, layout } = useMemo(() => {
    if (!rows.length || !xCol || !yCol) return { data: [], layout: {} }

    const { x, y } = aggregate(rows, xCol, yCol, effectiveAgg)

    const baseLayout = {
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'transparent',
      font: { color: '#e2e8f0', size: 11 },
      margin: { t: 20, r: 20, b: 50, l: 60 },
      height: 320,
      xaxis: { title: { text: xCol }, color: '#94a3b8', gridcolor: '#2a2d3a', automargin: true },
      yaxis: { title: { text: effectiveAgg === 'count' ? `count(${yCol})` : effectiveAgg === 'mean' ? `mean(${yCol})` : effectiveAgg === 'sum' ? `sum(${yCol})` : yCol }, color: '#94a3b8', gridcolor: '#2a2d3a', automargin: true },
    }

    if (chartType === 'pie') {
      return {
        data: [{
          type: 'pie' as const,
          labels: x.map(String),
          values: y,
          textinfo: 'label+percent' as const,
          marker: { colors: ['#4f8ef7', '#7c3aed', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#ec4899', '#84cc16'] },
        }],
        layout: { ...baseLayout, xaxis: undefined, yaxis: undefined },
      }
    }

    if (chartType === 'line') {
      return {
        data: [{
          type: 'scatter' as const,
          mode: 'lines+markers' as const,
          x,
          y,
          line: { color: '#4f8ef7' },
          marker: { color: '#4f8ef7', size: 6 },
        }],
        layout: baseLayout,
      }
    }

    if (chartType === 'scatter') {
      return {
        data: [{
          type: 'scatter' as const,
          mode: 'markers' as const,
          x,
          y,
          marker: { color: '#4f8ef7', size: 8 },
        }],
        layout: baseLayout,
      }
    }

    // bar — tell plotly which axis is the value axis. With orientation='h'
    // plotly treats x as values and y as categories (matches user picking a
    // numeric X column and a categorical Y column); with 'v' it's the reverse.
    const yIsNumeric = isNumericCol(rows, yCol)
    const horizontal = !xIsCategory && !yIsNumeric
    return {
      data: [{
        type: 'bar' as const,
        orientation: (horizontal ? 'h' : 'v') as 'h' | 'v',
        x,
        y,
        marker: { color: '#4f8ef7' },
      }],
      layout: baseLayout,
    }
  }, [rows, xCol, yCol, chartType, effectiveAgg, xIsCategory])

  if (!rows.length) return null

  const swap = () => {
    setXCol(yCol)
    setYCol(xCol)
  }

  const selectCls =
    'bg-herald-bg border border-herald-border rounded-md px-2 py-1 text-xs text-herald-text focus:outline-none focus:border-herald-accent'

  const tabBtn = (active: boolean) => [
    'px-2 py-1 rounded-md border text-xs transition-colors',
    active
      ? 'border-herald-accent text-herald-text bg-herald-accent/10'
      : 'border-herald-border text-herald-text-dim hover:text-herald-text hover:border-herald-accent',
  ].join(' ')

  return (
    <div className="mt-2 rounded-lg border border-herald-border overflow-hidden bg-herald-surface">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-herald-border text-xs">
        <button type="button" onClick={() => setAdvanced(false)} className={tabBtn(!advanced)}>
          Simple
        </button>
        <button
          type="button"
          onClick={() => setAdvanced(true)}
          className={tabBtn(advanced)}
          title="Full Plotly editor: multi-trace, styling, annotations, more chart types"
        >
          <span className="inline-flex items-center gap-1">
            <Sliders size={12} />
            Advanced
          </span>
        </button>
      </div>

      {advanced ? (
        <PlotlyChartAdvanced
          rows={rows}
          defaultX={defaultX}
          defaultY={defaultY}
          initialData={data as any[]}
          initialLayout={layout}
        />
      ) : (
        <>
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-herald-border text-xs">
        <label className="flex items-center gap-1 text-herald-text-dim">
          Type
          <select
            value={chartType}
            onChange={(e) => setChartType(e.target.value as ChartType)}
            className={selectCls}
          >
            <option value="bar">Bar</option>
            <option value="line">Line</option>
            <option value="scatter">Scatter</option>
            <option value="pie">Pie</option>
          </select>
        </label>

        <label className="flex items-center gap-1 text-herald-text-dim">
          {chartType === 'pie' ? 'Labels' : 'X'}
          <select value={xCol} onChange={(e) => setXCol(e.target.value)} className={selectCls}>
            {cols.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>

        <label className="flex items-center gap-1 text-herald-text-dim">
          {chartType === 'pie' ? 'Values' : 'Y'}
          <select value={yCol} onChange={(e) => setYCol(e.target.value)} className={selectCls}>
            {cols.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>

        {xIsCategory && (
          <label className="flex items-center gap-1 text-herald-text-dim">
            Agg
            <select value={agg} onChange={(e) => setAgg(e.target.value as Agg)} className={selectCls}>
              <option value="none">none</option>
              <option value="sum">sum</option>
              <option value="mean">mean</option>
              <option value="count">count</option>
            </select>
          </label>
        )}

        {chartType !== 'pie' && (
          <button
            type="button"
            onClick={swap}
            title="Swap X and Y"
            className="ml-auto flex items-center gap-1 px-2 py-1 rounded-md border border-herald-border text-herald-text-dim hover:text-herald-text hover:border-herald-accent transition-colors"
          >
            <ArrowLeftRight size={12} />
            Swap
          </button>
        )}
      </div>

      <div className="p-2" style={{ minHeight: 340 }}>
        <Plot
          data={data}
          layout={{ ...layout, autosize: true }}
          config={{
            displayModeBar: true,
            displaylogo: false,
            responsive: true,
            modeBarButtonsToRemove: ['sendDataToCloud'],
            toImageButtonOptions: { format: 'png', filename: 'herald-chart' },
          }}
          style={{ width: '100%', height: 320 }}
        />
      </div>
        </>
      )}
    </div>
  )
}

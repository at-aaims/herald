'use client'
import dynamic from 'next/dynamic'
import { useEffect, useMemo, useState } from 'react'
import { Plus, Trash2, MapPin } from 'lucide-react'

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false, loading: () => (
  <div className="h-64 flex items-center justify-center text-herald-muted text-sm">Loading chart…</div>
)})

type TraceType = 'bar' | 'line' | 'scatter' | 'pie' | 'box' | 'histogram' | 'heatmap'
type AxisType = 'auto' | 'linear' | 'log' | 'category' | 'date'

interface Trace {
  yCol: string
  type: TraceType
  color: string
  name: string
  yaxis: 'y' | 'y2'
  markerSize: number
  lineWidth: number
  opacity: number
  groupBy: string // '' = no grouping; otherwise emit one Plotly trace per distinct value
  showTotal: boolean // when grouped, also draw an aggregate line across all groups
  totalAgg: 'sum' | 'mean' | 'count'
  cumulative: boolean // running sum of y values over X
}

type BarMode = 'group' | 'stack' | 'relative' | 'overlay'
type LegendPos =
  | 'right' | 'left' | 'top' | 'bottom'
  | 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right'

interface AxisCfg {
  type: AxisType
  title: string
  tickFormat: string
  min: string
  max: string
}

interface Annotation { x: any; y: any; text: string }

interface Props {
  initialData: any[]
  initialLayout: any
  rows: Record<string, unknown>[]
  defaultX: string
  defaultY: string
}

const PALETTE = ['#4f8ef7', '#f59e0b', '#10b981', '#ef4444', '#7c3aed', '#06b6d4', '#ec4899', '#84cc16']

const emptyAxis = (title = ''): AxisCfg => ({ type: 'auto', title, tickFormat: '', min: '', max: '' })
const newTrace = (yCol: string, idx: number): Trace => ({
  yCol, type: 'bar', color: PALETTE[idx % PALETTE.length], name: yCol,
  yaxis: 'y', markerSize: 6, lineWidth: 2, opacity: 1, groupBy: '',
  showTotal: false, totalAgg: 'sum', cumulative: false,
})

// Sort xs by their natural order then turn ys into a running sum.
// Preserves the original x sequence; only transforms the y values.
function cumulate(xs: (string | number)[], ys: (string | number)[]): { xs: (string | number)[]; ys: number[] } {
  const pairs = xs.map((x, i) => ({ x, y: Number(ys[i]) || 0 }))
  pairs.sort((a, b) =>
    typeof a.x === 'number' && typeof b.x === 'number'
      ? a.x - b.x
      : String(a.x).localeCompare(String(b.x)),
  )
  let acc = 0
  return { xs: pairs.map((p) => p.x), ys: pairs.map((p) => (acc += p.y)) }
}

function coerceCell(v: unknown): string | number {
  if (typeof v === 'number') return v
  if (typeof v === 'string' && v !== '' && !isNaN(Number(v))) return Number(v)
  return String(v ?? '')
}

export default function PlotlyChartAdvanced({ rows, defaultX, defaultY }: Props) {
  const cols = rows.length ? Object.keys(rows[0]) : []
  const [xCol, setXCol] = useState(defaultX)
  const [traces, setTraces] = useState<Trace[]>([newTrace(defaultY, 0)])
  const [title, setTitle] = useState('')
  const [legend, setLegend] = useState(true)
  const [legendPos, setLegendPos] = useState<LegendPos>('right')
  const [legendCols, setLegendCols] = useState<number>(1)
  const [xAxis, setXAxis] = useState<AxisCfg>(emptyAxis(defaultX))
  const [yAxis, setYAxis] = useState<AxisCfg>(emptyAxis(defaultY))
  const [y2Axis, setY2Axis] = useState<AxisCfg>(emptyAxis(''))
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [annotMode, setAnnotMode] = useState(false)
  const [barMode, setBarMode] = useState<BarMode>('group')
  const [filterCol, setFilterCol] = useState<string>('')
  const [filterValues, setFilterValues] = useState<Set<string>>(new Set())

  // Distinct values of the filter column.
  const filterOptions = useMemo(() => {
    if (!filterCol) return [] as string[]
    const set = new Set<string>()
    for (const r of rows) set.add(String(r[filterCol] ?? ''))
    return Array.from(set).sort()
  }, [filterCol, rows])

  // Rows after applying the filter; empty filterValues = no filter.
  const filteredRows = useMemo(() => {
    if (!filterCol || filterValues.size === 0) return rows
    return rows.filter((r) => filterValues.has(String(r[filterCol] ?? '')))
  }, [rows, filterCol, filterValues])

  // Reset selection when the filter column changes
  useEffect(() => { setFilterValues(new Set()) }, [filterCol])

  const updateTrace = (i: number, patch: Partial<Trace>) =>
    setTraces((ts) => ts.map((t, j) => (j === i ? { ...t, ...patch } : t)))
  const addTrace = () => {
    const used = new Set(traces.map((t) => t.yCol))
    const next = cols.find((c) => !used.has(c) && c !== xCol) ?? cols[0]
    setTraces((ts) => [...ts, newTrace(next, ts.length)])
  }
  const removeTrace = (i: number) => setTraces((ts) => ts.filter((_, j) => j !== i))

  const usesY2 = traces.some((t) => t.yaxis === 'y2')

  const { data, layout } = useMemo(() => {
    if (!filteredRows.length) return { data: [], layout: {} }

    // Build the set of "sub-traces" each Trace produces. Without groupBy it's
    // a single sub-trace over all filtered rows; with groupBy we partition
    // rows by the chosen column and emit one sub-trace per distinct value.
    type Sub = { label: string; color: string; xs: (string | number)[]; ys: (string | number)[] }
    const buildSubs = (t: Trace): Sub[] => {
      if (!t.groupBy) {
        return [{
          label: t.name || t.yCol,
          color: t.color,
          xs: filteredRows.map((r) => coerceCell(r[xCol])),
          ys: filteredRows.map((r) => coerceCell(r[t.yCol])),
        }]
      }
      const groups = new Map<string, Record<string, unknown>[]>()
      for (const r of filteredRows) {
        const key = String(r[t.groupBy] ?? '')
        if (!groups.has(key)) groups.set(key, [])
        groups.get(key)!.push(r)
      }
      const keys = Array.from(groups.keys()).sort()
      // Honour an empty name field: when blank, the group key alone is the
      // label (e.g. "APH797" instead of "job_count · APH797").
      const prefix = t.name.trim()
      const subs: Sub[] = keys.map((k, i) => ({
        label: prefix ? `${prefix} · ${k}` : k,
        color: PALETTE[i % PALETTE.length],
        xs: groups.get(k)!.map((r) => coerceCell(r[xCol])),
        ys: groups.get(k)!.map((r) => coerceCell(r[t.yCol])),
      }))
      // Optional overall-total trace: aggregate the y column across groups,
      // bucketed by x. Drawn in muted gray and prepended so it's first in legend.
      if (t.showTotal) {
        const bucket = new Map<string, { x: string | number; ys: number[] }>()
        for (const r of filteredRows) {
          const x = coerceCell(r[xCol])
          const k = String(x)
          if (!bucket.has(k)) bucket.set(k, { x, ys: [] })
          const y = Number(r[t.yCol])
          if (!isNaN(y)) bucket.get(k)!.ys.push(y)
        }
        const sorted = Array.from(bucket.values()).sort((a, b) =>
          typeof a.x === 'number' && typeof b.x === 'number'
            ? a.x - b.x
            : String(a.x).localeCompare(String(b.x)),
        )
        const fold = t.totalAgg === 'mean'
          ? (ys: number[]) => (ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : 0)
          : t.totalAgg === 'count'
            ? (ys: number[]) => ys.length
            : (ys: number[]) => ys.reduce((a, b) => a + b, 0)
        subs.unshift({
          label: prefix ? `${prefix} · TOTAL (${t.totalAgg})` : `TOTAL (${t.totalAgg})`,
          color: '#94a3b8',
          xs: sorted.map((a) => a.x),
          ys: sorted.map((a) => fold(a.ys)),
        })
      }
      return subs
    }

    const data = traces.flatMap((t) => buildSubs(t).map((raw) => {
      // Apply per-trace cumulative transform after grouping/total, before render.
      const s = t.cumulative ? { ...raw, ...cumulate(raw.xs, raw.ys) } : raw
      const common = {
        name: s.label + (t.cumulative ? ' (cum)' : ''),
        marker: { color: s.color, size: t.markerSize, opacity: t.opacity },
        line: { color: s.color, width: t.lineWidth },
        opacity: t.opacity,
        yaxis: t.yaxis,
      }
      switch (t.type) {
        case 'line': return { ...common, type: 'scatter', mode: 'lines+markers', x: s.xs, y: s.ys }
        case 'scatter': return { ...common, type: 'scatter', mode: 'markers', x: s.xs, y: s.ys }
        case 'pie': return { type: 'pie', labels: s.xs.map(String), values: s.ys, name: s.label,
                              marker: { colors: PALETTE }, opacity: t.opacity }
        case 'box': return { ...common, type: 'box', y: s.ys, name: s.label }
        case 'histogram': return { ...common, type: 'histogram', x: s.ys }
        case 'heatmap': return { type: 'heatmap', x: s.xs, y: s.ys, z: s.ys, colorscale: 'Viridis', opacity: t.opacity, yaxis: t.yaxis }
        case 'bar':
        default: return { ...common, type: 'bar', x: s.xs, y: s.ys }
      }
    }))

    const axisLayout = (cfg: AxisCfg, fallback: string) => {
      const out: any = {
        title: { text: cfg.title || fallback },
        color: '#94a3b8',
        gridcolor: '#2a2d3a',
        automargin: true,
        ...(cfg.tickFormat ? { tickformat: cfg.tickFormat } : {}),
      }
      if (cfg.type !== 'auto') out.type = cfg.type
      if (cfg.min !== '' || cfg.max !== '') {
        const lo = cfg.min !== '' ? Number(cfg.min) : undefined
        const hi = cfg.max !== '' ? Number(cfg.max) : undefined
        if (lo !== undefined && hi !== undefined) out.range = [lo, hi]
      }
      return out
    }

    // Anchor table for each position: orientation + plot-relative x/y +
    // x/y anchor keywords. Outside-edge positions (top/bottom) flip to
    // horizontal orientation; left/right/corners stay vertical.
    const positions: Record<LegendPos, any> = {
      right:         { orientation: 'v', x: 1.02, y: 1,    xanchor: 'left',   yanchor: 'top' },
      left:          { orientation: 'v', x: -0.18, y: 1,   xanchor: 'left',   yanchor: 'top' },
      top:           { orientation: 'h', x: 0.5,  y: 1.12, xanchor: 'center', yanchor: 'bottom' },
      bottom:        { orientation: 'h', x: 0.5,  y: -0.25, xanchor: 'center', yanchor: 'top' },
      'top-left':    { orientation: 'v', x: 0.02, y: 0.98, xanchor: 'left',   yanchor: 'top',    bgcolor: 'rgba(15,23,42,0.6)' },
      'top-right':   { orientation: 'v', x: 0.98, y: 0.98, xanchor: 'right',  yanchor: 'top',    bgcolor: 'rgba(15,23,42,0.6)' },
      'bottom-left': { orientation: 'v', x: 0.02, y: 0.02, xanchor: 'left',   yanchor: 'bottom', bgcolor: 'rgba(15,23,42,0.6)' },
      'bottom-right':{ orientation: 'v', x: 0.98, y: 0.02, xanchor: 'right',  yanchor: 'bottom', bgcolor: 'rgba(15,23,42,0.6)' },
    }
    const legendDomain: any = { ...positions[legendPos] }
    // Multi-column wrapping: force horizontal orientation and set each entry
    // to ~ 1/N of plot width so the legend wraps into N columns.
    if (legendCols > 1) {
      legendDomain.orientation = 'h'
      legendDomain.entrywidth = 1 / legendCols
      legendDomain.entrywidthmode = 'fraction'
    }

    const layout: any = {
      title: title ? { text: title, font: { color: '#e2e8f0' } } : undefined,
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'transparent',
      font: { color: '#e2e8f0', size: 11 },
      margin: {
        t: title ? 40 : (legendPos === 'top' ? 60 : 20),
        r: legendPos === 'right' ? 140 : 20,
        b: legendPos === 'bottom' ? 80 : 50,
        l: legendPos === 'left' ? 140 : 60,
      },
      height: 380,
      autosize: true,
      barmode: barMode,
      showlegend: legend,
      legend: legendDomain,
      xaxis: axisLayout(xAxis, xCol),
      yaxis: axisLayout(yAxis, traces[0]?.yCol ?? ''),
      ...(usesY2 ? { yaxis2: { ...axisLayout(y2Axis, 'y2'), overlaying: 'y', side: 'right' } } : {}),
      annotations: annotations.map((a) => ({
        x: a.x, y: a.y, text: a.text, showarrow: true, arrowhead: 2,
        font: { color: '#e2e8f0' }, bgcolor: 'rgba(15,23,42,0.85)', bordercolor: '#475569',
      })),
    }
    return { data, layout }
  }, [filteredRows, xCol, traces, title, legend, legendPos, legendCols, xAxis, yAxis, y2Axis, usesY2, annotations, barMode])

  if (!rows.length) return null

  const inp = 'bg-herald-bg border border-herald-border rounded-md px-2 py-1 text-xs text-herald-text focus:outline-none focus:border-herald-accent'
  const sectionH = 'text-xs font-medium text-herald-text-dim uppercase tracking-wide mb-2'

  const onPlotClick = (e: any) => {
    if (!annotMode || !e?.points?.length) return
    const p = e.points[0]
    const text = window.prompt('Annotation text:')
    if (text) setAnnotations((a) => [...a, { x: p.x, y: p.y, text }])
    setAnnotMode(false)
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-3 p-3">
      {/* ── Controls ────────────────────────────────────────── */}
      <div className="space-y-4 text-xs max-h-[600px] overflow-y-auto scroll-area pr-1">
        <section>
          <div className={sectionH}>Chart</div>
          <label className="block mb-1 text-herald-text-dim">Title</label>
          <input value={title} onChange={(e) => setTitle(e.target.value)} className={`${inp} w-full mb-2`} placeholder="(none)" />
          <label className="block mb-1 text-herald-text-dim">X column</label>
          <select value={xCol} onChange={(e) => setXCol(e.target.value)} className={`${inp} w-full mb-2`}>
            {cols.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <label className="block mb-1 text-herald-text-dim" title="How multiple bar traces share each x bucket">Bar mode</label>
          <select value={barMode} onChange={(e) => setBarMode(e.target.value as BarMode)} className={`${inp} w-full`}>
            <option value="group">grouped (side-by-side)</option>
            <option value="stack">stacked</option>
            <option value="relative">stacked (%)</option>
            <option value="overlay">overlay</option>
          </select>
        </section>

        <section>
          <div className="flex items-center justify-between mb-2">
            <span className={sectionH + ' mb-0'}>Traces</span>
            <button onClick={addTrace} className="p-1 rounded border border-herald-border hover:border-herald-accent text-herald-text-dim hover:text-herald-text" title="Add trace">
              <Plus size={12} />
            </button>
          </div>
          <div className="space-y-2">
            {traces.map((t, i) => (
              <div key={i} className="p-2 rounded border border-herald-border space-y-1.5 bg-herald-bg/40">
                <div className="flex items-center gap-1.5">
                  <input type="color" value={t.color} onChange={(e) => updateTrace(i, { color: e.target.value })} className="w-6 h-6 rounded cursor-pointer bg-transparent border-0 p-0" title="Trace color" />
                  <input value={t.name} onChange={(e) => updateTrace(i, { name: e.target.value })} className={`${inp} flex-1`} placeholder="name" />
                  {traces.length > 1 && (
                    <button onClick={() => removeTrace(i)} className="p-1 text-red-400 hover:text-red-300" title="Remove trace">
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
                <div className="flex gap-1.5">
                  <select value={t.yCol} onChange={(e) => updateTrace(i, { yCol: e.target.value })} className={`${inp} flex-1`}>
                    {cols.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <select value={t.type} onChange={(e) => updateTrace(i, { type: e.target.value as TraceType })} className={inp}>
                    <option value="bar">bar</option><option value="line">line</option>
                    <option value="scatter">scatter</option><option value="pie">pie</option>
                    <option value="box">box</option><option value="histogram">hist</option>
                    <option value="heatmap">heatmap</option>
                  </select>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-herald-text-dim" title="Split into one trace per distinct value of this column">Group</span>
                  <select value={t.groupBy} onChange={(e) => updateTrace(i, { groupBy: e.target.value })} className={`${inp} flex-1`}>
                    <option value="">(none)</option>
                    {/* Show every column; never hide the currently-selected one
                        (filtering by xCol/yCol used to silently leave stale state
                        when the user later changed yCol to match groupBy). */}
                    {cols.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                {t.groupBy && (
                  <div className="flex items-center gap-1.5">
                    <label className="flex items-center gap-1 text-[10px] text-herald-text-dim cursor-pointer">
                      <input
                        type="checkbox"
                        checked={t.showTotal}
                        onChange={(e) => updateTrace(i, { showTotal: e.target.checked })}
                      />
                      Show total
                    </label>
                    {t.showTotal && (
                      <select value={t.totalAgg} onChange={(e) => updateTrace(i, { totalAgg: e.target.value as Trace['totalAgg'] })} className={inp} title="Aggregation for the total line">
                        <option value="sum">sum</option>
                        <option value="mean">mean</option>
                        <option value="count">count</option>
                      </select>
                    )}
                  </div>
                )}
                <label className="flex items-center gap-1 text-[10px] text-herald-text-dim cursor-pointer" title="Replace Y with a running sum along X">
                  <input
                    type="checkbox"
                    checked={t.cumulative}
                    onChange={(e) => updateTrace(i, { cumulative: e.target.checked })}
                  />
                  Cumulative
                </label>
                <div className="flex gap-1.5 items-center">
                  <select value={t.yaxis} onChange={(e) => updateTrace(i, { yaxis: e.target.value as 'y' | 'y2' })} className={inp} title="Y axis">
                    <option value="y">Y</option><option value="y2">Y2</option>
                  </select>
                  <label className="flex items-center gap-1 text-herald-text-dim flex-1 text-[10px]">
                    Marker<input type="range" min={2} max={20} value={t.markerSize} onChange={(e) => updateTrace(i, { markerSize: +e.target.value })} className="flex-1" />
                  </label>
                </div>
                <div className="flex gap-1.5 items-center">
                  <label className="flex items-center gap-1 text-herald-text-dim flex-1 text-[10px]">
                    Line<input type="range" min={1} max={6} value={t.lineWidth} onChange={(e) => updateTrace(i, { lineWidth: +e.target.value })} className="flex-1" />
                  </label>
                  <label className="flex items-center gap-1 text-herald-text-dim flex-1 text-[10px]">
                    Opacity<input type="range" min={0.1} max={1} step={0.05} value={t.opacity} onChange={(e) => updateTrace(i, { opacity: +e.target.value })} className="flex-1" />
                  </label>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section>
          <div className={sectionH}>
            Filter
            {filterCol && filterValues.size > 0 && (
              <span className="ml-1 normal-case font-normal text-herald-text-dim">
                ({filterValues.size}/{filterOptions.length} of {rows.length}→{filteredRows.length} rows)
              </span>
            )}
          </div>
          <select value={filterCol} onChange={(e) => setFilterCol(e.target.value)} className={`${inp} w-full mb-1.5`}>
            <option value="">(no filter)</option>
            {cols.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          {filterCol && (
            <>
              <div className="flex gap-2 mb-1 text-[10px] text-herald-text-dim">
                <button onClick={() => setFilterValues(new Set(filterOptions))} className="hover:text-herald-text underline">all</button>
                <button onClick={() => setFilterValues(new Set())} className="hover:text-herald-text underline">none</button>
              </div>
              <div className="max-h-32 overflow-y-auto scroll-area border border-herald-border rounded-md p-1 space-y-0.5">
                {filterOptions.map((v) => (
                  <label key={v} className="flex items-center gap-1.5 text-[11px] text-herald-text-dim hover:text-herald-text cursor-pointer">
                    <input
                      type="checkbox"
                      checked={filterValues.has(v)}
                      onChange={(e) => setFilterValues((s) => {
                        const next = new Set(s)
                        if (e.target.checked) next.add(v); else next.delete(v)
                        return next
                      })}
                    />
                    <span className="truncate">{v || '(empty)'}</span>
                  </label>
                ))}
              </div>
            </>
          )}
        </section>

        {(() => {
          const sections: Array<{ label: string; cfg: AxisCfg; setCfg: (c: AxisCfg) => void; fb: string }> = [
            { label: 'X axis', cfg: xAxis, setCfg: setXAxis, fb: xCol },
            { label: 'Y axis', cfg: yAxis, setCfg: setYAxis, fb: traces[0]?.yCol ?? '' },
          ]
          if (usesY2) sections.push({ label: 'Y2 axis', cfg: y2Axis, setCfg: setY2Axis, fb: '' })
          return sections.map(({ label, cfg, setCfg, fb }) => (
            <section key={label}>
              <div className={sectionH}>{label}</div>
              <div className="space-y-1.5">
                <input value={cfg.title} onChange={(e) => setCfg({ ...cfg, title: e.target.value })} className={`${inp} w-full`} placeholder={`title (${fb})`} />
                <select value={cfg.type} onChange={(e) => setCfg({ ...cfg, type: e.target.value as AxisType })} className={`${inp} w-full`}>
                  <option value="auto">auto scale</option><option value="linear">linear</option>
                  <option value="log">log</option><option value="category">category</option>
                  <option value="date">date</option>
                </select>
                <input value={cfg.tickFormat} onChange={(e) => setCfg({ ...cfg, tickFormat: e.target.value })} className={`${inp} w-full`} placeholder="tick format (e.g. .2s, %b %Y)" />
                <div className="flex gap-1.5">
                  <input value={cfg.min} onChange={(e) => setCfg({ ...cfg, min: e.target.value })} className={`${inp} flex-1`} placeholder="min" />
                  <input value={cfg.max} onChange={(e) => setCfg({ ...cfg, max: e.target.value })} className={`${inp} flex-1`} placeholder="max" />
                </div>
              </div>
            </section>
          ))
        })()}

        <section>
          <div className={sectionH}>Legend</div>
          <label className="flex items-center gap-2 mb-1.5 text-herald-text-dim">
            <input type="checkbox" checked={legend} onChange={(e) => setLegend(e.target.checked)} /> Show legend
          </label>
          <label className="block mb-1 text-[10px] text-herald-text-dim">Position</label>
          <select value={legendPos} onChange={(e) => setLegendPos(e.target.value as LegendPos)} className={`${inp} w-full mb-2`} disabled={!legend}>
            <optgroup label="outside">
              <option value="right">right</option>
              <option value="left">left</option>
              <option value="top">top</option>
              <option value="bottom">bottom</option>
            </optgroup>
            <optgroup label="inside (corners)">
              <option value="top-left">top-left</option>
              <option value="top-right">top-right</option>
              <option value="bottom-left">bottom-left</option>
              <option value="bottom-right">bottom-right</option>
            </optgroup>
          </select>
          <label className="block mb-1 text-[10px] text-herald-text-dim" title="Wrap legend entries into N columns (forces horizontal orientation)">Columns</label>
          <input type="number" min={1} max={6} value={legendCols} onChange={(e) => setLegendCols(Math.max(1, Math.min(6, +e.target.value || 1)))} className={`${inp} w-full`} disabled={!legend} />
        </section>

        <section>
          <div className="flex items-center justify-between mb-2">
            <span className={sectionH + ' mb-0'}>Annotations ({annotations.length})</span>
            <button onClick={() => setAnnotMode((m) => !m)} className={`p-1 rounded border ${annotMode ? 'border-herald-accent text-herald-accent' : 'border-herald-border text-herald-text-dim hover:text-herald-text'}`} title="Click chart to place">
              <MapPin size={12} />
            </button>
          </div>
          {annotMode && <p className="text-herald-muted mb-1">Click a chart point to place a label.</p>}
          <div className="space-y-1">
            {annotations.map((a, i) => (
              <div key={i} className="flex items-center gap-1.5">
                <span className="flex-1 truncate text-herald-text-dim">{a.text} @ {String(a.x).slice(0, 12)}</span>
                <button onClick={() => setAnnotations((ans) => ans.filter((_, j) => j !== i))} className="text-red-400 hover:text-red-300">
                  <Trash2 size={11} />
                </button>
              </div>
            ))}
          </div>
        </section>
      </div>

      {/* ── Chart ──────────────────────────────────────────── */}
      <div style={{ minHeight: 400 }}>
        <Plot
          data={data as any[]}
          layout={layout}
          config={{ displayModeBar: true, displaylogo: false, responsive: true, modeBarButtonsToRemove: ['sendDataToCloud'] }}
          style={{ width: '100%', height: 400 }}
          onClick={onPlotClick as any}
        />
      </div>
    </div>
  )
}

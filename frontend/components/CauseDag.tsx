'use client'

/**
 * CauseDag — SVG render of an upstream cause cascade.
 *
 * Single-hop mode (max_depth=1): clicked effect on the right, direct causes
 * stacked on the left.
 *
 * Multi-hop mode (max_depth>1, P6+): N columns laid out right-to-left by
 * depth. Clicked effect at depth 0 (rightmost), direct causes at depth 1,
 * their causes at depth 2, ..., up to max_depth. Each cause appears at
 * its FIRST (shallowest) depth in the tree; edges between adjacent depth
 * columns are colored by tier. Cycle-truncated nodes get a dashed border.
 *
 * No external graph lib — keeps the prototype self-contained.
 */

type Edge = {
  cause: string
  effect: string
  tier: string
  num_methods: number
  detected_by: string[]
}

type SubgraphNode = {
  id: string
  kind: 'effect' | 'cause'
  tier?: string
  instance_count?: number
}

type Subgraph = {
  nodes: SubgraphNode[]
  edges: Edge[]
}

type Instance = { ts: string; node: string; raw: string; severity: string }

type CascadeNode = {
  event_type: string
  depth: number
  tier?: string
  num_methods?: number
  detected_by?: string[]
  instance_count?: number
  instances?: Instance[]
  upstream?: CascadeNode[]
  cycle_truncated?: boolean
}

type Props = {
  subgraph: Subgraph
  independent: boolean
  cascadeTree?: CascadeNode | null
  maxDepth?: number
  // Click handler for cause boxes. Fired when the operator selects a hop
  // in the cascade — the side panel uses it to switch the Causes section
  // to show that hop's raw messages while keeping the originally-clicked
  // event in focus. Effect (clicked-event) box is never clickable.
  // `focusedEventType` highlights the box that's currently shown below.
  onCauseClick?: (eventType: string) => void
  focusedEventType?: string | null
}

const TIER_COLORS: Record<string, string> = {
  'Tier 1': '#10b981',  // emerald — strong agreement (all 3 methods)
  'Tier 2': '#f59e0b',  // amber  — 2 of 3 methods
  'Manual': '#8b5cf6',  // violet — operator-curated (or LLM-proposed + operator-approved)
}

// Sized so a 5-column tree (depth 0..4) fits ~900px of horizontal space —
// roughly a default side-panel width. Deeper cascades or narrower panels
// still scroll via the inner overflow-x-auto wrapper.
const BOX_W = 130
const BOX_H = 42
const GAP_Y = 10
const COL_GAP = 50
const LABEL_FONT = 10
const META_FONT = 8


// ── Multi-hop layout ──────────────────────────────────────────────────────


type LaidOutNode = {
  event_type: string
  depth: number
  tier?: string
  instance_count?: number
  cycle_truncated?: boolean
  isEffect: boolean
  instances?: Instance[]
}

type LaidOutEdge = {
  fromEventType: string   // deeper cause (further from clicked event)
  toEventType: string     // shallower effect (closer to clicked event)
  tier: string
}

/**
 * Walk the cascade tree depth-first. Each event_type is placed at its
 * MINIMUM depth (closest to root). Edges go FROM deeper (cause) TO
 * shallower (effect) — consistent with the original single-hop view
 * where causes-on-left → effect-on-right.
 */
function layoutCascade(root: CascadeNode): {
  nodes: LaidOutNode[]
  edges: LaidOutEdge[]
} {
  const minDepth = new Map<string, number>()
  const tier = new Map<string, string | undefined>()
  const count = new Map<string, number | undefined>()
  const instances = new Map<string, Instance[] | undefined>()
  const truncated = new Map<string, boolean>()
  const edges: LaidOutEdge[] = []
  const seenEdge = new Set<string>()

  function visit(node: CascadeNode, parent: string | null) {
    const et = node.event_type
    const prior = minDepth.get(et)
    if (prior === undefined || node.depth < prior) {
      minDepth.set(et, node.depth)
      tier.set(et, node.tier)
      count.set(et, node.instance_count)
      instances.set(et, node.instances)
    }
    if (node.cycle_truncated) truncated.set(et, true)

    if (parent !== null && parent !== et) {
      // Edge goes from cause (the current node, which is upstream of parent)
      // to effect (parent). Dedupe by direction.
      const edgeKey = `${et}->${parent}`
      if (!seenEdge.has(edgeKey)) {
        seenEdge.add(edgeKey)
        edges.push({
          fromEventType: et, toEventType: parent,
          tier: node.tier ?? 'Tier 2',
        })
      }
    }
    if (truncated.get(et)) return   // don't recurse beyond truncation point
    for (const child of node.upstream ?? []) {
      visit(child, et)
    }
  }

  visit(root, null)
  const nodes: LaidOutNode[] = [...minDepth.entries()].map(([et, depth]) => ({
    event_type: et,
    depth,
    tier: tier.get(et),
    instance_count: count.get(et),
    instances: instances.get(et),
    cycle_truncated: truncated.get(et) ?? false,
    isEffect: depth === 0,
  }))
  return { nodes, edges }
}


// ── Component ─────────────────────────────────────────────────────────────


export default function CauseDag({
  subgraph,
  independent,
  cascadeTree,
  maxDepth = 1,
  onCauseClick,
  focusedEventType,
}: Props) {
  if (independent) {
    const effect =
      cascadeTree?.event_type
      ?? subgraph.nodes.find((n) => n.kind === 'effect')?.id
      ?? 'event'
    return (
      <div className="border border-herald-border rounded p-4 bg-herald-surface">
        <div className="flex items-center gap-2 mb-2">
          <span className="inline-block w-2 h-2 rounded-full bg-emerald-400" />
          <span className="text-sm font-medium text-herald-text">Independent event</span>
        </div>
        <p className="text-xs text-herald-text-dim leading-relaxed">
          <span className="font-mono text-herald-text">{effect}</span> has no
          upstream causes in the lookback window. Either no causal edges exist
          in the static graph, or the causes that exist did not fire on this
          node recently.
        </p>
      </div>
    )
  }

  // Multi-hop path uses the cascade tree. Single-hop falls back to the
  // legacy subgraph layout (preserves existing depth=1 visuals).
  const useTree = !!cascadeTree && maxDepth > 1

  // Compute per-column lists either from the cascade tree or the legacy subgraph.
  let columns: Map<number, LaidOutNode[]>
  let renderEdges: LaidOutEdge[]
  let totalCauses: number

  if (useTree && cascadeTree) {
    const laid = layoutCascade(cascadeTree)
    columns = new Map()
    for (const n of laid.nodes) {
      const col = columns.get(n.depth) ?? []
      col.push(n)
      columns.set(n.depth, col)
    }
    renderEdges = laid.edges
    totalCauses = laid.nodes.filter((n) => !n.isEffect).length
  } else {
    columns = new Map()
    const effectN = subgraph.nodes.find((n) => n.kind === 'effect')
    const causeNs = subgraph.nodes.filter((n) => n.kind === 'cause')
    if (effectN) {
      columns.set(0, [{
        event_type: effectN.id, depth: 0,
        tier: effectN.tier, instance_count: effectN.instance_count,
        cycle_truncated: false, isEffect: true,
      }])
    }
    columns.set(1, causeNs.map((n) => ({
      event_type: n.id, depth: 1,
      tier: n.tier, instance_count: n.instance_count,
      cycle_truncated: false, isEffect: false,
    })))
    renderEdges = subgraph.edges.map((e) => ({
      fromEventType: e.cause, toEventType: e.effect, tier: e.tier,
    }))
    totalCauses = causeNs.length
  }

  const depths = [...columns.keys()].sort((a, b) => a - b)
  if (depths.length === 0) return null
  const maxDepthInTree = depths[depths.length - 1]
  // Column x-positions, indexed by depth. Depth 0 (effect) is rightmost.
  const colX = new Map<number, number>()
  for (let d = 0; d <= maxDepthInTree; d++) {
    // Reverse: depth=maxDepthInTree at x=16 (leftmost), depth=0 rightmost
    colX.set(d, 16 + (maxDepthInTree - d) * (BOX_W + COL_GAP))
  }
  const totalWidth = 16 + (maxDepthInTree + 1) * (BOX_W + COL_GAP)

  // Per-column y stacking
  const yByNode = new Map<string, number>()
  let totalHeight = BOX_H + 16
  for (const d of depths) {
    const col = columns.get(d) ?? []
    for (let i = 0; i < col.length; i++) {
      yByNode.set(col[i].event_type, 8 + i * (BOX_H + GAP_Y))
    }
    totalHeight = Math.max(totalHeight, col.length * (BOX_H + GAP_Y) + 16)
  }

  return (
    <div className="border border-herald-border rounded bg-herald-surface">
      {/* Header stays in a non-scrolling container so it doesn't stretch to
          the SVG's full width when the cascade is wide. */}
      <div className="flex items-center justify-between p-3 pb-2 gap-3 flex-wrap">
        <span className="text-sm font-medium text-herald-text">
          {useTree
            ? `Upstream cascade (${totalCauses} cause${totalCauses === 1 ? '' : 's'}, depth ${maxDepthInTree})`
            : `Upstream causes (${totalCauses})`}
        </span>
        <div className="flex items-center gap-3 text-[10px] text-herald-text-dim flex-wrap">
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5" style={{ background: TIER_COLORS['Tier 1'] }} />
            Tier 1 (3/3 methods)
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5" style={{ background: TIER_COLORS['Tier 2'] }} />
            Tier 2 (2/3 methods)
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5" style={{ background: TIER_COLORS['Manual'] }} />
            Manual
          </span>
        </div>
      </div>

      {/* Only the SVG scrolls horizontally when the cascade is wide. */}
      <div className="overflow-x-auto px-3 pb-3">
      <svg width={totalWidth} height={totalHeight} className="block">
        <defs>
          {Object.entries(TIER_COLORS).map(([tier, color]) => (
            <marker
              key={tier}
              id={`arrow-${tier.replace(' ', '-')}`}
              viewBox="0 0 10 10"
              refX="9" refY="5"
              markerWidth="6" markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
            </marker>
          ))}
        </defs>

        {/* Edges first so boxes render on top */}
        {renderEdges.map((e, i) => {
          const fromNode = [...columns.values()].flat().find((n) => n.event_type === e.fromEventType)
          const toNode = [...columns.values()].flat().find((n) => n.event_type === e.toEventType)
          if (!fromNode || !toNode) return null
          const fromX = (colX.get(fromNode.depth) ?? 16) + BOX_W
          const toX = colX.get(toNode.depth) ?? 16
          const fromY = (yByNode.get(fromNode.event_type) ?? 0) + BOX_H / 2
          const toY = (yByNode.get(toNode.event_type) ?? 0) + BOX_H / 2
          const dx = toX - fromX
          const cx1 = fromX + dx * 0.4
          const cx2 = toX - dx * 0.4
          const color = TIER_COLORS[e.tier] ?? '#6b7280'
          return (
            <path
              key={`${e.fromEventType}->${e.toEventType}-${i}`}
              d={`M ${fromX} ${fromY} C ${cx1} ${fromY}, ${cx2} ${toY}, ${toX} ${toY}`}
              stroke={color}
              strokeWidth={1.5}
              fill="none"
              markerEnd={`url(#arrow-${e.tier.replace(' ', '-')})`}
              opacity={0.85}
            />
          )
        })}

        {/* Boxes */}
        {[...columns.values()].flat().map((n) => {
          const x = colX.get(n.depth) ?? 16
          const y = yByNode.get(n.event_type) ?? 0
          const isFocused = !n.isEffect && focusedEventType === n.event_type
          const stroke = n.isEffect
            ? '#4f8ef7'
            : isFocused
              ? '#e2e8f0'
              : (TIER_COLORS[n.tier ?? ''] ?? '#2a2d3a')
          const strokeW = n.isEffect || isFocused ? 2 : 1.5
          // Truncate label if it would overflow the (smaller) box width.
          // ~6 px/char for a 10 px monospace font; box has 8 px padding on each side.
          const maxChars = Math.floor((BOX_W - 14) / 6)
          const label = n.event_type.length > maxChars
            ? n.event_type.slice(0, maxChars - 1) + '…'
            : n.event_type
          const meta = n.isEffect
            ? 'clicked event'
            : `${n.tier ?? '?'} · d${n.depth} · ${n.instance_count ?? 0}`
          // Cause boxes (non-effect) with at least one instance are clickable
          // to show their raw messages in the Causes section below. The
          // panel stays on the originally-clicked event.
          const hasInstance = n.instances && n.instances.length > 0
          const isClickable = !n.isEffect && hasInstance && !!onCauseClick
          const handleClick = isClickable
            ? () => onCauseClick!(n.event_type)
            : undefined
          const titleText = isClickable
            ? `${n.event_type} — ${n.tier} · depth ${n.depth} · ${n.instance_count ?? 0} instance${n.instance_count === 1 ? '' : 's'} · click to view its messages`
            : `${n.event_type}${n.isEffect ? ' (clicked)' : ` — ${n.tier} · depth ${n.depth} · ${n.instance_count ?? 0} instance${n.instance_count === 1 ? '' : 's'}`}`
          return (
            <g
              key={n.event_type}
              transform={`translate(${x}, ${y})`}
              onClick={handleClick}
              style={isClickable ? { cursor: 'pointer' } : undefined}
              className={isClickable ? 'hover:opacity-80' : undefined}
            >
              <rect
                width={BOX_W} height={BOX_H} rx={5}
                fill="#1a1d27"
                stroke={stroke}
                strokeWidth={strokeW}
                strokeDasharray={n.cycle_truncated ? '4 3' : undefined}
              />
              <title>{titleText}</title>
              <text x={8} y={18} fontSize={LABEL_FONT} fontFamily="JetBrains Mono, monospace" fill="#e2e8f0">
                {label}
              </text>
              <text x={8} y={33} fontSize={META_FONT} fill={n.isEffect ? '#4f8ef7' : '#94a3b8'}>
                {meta}
              </text>
              {n.cycle_truncated && (
                <text x={BOX_W - 8} y={BOX_H - 6} fontSize={META_FONT} textAnchor="end" fill="#f59e0b">
                  ↻ cycle
                </text>
              )}
            </g>
          )
        })}
      </svg>
      </div>
    </div>
  )
}

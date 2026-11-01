'use client'
import { ToolDef, TOOL_COLORS } from '@/lib/tools'

interface Props {
  tools: ToolDef[]
  enabled: Set<string>
  onChange: (name: string, on: boolean) => void
  /** 'vertical' stacks full-width rows (sidebar); 'horizontal' wraps chips. */
  orientation?: 'vertical' | 'horizontal'
}

export default function ToolSelector({ tools, enabled, onChange, orientation = 'horizontal' }: Props) {
  const vertical = orientation === 'vertical'

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[10px] text-herald-muted uppercase tracking-widest px-1">
        Active sub-agents
      </p>
      <div className={vertical ? 'flex flex-col gap-1' : 'flex flex-wrap gap-2'}>
        {tools.map((t) => {
          const on = enabled.has(t.name)
          const color = TOOL_COLORS[t.name] ?? 'text-herald-text border-herald-border bg-herald-border/20'

          if (vertical) {
            return (
              <button
                key={t.name}
                onClick={() => onChange(t.name, !on)}
                title={`${t.description} — click to ${on ? 'disable' : 'enable'}`}
                aria-pressed={on}
                className={[
                  'w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md border text-xs font-medium text-left',
                  'transition-colors duration-150 select-none',
                  on
                    ? color
                    : 'text-herald-text-dim border-herald-border/60 bg-transparent hover:bg-herald-bg hover:text-herald-text',
                ].join(' ')}
              >
                <span
                  className={[
                    'w-2 h-2 rounded-full flex-shrink-0',
                    on ? 'bg-current' : 'border border-herald-muted',
                  ].join(' ')}
                />
                <span className="flex-1 truncate">{t.displayName}</span>
                <span className="text-[9px] uppercase tracking-wide opacity-70">{on ? 'on' : 'off'}</span>
              </button>
            )
          }

          return (
            <button
              key={t.name}
              onClick={() => onChange(t.name, !on)}
              title={`${t.description} — click to ${on ? 'disable' : 'enable'}`}
              aria-pressed={on}
              className={[
                'flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-medium',
                'transition-all duration-150 select-none cursor-pointer',
                on ? color : 'text-herald-muted border-dashed border-herald-border bg-transparent opacity-60',
              ].join(' ')}
            >
              <span className={['w-1.5 h-1.5 rounded-full', on ? 'bg-current' : 'bg-herald-muted opacity-50'].join(' ')} />
              {t.displayName}
            </button>
          )
        })}
      </div>
    </div>
  )
}

'use client'
import { useEffect, useState, type ReactNode } from 'react'
import { usePathname } from 'next/navigation'
import BrandLogos from './BrandLogos'

const SIDEBAR_KEY = 'herald.sidebar.open'

// Exported so page-specific sidebar items (Knowledge Base, Proposal queue) match.
export const navBase =
  'w-full flex items-center gap-2 px-2.5 py-2 rounded-md text-sm transition-colors text-left'
export const navIdle = 'text-herald-text-dim hover:text-herald-text hover:bg-herald-bg'
export const navActive = 'text-herald-text bg-herald-bg border-l-2 border-herald-accent'

/**
 * Shared app chrome: a collapsible left sidebar (logos + common nav, plus an
 * optional page-specific slot) and a slim top bar with the toggle. Used by the
 * chat and Syslog Monitor pages so the product reads as one app.
 *
 * Common nav is only the top-level pages (Chat, Syslog Monitor). Page-specific
 * entries (Knowledge Base on chat, Proposal queue on syslog) and sections
 * (chat sub-agents) are passed via `sidebarExtra`.
 */
export default function AppShell({
  title,
  sidebarExtra,
  children,
}: {
  title?: string
  sidebarExtra?: ReactNode
  children: ReactNode
}) {
  const [open, setOpen] = useState(true)
  const pathname = usePathname()

  useEffect(() => {
    const stored = typeof window !== 'undefined' ? window.localStorage.getItem(SIDEBAR_KEY) : null
    if (stored !== null) setOpen(stored === '1')
  }, [])

  const toggle = () =>
    setOpen((o) => {
      try { window.localStorage.setItem(SIDEBAR_KEY, o ? '0' : '1') } catch {}
      return !o
    })

  const cls = (href: string) => `${navBase} ${pathname === href ? navActive : navIdle}`

  return (
    <div className="flex h-screen bg-herald-bg overflow-hidden">
      {/* Sidebar */}
      <aside
        className={[
          'flex-shrink-0 overflow-hidden border-r border-herald-border bg-herald-surface',
          'transition-[width] duration-200 ease-in-out',
          open ? 'w-64' : 'w-0',
        ].join(' ')}
      >
        <div className="w-64 h-full flex flex-col">
          {/* Brand */}
          <div className="px-4 pt-4 pb-3 border-b border-herald-border">
            <BrandLogos className="mb-3" />
            <div className="flex items-center justify-between">
              <a href="/" className="font-bold text-lg tracking-tight text-herald-text hover:text-herald-accent">
                HERALD
              </a>
              <button
                onClick={toggle}
                title="Collapse sidebar"
                aria-label="Collapse sidebar"
                className="text-herald-text-dim hover:text-herald-text px-1 text-sm"
              >
                «
              </button>
            </div>
            <p className="text-[11px] text-herald-text-dim mt-0.5">HPC Operations Assistant</p>
          </div>

          {/* Common nav — top-level pages only */}
          <nav className="px-3 py-3 space-y-1 border-b border-herald-border">
            <p className="px-1 text-[10px] uppercase tracking-widest text-herald-muted mb-1">Navigate</p>
            <a href="/" className={cls('/')}>
              <span className="text-herald-accent">▮</span><span className="flex-1">Chat</span>
            </a>
            <a href="/syslog" className={cls('/syslog')}>
              <span className="text-herald-accent">◧</span><span className="flex-1">Syslog Monitor</span>
            </a>
            <a href="/setup" className={cls('/setup')}>
              <span className="text-herald-accent">⚙</span><span className="flex-1">Setup</span>
            </a>
          </nav>

          {/* Page-specific content (chat: Knowledge Base + sub-agents; syslog: Proposal queue) */}
          {sidebarExtra && (
            <div className="px-3 py-3 flex-1 overflow-y-auto scroll-area">{sidebarExtra}</div>
          )}
        </div>
      </aside>

      {/* Main column */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="flex items-center gap-3 px-4 py-2.5 border-b border-herald-border bg-herald-surface flex-shrink-0">
          <button
            onClick={toggle}
            title={open ? 'Hide sidebar' : 'Show sidebar'}
            aria-label="Toggle sidebar"
            className="text-herald-text-dim hover:text-herald-text text-lg leading-none px-1"
          >
            ☰
          </button>
          {!open && <span className="font-bold text-herald-text tracking-tight">HERALD</span>}
          {title && <span className="text-sm text-herald-text-dim">{title}</span>}
          <div className="flex-1" />
        </header>
        <main className="flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  )
}

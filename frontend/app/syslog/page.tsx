import SyslogMonitor from '@/components/SyslogMonitor'
import AppShell from '@/components/AppShell'

export const metadata = {
  title: 'HERALD — Syslog Monitor',
}

// Matches AppShell's navBase + navIdle (inlined; this is a server component).
const navLink =
  'w-full flex items-center gap-2 px-2.5 py-2 rounded-md text-sm transition-colors text-left ' +
  'text-herald-text-dim hover:text-herald-text hover:bg-herald-bg'

export default function SyslogPage() {
  return (
    <AppShell
      title="Syslog Monitor · causal triangulation (tier1+tier2)"
      sidebarExtra={
        <div className="space-y-3">
          <div className="space-y-1">
            <p className="px-1 text-[10px] uppercase tracking-widest text-herald-muted mb-1">Syslog</p>
            <a href="/syslog/proposals" className={navLink}>
              <span className="text-herald-accent">≣</span>
              <span className="flex-1">Proposal queue</span>
              <span className="text-herald-muted">→</span>
            </a>
          </div>
          {/* SyslogMonitor portals its stream controls in here (keeps its state local). */}
          <div id="syslog-sidebar-controls" />
        </div>
      }
    >
      <SyslogMonitor />
    </AppShell>
  )
}

import ProposalsTable from '@/components/ProposalsTable'

export const metadata = {
  title: 'HERALD — Proposal queue',
}

export default function ProposalsPage() {
  return (
    <div className="flex flex-col h-screen bg-herald-bg">
      <header className="flex items-center justify-between px-6 py-3 border-b border-herald-border bg-herald-surface flex-shrink-0">
        <div className="flex items-center gap-3">
          <a href="/" className="font-bold text-herald-text tracking-tight text-lg hover:text-herald-accent">
            HERALD
          </a>
          <span className="text-xs text-herald-muted">/</span>
          <a href="/syslog" className="text-sm text-herald-text-dim hover:text-herald-text">
            Syslog Monitor
          </a>
          <span className="text-xs text-herald-muted">/</span>
          <span className="text-sm text-herald-text">Proposal queue</span>
          <span className="text-xs text-herald-muted border border-herald-border rounded px-1.5 py-0.5 ml-2">
            residual control plane · P6
          </span>
        </div>
        <a
          href="/syslog"
          className="text-xs text-herald-text-dim hover:text-herald-text border border-herald-border rounded px-2 py-1"
        >
          ← Monitor
        </a>
      </header>
      <main className="flex-1 overflow-hidden">
        <ProposalsTable />
      </main>
    </div>
  )
}

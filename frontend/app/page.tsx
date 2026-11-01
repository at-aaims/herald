'use client'
import { useEffect, useState } from 'react'
import ChatInterface from '@/components/ChatInterface'
import ToolSelector from '@/components/ToolSelector'
import RagDocuments from '@/components/RagDocuments'
import AppShell, { navBase, navIdle } from '@/components/AppShell'
import { ToolDef, fetchTools } from '@/lib/tools'

export default function Home() {
  const [tools, setTools] = useState<ToolDef[]>([])
  const [enabled, setEnabled] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchTools().then((t) => {
      setTools(t)
      setEnabled(new Set(t.filter((x) => x.enabledByDefault).map((x) => x.name)))
      setLoading(false)
    })
  }, [])

  const toggleTool = (name: string, on: boolean) => {
    setEnabled((prev) => {
      const next = new Set(prev)
      on ? next.add(name) : next.delete(name)
      return next
    })
  }

  // Chat-specific sidebar content: Knowledge Base (drawer) + the sub-agent toggles.
  const sidebarExtra = (
    <div className="space-y-4">
      <div className="space-y-1">
        <p className="px-1 text-[10px] uppercase tracking-widest text-herald-muted">Knowledge</p>
        <RagDocuments triggerClassName={`${navBase} ${navIdle}`} />
      </div>
      {!loading && (
        <ToolSelector tools={tools} enabled={enabled} onChange={toggleTool} orientation="vertical" />
      )}
    </div>
  )

  return (
    <AppShell sidebarExtra={sidebarExtra}>
      <ChatInterface enabledTools={[...enabled]} />
    </AppShell>
  )
}

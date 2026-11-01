'use client'

/**
 * RagDocuments — a header button + slide-over panel for managing the RAG
 * knowledge base. Operators upload their own docs/images (drag-drop or picker),
 * watch per-file ingest progress, replace a document with a new version, and
 * delete documents. Uploaded content becomes searchable by the chat's `rag`
 * (HPC Documentation Search) tool.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  RagDoc, fetchDocuments, ingestOneFile, deleteDocument,
  isImageDoc, docFileUrl, ACCEPTED_EXTENSIONS,
} from '@/lib/rag'

function relTime(iso: string): string {
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return ''
  const s = Math.max(0, (Date.now() - t) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

type UploadStatus = 'uploading' | 'done' | 'error'
interface UploadItem {
  id: string
  name: string
  status: UploadStatus
  detail?: string
}

export default function RagDocuments({ triggerClassName }: { triggerClassName?: string } = {}) {
  const [open, setOpen] = useState(false)
  const [docs, setDocs] = useState<RagDoc[]>([])
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [uploads, setUploads] = useState<UploadItem[]>([])
  const inputRef = useRef<HTMLInputElement | null>(null)
  const replaceInputRef = useRef<HTMLInputElement | null>(null)
  const replaceTargetRef = useRef<string | null>(null)

  const refresh = useCallback(() => {
    setLoading(true)
    fetchDocuments().then(setDocs).finally(() => setLoading(false))
  }, [])

  useEffect(() => { if (open) refresh() }, [open, refresh])

  const setItem = (id: string, patch: Partial<UploadItem>) =>
    setUploads((prev) => prev.map((u) => (u.id === id ? { ...u, ...patch } : u)))

  // Upload files one at a time so each shows its own progress and result.
  const handleFiles = useCallback(async (files: File[], replaceDocId?: string) => {
    if (files.length === 0) return
    setBusy(true)
    const items: UploadItem[] = files.map((f, i) => ({
      id: `${Date.now()}-${i}-${f.name}`,
      name: f.name,
      status: 'uploading',
    }))
    setUploads((prev) => [...items, ...prev])
    for (let i = 0; i < files.length; i++) {
      const item = items[i]
      try {
        const r = await ingestOneFile(files[i], replaceDocId)
        if (r.error) {
          setItem(item.id, { status: 'error', detail: r.error })
        } else {
          const parts = [
            r.chunks ? `${r.chunks} chunks` : '',
            r.tables ? `${r.tables} tables` : '',
            r.images ? `${r.images} images` : '',
          ].filter(Boolean)
          setItem(item.id, { status: 'done', detail: parts.join(' · ') || 'ingested' })
        }
      } catch (e) {
        setItem(item.id, { status: 'error', detail: String(e) })
      }
      refresh()
    }
    setBusy(false)
  }, [refresh])

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    handleFiles(Array.from(e.dataTransfer.files))
  }

  const onReplaceClick = (docId: string) => {
    replaceTargetRef.current = docId
    replaceInputRef.current?.click()
  }

  const onDelete = async (docId: string) => {
    const ok = await deleteDocument(docId)
    if (ok) setDocs((prev) => prev.filter((d) => d.doc_id !== docId))
  }

  const statusDot = (s: UploadStatus) =>
    s === 'uploading' ? 'bg-herald-accent animate-pulse'
      : s === 'done' ? 'bg-emerald-400' : 'bg-red-400'

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        title="Upload and manage your own documents/images for the chat's documentation search."
        className={triggerClassName ?? 'text-xs text-herald-text-dim hover:text-herald-text border border-herald-border rounded px-2 py-1'}
      >
        Knowledge Base
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <aside className="relative w-[420px] max-w-[90vw] h-full bg-herald-bg border-l border-herald-border flex flex-col shadow-2xl">
            <div className="flex items-center justify-between px-4 py-3 border-b border-herald-border">
              <div>
                <h2 className="text-sm font-semibold text-herald-text">Knowledge Base</h2>
                <p className="text-[11px] text-herald-text-dim">
                  Files you add here are searchable by the documentation tool.
                </p>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="text-herald-text-dim hover:text-herald-text text-lg leading-none px-1"
                aria-label="Close"
              >
                ×
              </button>
            </div>

            {/* Upload zone */}
            <div className="p-4">
              <div
                onClick={() => inputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
                className={`cursor-pointer rounded-lg border border-dashed px-4 py-6 text-center transition-colors ${
                  dragOver
                    ? 'border-herald-accent bg-herald-accent/10'
                    : 'border-herald-border hover:border-herald-accent/60 bg-herald-surface'
                }`}
              >
                <input
                  ref={inputRef}
                  type="file"
                  multiple
                  accept={ACCEPTED_EXTENSIONS}
                  className="hidden"
                  onChange={(e) => { handleFiles(Array.from(e.target.files ?? [])); e.target.value = '' }}
                />
                <p className="text-xs text-herald-text">Drop files here or click to choose</p>
                <p className="text-[10px] text-herald-text-dim mt-1">
                  txt · md · rst · html · pdf · docx · images
                </p>
              </div>

              {/* Hidden input used by per-document Replace */}
              <input
                ref={replaceInputRef}
                type="file"
                accept={ACCEPTED_EXTENSIONS}
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  const target = replaceTargetRef.current
                  if (f && target) handleFiles([f], target)
                  replaceTargetRef.current = null
                  e.target.value = ''
                }}
              />

              {/* Per-file progress */}
              {uploads.length > 0 && (
                <div className="mt-3 space-y-1">
                  {uploads.slice(0, 8).map((u) => (
                    <div key={u.id} className="flex items-center gap-2 text-[11px]">
                      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${statusDot(u.status)}`} />
                      <span className="text-herald-text truncate flex-1" title={u.name}>{u.name}</span>
                      <span className={u.status === 'error' ? 'text-red-400' : 'text-herald-text-dim'}>
                        {u.status === 'uploading' ? 'ingesting…' : u.detail}
                      </span>
                    </div>
                  ))}
                  {uploads.some((u) => u.status !== 'uploading') && (
                    <button
                      onClick={() => setUploads((prev) => prev.filter((u) => u.status === 'uploading'))}
                      className="text-[10px] text-herald-accent hover:underline"
                    >
                      clear finished
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* Document list */}
            <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-wider text-herald-text-dim">
                  Ingested documents
                </span>
                <button onClick={refresh} className="text-[11px] text-herald-accent hover:underline">
                  refresh
                </button>
              </div>

              {loading && <p className="text-xs text-herald-text-dim">Loading…</p>}
              {!loading && docs.length === 0 && (
                <p className="text-xs text-herald-text-dim">
                  No documents yet. Upload files above to add them to the knowledge base.
                </p>
              )}

              {docs.map((d) => (
                <div
                  key={d.doc_id}
                  className="flex items-center gap-3 border border-herald-border rounded-lg bg-herald-surface px-3 py-2"
                >
                  {isImageDoc(d) ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={docFileUrl(d.doc_id)}
                      alt={d.filename}
                      className="w-10 h-10 object-cover rounded flex-shrink-0 border border-herald-border"
                    />
                  ) : (
                    <span className="w-10 h-10 flex items-center justify-center rounded bg-herald-bg border border-herald-border text-[10px] font-mono text-herald-text-dim flex-shrink-0 uppercase">
                      {d.ext.replace('.', '').slice(0, 4)}
                    </span>
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="text-xs text-herald-text truncate" title={d.filename}>
                      {d.filename}
                      {(d as any).watch_path && (
                        <span className="ml-1 text-[9px] text-herald-muted border border-herald-border rounded px-1">watched</span>
                      )}
                    </div>
                    <div className="text-[10px] text-herald-text-dim">
                      {d.chunks > 0 && `${d.chunks} chunks`}
                      {d.tables > 0 && ` · ${d.tables} tables`}
                      {d.images > 0 && ` · ${d.images} images`}
                      {d.ingested_at && ` · ${relTime(d.ingested_at)}`}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={() => onReplaceClick(d.doc_id)}
                      disabled={busy}
                      title="Replace this document with a newer file"
                      className="text-[11px] text-herald-text-dim hover:text-herald-accent disabled:opacity-40 px-1"
                    >
                      replace
                    </button>
                    <button
                      onClick={() => onDelete(d.doc_id)}
                      title="Remove from the knowledge base"
                      className="text-[11px] text-herald-text-dim hover:text-red-400 px-1"
                    >
                      delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </aside>
        </div>
      )}
    </>
  )
}

// Client helpers for the RAG user-document ingestion API.
// All paths are relative so they proxy through the Next.js /api rewrite.

export interface RagDoc {
  doc_id: string
  filename: string
  ext: string
  ingested_at: string
  chunks: number
  tables: number
  images: number
  error?: string
}

export async function fetchDocuments(): Promise<RagDoc[]> {
  const res = await fetch('/api/rag/documents')
  if (!res.ok) return []
  const data = await res.json()
  return (data.documents ?? []) as RagDoc[]
}

/** Upload one or more files for ingestion. Returns a per-file result/summary
 *  (each may carry an `error` instead of stats). */
export async function ingestFiles(files: File[]): Promise<RagDoc[]> {
  const fd = new FormData()
  for (const f of files) fd.append('files', f)
  const res = await fetch('/api/rag/ingest', { method: 'POST', body: fd })
  if (!res.ok) throw new Error(`Ingest failed (${res.status})`)
  const data = await res.json()
  return (data.results ?? []) as RagDoc[]
}

/** Ingest a single file (enables per-file progress in the UI). When
 *  `replaceDocId` is set, the named existing document is replaced once the new
 *  one ingests successfully. */
export async function ingestOneFile(file: File, replaceDocId?: string): Promise<RagDoc> {
  const fd = new FormData()
  fd.append('files', file)
  if (replaceDocId) fd.append('replace_doc_id', replaceDocId)
  const res = await fetch('/api/rag/ingest', { method: 'POST', body: fd })
  if (!res.ok) throw new Error(`Ingest failed (${res.status})`)
  const data = await res.json()
  const results = (data.results ?? []) as RagDoc[]
  return results[0] ?? { filename: file.name, ext: '', doc_id: '', ingested_at: '', chunks: 0, tables: 0, images: 0, error: 'No result returned' }
}

export async function deleteDocument(docId: string): Promise<boolean> {
  const res = await fetch(`/api/rag/documents/${docId}`, { method: 'DELETE' })
  return res.ok
}

const IMAGE_EXT = new Set(['.jpg', '.jpeg', '.png', '.gif', '.webp'])
export const isImageDoc = (d: RagDoc) => IMAGE_EXT.has(d.ext)
export const docFileUrl = (docId: string) => `/api/rag/documents/${docId}/file`

// Mirrors settings.rag_upload_allowed_extensions on the backend.
export const ACCEPTED_EXTENSIONS =
  '.txt,.md,.markdown,.rst,.html,.htm,.pdf,.docx,.jpg,.jpeg,.png,.gif,.webp'

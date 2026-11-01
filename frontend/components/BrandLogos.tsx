'use client'
import { useState } from 'react'

/**
 * Shared institutional branding — ORNL + Frontier logos. Used by the chat
 * sidebar and the Syslog Monitor header so the app reads as one product.
 * Each logo hides itself if its file isn't present in /public (no broken icons).
 */
export default function BrandLogos({
  ornlClass = 'h-7',
  frontierClass = 'h-9',
  className = '',
}: {
  ornlClass?: string
  frontierClass?: string
  className?: string
}) {
  const [err, setErr] = useState<Set<string>>(new Set())
  const mark = (id: string) => setErr((p) => new Set(p).add(id))
  if (err.has('ornl') && err.has('frontier')) return null

  return (
    <div className={`flex items-center gap-3 ${className}`}>
      {!err.has('ornl') && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src="/ornl_logo_green.svg" alt="Oak Ridge National Laboratory"
             className={`${ornlClass} w-auto`} onError={() => mark('ornl')} />
      )}
      {!err.has('frontier') && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src="/frontier_logo.webp" alt="Frontier"
             className={`${frontierClass} w-auto`} onError={() => mark('frontier')} />
      )}
    </div>
  )
}

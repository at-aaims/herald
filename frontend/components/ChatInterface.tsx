'use client'
import { useChat } from '@ai-sdk/react'
import { DefaultChatTransport } from 'ai'
import { useRef, useEffect, useState, useMemo, type PointerEvent as ReactPointerEvent } from 'react'
import { Send, Square } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ToolCallCard from './ToolCallCard'

interface Props {
  enabledTools: string[]
}

export default function ChatInterface({ enabledTools }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [input, setInput] = useState('')
  // Hide the landing Frontier logo if /frontier-logo.png isn't present yet.
  const [landingLogoFailed, setLandingLogoFailed] = useState(false)

  // Shell-style history recall: Up/Down cycle through previously sent
  // messages when the caret is at the start/end of the box (so normal
  // multi-line cursor movement inside a draft still works). historyIndex
  // -1 means "not browsing" (i.e. showing the live draft); draftRef holds
  // whatever was typed before Up was first pressed, so Down can restore it.
  const [sentHistory, setSentHistory] = useState<string[]>([])
  const [historyIndex, setHistoryIndex] = useState(-1)
  const draftRef = useRef('')

  // useChat captures the transport once on mount, so transports rebuilt from
  // enabledTools changes don't propagate. Pass body per-call via sendMessage's
  // options instead — that's the only reliable way to forward fresh state.
  const transport = useMemo(
    () => new DefaultChatTransport({ api: '/api/chat' }),
    [],
  )

  const { messages, sendMessage, status, error, stop } = useChat({ transport })
  // An in-band stream error (e.g. the orchestrator's API call failed --
  // wrong/unreachable endpoint, no VPN, rate limit) doesn't reliably settle
  // `status` back to 'ready'. Without `&& !error` here, that leaves `busy`
  // stuck true forever: the "thinking" dots never stop, the error message
  // below stays hidden behind its own `!busy` guard, and the input/Stop
  // button stay locked -- a real request that already finished (with an
  // error) looks identical to one still silently hanging.
  const busy = status !== 'ready' && !error

  // Draggable width for AI bubbles that show a tool-call card. One shared
  // value across all tool messages — drag any handle, all chart cards snap.
  // Persisted to localStorage so it survives reloads.
  const DEFAULT_TOOL_WIDTH = 1152 // ~max-w-6xl
  const MIN_TOOL_WIDTH = 480
  const MAX_TOOL_WIDTH = 1800
  const STORAGE_KEY = 'herald.toolBubbleWidth'
  const [toolWidth, setToolWidth] = useState<number>(() => {
    if (typeof window === 'undefined') return DEFAULT_TOOL_WIDTH
    const raw = window.localStorage.getItem(STORAGE_KEY)
    const n = raw ? Number(raw) : NaN
    return Number.isFinite(n) && n >= MIN_TOOL_WIDTH && n <= MAX_TOOL_WIDTH ? n : DEFAULT_TOOL_WIDTH
  })
  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, String(toolWidth))
    }
  }, [toolWidth])
  const dragRef = useRef<{ startX: number; startW: number } | null>(null)
  const onDragStart = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startW: toolWidth }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onDragMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return
    const dx = e.clientX - dragRef.current.startX
    setToolWidth(Math.min(MAX_TOOL_WIDTH, Math.max(MIN_TOOL_WIDTH, dragRef.current.startW + dx)))
  }
  const onDragEnd = (e: ReactPointerEvent<HTMLDivElement>) => {
    dragRef.current = null
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId)
    }
  }
  const onDragReset = () => setToolWidth(DEFAULT_TOOL_WIDTH)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const text = input.trim()
    if (!text || busy) return
    sendMessage({ text }, { body: { enabledTools } })
    setInput('')
    setSentHistory((h) => (h[h.length - 1] === text ? h : [...h, text]))
    setHistoryIndex(-1)
    draftRef.current = ''
  }

  const recallHistory = (direction: 'up' | 'down', el: HTMLTextAreaElement) => {
    if (sentHistory.length === 0) return false
    if (direction === 'up') {
      if (el.selectionStart !== 0 || el.selectionEnd !== 0) return false
      if (historyIndex === -1) draftRef.current = input
      const nextIndex = historyIndex === -1 ? sentHistory.length - 1 : Math.max(0, historyIndex - 1)
      setHistoryIndex(nextIndex)
      setInput(sentHistory[nextIndex])
    } else {
      if (historyIndex === -1) return false
      if (el.selectionStart !== input.length || el.selectionEnd !== input.length) return false
      const nextIndex = historyIndex + 1
      if (nextIndex >= sentHistory.length) {
        setHistoryIndex(-1)
        setInput(draftRef.current)
      } else {
        setHistoryIndex(nextIndex)
        setInput(sentHistory[nextIndex])
      }
    }
    // Move the caret to the end after the value swaps in (next paint).
    requestAnimationFrame(() => {
      const len = el.value.length
      el.setSelectionRange(len, len)
    })
    return true
  }

  const isEmpty = messages.length === 0

  return (
    <div className="flex flex-col h-full">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto scroll-area px-4 py-6 space-y-6">
        {isEmpty && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-4 text-herald-muted">
            {!landingLogoFailed && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src="/frontier_logo.webp"
                alt="Frontier"
                className="h-28 md:h-36 w-auto mb-3"
                onError={() => setLandingLogoFailed(true)}
              />
            )}
            <p className="text-2xl font-semibold text-herald-text">HERALD</p>
            <p className="text-xs uppercase tracking-[0.2em] text-herald-text-dim -mt-2">
              HPC Ensemble Reasoning, Analytics &amp; LLM-Driven Diagnostics
            </p>
            <p className="text-sm max-w-sm">
              Ask about HPC job data, energy usage, system policies, or predict
              resource consumption for upcoming jobs.
            </p>
            <div className="flex flex-wrap gap-2 justify-center mt-2">
              {[
                'How many GPU jobs ran last month?',
                'What are the leadership-class job requirements?',
                'Predict energy for a PHY job on 2048 nodes for 4 hours',
              ].map((ex) => (
                <button
                  key={ex}
                  onClick={() => setInput(ex)}
                  className="px-3 py-1.5 rounded-full border border-herald-border text-xs text-herald-text-dim hover:border-herald-accent hover:text-herald-text transition-colors"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => {
          // AI replies with a tool-call card (SQL result + chart) need room
          // to breathe. Plain-text replies stay at the narrower reading width.
          const hasToolPart = msg.role !== 'user' && msg.parts.some((p) => p.type.startsWith('tool-'))
          return (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              style={hasToolPart ? { maxWidth: toolWidth } : undefined}
              className={[
                'relative w-full rounded-2xl px-4 py-3 text-sm',
                hasToolPart ? '' : 'max-w-2xl',
                msg.role === 'user'
                  ? 'bg-herald-accent text-white ml-12 rounded-br-sm'
                  : 'bg-herald-surface border border-herald-border text-herald-text mr-12 rounded-bl-sm',
              ].join(' ')}
            >
              {hasToolPart && (
                <div
                  onPointerDown={onDragStart}
                  onPointerMove={onDragMove}
                  onPointerUp={onDragEnd}
                  onPointerCancel={onDragEnd}
                  onDoubleClick={onDragReset}
                  className="absolute top-2 bottom-2 -right-1.5 w-3 cursor-ew-resize rounded-full hover:bg-herald-accent/60 active:bg-herald-accent transition-colors z-10"
                  title={`Drag to resize · double-click to reset · ${toolWidth}px`}
                />
              )}
              <p
                className={`text-xs font-medium mb-1.5 ${msg.role === 'user' ? 'text-blue-200' : 'text-herald-text-dim'}`}
              >
                {msg.role === 'user' ? 'You' : 'HERALD'}
              </p>

              {/* AI SDK v5: messages have `parts` — render each based on type */}
              <div className="space-y-2">
                {msg.parts.map((part, i) => {
                  // Plain text — render markdown for AI, plain for user
                  if (part.type === 'text') {
                    if (msg.role === 'user') {
                      return (
                        <div key={i} className="whitespace-pre-wrap leading-relaxed">
                          {part.text}
                        </div>
                      )
                    }
                    return (
                      <div key={i} className="ai-prose leading-relaxed">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {part.text}
                        </ReactMarkdown>
                      </div>
                    )
                  }

                  // Tool call (type is `tool-<name>`)
                  if (part.type.startsWith('tool-')) {
                    return <ToolCallCard key={i} part={part as any} />
                  }

                  return null
                })}
              </div>
            </div>
          </div>
          )
        })}

        {busy && (
          <div className="flex justify-start">
            <div className="bg-herald-surface border border-herald-border rounded-2xl rounded-bl-sm px-4 py-3">
              <div className="flex gap-1 items-center h-4">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-herald-accent animate-bounce"
                    style={{ animationDelay: `${i * 150}ms` }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="flex justify-start">
            <div className="max-w-2xl bg-amber-500/10 border border-amber-500/40 text-amber-200 rounded-2xl rounded-bl-sm px-4 py-3 text-sm">
              <p className="font-medium text-amber-100">I couldn’t complete that request.</p>
              <p className="mt-1 text-amber-200/90">
                {error?.message || 'This question may not be answerable with the currently enabled '
                  + 'tools, or the request hit a processing limit. Try rephrasing it, or enable a '
                  + 'relevant sub-agent in the sidebar and ask again. If no model backend is '
                  + 'configured yet, visit Setup in the sidebar.'}
              </p>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-herald-border bg-herald-bg px-4 py-3">
        <form onSubmit={submit} className="flex gap-2 items-end max-w-3xl mx-auto">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value)
              // Any manual edit exits history browsing — start a fresh draft.
              if (historyIndex !== -1) setHistoryIndex(-1)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                submit(e as any)
                return
              }
              if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
                const handled = recallHistory(e.key === 'ArrowUp' ? 'up' : 'down', e.currentTarget)
                if (handled) e.preventDefault()
              }
            }}
            placeholder="Ask about HPC jobs, energy, policies, or predictions…"
            rows={1}
            disabled={busy}
            className={[
              'flex-1 resize-none bg-herald-surface border border-herald-border rounded-xl',
              'px-4 py-3 text-sm text-herald-text placeholder:text-herald-muted',
              'focus:outline-none focus:border-herald-accent transition-colors',
              'max-h-40 scroll-area disabled:opacity-50',
            ].join(' ')}
            style={{ minHeight: '48px' }}
          />
          <button
            type={busy ? 'button' : 'submit'}
            onClick={busy ? () => stop() : undefined}
            disabled={!busy && !input.trim()}
            title={busy ? 'Stop' : 'Send'}
            className={[
              'flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center',
              'bg-herald-accent hover:bg-herald-accent-hover transition-colors',
              'disabled:opacity-40 disabled:cursor-not-allowed',
            ].join(' ')}
          >
            {busy ? (
              <Square size={14} className="text-white" fill="currentColor" />
            ) : (
              <Send size={16} className="text-white" />
            )}
          </button>
        </form>
        <p className="text-center text-xs text-herald-muted mt-2">
          Shift+Enter for new line · Enter to send · ↑/↓ to recall previous messages
        </p>
      </div>
    </div>
  )
}

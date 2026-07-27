'use client'
import { useEffect, useRef, useState } from 'react'
import { RotateCcw, Send, Paperclip } from 'lucide-react'
import type { BotBranding, DesignConfig, ChatSettings } from '@/types'

export interface PreviewMessage {
  id: string
  role: 'bot' | 'user'
  content: string
  choices?: { label: string; value: string }[]
  time?: string
}

interface ChatThemeProps {
  branding: BotBranding
  design: DesignConfig
  chatSettings: ChatSettings
  messages?: PreviewMessage[]
  typing?: boolean
  interactive?: boolean
  onSend?: (text: string) => void
  onRestart?: () => void
  className?: string
}

const DEMO_MESSAGES: PreviewMessage[] = [
  { id: 'm1', role: 'bot', content: "Hi there! 👋 I'm here to help — ask me anything.", time: '9:41 AM' },
  { id: 'm2', role: 'user', content: 'What can you do?', time: '9:41 AM' },
  { id: 'm3', role: 'bot', content: 'I can answer questions, pull from your knowledge base, and route to a human when needed.', time: '9:42 AM' },
]

/** Renders the fully themed chat surface — background, bubbles, typography,
 * radius, shadows, glassmorphism, and every Deployment Setting toggle.
 * Used both as the builder's instant live preview and (via the same props
 * shape) on the public /chat/[slug] page, so "what you see is what ships". */
export function ChatTheme({
  branding, design, chatSettings, messages, typing, interactive, onSend, onRestart, className = '',
}: ChatThemeProps) {
  const [draft, setDraft] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const list = messages ?? DEMO_MESSAGES
  const isLight = design.mode === 'light'

  useEffect(() => {
    if (chatSettings.enable_auto_scroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [list.length, typing, chatSettings.enable_auto_scroll])

  const bg = design.background_gradient || design.background_color || (isLight ? '#ffffff' : '#070708')
  const fg = isLight ? '#0a0a0a' : '#ffffff'
  const radius = design.border_radius ?? 16
  const font = design.font_family || 'Inter, system-ui, sans-serif'
  const fontSize = design.font_size ?? 15
  const glass = !!design.glassmorphism
  const shadow = design.shadows !== false

  function submit() {
    const v = draft.trim()
    if (!v) return
    onSend?.(v)
    setDraft('')
  }

  return (
    <div
      className={`tb-chat-theme flex flex-col overflow-hidden ${className}`}
      style={{
        background: bg,
        backgroundImage: design.background_image ? `url(${design.background_image})` : undefined,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        color: fg,
        fontFamily: font,
        fontSize,
        borderRadius: radius,
        boxShadow: shadow ? '0 12px 40px rgba(0,0,0,0.28)' : 'none',
      }}
    >
      {/* Header */}
      <div
        className="tb-anim-fade-up flex items-center gap-2.5 px-4 py-3 flex-shrink-0"
        style={{
          borderBottom: `1px solid ${isLight ? 'rgba(0,0,0,0.08)' : 'rgba(255,255,255,0.08)'}`,
          background: glass ? (isLight ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.25)') : 'transparent',
          backdropFilter: glass ? 'blur(12px)' : undefined,
        }}
      >
        {chatSettings.show_bot_logo && (branding.logo_url || branding.avatar_url) && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={branding.logo_url || branding.avatar_url || ''}
            alt=""
            className="w-6 h-6 rounded-md object-cover flex-shrink-0"
            style={{ boxShadow: shadow ? '0 2px 8px rgba(0,0,0,0.2)' : undefined }}
          />
        )}
        {chatSettings.show_bot_name && (
          <span className="text-[13px] font-semibold truncate">{branding.bot_name || 'Chatbot'}</span>
        )}
        <div className="flex-1" />
        {chatSettings.show_restart_button && (
          <button
            onClick={onRestart}
            className="tb-hover-lift p-1.5 rounded-md opacity-50 hover:opacity-100 transition"
            title="Restart conversation"
          >
            <RotateCcw size={13} />
          </button>
        )}
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-2.5 min-h-0">
        {list.length === 0 && (
          <div className="tb-anim-fade-up m-auto text-center px-4">
            <p className="text-[15px] font-semibold mb-1">{branding.welcome_title}</p>
            <p className="text-[13px] opacity-60">{branding.welcome_description}</p>
          </div>
        )}
        {list.map((m, i) => (
          <div
            key={m.id}
            className={`tb-anim-msg-in flex flex-col ${m.role === 'user' ? 'items-end self-end' : 'items-start self-start'}`}
            style={{ animationDelay: `${Math.min(i, 6) * 30}ms`, maxWidth: '85%' }}
          >
            <div
              className="px-3.5 py-2.5 leading-relaxed"
              style={{
                background: m.role === 'user'
                  ? (design.user_bubble_color || branding.theme_color)
                  : (design.bot_bubble_color || (isLight ? '#f2f2f5' : '#161616')),
                color: m.role === 'user' ? '#fff' : fg,
                borderRadius: radius,
                borderBottomRightRadius: m.role === 'user' ? 4 : radius,
                borderBottomLeftRadius: m.role === 'bot' ? 4 : radius,
                backdropFilter: glass && m.role === 'bot' ? 'blur(10px)' : undefined,
                boxShadow: shadow ? '0 2px 10px rgba(0,0,0,0.12)' : undefined,
                wordBreak: 'break-word',
              }}
            >
              {m.content}
            </div>
            {m.choices && m.choices.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {m.choices.map((c) => (
                  <button
                    key={c.value}
                    className="tb-hover-lift text-[12px] px-3 py-1.5 rounded-full border transition"
                    style={{ borderColor: `${branding.theme_color}66`, color: branding.theme_color }}
                    onClick={() => onSend?.(c.value)}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
            )}
            {chatSettings.show_timestamp && m.time && (
              <span className="text-[10px] opacity-35 mt-1 px-1">{m.time}</span>
            )}
          </div>
        ))}
        {typing && chatSettings.show_typing_indicator && (
          <div
            className="tb-anim-fade-up self-start px-3.5 py-3 flex items-center gap-1"
            style={{
              background: design.bot_bubble_color || (isLight ? '#f2f2f5' : '#161616'),
              borderRadius: radius,
              borderBottomLeftRadius: 4,
            }}
          >
            <span className="typing-dot w-1.5 h-1.5 rounded-full" style={{ background: `${fg}88` }} />
            <span className="typing-dot w-1.5 h-1.5 rounded-full" style={{ background: `${fg}88` }} />
            <span className="typing-dot w-1.5 h-1.5 rounded-full" style={{ background: `${fg}88` }} />
          </div>
        )}
      </div>

      {/* Footer */}
      <div
        className="flex items-center gap-2 px-3 py-3 flex-shrink-0"
        style={{ borderTop: `1px solid ${isLight ? 'rgba(0,0,0,0.08)' : 'rgba(255,255,255,0.08)'}` }}
      >
        {chatSettings.enable_file_upload && (
          <button className="tb-hover-lift p-2 rounded-lg opacity-50 hover:opacity-100 transition flex-shrink-0">
            <Paperclip size={15} />
          </button>
        )}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }}
          disabled={!interactive}
          placeholder="Type a message…"
          className="flex-1 min-w-0 px-3.5 py-2.5 text-[13px] outline-none transition-colors"
          style={{
            background: design.bot_bubble_color || (isLight ? '#f2f2f5' : '#161616'),
            color: fg,
            borderRadius: Math.max(radius - 4, 6),
            border: '1px solid transparent',
          }}
        />
        <button
          onClick={submit}
          disabled={!interactive}
          className="tb-hover-lift p-2.5 rounded-lg flex-shrink-0 transition disabled:opacity-40"
          style={{ background: branding.theme_color, color: '#fff', borderRadius: Math.max(radius - 4, 6) }}
        >
          <Send size={14} />
        </button>
      </div>

      {chatSettings.show_powered_by && (
        <div className="text-center text-[10px] opacity-30 pb-2 flex-shrink-0">Powered by ThunderBots</div>
      )}
    </div>
  )
}

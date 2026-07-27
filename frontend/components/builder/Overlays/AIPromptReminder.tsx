'use client'
// ============================================================
// AI Chatbot by Prompt — Builder reminder
//
// A small glowing nudge shown inside the Builder every 10 minutes,
// pointing users at /create-with-ai. Purely presentational and
// client-side: no polling, no backend calls, no effect on Builder
// state, Nodes, or the AI Agent runtime. Once the user has
// generated a chatbot via AI Prompt (ever, tracked in
// localStorage) it never shows again. Dismissing it hides it for
// the rest of the current browser session (sessionStorage).
// ============================================================
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Sparkles, X } from 'lucide-react'
import {
  hasGeneratedChatbotViaAI, isReminderDismissedForSession, dismissReminderForSession,
} from '@/lib/ai-create/storage'

const INTERVAL_MS = 10 * 60 * 1000 // 10 minutes
const INITIAL_DELAY_MS = 10 * 60 * 1000 // first nudge also waits a full interval

export function AIPromptReminder() {
  const router = useRouter()
  const [visible, setVisible] = useState(false)
  const [suppressed, setSuppressed] = useState(false)

  useEffect(() => {
    // Never show if the user already generated a chatbot via AI Prompt,
    // or already dismissed the reminder earlier in this session.
    if (hasGeneratedChatbotViaAI() || isReminderDismissedForSession()) {
      setSuppressed(true)
      return
    }

    const tick = () => {
      if (hasGeneratedChatbotViaAI() || isReminderDismissedForSession()) {
        setSuppressed(true)
        return
      }
      setVisible(true)
    }

    const timer = setInterval(tick, INTERVAL_MS)
    const initial = setTimeout(tick, INITIAL_DELAY_MS)
    return () => { clearInterval(timer); clearTimeout(initial) }
  }, [])

  if (suppressed || !visible) return null

  const dismiss = () => {
    setVisible(false)
    dismissReminderForSession()
    setSuppressed(true)
  }

  return (
    <div className="absolute top-5 right-5 z-30 tb-anim-slide-in">
      <div
        className="flex items-center gap-3 pl-4 pr-2.5 py-2.5 rounded-2xl border border-[#6366f1]/40 bg-[#111018]/95 backdrop-blur-md shadow-[0_0_24px_rgba(99,102,241,0.35)]"
      >
        <Sparkles size={14} className="text-[#a5b4fc] flex-shrink-0" />
        <span className="text-[11.5px] font-medium text-white/85 whitespace-nowrap">
          Create your chatbot with AI Prompt.
        </span>
        <button
          onClick={() => router.push('/create-with-ai')}
          className="text-[11px] font-semibold px-3 py-1.5 rounded-lg bg-[#6366f1] hover:bg-[#5558e8] text-white transition whitespace-nowrap"
        >
          Create Now
        </button>
        <button
          onClick={dismiss}
          aria-label="Dismiss"
          className="text-white/30 hover:text-white/70 transition p-1 flex-shrink-0"
        >
          <X size={13} />
        </button>
      </div>
    </div>
  )
}

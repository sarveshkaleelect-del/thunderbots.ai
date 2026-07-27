'use client'
/**
 * AI Call Agent — mode selection landing page — /call-agent
 *
 * v93: Root-cause of the old UX bug — this route used to jump straight into
 * the Phone Number list (now moved, unchanged, to /call-agent/phone), which
 * forced every visitor toward phone verification even if all they wanted
 * was the phone-free website Voice Bubble. This page now asks first:
 *
 *   "Choose your AI Call experience"
 *     -> Web Voice Bubble  -> /call-agent/voice   (no phone number, ever)
 *     -> Phone AI Agent    -> /call-agent/phone   (phone verification lives here only)
 *
 * This page does not call any phone-number or telephony API — it only
 * renders two navigation cards. No existing module is touched.
 */
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Globe, Phone, Check, ArrowRight, Bot, PhoneCall, FileStack, Zap } from 'lucide-react'
import { getToken } from '@/lib/api/auth'
import { voiceAgentsApi } from '@/lib/api/callAgent'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { SubPageBar } from '@/components/ui/TopBar'
import { CallAgentNav } from '@/components/callAgent/CallAgentNav'

interface ModeCard {
  href: string
  icon: React.ReactNode
  emoji: string
  title: string
  subtitle: string
  features: string[]
  cta: string
  accent: 'cyan' | 'violet'
}

const MODES: ModeCard[] = [
  {
    href: '/call-agent/voice',
    icon: <Globe size={20} className="text-cyan-300" />,
    emoji: '🌐',
    title: 'Web Voice Bubble',
    subtitle: 'Talk with visitors directly from your website.',
    features: [
      'No phone number required',
      'Website voice widget',
      'AI conversations',
      'Knowledge Base',
      'Voice settings',
    ],
    cta: 'Continue',
    accent: 'cyan',
  },
  {
    href: '/call-agent/phone',
    icon: <Phone size={20} className="text-[#a5b4fc]" />,
    emoji: '📞',
    title: 'Phone AI Agent',
    subtitle: 'Answer real phone calls using AI.',
    features: [
      'Incoming & outgoing calls',
      'Phone verification',
      'Call recording',
      'Human handoff',
      'Analytics',
    ],
    cta: 'Setup Phone',
    accent: 'violet',
  },
]

export default function CallAgentLandingPage() {
  const router = useRouter()

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) router.replace('/login')
  }, [router])

  const { data: dashboard } = useQuery({
    queryKey: ['voice-agent-dashboard'],
    queryFn: voiceAgentsApi.dashboard,
  })

  const stats = [
    { label: 'Voice Agents', value: dashboard?.total_agents ?? '—', icon: Bot },
    { label: 'Enabled', value: dashboard?.enabled_agents ?? '—', icon: Zap },
    { label: 'Numbers bound', value: dashboard?.bound_phone_numbers ?? '—', icon: Phone },
    { label: 'Total calls', value: dashboard?.total_calls ?? '—', icon: PhoneCall },
    { label: 'Knowledge docs', value: dashboard?.total_knowledge_documents ?? '—', icon: FileStack },
  ]

  return (
    <div className="tb2-shell">
      <SubPageBar crumb="AI Call Agent" crumbIcon={<Phone size={13} className="text-cyan-300/70" />} />
      <CallAgentNav />

      <div className="max-w-6xl mx-auto px-3 sm:px-6 py-6 grid grid-cols-2 sm:grid-cols-5 gap-3">
        {stats.map(s => (
          <Card key={s.label} className="p-4">
            <s.icon size={14} className="text-cyan-300/70 mb-2" />
            <p className="text-lg font-bold text-white">{s.value}</p>
            <p className="text-[10px] text-white/35 uppercase tracking-wide mt-0.5">{s.label}</p>
          </Card>
        ))}
      </div>

      <div className="max-w-3xl mx-auto px-6 pb-10 space-y-6">
        <div className="tb2-rise text-center space-y-1.5">
          <h1 className="text-xl font-bold text-white">Choose your AI Call experience</h1>
          <p className="text-sm text-white/35">
            Pick the mode that fits — you can set up both later, independently.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          {MODES.map(mode => (
            <Card key={mode.href} className="p-5 flex flex-col gap-4 tb2-rise" hover>
              <div className="flex items-center gap-3">
                <div
                  className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 border ${
                    mode.accent === 'cyan'
                      ? 'bg-cyan-500/10 border-cyan-500/20'
                      : 'bg-[#6366f1]/10 border-[#6366f1]/25'
                  }`}
                >
                  {mode.icon}
                </div>
                <div className="min-w-0">
                  <h2 className="text-sm font-bold text-white/90 flex items-center gap-1.5">
                    <span aria-hidden>{mode.emoji}</span> {mode.title}
                  </h2>
                  <p className="text-xs text-white/40 mt-0.5">{mode.subtitle}</p>
                </div>
              </div>

              <ul className="space-y-1.5 flex-1">
                {mode.features.map(f => (
                  <li key={f} className="flex items-center gap-2 text-xs text-white/55">
                    <Check size={12} className={mode.accent === 'cyan' ? 'text-cyan-300/80' : 'text-[#a5b4fc]/80'} />
                    {f}
                  </li>
                ))}
              </ul>

              <Button
                variant={mode.accent === 'cyan' ? 'primary' : 'secondary'}
                icon={<ArrowRight size={13} />}
                className="w-full justify-center"
                onClick={() => router.push(mode.href)}
              >
                {mode.cta}
              </Button>
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}

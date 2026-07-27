'use client'
/**
 * AI Call Agent — Settings — /call-agent/settings
 *
 * NEW (Voice AI Part 5). Module-level hub — per-agent settings live on
 * each Voice Agent's own tabs (/call-agent/agents/[id]), and per-number
 * call routing settings live at /call-agent/settings/[id] (unchanged,
 * this static route does not conflict with that dynamic one). This page
 * is the map between the two so nothing gets lost among 12 nav sections.
 */
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Settings, Bot, Phone, ArrowRight } from 'lucide-react'
import { getToken } from '@/lib/api/auth'
import { callAgentApi, voiceAgentsApi } from '@/lib/api/callAgent'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { SubPageBar } from '@/components/ui/TopBar'
import { CallAgentNav } from '@/components/callAgent/CallAgentNav'

export default function CallAgentSettingsPage() {
  const router = useRouter()

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) router.replace('/login')
  }, [router])

  const { data: agents = [] } = useQuery({ queryKey: ['voice-agents'], queryFn: voiceAgentsApi.list })
  const { data: numbers = [] } = useQuery({ queryKey: ['call-agent-numbers'], queryFn: callAgentApi.list })

  return (
    <div className="tb2-shell">
      <SubPageBar backHref="/call-agent" crumb="Settings" crumbIcon={<Settings size={13} className="text-cyan-300/70" />} />
      <CallAgentNav />

      <div className="max-w-3xl mx-auto px-3 sm:px-6 py-8 space-y-5">
        <div className="tb2-rise">
          <h1 className="text-xl font-bold text-white">Settings</h1>
          <p className="text-sm text-white/35 mt-1">
            Each Voice Agent has its own General, Instructions, Knowledge Base, and Voice settings. Each phone number has its own call routing settings.
          </p>
        </div>

        <Card className="p-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <Bot size={16} className="text-cyan-300/70 flex-shrink-0" />
            <div className="min-w-0">
              <p className="text-sm text-white/80">Voice Agent settings</p>
              <p className="text-[11px] text-white/35">{agents.length} agent{agents.length === 1 ? '' : 's'} — provider, instructions, voice, advanced</p>
            </div>
          </div>
          <Button size="sm" variant="secondary" icon={<ArrowRight size={12} />} onClick={() => router.push('/call-agent/agents')}>Manage</Button>
        </Card>

        <Card className="p-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <Phone size={16} className="text-[#a5b4fc] flex-shrink-0" />
            <div className="min-w-0">
              <p className="text-sm text-white/80">Phone number call routing</p>
              <p className="text-[11px] text-white/35">{numbers.length} number{numbers.length === 1 ? '' : 's'} — bind a Voice Agent, business hours, recording</p>
            </div>
          </div>
          <Button size="sm" variant="secondary" icon={<ArrowRight size={12} />} onClick={() => router.push('/call-agent/phone')}>Manage</Button>
        </Card>
      </div>
    </div>
  )
}

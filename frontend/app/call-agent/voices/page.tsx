'use client'
/**
 * AI Call Agent — Voices — /call-agent/voices
 *
 * NEW (Voice AI Part 5). Read-only gallery of every TTS voice available
 * across configured providers, reusing the existing GET /call-agent/voices
 * catalog (backend/app/api/v1/call_agent_calls.py). Voice selection itself
 * happens per Voice Agent on its own Voice tab (/call-agent/agents/[id]).
 */
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Mic2, KeyRound } from 'lucide-react'
import { getToken } from '@/lib/api/auth'
import { callAgentApi } from '@/lib/api/callAgent'
import { Card, Badge } from '@/components/ui/Card'
import { SubPageBar } from '@/components/ui/TopBar'
import { CallAgentNav } from '@/components/callAgent/CallAgentNav'
import { PageLoader, ErrorState, EmptyState } from '@/components/ui/States'
import { getErrorMessage } from '@/lib/utils/errors'

export default function VoicesPage() {
  const router = useRouter()

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) router.replace('/login')
  }, [router])

  const { data: providers = [], isLoading, error, refetch } = useQuery({
    queryKey: ['call-voices'],
    queryFn: callAgentApi.listVoices,
  })

  return (
    <div className="tb2-shell">
      <SubPageBar backHref="/call-agent" crumb="Voices" crumbIcon={<Mic2 size={13} className="text-cyan-300/70" />} />
      <CallAgentNav />

      <div className="max-w-5xl mx-auto px-3 sm:px-6 py-8 space-y-6">
        <div className="tb2-rise">
          <h1 className="text-xl font-bold text-white">Voices</h1>
          <p className="text-sm text-white/35 mt-1">Every text-to-speech voice available across your configured providers.</p>
        </div>

        {isLoading ? (
          <PageLoader />
        ) : error ? (
          <ErrorState title="Couldn't load voices" description={getErrorMessage(error)} onRetry={() => refetch()} />
        ) : providers.length === 0 ? (
          <EmptyState icon={<Mic2 size={22} />} title="No voice providers configured" />
        ) : (
          <div className="space-y-6">
            {providers.map(provider => (
              <div key={provider.name}>
                <div className="flex items-center gap-2 mb-2.5">
                  <h2 className="text-sm font-semibold text-white/80">{provider.name}</h2>
                  {provider.configured ? (
                    <Badge tone="success" dot>Configured</Badge>
                  ) : (
                    <Badge tone="warning"><KeyRound size={9} className="mr-0.5" />No API key</Badge>
                  )}
                </div>
                {provider.voices.length === 0 ? (
                  <p className="text-xs text-white/25">No voices listed for this provider.</p>
                ) : (
                  <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                    {provider.voices.map(voice => (
                      <Card key={voice.id} className="p-3 flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-sm text-white/80 truncate">{voice.name}</p>
                          <p className="text-[10px] text-white/30">{voice.gender}</p>
                        </div>
                      </Card>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

'use client'
import { Suspense, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Key, Plus, Trash2, Check, X, Loader2,
  Wifi, WifiOff, Eye, EyeOff, Settings,
} from 'lucide-react'
import { settingsApi } from '@/lib/api/settings'
import { getErrorMessage } from '@/lib/utils/errors'
import type { UserAPIKey, AIProvider } from '@/types'
import { Card, Badge } from '@/components/ui/Card'
import { Button, IconButton } from '@/components/ui/Button'
import { FieldLabel, Input } from '@/components/ui/Field'
import { SubPageBar } from '@/components/ui/TopBar'
import { PageLoader, ErrorState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { cn } from '@/lib/utils/cn'

const PROVIDER_META: Record<string, { color: string; description: string; keyLabel: string; docsUrl: string }> = {
  gemini:     { color: '#4285f4', description: 'Gemini 2.5 Pro, Flash', keyLabel: 'API Key', docsUrl: 'https://aistudio.google.com/apikey' },
  elevenlabs:   { color: '#000000', description: 'Voice Responses — ElevenLabs TTS', keyLabel: 'API Key', docsUrl: 'https://elevenlabs.io/app/settings/api-keys' },
  azure_speech: { color: '#0078d4', description: 'Voice Responses — Azure Speech TTS', keyLabel: 'API Key', docsUrl: 'https://portal.azure.com' },
  google_tts:   { color: '#4285f4', description: 'Voice Responses — Google Cloud TTS', keyLabel: 'API Key', docsUrl: 'https://console.cloud.google.com/apis/credentials' },
}

// Voice-only providers have no ai_engine chat entry, so they aren't part of
// settingsApi.listProviders() — they're listed here statically and rendered
// with the same ProviderRow used for AI providers. Gemini TTS reuses the
// "gemini" key saved above (same vendor, same key).
const VOICE_ONLY_PROVIDERS: AIProvider[] = [
  { id: 'elevenlabs',   name: 'ElevenLabs',       requires_key: true, models: [], default: '', configured: false },
  { id: 'azure_speech', name: 'Azure Speech',     requires_key: true, models: [], default: '', configured: false },
  { id: 'google_tts',   name: 'Google Cloud TTS', requires_key: true, models: [], default: '', configured: false },
]

function ProviderRow({
  provider, savedKey, onKeySaved,
}: {
  provider: AIProvider
  savedKey?: UserAPIKey
  onKeySaved?: () => void
}) {
  const qc = useQueryClient()
  const { toast } = useToast()
  const meta = PROVIDER_META[provider.id] || { color: '#6366f1', description: '', keyLabel: 'API Key', docsUrl: '#' }

  const [expanded, setExpanded] = useState(false)
  const [inputVal, setInputVal] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [label, setLabel] = useState(savedKey?.label || '')
  const [baseUrl, setBaseUrl] = useState(savedKey?.base_url || '')
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const isAzureSpeech = provider.id === 'azure_speech'

  const addMutation = useMutation({
    mutationFn: () => settingsApi.addKey({
      provider: provider.id,
      api_key: inputVal,
      label,
      base_url: isAzureSpeech ? baseUrl : undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['api-keys'] })
      qc.invalidateQueries({ queryKey: ['providers'] })
      setExpanded(false)
      setInputVal('')
      setTestResult(null)
      onKeySaved?.()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => settingsApi.deleteKey(savedKey!.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['api-keys'] })
      qc.invalidateQueries({ queryKey: ['providers'] })
    },
    // ROOT CAUSE FIX (silent failure): a failed delete previously left the
    // key row exactly as it was with zero feedback — indistinguishable from
    // the button not having been clicked at all.
    onError: err => toast('error', getErrorMessage(err, 'Could not remove this key.')),
  })

  const handleTest = async () => {
    if (!savedKey) return
    setTesting(true)
    setTestResult(null)
    try {
      const result = await settingsApi.testKey(savedKey.id)
      setTestResult({
        ok: result.ok,
        message: result.ok
          ? `Connected · ${result.latency_ms}ms${result.models ? ` · ${result.models.length} models` : ''}`
          : result.error || 'Connection failed — the provider rejected the request.',
      })
      qc.invalidateQueries({ queryKey: ['api-keys'] })
    } catch (err) {
      setTestResult({ ok: false, message: getErrorMessage(err, 'Could not reach the backend to run the test.') })
    } finally {
      setTesting(false)
    }
  }

  const isConfigured = !!savedKey

  return (
    <Card className={cn('overflow-hidden', isConfigured && 'border-white/[0.14]')}>
      <div className="flex items-center gap-3 p-4">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 text-xs font-bold"
          style={{ background: `${meta.color}15`, border: `1px solid ${meta.color}25`, color: meta.color }}
        >
          {provider.name.slice(0, 2).toUpperCase()}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-white/80">{provider.name}</span>
            {isConfigured && savedKey?.is_valid && <Badge tone="success">Valid</Badge>}
            {isConfigured && !savedKey?.is_valid && <Badge tone="warning">Untested</Badge>}
            {!isConfigured && <Badge tone="default">Not configured</Badge>}
          </div>
          <p className="text-[11px] text-white/30 mt-0.5 truncate">
            {isConfigured && savedKey?.key_preview
              ? `${meta.keyLabel}: ${savedKey.key_preview}`
              : meta.description}
          </p>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {isConfigured && (
            <>
              <button
                onClick={handleTest}
                disabled={testing}
                className="flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-lg tb2-btn-ghost
                           bg-white/[0.04] hover:bg-white/[0.08] border border-white/10
                           text-white/50 hover:text-white/80 transition disabled:opacity-40"
              >
                {testing
                  ? <Loader2 size={10} className="animate-spin" />
                  : savedKey?.is_valid ? <Wifi size={10} /> : <WifiOff size={10} />
                }
                Test
              </button>
              <IconButton aria-label="Remove key" variant="danger" onClick={() => deleteMutation.mutate()}>
                <Trash2 size={13} />
              </IconButton>
            </>
          )}

          <button
            onClick={() => setExpanded(e => !e)}
            className="tb2-btn-ghost flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-lg
                       bg-[#6366f1]/10 hover:bg-[#6366f1]/20 border border-[#6366f1]/20
                       text-[#a5b4fc] transition"
          >
            <Plus size={10} />
            {isConfigured ? 'Update' : 'Add Key'}
          </button>
        </div>
      </div>

      {testResult && (
        <div className={cn(
          'mx-4 mb-3 flex items-center gap-2 text-[11px] px-3 py-2 rounded-lg tb2-rise',
          testResult.ok
            ? 'bg-emerald-500/8 border border-emerald-500/20 text-emerald-400'
            : 'bg-red-500/8 border border-red-500/20 text-red-400'
        )}>
          {testResult.ok ? <Check size={11} /> : <X size={11} />}
          {testResult.message}
        </div>
      )}

      {expanded && (
        <div className="px-4 pb-4 border-t border-white/[0.06] pt-4 space-y-3 tb2-rise">
          <div>
            <FieldLabel>{meta.keyLabel}</FieldLabel>
            <div className="relative">
              <Input
                type={showKey ? 'text' : 'password'}
                value={inputVal}
                onChange={e => setInputVal(e.target.value)}
                placeholder={`Paste your ${provider.name} API key`}
                autoFocus
                className="pr-10 font-mono"
              />
              <button
                type="button"
                onClick={() => setShowKey(v => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-white/25 hover:text-white/60 transition"
              >
                {showKey ? <EyeOff size={13} /> : <Eye size={13} />}
              </button>
            </div>
          </div>

          {isAzureSpeech && (
            <div>
              <FieldLabel>Azure Region</FieldLabel>
              <Input
                type="text"
                value={baseUrl}
                onChange={e => setBaseUrl(e.target.value)}
                placeholder="eastus"
                className="font-mono"
              />
              <p className="text-[10px] text-white/25 mt-1.5">
                The Azure region your Speech resource was created in (e.g. eastus, westeurope).
              </p>
            </div>
          )}

          <div>
            <FieldLabel>Label (optional)</FieldLabel>
            <Input
              type="text"
              value={label}
              onChange={e => setLabel(e.target.value)}
              placeholder="e.g. Production key"
            />
          </div>

          <div className="flex gap-2 pt-1">
            <Button
              variant="secondary"
              size="sm"
              className="flex-1"
              onClick={() => { setExpanded(false); setInputVal(''); setTestResult(null) }}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              className="flex-1"
              loading={addMutation.isPending}
              disabled={!inputVal.trim()}
              onClick={() => addMutation.mutate()}
            >
              Save Key
            </Button>
          </div>

          {addMutation.isError && (
            <p className="text-[11px] text-red-400 -mt-1">
              {getErrorMessage(addMutation.error, 'Could not save this key. Please try again.')}
            </p>
          )}

          <a
            href={meta.docsUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-center text-[10px] text-[#818cf8]/70 hover:text-cyan-300 transition-colors"
          >
            Get your {provider.name} API key →
          </a>
        </div>
      )}
    </Card>
  )
}

function APIKeysPageInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  // If we arrived here via the "AI generation requires an API key" prompt
  // (see /create-with-ai), returnTo tells us where to send the user back
  // to automatically once they've saved a key — no new API Key page, no
  // lost prompt.
  const returnTo = searchParams?.get('returnTo') || null

  const { data: providers = [], isLoading: loadingProviders, error: providersError, refetch: refetchProviders } = useQuery({
    queryKey: ['providers'],
    queryFn: settingsApi.listProviders,
  })

  const { data: savedKeys = [] } = useQuery({
    queryKey: ['api-keys'],
    queryFn: settingsApi.listKeys,
  })

  const keysByProvider = Object.fromEntries(
    (savedKeys as UserAPIKey[]).map(k => [k.provider, k])
  )

  const handleKeySaved = () => {
    if (returnTo) router.push(returnTo)
  }

  return (
    <div className="tb2-shell">
      <SubPageBar crumb="API Keys" crumbIcon={<Settings size={13} />} />

      <main className="max-w-2xl mx-auto px-6 py-10">
        <div className="mb-8 tb2-rise">
          <h1 className="text-xl font-bold text-white">AI Providers</h1>
          <p className="text-sm text-white/35 mt-1">
            {returnTo
              ? "Add a key below to continue — you'll be returned to your AI chatbot prompt automatically."
              : 'Configure providers to power your AI nodes. Keys are encrypted and stored securely.'}
          </p>
        </div>

        {loadingProviders ? (
          <PageLoader />
        ) : providersError ? (
          <ErrorState
            title="Couldn't load AI providers"
            description={getErrorMessage(providersError, 'Check your connection and that the backend is running.')}
            onRetry={() => refetchProviders()}
          />
        ) : (
          <div className="space-y-3">
            {(providers as AIProvider[]).map(provider => (
              <ProviderRow
                key={provider.id}
                provider={provider}
                savedKey={keysByProvider[provider.id]}
                onKeySaved={handleKeySaved}
              />
            ))}
          </div>
        )}

        <div className="mt-10 mb-4 tb2-rise">
          <h2 className="text-sm font-bold text-white/80">Voice Providers</h2>
          <p className="text-[11px] text-white/30 mt-1">
            Optional — only needed for premium Voice Response providers (Deploy Settings →
            Voice Responses, or the Test Chat panel). Browser voice needs no key and isn't listed
            here. Gemini TTS reuses the key saved above.
          </p>
        </div>
        <div className="space-y-3">
          {VOICE_ONLY_PROVIDERS.map(provider => (
            <ProviderRow
              key={provider.id}
              provider={provider}
              savedKey={keysByProvider[provider.id]}
              onKeySaved={handleKeySaved}
            />
          ))}
        </div>

        <Card className="mt-8 p-4">
          <div className="flex items-start gap-3">
            <Key size={13} className="text-white/25 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-xs font-semibold text-white/50 mb-1">Security Note</p>
              <p className="text-[11px] text-white/30 leading-relaxed">
                API keys are encrypted with AES before storage. They are never logged or exposed in responses.
                Only the last 4 characters are shown for identification.
              </p>
            </div>
          </div>
        </Card>
      </main>
    </div>
  )
}

export default function APIKeysPage() {
  return (
    <Suspense fallback={<PageLoader />}>
      <APIKeysPageInner />
    </Suspense>
  )
}

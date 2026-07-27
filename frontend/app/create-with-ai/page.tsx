'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Sparkles, Wand2, AlertCircle, KeyRound, ExternalLink } from 'lucide-react'
import Link from 'next/link'

import { settingsApi } from '@/lib/api/settings'
import { workflowsApi } from '@/lib/api/workflows'
import { getErrorMessage } from '@/lib/utils/errors'
import { cn } from '@/lib/utils/cn'
import type { UserAPIKey, AIProvider } from '@/types'
import type { AIProviderId, GenerationStage, GenerationRetryInfo, GenerationMeta } from '@/lib/thunderguide/types'
import { GENERATION_STAGE_PROGRESS } from '@/lib/thunderguide/types'
import { PROVIDER_LABELS, getSessionKey, setSessionKey } from '@/lib/thunderguide/aiClient'
import { buildWorkflowFromPrompt, isValidGeneratedWorkflow } from '@/lib/thunderguide/aiActions'
import { detectPromptLanguage } from '@/lib/thunderguide/languageDetect'
import { buildGenerationSummary, type GenerationSummary } from '@/lib/thunderguide/summary'
import { ThunderGuideProgress } from '@/components/builder/Panels/ThunderGuideProgress'
import { ThunderGuideSuccessScreen } from '@/components/ai-create/ThunderGuideSuccessScreen'
import { ApiKeyRequiredModal } from '@/components/ai-create/ApiKeyRequiredModal'
import {
  savePromptDraft, loadPromptDraft, clearPromptDraft,
  setPendingImport, markChatbotGeneratedViaAI,
} from '@/lib/ai-create/storage'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { SubPageBar } from '@/components/ui/TopBar'
import { ApiKeyReminder } from '@/components/ui/ApiKeyReminder'
import { useToast } from '@/components/ui/Toast'

const SUPPORTED: AIProviderId[] = ['gemini']
const API_KEYS_SETTINGS_PATH = '/settings/api-keys'
const RETURN_PATH = '/create-with-ai'

/** Derives a short workflow name + description from the free-text prompt. */
function deriveWorkflowMeta(prompt: string): { name: string; description: string } {
  const trimmed = prompt.trim()
  const firstLine = trimmed.split(/\r?\n/)[0] || trimmed
  const name = firstLine.length > 60 ? `${firstLine.slice(0, 57)}...` : (firstLine || 'AI Generated Bot')
  return { name, description: trimmed }
}

export default function CreateWithAIPage() {
  const router = useRouter()
  const { toast } = useToast()

  const { data: providers = [] } = useQuery({ queryKey: ['providers'], queryFn: settingsApi.listProviders })
  const { data: keys = [] } = useQuery({ queryKey: ['api-keys'], queryFn: settingsApi.listKeys })

  const validConfigured = SUPPORTED.filter(p => {
    const k = (keys as UserAPIKey[]).find(key => key.provider === p)
    const providerMeta = (providers as AIProvider[]).find(pr => pr.id === p)
    return !!k && (k.is_valid || providerMeta?.configured)
  })

  const [prompt, setPrompt] = useState('')
  const [selectedProvider, setSelectedProvider] = useState<AIProviderId | null>(null)
  const [sessionTick, setSessionTick] = useState(0)
  const [sessionKeyInput, setSessionKeyInput] = useState('')
  const [showApiKeyModal, setShowApiKeyModal] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stage, setStage] = useState<GenerationStage | null>(null)
  const [progress, setProgress] = useState(0)
  const [retryInfo, setRetryInfo] = useState<GenerationRetryInfo | null>(null)
  const [summary, setSummary] = useState<GenerationSummary | null>(null)
  const [pendingWorkflowId, setPendingWorkflowId] = useState<string | null>(null)

  // Restore a draft prompt/provider left behind from a trip to API Settings.
  useEffect(() => {
    const draft = loadPromptDraft()
    if (draft.prompt) setPrompt(draft.prompt)
    if (draft.provider) setSelectedProvider(draft.provider as AIProviderId)
  }, [])

  // ROOT CAUSE FIX: this used to fall back to whichever configured provider
  // came first in the SUPPORTED display order (OpenAI), regardless of which
  // one the user actually has configured as their default. Gemini must
  // remain the default provider for Create with AI whenever it's available
  // and the user hasn't explicitly picked something else this session.
  const activeProvider = selectedProvider
    ?? (validConfigured.includes('gemini') ? 'gemini' : validConfigured[0]) as AIProviderId | undefined
    ?? null
  const hasSessionKey = activeProvider ? !!getSessionKey(activeProvider) : false

  const createMutation = useMutation({
    mutationFn: ({ name, description }: { name: string; description: string }) =>
      workflowsApi.create(name, description),
  })

  const goToApiSettings = () => {
    savePromptDraft(prompt, activeProvider)
    router.push(`${API_KEYS_SETTINGS_PATH}?returnTo=${encodeURIComponent(RETURN_PATH)}`)
  }

  const handleGenerate = async () => {
    if (!prompt.trim()) return

    // Gate 1: does the selected provider (or any provider) have a
    // configured API key at all?
    if (validConfigured.length === 0) {
      savePromptDraft(prompt, activeProvider)
      setShowApiKeyModal(true)
      return
    }

    if (!activeProvider || !hasSessionKey) return

    setLoading(true); setError(null); setStage(null); setProgress(0)
    setRetryInfo(null); setSummary(null); setPendingWorkflowId(null)
    try {
      const apiKey = getSessionKey(activeProvider) || ''
      let generationMeta: GenerationMeta | null = null
      const gw = await buildWorkflowFromPrompt(
        { provider: activeProvider, apiKey },
        prompt.trim(),
        // A new stage means ThunderGuide has moved on (either forward, or
        // into a fresh retry attempt) — clear any stale retry banner so it
        // never lingers once generation is actually progressing again.
        // Progress is derived from this same real stage, never a timer.
        (s) => { setRetryInfo(null); setStage(s); setProgress(GENERATION_STAGE_PROGRESS[s]) },
        (info) => setRetryInfo(info),
        (meta) => { generationMeta = meta },
      )

      // ROOT CAUSE FIX (never open an empty Builder): buildWorkflowFromPrompt
      // now throws for a genuinely invalid generation (see aiActions.ts), so
      // this should never fail in normal operation — but the Builder must
      // never be opened as a result of THIS action unless what's about to be
      // handed to it is unquestionably valid. Re-validate defensively right
      // here, at the last point before a workflow record + navigation happen.
      if (!isValidGeneratedWorkflow(gw)) {
        setError('ThunderGuide could not generate a fully valid workflow from this description. Try rephrasing or narrowing the request, then generate again.')
        return
      }

      // Generation itself has now genuinely succeeded — this is the only
      // place progress is allowed to reach 100%.
      setProgress(100)

      const { name, description } = deriveWorkflowMeta(prompt)
      const wf = await createMutation.mutateAsync({ name, description })

      // Only proceed to the Builder once the generated graph is actually
      // queued for import. If sessionStorage rejects the write (quota/
      // private-browsing), stay right here instead of opening a Builder
      // that will silently show 0 nodes and 0 connections.
      const queued = setPendingImport(wf.id, gw)
      if (!queued) {
        setError('Generated the chatbot, but could not hand it off to the Builder (browser storage is full or unavailable). Try again, or free up some storage and retry.')
        return
      }

      markChatbotGeneratedViaAI()
      clearPromptDraft()

      // Final Success Screen: hand off is queued and safe, but the Builder
      // opens only when the person clicks "Open Workflow" below — not via
      // an automatic redirect — so they get to see what was actually built.
      const meta: GenerationMeta = generationMeta ?? {
        generationTimeMs: 0, attemptsUsed: 1, retryCount: 0,
        autoRepaired: false, usedFallback: false, wasShortPrompt: false, matchedDomain: null,
      }
      setSummary(buildGenerationSummary(prompt, activeProvider, detectPromptLanguage(prompt), gw, meta))
      setPendingWorkflowId(wf.id)
    } catch (e) {
      setError(getErrorMessage(e, 'Could not generate a chatbot from this description.'))
    } finally {
      setLoading(false)
      setRetryInfo(null)
    }
  }

  const handleOpenWorkflow = () => {
    if (!pendingWorkflowId) return
    toast('success', 'Opening the builder…')
    router.push(`/builder/${pendingWorkflowId}`)
  }

  return (
    <div className="tb2-shell">
      <SubPageBar crumb="Create with AI" crumbIcon={<Sparkles size={13} />} />

      <main className="max-w-2xl mx-auto px-6 py-10">
        <div className="mb-8 tb2-rise">
          <div className="flex items-center gap-2.5 mb-2">
            <div className="w-9 h-9 rounded-xl bg-[#6366f1]/15 border border-[#6366f1]/25 flex items-center justify-center">
              <Wand2 size={16} className="text-[#a5b4fc]" />
            </div>
            <h1 className="text-xl font-bold text-white">Create with AI</h1>
          </div>
          <p className="text-sm text-white/35">
            Describe the chatbot you want and generate a complete workflow — nodes, branches, and all.
          </p>
        </div>

        <Card className="p-5 space-y-4 tb2-rise">
          <div>
            <p className="text-[10px] font-semibold text-white/40 uppercase tracking-wider mb-2">Provider</p>
            <div className="flex flex-wrap gap-1.5 mb-2.5">
              {SUPPORTED.map(p => {
                const configured = validConfigured.includes(p)
                return (
                  <button
                    key={p}
                    onClick={() => setSelectedProvider(p)}
                    className={cn(
                      'text-[11px] px-3 py-1.5 rounded-lg border transition font-medium',
                      activeProvider === p
                        ? 'bg-[#6366f1]/20 border-[#6366f1]/40 text-[#a5b4fc]'
                        : configured
                        ? 'bg-white/[0.03] border-white/10 text-white/50 hover:text-white/80 hover:border-white/20'
                        : 'bg-white/[0.02] border-white/5 text-white/25 hover:text-white/50'
                    )}
                  >
                    {PROVIDER_LABELS[p]}
                    {!configured && <span className="ml-1 text-white/20">· not configured</span>}
                  </button>
                )
              })}
            </div>

            {activeProvider && validConfigured.includes(activeProvider) && !hasSessionKey && (
              <div className="p-3 rounded-xl border border-[#2a2a2a] bg-[#111] space-y-2">
                <p className="text-[10px] text-white/40 leading-relaxed">
                  To generate with {PROVIDER_LABELS[activeProvider]} in this session, paste the same key you
                  configured in API Settings. It's kept only in this browser tab.
                </p>
                <div className="flex gap-2">
                  <input
                    type="password"
                    value={sessionKeyInput}
                    onChange={e => setSessionKeyInput(e.target.value)}
                    placeholder={`${PROVIDER_LABELS[activeProvider]} API key`}
                    className="flex-1 bg-[#1a1a1a] text-xs text-white border border-[#2a2a2a] rounded-lg px-3 py-2 outline-none focus:border-[#6366f1]/50 transition font-mono"
                  />
                  <button
                    onClick={() => {
                      if (sessionKeyInput.trim()) {
                        setSessionKey(activeProvider, sessionKeyInput.trim())
                        setSessionKeyInput('')
                        setSessionTick(t => t + 1)
                      }
                    }}
                    disabled={!sessionKeyInput.trim()}
                    className="px-3 py-2 rounded-lg text-[11px] font-semibold bg-[#6366f1] hover:bg-[#5558e8] text-white transition disabled:opacity-40"
                  >
                    Use
                  </button>
                </div>
              </div>
            )}
          </div>

          <div>
            <p className="text-[10px] font-semibold text-white/40 uppercase tracking-wider mb-2">Describe your chatbot</p>
            <textarea
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              placeholder="e.g. A support bot that greets the user, asks if they need billing or technical help, then routes to an AI agent for each"
              rows={6}
              className="w-full bg-[#1a1a1a] text-sm text-white border border-[#2a2a2a] rounded-xl px-3.5 py-3 outline-none focus:border-[#6366f1]/50 transition resize-none placeholder-white/20"
            />
          </div>

          <Button
            className="w-full"
            disabled={loading || !prompt.trim() || (validConfigured.length > 0 && (!activeProvider || !hasSessionKey))}
            loading={loading}
            icon={!loading ? <Wand2 size={14} /> : undefined}
            onClick={handleGenerate}
          >
            Generate Chatbot
          </Button>

          {stage && (loading || error) && (
            <ThunderGuideProgress stage={stage} progress={progress} retry={retryInfo} />
          )}

          {error && (
            <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-red-500/10 border border-red-500/20">
              <AlertCircle size={13} className="text-red-400 mt-0.5 flex-shrink-0" />
              <p className="text-xs text-red-300 leading-snug">{error}</p>
            </div>
          )}
        </Card>

        {summary && !loading && (
          <div className="mt-4">
            <ThunderGuideSuccessScreen summary={summary} onOpenWorkflow={handleOpenWorkflow} />
          </div>
        )}

        <div className="mt-4 flex items-center justify-center">
          <Link
            href={API_KEYS_SETTINGS_PATH}
            className="flex items-center gap-1.5 text-[11px] text-white/25 hover:text-white/60 transition"
          >
            <KeyRound size={11} /> Manage AI Provider Keys <ExternalLink size={9} />
          </Link>
        </div>
      </main>

      {showApiKeyModal && (
        <ApiKeyRequiredModal
          onCancel={() => setShowApiKeyModal(false)}
          onGoToSettings={goToApiSettings}
        />
      )}
      <ApiKeyReminder />
    </div>
  )
}

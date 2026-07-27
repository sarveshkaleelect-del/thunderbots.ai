'use client'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Key, Palette, Globe, Bot, Check, ChevronRight, MessageCircle, Instagram, Send, Lock, Phone,
} from 'lucide-react'
import Link from 'next/link'
import { settingsApi } from '@/lib/api/settings'
import type { UserPreferences, AIProvider } from '@/types'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Field'
import { SubPageBar } from '@/components/ui/TopBar'
import { PageLoader, ErrorState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'
import { cn } from '@/lib/utils/cn'
import { useThemeStore, THEMES, type ThemeId } from '@/store/themeStore'

export default function SettingsPage() {
  const qc = useQueryClient()
  const { toast } = useToast()

  const { data: prefs, isLoading: loadingPrefs, error: prefsError, refetch: refetchPrefs } = useQuery({
    queryKey: ['preferences'],
    queryFn: settingsApi.getPreferences,
  })

  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: settingsApi.listProviders,
  })

  const prefsMutation = useMutation({
    mutationFn: (data: Partial<UserPreferences>) => settingsApi.updatePreferences(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['preferences'] }),
  })

  // Theme applies instantly (DOM + localStorage) and persists per-user in
  // the background, independent of the batched "Save Preferences" flow
  // below — a theme switch shouldn't wait for an explicit Save click.
  const activeTheme = useThemeStore(s => s.theme)
  const setLocalTheme = useThemeStore(s => s.setLocalTheme)
  const themeMutation = useMutation({
    mutationFn: (theme: ThemeId) => settingsApi.updatePreferences({ theme }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['preferences'] }),
  })
  const handleThemeChange = (theme: ThemeId) => {
    setLocalTheme(theme)
    themeMutation.mutate(theme)
  }

  const [saved, setSaved] = useState(false)
  const [localPrefs, setLocalPrefs] = useState<Partial<UserPreferences>>({})

  const current = { ...prefs, ...localPrefs }

  const handleSave = async () => {
    try {
      await prefsMutation.mutateAsync(localPrefs)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      setLocalPrefs({})
    } catch (err) {
      // ROOT CAUSE FIX (silent failure): a failed save previously left the
      // user with no feedback at all — no error, no "Saved!" state, just a
      // button that stopped loading. Surface it and keep localPrefs intact
      // so the unsaved changes (and the Save button) are still there to retry.
      toast('error', getErrorMessage(err, 'Could not save your preferences.'))
    }
  }

  const update = (key: keyof UserPreferences, val: string) => {
    setLocalPrefs(p => ({ ...p, [key]: val }))
  }

  const selectedProvider = (providers as AIProvider[]).find(p => p.id === (current.default_provider || 'gemini'))
  const availableModels = selectedProvider?.models || []

  return (
    <div className="tb2-shell">
      <SubPageBar crumb="Settings" />

      <div className="max-w-2xl mx-auto px-6 py-10 space-y-6">
        <h1 className="text-xl font-bold text-white tb2-rise">Settings</h1>

        <Link
          href="/settings/api-keys"
          className="tb2-row tb2-glass tb2-glass-hover flex items-center gap-3 p-4 group"
        >
          <div className="w-9 h-9 rounded-xl bg-[#6366f1]/15 border border-[#6366f1]/25 flex items-center justify-center flex-shrink-0">
            <Key size={16} className="text-[#a5b4fc]" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white/80">AI Providers</p>
            <p className="text-[11px] text-white/35">Configure your Google Gemini API key…</p>
          </div>
          <ChevronRight size={14} className="text-white/25 group-hover:text-cyan-300 transition-colors" />
        </Link>

        <Link
          href="/whatsapp"
          className="tb2-row tb2-glass tb2-glass-hover flex items-center gap-3 p-4 group"
        >
          <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center flex-shrink-0">
            <MessageCircle size={16} className="text-emerald-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white/80">WhatsApp</p>
            <p className="text-[11px] text-white/35">Connect chatbots to WhatsApp via the Meta Cloud API</p>
          </div>
          <ChevronRight size={14} className="text-white/25 group-hover:text-cyan-300 transition-colors" />
        </Link>

        {/* NEW (Instagram DM Channel) */}
        <Link
          href="/instagram"
          className="tb2-row tb2-glass tb2-glass-hover flex items-center gap-3 p-4 group"
        >
          <div className="w-9 h-9 rounded-xl bg-pink-500/10 border border-pink-500/20 flex items-center justify-center flex-shrink-0">
            <Instagram size={16} className="text-pink-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white/80">Instagram</p>
            <p className="text-[11px] text-white/35">Connect chatbots to Instagram DMs via Meta OAuth</p>
          </div>
          <ChevronRight size={14} className="text-white/25 group-hover:text-cyan-300 transition-colors" />
        </Link>

        {/* NEW (Telegram Channel) */}
        <Link
          href="/telegram"
          className="tb2-row tb2-glass tb2-glass-hover flex items-center gap-3 p-4 group"
        >
          <div className="w-9 h-9 rounded-xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center flex-shrink-0">
            <Send size={16} className="text-sky-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white/80">Telegram</p>
            <p className="text-[11px] text-white/35">Connect chatbots to a Telegram Bot via the official Bot API</p>
          </div>
          <ChevronRight size={14} className="text-white/25 group-hover:text-cyan-300 transition-colors" />
        </Link>

        {/* NEW (AI Call Agent — Voice AI Part 2) */}
        <Link
          href="/call-agent"
          className="tb2-row tb2-glass tb2-glass-hover flex items-center gap-3 p-4 group"
        >
          <div className="w-9 h-9 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center flex-shrink-0">
            <Phone size={16} className="text-cyan-300" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white/80">AI Call Agent</p>
            <p className="text-[11px] text-white/35">Connect and verify phone numbers</p>
          </div>
          <ChevronRight size={14} className="text-white/25 group-hover:text-cyan-300 transition-colors" />
        </Link>

        {/* NEW (Google SSO & 2FA) */}
        <Link
          href="/settings/security"
          className="tb2-row tb2-glass tb2-glass-hover flex items-center gap-3 p-4 group"
        >
          <div className="w-9 h-9 rounded-xl bg-[#6366f1]/15 border border-[#6366f1]/25 flex items-center justify-center flex-shrink-0">
            <Lock size={16} className="text-[#a5b4fc]" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white/80">Security</p>
            <p className="text-[11px] text-white/35">Google sign-in and two-factor authentication</p>
          </div>
          <ChevronRight size={14} className="text-white/25 group-hover:text-cyan-300 transition-colors" />
        </Link>

        {loadingPrefs ? (
          <PageLoader />
        ) : prefsError ? (
          <ErrorState
            title="Couldn't load your settings"
            description={getErrorMessage(prefsError, 'Check your connection and that the backend is running.')}
            onRetry={() => refetchPrefs()}
          />
        ) : (
          <div className="space-y-4">
            <Section icon={<Bot size={14} />} title="Default AI Provider">
              <div className="grid grid-cols-2 gap-2">
                {(providers as AIProvider[]).map(p => (
                  <button
                    key={p.id}
                    onClick={() => { update('default_provider', p.id); update('default_model', p.default) }}
                    className={cn(
                      'flex items-center gap-2.5 p-3 rounded-lg border text-left transition tb2-row',
                      current.default_provider === p.id
                        ? 'border-[#6366f1]/50 bg-[#6366f1]/10 text-white/80'
                        : 'border-white/10 bg-white/[0.02] text-white/40 hover:text-white/60 hover:border-white/20'
                    )}
                  >
                    <span className="text-xs font-bold w-5 text-center opacity-70">
                      {p.name.slice(0, 2).toUpperCase()}
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs font-medium truncate">{p.name}</p>
                      {!p.configured && p.requires_key && (
                        <p className="text-[9px] text-amber-400/60">No key set</p>
                      )}
                    </div>
                    {current.default_provider === p.id && (
                      <Check size={11} className="text-cyan-300 ml-auto flex-shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            </Section>

            {availableModels.length > 0 && (
              <Section icon={<Bot size={14} />} title="Default Model">
                <Select value={current.default_model || ''} onChange={e => update('default_model', e.target.value)}>
                  {availableModels.map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </Select>
              </Section>
            )}

            <Section icon={<Palette size={14} />} title="Appearance — Theme">
              <div className="grid grid-cols-2 gap-2">
                {THEMES.map(t => (
                  <button
                    key={t.id}
                    onClick={() => handleThemeChange(t.id)}
                    aria-pressed={activeTheme === t.id}
                    className={cn(
                      'py-2.5 rounded-lg border text-xs font-medium transition tb2-row flex items-center justify-center gap-1.5',
                      activeTheme === t.id
                        ? 'border-[#6366f1]/50 bg-[#6366f1]/10 text-[#a5b4fc]'
                        : 'border-white/10 bg-white/[0.02] text-white/40 hover:text-white/60 hover:border-white/20'
                    )}
                  >
                    <span>{t.emoji}</span>
                    <span>{t.label}</span>
                    {activeTheme === t.id && <Check size={11} className="text-cyan-300 ml-0.5" />}
                  </button>
                ))}
              </div>
              <p className="text-[10px] text-white/30 mt-2.5">
                Applies instantly across the whole platform and syncs to your account — no page refresh needed.
              </p>
            </Section>

            <Section icon={<Globe size={14} />} title="Language">
              <Select value={current.language || 'en'} onChange={e => update('language', e.target.value)}>
                <option value="en">English</option>
                <option value="es">Español</option>
                <option value="fr">Français</option>
                <option value="de">Deutsch</option>
                <option value="pt">Português</option>
                <option value="ja">日本語</option>
                <option value="zh">中文</option>
                <option value="ar">العربية</option>
              </Select>
            </Section>

            {Object.keys(localPrefs).length > 0 && (
              <Button
                className="w-full"
                loading={prefsMutation.isPending}
                icon={saved ? <Check size={14} /> : undefined}
                onClick={handleSave}
              >
                {saved ? 'Saved!' : 'Save Preferences'}
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center gap-2 text-white/50">
        {icon}
        <span className="text-xs font-semibold uppercase tracking-wider">{title}</span>
      </div>
      {children}
    </Card>
  )
}

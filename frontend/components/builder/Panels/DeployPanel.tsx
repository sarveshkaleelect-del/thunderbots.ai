'use client'
import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Rocket, Globe, Copy, Check, Loader2, ExternalLink, PowerOff, AlertCircle,
  Palette, Paintbrush, LayoutGrid, SlidersHorizontal, Share2,
  Monitor, Tablet, Smartphone, Sun, Moon, Link2, Save,
  Volume2, VolumeX, Volume1, Sparkles,
} from 'lucide-react'
import { useWorkflowStore } from '@/store/workflowStore'
import { useUIStore } from '@/store/uiStore'
import { deployApi } from '@/lib/api/deploy'
import { voiceApi } from '@/lib/api/voice'
import { getErrorMessage } from '@/lib/utils/errors'
import type { Deployment, VoiceProviderId, VoiceProviderInfo, VoiceGender, VoicePersonality } from '@/types'
import { useBrandingDraft } from './deploy/useBrandingDraft'
import { ColorField } from './deploy/ColorField'
import { AssetUploader } from './deploy/AssetUploader'
import { ToggleRow } from './deploy/ToggleRow'
import { ChatTheme } from '@/components/chat/ChatTheme'
import { VOICE_PERSONALITIES, DEFAULT_VOICE_PERSONALITY } from '@/lib/voice/personality'

type SubTab = 'publish' | 'branding' | 'design' | 'widget' | 'settings'
type Device = 'desktop' | 'tablet' | 'mobile'

const DEVICE_FRAME: Record<Device, { w: number; h: number }> = {
  desktop: { w: 300, h: 300 },
  tablet:  { w: 240, h: 320 },
  mobile:  { w: 200, h: 340 },
}

function CopyBtn({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }).catch(() => {
      // Clipboard permission denied / insecure context — nothing to recover,
      // just avoid an unhandled rejection. Button silently stays "Copy".
    })
  }
  return (
    <button
      onClick={copy}
      className="tb-hover-lift flex items-center gap-1.5 text-[10px] px-2 py-1 rounded-lg
                 bg-[#1a1a1a] border border-[#2a2a2a] text-white/40
                 hover:text-white/70 hover:border-[#3a3a3a] transition flex-shrink-0"
    >
      {copied ? <Check size={10} className="text-emerald-400" /> : <Copy size={10} />}
      {copied ? 'Copied!' : label}
    </button>
  )
}

const SUB_TABS: { id: SubTab; label: string; icon: typeof Rocket }[] = [
  { id: 'publish',  label: 'Publish',  icon: Rocket },
  { id: 'branding', label: 'Branding', icon: Palette },
  { id: 'design',   label: 'Design',   icon: Paintbrush },
  { id: 'widget',   label: 'Widget',   icon: LayoutGrid },
  { id: 'settings', label: 'Settings', icon: SlidersHorizontal },
]

export function DeployPanel() {
  const workflowId = useWorkflowStore(s => s.workflowId)
  const qc         = useQueryClient()
  const [tab, setTab]           = useState<SubTab>('publish')
  const [shareTab, setShareTab] = useState<'share' | 'embed'>('share')
  const [device, setDevice]     = useState<Device>('desktop')
  const [slugInput, setSlugInput] = useState('')
  const [slugMsg, setSlugMsg]     = useState<{ ok: boolean; text: string } | null>(null)

  const { data: raw, isLoading, error } = useQuery({
    queryKey:  ['deployment', workflowId],
    queryFn:   () => deployApi.get(workflowId!),
    enabled:   !!workflowId,
    retry:     1,
    retryDelay: 1000,
  })

  const publishMutation = useMutation({
    mutationFn: () => deployApi.publish(workflowId!),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['deployment', workflowId] }),
  })
  const unpublishMutation = useMutation({
    mutationFn: () => deployApi.unpublish(workflowId!),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['deployment', workflowId] }),
  })
  const slugMutation = useMutation({
    mutationFn: (slug: string) => deployApi.updateSlug(workflowId!, slug),
    onSuccess:  (dep) => {
      qc.setQueryData(['deployment', workflowId], dep)
      setSlugMsg({ ok: true, text: 'Deploy URL updated' })
    },
    onError: (e) => setSlugMsg({ ok: false, text: getErrorMessage(e, 'That name is taken') }),
  })

  const isDeployed = raw && 'slug' in raw && (raw as Deployment).is_active
  const deployment = isDeployed ? (raw as Deployment) : null
  const publishError = publishMutation.error
    ? getErrorMessage(publishMutation.error, 'Publish failed. Make sure the workflow has a Start node.')
    : null
  const loadErrorMsg = error ? getErrorMessage(error, 'Could not load deployment status.') : null

  const draft = useBrandingDraft(workflowId)
  const frame = DEVICE_FRAME[device]

  if (!workflowId) {
    return (
      <div className="flex flex-col h-full">
        <PanelHeader isDeployed={false} />
        <p className="text-xs text-white/25 text-center mt-8 px-4">Save your workflow first to deploy it</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <PanelHeader isDeployed={!!isDeployed} />

      {/* Sub-tab nav */}
      <div className="flex items-center gap-0.5 px-2 pt-2 border-b border-[#1a1a1a] flex-shrink-0 overflow-x-auto">
        {SUB_TABS.map(t => {
          const Icon = t.icon
          const active = tab === t.id
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1 px-2.5 py-2 text-[11px] font-medium rounded-t-md
                          border-b-2 transition whitespace-nowrap ${
                active ? 'text-white/90 border-[#6366f1]' : 'text-white/35 border-transparent hover:text-white/60'
              }`}
            >
              <Icon size={11} /> {t.label}
            </button>
          )
        })}
      </div>

      {/* Live preview — visible on branding/design/widget/settings tabs */}
      {tab !== 'publish' && !draft.isLoading && draft.branding && draft.design && draft.chatSettings && (
        <div className="flex-shrink-0 px-4 pt-3 pb-2 border-b border-[#1a1a1a] bg-[#0a0a0a]">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-semibold text-white/30 uppercase tracking-wider">Live Preview</span>
            <div className="flex items-center gap-2">
              <SaveIndicator state={draft.saveState} />
              <div className="flex bg-[#141414] rounded-md p-0.5 border border-[#242424]">
                {([
                  ['desktop', Monitor], ['tablet', Tablet], ['mobile', Smartphone],
                ] as [Device, typeof Monitor][]).map(([d, Icon]) => (
                  <button
                    key={d}
                    onClick={() => setDevice(d)}
                    className={`p-1 rounded ${device === d ? 'bg-[#242424] text-white/80' : 'text-white/25 hover:text-white/50'} transition`}
                  >
                    <Icon size={10} />
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="flex justify-center">
            <div
              className="tb-anim-pop-in tb-viewport-transition"
              style={{ width: frame.w, height: frame.h }}
            >
              <ChatTheme
                branding={draft.branding}
                design={draft.design}
                chatSettings={draft.chatSettings}
                typing={false}
                interactive={false}
                className="w-full h-full"
              />
            </div>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {tab === 'publish' && (
          <PublishTab
            workflowId={workflowId}
            isLoading={isLoading}
            loadErrorMsg={loadErrorMsg}
            raw={raw}
            isDeployed={!!isDeployed}
            deployment={deployment}
            publishMutation={publishMutation}
            unpublishMutation={unpublishMutation}
            publishError={publishError}
            shareTab={shareTab}
            setShareTab={setShareTab}
            slugInput={slugInput}
            setSlugInput={setSlugInput}
            slugMutation={slugMutation}
            slugMsg={slugMsg}
          />
        )}

        {tab === 'branding' && draft.branding && (
          <BrandingTab workflowId={workflowId} branding={draft.branding} update={draft.updateBranding} onAsset={draft.applyAssetUrl} />
        )}

        {tab === 'design' && draft.design && (
          <DesignTab design={draft.design} update={draft.updateDesign} workflowId={workflowId} onAsset={draft.applyAssetUrl} />
        )}

        {tab === 'widget' && draft.widgetConfig && (
          <WidgetTab workflowId={workflowId} widget={draft.widgetConfig} update={draft.updateWidgetConfig} onAsset={draft.applyAssetUrl} deployment={deployment} />
        )}

        {tab === 'settings' && draft.chatSettings && (
          <SettingsTab settings={draft.chatSettings} update={draft.updateChatSettings} />
        )}

        {tab !== 'publish' && draft.isLoading && (
          <div className="flex items-center justify-center py-10">
            <Loader2 size={18} className="animate-spin text-white/20" />
          </div>
        )}
      </div>
    </div>
  )
}

function PanelHeader({ isDeployed }: { isDeployed: boolean }) {
  const setRightPanel = useUIStore(s => s.setRightPanel)
  return (
    <div className="flex items-center gap-2 px-4 py-3 border-b border-[#1a1a1a] flex-shrink-0">
      <Rocket size={13} className="text-white/40" />
      <span className="text-xs font-semibold text-white/60">Deploy</span>
      {isDeployed && (
        <span className="ml-1 text-[9px] px-1.5 py-0.5 rounded-full
                         bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 tb-anim-pop-in">
          LIVE
        </span>
      )}
      <button
        onClick={() => setRightPanel('simulator')}
        title="Run a simulated conversation pass before deploying"
        className="ml-auto flex items-center gap-1 text-[10px] px-2 py-1 rounded-lg
                   bg-[#6366f1]/10 border border-[#6366f1]/25 text-[#a5b4fc]
                   hover:bg-[#6366f1]/20 hover:border-[#6366f1]/40 transition"
      >
        <Sparkles size={10} /> Run AI Simulation
      </button>
    </div>
  )
}

function SaveIndicator({ state }: { state: 'idle' | 'saving' | 'saved' | 'error' }) {
  if (state === 'idle') return null
  if (state === 'saving') return <span className="flex items-center gap-1 text-[10px] text-white/30"><Loader2 size={9} className="animate-spin" /> Saving</span>
  if (state === 'error') return <span className="flex items-center gap-1 text-[10px] text-red-400"><AlertCircle size={9} /> Failed</span>
  return <span className="flex items-center gap-1 text-[10px] text-emerald-400 tb-anim-fade-up"><Save size={9} /> Saved</span>
}

// ── Publish tab (status, publish/unpublish, deploy URL rename, share/embed) ──
function PublishTab(props: any) {
  const {
    workflowId, isLoading, loadErrorMsg, raw, isDeployed, deployment,
    publishMutation, unpublishMutation, publishError,
    shareTab, setShareTab, slugInput, setSlugInput, slugMutation, slugMsg,
  } = props

  if (isLoading) {
    return <div className="flex items-center justify-center py-10"><Loader2 size={18} className="animate-spin text-white/20" /></div>
  }
  if (loadErrorMsg && !raw) {
    return (
      <div className="flex items-start gap-2.5 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20">
        <AlertCircle size={14} className="text-red-400 mt-0.5 flex-shrink-0" />
        <p className="text-xs text-red-300 leading-snug">{loadErrorMsg}</p>
      </div>
    )
  }

  return (
    <>
      <div className={`tb-card rounded-xl border p-4 ${isDeployed ? 'border-emerald-500/20 bg-emerald-500/5' : 'border-[#1e1e1e] bg-[#111]'}`}>
        <div className="flex items-center gap-3">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${isDeployed ? 'bg-emerald-500/15' : 'bg-white/5'}`}>
            {isDeployed ? <Globe size={16} className="text-emerald-400" /> : <PowerOff size={16} className="text-white/25" />}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white/80">{isDeployed ? 'Published & Live' : 'Not Published'}</p>
            <p className="text-[11px] text-white/35 mt-0.5 truncate">
              {isDeployed && deployment ? `/${deployment.slug}` : 'Publish to get a shareable chat link'}
            </p>
          </div>
        </div>

        <div className="mt-3 flex gap-2">
          {!isDeployed ? (
            <button
              onClick={() => publishMutation.mutate()}
              disabled={publishMutation.isPending}
              className="tb-hover-lift flex-1 flex items-center justify-center gap-2 py-2 rounded-lg
                         bg-[#6366f1] hover:bg-[#5558e8] text-sm text-white font-medium transition disabled:opacity-50"
            >
              {publishMutation.isPending ? <Loader2 size={13} className="animate-spin" /> : <Rocket size={13} />}
              {publishMutation.isPending ? 'Publishing…' : 'Publish Now'}
            </button>
          ) : (
            <>
              <button
                onClick={() => publishMutation.mutate()}
                disabled={publishMutation.isPending}
                className="tb-hover-lift flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-[#1a1a1a]
                           hover:bg-[#222] border border-[#2a2a2a] text-xs text-white/60 hover:text-white/90 transition disabled:opacity-40"
              >
                {publishMutation.isPending ? <Loader2 size={11} className="animate-spin" /> : <Rocket size={11} />}
                Republish
              </button>
              <button
                onClick={() => unpublishMutation.mutate()}
                disabled={unpublishMutation.isPending}
                className="tb-hover-lift flex items-center gap-1.5 py-2 px-3 rounded-lg bg-red-500/10
                           hover:bg-red-500/20 border border-red-500/20 text-xs text-red-400 transition disabled:opacity-40"
              >
                {unpublishMutation.isPending ? <Loader2 size={11} className="animate-spin" /> : <PowerOff size={11} />}
                Unpublish
              </button>
            </>
          )}
        </div>

        {publishError && (
          <div className="mt-2 flex items-start gap-1.5 text-[11px] text-red-400">
            <AlertCircle size={11} className="flex-shrink-0 mt-0.5" /> {publishError}
          </div>
        )}
      </div>

      {isDeployed && deployment && (
        <>
          {/* Deploy URL rename */}
          <div className="tb-card rounded-xl border border-[#1e1e1e] bg-[#111] p-3.5">
            <p className="text-[10px] font-semibold text-white/35 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Link2 size={10} /> Deploy Name
            </p>
            <div className="flex gap-2">
              <input
                value={slugInput || deployment.slug}
                onChange={(e) => setSlugInput(e.target.value)}
                placeholder={deployment.slug}
                className="flex-1 min-w-0 bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg px-3 py-2 text-xs
                           text-white/70 font-mono outline-none focus:border-[#6366f1] transition"
              />
              <button
                onClick={() => slugMutation.mutate(slugInput || deployment.slug)}
                disabled={slugMutation.isPending || !slugInput || slugInput === deployment.slug}
                className="tb-hover-lift px-3 py-2 rounded-lg bg-[#1a1a1a] border border-[#2a2a2a] text-xs
                           text-white/60 hover:text-white/90 transition disabled:opacity-30"
              >
                {slugMutation.isPending ? <Loader2 size={11} className="animate-spin" /> : 'Save'}
              </button>
            </div>
            <p className="text-[10px] text-white/20 mt-1.5">
              Changing this updates your URL without breaking the deployment.
            </p>
            {slugMsg && (
              <p className={`text-[10px] mt-1 ${slugMsg.ok ? 'text-emerald-400' : 'text-red-400'}`}>{slugMsg.text}</p>
            )}
          </div>

          <div className="flex bg-[#111] rounded-lg p-0.5 border border-[#1a1a1a]">
            {(['share', 'embed'] as const).map(t => (
              <button
                key={t}
                onClick={() => setShareTab(t)}
                className={`flex-1 py-1.5 rounded-md text-xs font-medium transition ${
                  shareTab === t ? 'bg-[#1e1e1e] text-white/80' : 'text-white/30 hover:text-white/60'
                }`}
              >
                {t === 'share' ? '🔗 Share' : '</> Embed'}
              </button>
            ))}
          </div>

          {shareTab === 'share' && (
            <div className="space-y-3 tb-anim-fade-up">
              <div>
                <p className="text-[10px] font-semibold text-white/35 uppercase tracking-wider mb-1.5">Share URL</p>
                <div className="flex gap-2 items-center">
                  <div className="flex-1 bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg px-3 py-2 text-xs text-white/50 font-mono truncate">
                    {deployment.share_url}
                  </div>
                  <CopyBtn text={deployment.share_url} label="Copy" />
                </div>
                <div className="flex gap-2 items-center mt-2">
                  <div className="flex-1 bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg px-3 py-2 text-xs text-white/35 font-mono truncate">
                    {deployment.share_url_alt}
                  </div>
                  <CopyBtn text={deployment.share_url_alt} label="Copy" />
                </div>
              </div>
              <a
                href={deployment.share_url}
                target="_blank"
                rel="noopener noreferrer"
                className="tb-hover-lift flex items-center justify-center gap-1.5 w-full py-2 rounded-lg border
                           border-[#2a2a2a] text-xs text-white/40 hover:text-white/70 hover:border-[#3a3a3a] transition"
              >
                <ExternalLink size={11} /> Open in new tab
              </a>
            </div>
          )}

          {shareTab === 'embed' && (
            <div className="space-y-3 tb-anim-fade-up">
              <div>
                <p className="text-[10px] font-semibold text-white/35 uppercase tracking-wider mb-1.5">iFrame Embed</p>
                <div className="bg-[#0d0d0d] border border-[#1a1a1a] rounded-lg p-3">
                  <code className="text-[10px] text-emerald-400/80 font-mono break-all leading-relaxed">
                    {deployment.embed_snippet}
                  </code>
                </div>
                <div className="flex justify-end mt-1.5">
                  <CopyBtn text={deployment.embed_snippet} label="Copy iFrame" />
                </div>
              </div>
              <div>
                <p className="text-[10px] font-semibold text-white/35 uppercase tracking-wider mb-1.5">Widget Script</p>
                <div className="bg-[#0d0d0d] border border-[#1a1a1a] rounded-lg p-3">
                  <code className="text-[10px] text-blue-400/80 font-mono break-all leading-relaxed">
                    {deployment.widget_script}
                  </code>
                </div>
                <div className="flex justify-end mt-1.5">
                  <CopyBtn text={deployment.widget_script} label="Copy Script" />
                </div>
                <p className="text-[10px] text-white/20 mt-1.5">
                  Configure the launcher's look and greeting in the Widget tab — this script updates automatically.
                </p>
              </div>
            </div>
          )}
        </>
      )}
    </>
  )
}

// ── Branding tab ──────────────────────────────────────────────────────────
function BrandingTab({ workflowId, branding, update, onAsset }: any) {
  return (
    <div className="space-y-4 tb-anim-fade-up">
      <Field label="Bot Name">
        <input
          value={branding.bot_name}
          onChange={(e) => update({ bot_name: e.target.value })}
          className="tb-input"
        />
      </Field>

      <AssetUploader
        workflowId={workflowId} field="logo" label="Bot Logo" currentUrl={branding.logo_url}
        onUploaded={(url) => { update({ logo_url: url }); onAsset('branding', 'logo_url', url) }}
        onCleared={() => update({ logo_url: null })}
      />
      <AssetUploader
        workflowId={workflowId} field="avatar" label="Bot Avatar" currentUrl={branding.avatar_url} shape="round"
        onUploaded={(url) => { update({ avatar_url: url }); onAsset('branding', 'avatar_url', url) }}
        onCleared={() => update({ avatar_url: null })}
      />

      <Field label="Welcome Title">
        <input value={branding.welcome_title} onChange={(e) => update({ welcome_title: e.target.value })} className="tb-input" />
      </Field>
      <Field label="Welcome Description">
        <textarea
          value={branding.welcome_description}
          onChange={(e) => update({ welcome_description: e.target.value })}
          rows={2}
          className="tb-input resize-none"
        />
      </Field>

      <Field label="Browser Title">
        <input
          value={branding.browser_title || ''}
          placeholder={branding.bot_name}
          onChange={(e) => update({ browser_title: e.target.value || null })}
          className="tb-input"
        />
      </Field>
      <AssetUploader
        workflowId={workflowId} field="favicon" label="Favicon" currentUrl={branding.favicon_url} shape="round"
        onUploaded={(url) => { update({ favicon_url: url }); onAsset('branding', 'favicon_url', url) }}
        onCleared={() => update({ favicon_url: null })}
      />

      <div className="grid grid-cols-2 gap-3">
        <ColorField label="Theme Color" value={branding.theme_color} onChange={(hex) => update({ theme_color: hex })} />
        <ColorField label="Accent Color" value={branding.accent_color} onChange={(hex) => update({ accent_color: hex })} />
      </div>
    </div>
  )
}

// ── Design tab ────────────────────────────────────────────────────────────
function DesignTab({ design, update, workflowId, onAsset }: any) {
  return (
    <div className="space-y-4 tb-anim-fade-up">
      <div>
        <label className="text-[10px] font-semibold text-white/35 uppercase tracking-wider mb-1.5 block">Mode</label>
        <div className="flex bg-[#111] rounded-lg p-0.5 border border-[#1a1a1a]">
          <button
            onClick={() => update({ mode: 'dark' })}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-medium transition ${
              design.mode === 'dark' ? 'bg-[#1e1e1e] text-white/80' : 'text-white/30 hover:text-white/60'
            }`}
          ><Moon size={11} /> Dark</button>
          <button
            onClick={() => update({ mode: 'light' })}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-medium transition ${
              design.mode === 'light' ? 'bg-[#1e1e1e] text-white/80' : 'text-white/30 hover:text-white/60'
            }`}
          ><Sun size={11} /> Light</button>
        </div>
      </div>

      <ColorField label="Background Color" value={design.background_color} onChange={(hex) => update({ background_color: hex, background_gradient: null })} />
      <Field label="Background Gradient (CSS)">
        <input
          value={design.background_gradient || ''}
          placeholder="linear-gradient(135deg,#0f0f14,#1a1a24)"
          onChange={(e) => update({ background_gradient: e.target.value || null })}
          className="tb-input font-mono text-[11px]"
        />
      </Field>
      <AssetUploader
        workflowId={workflowId} field="background_image" label="Background Image" currentUrl={design.background_image} shape="wide"
        onUploaded={(url) => { update({ background_image: url }); onAsset('design', 'background_image', url) }}
        onCleared={() => update({ background_image: null })}
      />

      <div className="grid grid-cols-2 gap-3">
        <ColorField label="Bot Bubble" value={design.bot_bubble_color} onChange={(hex) => update({ bot_bubble_color: hex })} />
        <ColorField label="User Bubble" value={design.user_bubble_color} onChange={(hex) => update({ user_bubble_color: hex })} />
      </div>

      <Field label="Font Family">
        <select
          value={design.font_family}
          onChange={(e) => update({ font_family: e.target.value })}
          className="tb-input"
        >
          <option value="Inter, system-ui, sans-serif">Inter</option>
          <option value="'JetBrains Mono', monospace">JetBrains Mono</option>
          <option value="Georgia, serif">Georgia</option>
          <option value="'Segoe UI', system-ui, sans-serif">Segoe UI</option>
          <option value="system-ui, sans-serif">System Default</option>
        </select>
      </Field>

      <SliderField label="Font Size" value={design.font_size} min={12} max={20} unit="px" onChange={(v) => update({ font_size: v })} />
      <SliderField label="Border Radius" value={design.border_radius} min={0} max={32} unit="px" onChange={(v) => update({ border_radius: v })} />

      <ToggleRow label="Shadows" hint="Depth on bubbles and containers" checked={design.shadows} onChange={(v) => update({ shadows: v })} />
      <ToggleRow label="Glassmorphism" hint="Frosted-glass blur on surfaces" checked={design.glassmorphism} onChange={(v) => update({ glassmorphism: v })} />
    </div>
  )
}

// ── Widget tab ────────────────────────────────────────────────────────────
function WidgetTab({ workflowId, widget, update, onAsset, deployment }: any) {
  return (
    <div className="space-y-4 tb-anim-fade-up">
      <AssetUploader
        workflowId={workflowId} field="launcher_icon" label="Launcher Icon" currentUrl={widget.launcher_icon} shape="round"
        onUploaded={(url) => { update({ launcher_icon: url }); onAsset('widget_config', 'launcher_icon', url) }}
        onCleared={() => update({ launcher_icon: null })}
      />
      <ColorField label="Launcher Color" value={widget.launcher_color} onChange={(hex) => update({ launcher_color: hex })} />

      <Field label="Size">
        <div className="flex bg-[#111] rounded-lg p-0.5 border border-[#1a1a1a]">
          {(['small', 'medium', 'large'] as const).map(s => (
            <button
              key={s}
              onClick={() => update({ size: s })}
              className={`flex-1 py-1.5 rounded-md text-xs font-medium capitalize transition ${
                widget.size === s ? 'bg-[#1e1e1e] text-white/80' : 'text-white/30 hover:text-white/60'
              }`}
            >{s}</button>
          ))}
        </div>
      </Field>

      <Field label="Position">
        <div className="grid grid-cols-2 gap-2">
          {([
            ['bottom-right', 'Bottom Right'], ['bottom-left', 'Bottom Left'],
            ['top-right', 'Top Right'], ['top-left', 'Top Left'],
          ] as const).map(([v, l]) => (
            <button
              key={v}
              onClick={() => update({ position: v })}
              className={`py-1.5 rounded-lg text-[11px] font-medium border transition ${
                widget.position === v
                  ? 'bg-[#1e1e1e] border-[#6366f1]/50 text-white/80'
                  : 'bg-[#141414] border-[#242424] text-white/35 hover:text-white/60'
              }`}
            >{l}</button>
          ))}
        </div>
      </Field>

      <SliderField label="Border Radius" value={widget.border_radius} min={0} max={32} unit="px" onChange={(v) => update({ border_radius: v })} />

      <Field label="Open Animation">
        <select value={widget.animation} onChange={(e) => update({ animation: e.target.value })} className="tb-input">
          <option value="pop">Pop</option>
          <option value="slide">Slide</option>
          <option value="fade">Fade</option>
          <option value="none">None</option>
        </select>
      </Field>

      <Field label="Initial Greeting">
        <input value={widget.initial_greeting} onChange={(e) => update({ initial_greeting: e.target.value })} className="tb-input" />
      </Field>

      {deployment && (
        <div className="bg-[#0d0d0d] border border-[#1a1a1a] rounded-lg p-3">
          <p className="text-[10px] font-semibold text-white/35 uppercase tracking-wider mb-1.5">Updated Embed Script</p>
          <code className="text-[10px] text-blue-400/80 font-mono break-all leading-relaxed">
            {deployment.widget_script}
          </code>
          <div className="flex justify-end mt-1.5">
            <CopyBtn text={deployment.widget_script} label="Copy Script" />
          </div>
        </div>
      )}
    </div>
  )
}

// ── Settings tab ──────────────────────────────────────────────────────────
const VOICE_MODES: { id: 'text_only' | 'voice_text' | 'voice_only'; label: string; hint: string; icon: typeof Volume2 }[] = [
  { id: 'text_only', label: 'Text Only', hint: 'No voice — current behavior, unchanged', icon: VolumeX },
  { id: 'voice_text', label: 'Voice + Text', hint: 'Show text immediately, then play voice', icon: Volume1 },
  { id: 'voice_only', label: 'Voice Only', hint: 'Play voice; text stays available for accessibility & history', icon: Volume2 },
]

const GENDER_OPTIONS: { id: VoiceGender; label: string }[] = [
  { id: 'neutral', label: 'Neutral' },
  { id: 'male',    label: 'Male' },
  { id: 'female',  label: 'Female' },
]

function VoiceResponsesSection({ settings, update }: any) {
  const voice = settings.voice ?? {}
  const enabled = !!voice.enabled
  const mode: 'voice_text' | 'voice_only' = voice.response_mode === 'voice_only' ? 'voice_only' : 'voice_text'
  const provider: VoiceProviderId = voice.provider ?? 'browser'
  const gender: VoiceGender = voice.gender ?? 'neutral'
  const voiceId: string | null = voice.voice_id ?? null
  const personality: VoicePersonality = voice.personality ?? DEFAULT_VOICE_PERSONALITY
  const allowMute = voice.allow_mute !== false
  const defaultState: 'on' | 'off' = voice.default_state === 'off' ? 'off' : 'on'

  const [providers, setProviders] = useState<VoiceProviderInfo[]>([])

  useEffect(() => {
    voiceApi.listProviders().then(setProviders).catch(() => {})
  }, [])

  // Always writes the FULL voice object back — `update()` shallow-merges at
  // the top level of chat_settings, so a patch of just `{ voice: {...} }`
  // would otherwise silently drop any fields not included here.
  const patchVoice = (patch: Partial<typeof voice>) => update({ voice: { ...voice, ...patch } })

  const activeVoices = providers.find(p => p.id === provider)?.voices ?? []
  const voiceChoices = gender === 'neutral' ? activeVoices : activeVoices.filter(v => v.gender === gender)
  const voiceOptions = voiceChoices.length > 0 ? voiceChoices : activeVoices

  return (
    <div className="pt-4 pb-1 space-y-3">
      <div>
        <label className="text-[10px] font-semibold text-white/35 uppercase tracking-wider mb-1.5 block">
          Voice Responses
        </label>
        <p className="text-[11px] text-white/30 leading-snug">
          Deployed automatically with this bot. End users never see these settings — only a
          Speaker ON/OFF icon in the chat header (if you allow it below).
        </p>
      </div>

      <ToggleRow
        label="Enable Voice Responses"
        hint="Turn Voice Responses on for the deployed chatbot"
        checked={enabled}
        onChange={(v) => patchVoice({ enabled: v, response_mode: v ? (mode ?? 'voice_text') : 'text_only' })}
      />

      {enabled && (
        <>
          <div className="space-y-1.5">
            {VOICE_MODES.filter(m => m.id !== 'text_only').map(({ id, label, hint, icon: Icon }) => (
              <button
                key={id}
                onClick={() => patchVoice({ response_mode: id })}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg border text-left transition ${
                  mode === id
                    ? 'bg-[#1e1e1e] border-[#3a3a3a] text-white/85'
                    : 'border-[#1a1a1a] text-white/40 hover:text-white/65 hover:border-[#2a2a2a]'
                }`}
              >
                <Icon size={13} className="flex-shrink-0" />
                <span className="min-w-0">
                  <span className="block text-xs font-medium">{label}</span>
                  <span className="block text-[10px] opacity-70 truncate">{hint}</span>
                </span>
              </button>
            ))}
          </div>

          <Field label="Default Voice Provider">
            <select
              value={provider}
              onChange={(e) => patchVoice({ provider: e.target.value as VoiceProviderId, voice_id: null })}
              className="tb-input"
            >
              <option value="browser">Browser (Free)</option>
              {providers.filter(p => p.id !== 'browser').map(p => (
                <option key={p.id} value={p.id} disabled={!p.configured}>
                  {p.name}{!p.configured ? ' — no API key saved' : ''}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Default Voice">
            <div className="flex bg-[#111] rounded-lg p-0.5 border border-[#1a1a1a] mb-1.5">
              {GENDER_OPTIONS.map(g => (
                <button
                  key={g.id}
                  onClick={() => patchVoice({ gender: g.id, voice_id: null })}
                  className={`flex-1 py-1.5 rounded-md text-[11px] font-medium transition ${
                    gender === g.id ? 'bg-[#242424] text-white/80' : 'text-white/30 hover:text-white/55'
                  }`}
                >{g.label}</button>
              ))}
            </div>
            {provider !== 'browser' && (
              <select value={voiceId ?? ''} onChange={(e) => patchVoice({ voice_id: e.target.value || null })} className="tb-input">
                <option value="">Auto-detect</option>
                {voiceOptions.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
            )}
            {provider === 'browser' && (
              <p className="text-[10px] text-white/25">Browser voices are chosen automatically on each visitor's device.</p>
            )}
          </Field>

          <Field label="Voice Personality">
            <select
              value={personality}
              onChange={(e) => patchVoice({ personality: e.target.value as VoicePersonality })}
              className="tb-input"
            >
              {VOICE_PERSONALITIES.map(p => (
                <option key={p.id} value={p.id}>{p.label} — {p.hint}</option>
              ))}
            </select>
            <p className="text-[10px] text-white/25 mt-1">
              Affects only how replies are spoken. Falls back to the default voice automatically if the selected provider doesn't support it.
            </p>
          </Field>

          <ToggleRow
            label="Allow End Users to Mute"
            hint="Show the Speaker ON/OFF control in the chat header"
            checked={allowMute}
            onChange={(v) => patchVoice({ allow_mute: v })}
          />

          <Field label="Default State">
            <div className="flex bg-[#111] rounded-lg p-0.5 border border-[#1a1a1a]">
              {(['on', 'off'] as const).map(s => (
                <button
                  key={s}
                  onClick={() => patchVoice({ default_state: s })}
                  className={`flex-1 py-1.5 rounded-md text-xs font-medium uppercase transition ${
                    defaultState === s ? 'bg-[#242424] text-white/80' : 'text-white/30 hover:text-white/60'
                  }`}
                >{s}</button>
              ))}
            </div>
          </Field>
        </>
      )}
    </div>
  )
}

function SettingsTab({ settings, update }: any) {
  const rows: [keyof typeof settings, string, string][] = [
    ['show_bot_logo', 'Show Bot Logo', 'Display logo in the chat header'],
    ['show_bot_name', 'Show Bot Name', 'Display name in the chat header'],
    ['show_timestamp', 'Show Timestamp', 'Time under each message'],
    ['show_typing_indicator', 'Show Typing Indicator', 'Animated dots while the bot replies'],
    ['show_restart_button', 'Show Restart Button', 'Let users reset the conversation'],
    ['show_powered_by', 'Show "Powered By"', 'Small footer credit'],
    ['enable_sound', 'Enable Sound', 'Notification chime on new messages'],
    ['enable_file_upload', 'Enable File Upload', 'Attachment button in composer'],
    ['enable_markdown', 'Enable Markdown', 'Render **bold**, links, lists, code'],
    ['enable_auto_scroll', 'Enable Auto Scroll', 'Keep the latest message in view'],
  ]
  return (
    <div className="tb-anim-fade-up divide-y divide-[#1a1a1a]">
      {rows.map(([key, label, hint]) => (
        <ToggleRow key={key as string} label={label} hint={hint} checked={!!settings[key]} onChange={(v) => update({ [key]: v })} />
      ))}
      <VoiceResponsesSection settings={settings} update={update} />
    </div>
  )
}

// ── Shared field primitives ──────────────────────────────────────────────
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[10px] font-semibold text-white/35 uppercase tracking-wider mb-1.5 block">{label}</label>
      {children}
    </div>
  )
}

function SliderField({ label, value, min, max, unit, onChange }: { label: string; value: number; min: number; max: number; unit: string; onChange: (v: number) => void }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <label className="text-[10px] font-semibold text-white/35 uppercase tracking-wider">{label}</label>
        <span className="text-[10px] text-white/40 font-mono">{value}{unit}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[#6366f1]"
      />
    </div>
  )
}

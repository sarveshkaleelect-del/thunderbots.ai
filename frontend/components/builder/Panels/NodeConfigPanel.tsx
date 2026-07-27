'use client'
import { useState } from 'react'
import { X, Trash2, Settings, Plus, Trash } from 'lucide-react'
import { useWorkflowStore } from '@/store/workflowStore'
import { useQuery } from '@tanstack/react-query'
import { settingsApi } from '@/lib/api/settings'
import { knowledgeApi } from '@/lib/api/knowledge'
import type { AIProvider, TransitionCondition, NodeMediaAttachment } from '@/types'
import { v4 as uuidv4 } from 'uuid'
import { MediaAttachment } from '../Shared/MediaAttachment'

// ── Shared primitives ─────────────────────────────────────────
const Label = ({ children }: { children: React.ReactNode }) => (
  <label className="block text-[10px] font-semibold text-white/35 uppercase tracking-wider mb-1.5">
    {children}
  </label>
)

const Input = ({ value, onChange, placeholder, type = 'text' }: {
  value: string | number; onChange: (v: string) => void; placeholder?: string; type?: string
}) => (
  <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
    className="w-full bg-[#141414] text-sm text-white border border-[#222] rounded-lg px-3 py-2
               outline-none focus:border-[#6366f1]/50 transition placeholder-white/15" />
)

const Textarea = ({ value, onChange, placeholder, rows = 3 }: {
  value: string; onChange: (v: string) => void; placeholder?: string; rows?: number
}) => (
  <textarea value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} rows={rows}
    className="w-full bg-[#141414] text-sm text-white border border-[#222] rounded-lg px-3 py-2
               outline-none focus:border-[#6366f1]/50 transition placeholder-white/15 resize-none leading-relaxed" />
)

const Select = ({ value, onChange, children }: {
  value: string; onChange: (v: string) => void; children: React.ReactNode
}) => (
  <select value={value} onChange={e => onChange(e.target.value)}
    className="w-full bg-[#141414] text-sm text-white border border-[#222] rounded-lg px-3 py-2
               outline-none focus:border-[#6366f1]/50 transition appearance-none">
    {children}
  </select>
)

// ── Node editors ──────────────────────────────────────────────
function StartEditor({ data, onChange }: { data: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  return (
    <div className="space-y-4">
      <div><Label>Welcome Message</Label>
        <Textarea value={data.welcomeMessage as string || ''} onChange={v => onChange('welcomeMessage', v)}
          placeholder="Hello! How can I help you today?" />
      </div>
    </div>
  )
}

function TextCardEditor({ data, onChange }: { data: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  return (
    <div className="space-y-4">
      <div><Label>Label</Label>
        <Input value={data.label as string || ''} onChange={v => onChange('label', v)} placeholder="Card label" />
      </div>
      <div><Label>Message Content</Label>
        <Textarea rows={6} value={data.content as string || ''} onChange={v => onChange('content', v)}
          placeholder="Type your message. Use {{variable}} for dynamic values." />
      </div>
      <p className="text-[10px] text-white/20">Supports Markdown · Use {'{{variable}}'} syntax</p>
    </div>
  )
}

function MultipleChoiceEditor({ data, onChange, workflowId }: { data: Record<string, unknown>; onChange: (k: string, v: unknown) => void; workflowId: string | null }) {
  const choices = (data.choices as Array<{ label: string; value: string }>) || []
  const updateChoice = (i: number, field: string, val: string) =>
    onChange('choices', choices.map((c, idx) => idx === i ? { ...c, [field]: val } : c))
  const addChoice = () => onChange('choices', [...choices, { label: `Option ${choices.length + 1}`, value: `option_${choices.length + 1}` }])
  const removeChoice = (i: number) => onChange('choices', choices.filter((_, idx) => idx !== i))

  return (
    <div className="space-y-4">
      <div><Label>Question</Label>
        <Textarea value={data.question as string || ''} onChange={v => onChange('question', v)}
          placeholder="What would you like to do?" rows={2} />
      </div>
      <MediaAttachment
        workflowId={workflowId}
        value={data.image as NodeMediaAttachment | null | undefined}
        onChange={(image) => onChange('image', image)}
      />
      <div>
        <Label>Choices</Label>
        <div className="space-y-2">
          {choices.map((c, i) => (
            <div key={i} className="flex gap-2 items-center">
              <input value={c.label} onChange={e => updateChoice(i, 'label', e.target.value)}
                placeholder={`Choice ${i + 1}`}
                className="flex-1 bg-[#141414] text-xs text-white border border-[#222] rounded-lg
                           px-2.5 py-1.5 outline-none focus:border-[#6366f1]/50 transition" />
              <button onClick={() => removeChoice(i)}
                className="p-1.5 text-white/20 hover:text-red-400 transition flex-shrink-0">
                <Trash2 size={11} />
              </button>
            </div>
          ))}
          <button onClick={addChoice}
            className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg
                       border border-dashed border-[#222] text-[10px] text-white/25
                       hover:text-white/60 hover:border-[#333] transition">
            <Plus size={10} /> Add Choice
          </button>
        </div>
      </div>
    </div>
  )
}

const PROVIDER_COLORS: Record<string, string> = {
  gemini: '#4285f4',
}

function AIAgentEditor({ data, onChange }: { data: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  const { data: providers = [] } = useQuery<AIProvider[]>({
    queryKey: ['providers'],
    queryFn: settingsApi.listProviders,
  })
  const { data: kbs = [] } = useQuery({ queryKey: ['knowledge-bases'], queryFn: knowledgeApi.list })

  const currentProvider = (providers as AIProvider[]).find(p => p.id === data.provider)
  const models = currentProvider?.models || []

  return (
    <div className="space-y-4">
      <div><Label>Label</Label>
        <Input value={data.label as string || ''} onChange={v => onChange('label', v)} placeholder="AI Agent" />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div><Label>Provider</Label>
          {/* ROOT CAUSE FIX: this used to fall back to 'openai' whenever
              data.provider was unset, which silently showed "OpenAI" as the
              selected value even though nothing had actually been chosen for
              this node (e.g. every imported marketplace template, which no
              longer hardcodes a provider). That misled builders into
              thinking OpenAI was locked in when the node would really
              auto-resolve to their configured default provider at chat time.
              An empty value now means "use my default provider" explicitly,
              and is never silently coerced to any one vendor. */}
          <Select value={data.provider as string || ''}
            onChange={v => { onChange('provider', v || null); onChange('model', '') }}>
            <option value="">Use my default provider</option>
            {(providers as AIProvider[]).map(p => (
              <option key={p.id} value={p.id} disabled={!p.configured && p.requires_key}>
                {p.name}{!p.configured && p.requires_key ? ' (no key)' : ''}
              </option>
            ))}
          </Select>
        </div>
        <div><Label>Model</Label>
          <Select value={data.model as string || ''} onChange={v => onChange('model', v)}>
            {models.length === 0 && <option value="">Default</option>}
            {models.map((m: string) => <option key={m} value={m}>{m}</option>)}
          </Select>
        </div>
      </div>

      {/* Provider badge */}
      {Boolean(data.provider) && (
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ background: PROVIDER_COLORS[data.provider as string] || '#6366f1' }} />
          <span className="text-[10px] text-white/30">{currentProvider?.name}</span>
        </div>
      )}

      <div><Label>System Prompt</Label>
        <Textarea rows={4} value={data.systemPrompt as string || ''} onChange={v => onChange('systemPrompt', v)}
          placeholder="You are a helpful assistant..." />
      </div>
      <div><Label>Instructions</Label>
        <Textarea rows={3} value={data.instructions as string || ''} onChange={v => onChange('instructions', v)}
          placeholder="Additional rules and behavior..." />
      </div>

      <div><Label>Temperature: {(data.temperature as number | undefined) ?? 0.7}</Label>
        <input type="range" min="0" max="1" step="0.05" value={data.temperature as number ?? 0.7}
          onChange={e => onChange('temperature', parseFloat(e.target.value))}
          className="w-full accent-[#6366f1]" />
        <div className="flex justify-between text-[9px] text-white/20 mt-0.5">
          <span>Precise</span><span>Creative</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div><Label>Max Tokens</Label>
          <Input type="number" value={data.maxTokens as number ?? 1000} onChange={v => onChange('maxTokens', parseInt(v))} />
        </div>
        <div><Label>Memory (turns)</Label>
          <Input type="number" value={data.contextWindow as number ?? 10} onChange={v => onChange('contextWindow', parseInt(v))} />
        </div>
      </div>

      {(kbs as Array<{ id: string; name: string }>).length > 0 && (
        <div><Label>Knowledge Base</Label>
          <Select value={data.knowledgeBaseId as string || ''} onChange={v => onChange('knowledgeBaseId', v || null)}>
            <option value="">None</option>
            {(kbs as Array<{ id: string; name: string }>).map(kb => (
              <option key={kb.id} value={kb.id}>{kb.name}</option>
            ))}
          </Select>
        </div>
      )}

      <div className="flex items-center gap-2">
        <input type="checkbox" id="stayOnNode" checked={data.stayOnNode as boolean ?? true}
          onChange={e => onChange('stayOnNode', e.target.checked)} className="accent-[#6366f1]" />
        <label htmlFor="stayOnNode" className="text-xs text-white/40">Stay on node (multi-turn conversation)</label>
      </div>
    </div>
  )
}

const OPERATORS = [
  { value: 'contains',     label: 'contains' },
  { value: 'equals',       label: 'equals' },
  { value: 'starts_with',  label: 'starts with' },
  { value: 'ends_with',    label: 'ends with' },
  { value: 'not_contains', label: 'does not contain' },
  { value: 'greater_than', label: '>' },
  { value: 'less_than',    label: '<' },
]

function TransitionEditor({ data, onChange }: { data: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  const conditions = (data.conditions as TransitionCondition[]) || []

  const addCondition = () => onChange('conditions', [...conditions, {
    id: uuidv4(), field: 'user_message', operator: 'contains', value: '', handle: `output_${conditions.length}`,
  }])

  const updateCondition = (i: number, patch: Partial<TransitionCondition>) =>
    onChange('conditions', conditions.map((c, idx) => idx === i ? { ...c, ...patch } : c))

  const removeCondition = (i: number) =>
    onChange('conditions', conditions.filter((_, idx) => idx !== i))

  return (
    <div className="space-y-4">
      <div><Label>Node Label</Label>
        <Input value={data.label as string || ''} onChange={v => onChange('label', v)} placeholder="Transition" />
      </div>

      <div>
        <Label>Conditions</Label>
        <p className="text-[10px] text-white/25 mb-3">
          Conditions are checked top-to-bottom. First match wins. Unmatched routes to the default handle.
        </p>
        <div className="space-y-3">
          {conditions.map((c, i) => (
            <div key={c.id} className="p-3 rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-white/35 font-semibold">Condition {i + 1}</span>
                <button onClick={() => removeCondition(i)}
                  className="p-1 text-white/20 hover:text-red-400 transition">
                  <Trash size={10} />
                </button>
              </div>
              <div>
                <Label>Field</Label>
                <Select value={c.field} onChange={v => updateCondition(i, { field: v })}>
                  <option value="user_message">User message</option>
                  <option value="last_choice">Last choice value</option>
                  <option value="turn_count">Turn count</option>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>Operator</Label>
                  <Select value={c.operator} onChange={v => updateCondition(i, { operator: v as TransitionCondition['operator'] })}>
                    {OPERATORS.map(op => <option key={op.value} value={op.value}>{op.label}</option>)}
                  </Select>
                </div>
                <div><Label>Value</Label>
                  <Input value={c.value} onChange={v => updateCondition(i, { value: v })} placeholder="match value" />
                </div>
              </div>
              <div><Label>Route to handle</Label>
                <Input value={c.handle} onChange={v => updateCondition(i, { handle: v })}
                  placeholder="output_0" />
                <p className="text-[9px] text-white/20 mt-1">Connect this handle to the next node</p>
              </div>
            </div>
          ))}
          <button onClick={addCondition}
            className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg
                       border border-dashed border-[#222] text-[10px] text-white/25
                       hover:text-white/60 hover:border-[#333] transition">
            <Plus size={10} /> Add Condition
          </button>
        </div>
      </div>
    </div>
  )
}

function EndEditor({ data, onChange }: { data: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  return (
    <div className="space-y-4">
      <div><Label>Closing Message</Label>
        <Textarea value={data.message as string || ''} onChange={v => onChange('message', v)}
          placeholder="Thank you! Have a great day." />
      </div>
    </div>
  )
}

// ── Condition (🔀) ────────────────────────────────────────────
function ConditionEditor({ data, onChange }: { data: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  return (
    <div className="space-y-4">
      <div><Label>Node Label</Label>
        <Input value={data.label as string || ''} onChange={v => onChange('label', v)} placeholder="Condition" />
      </div>
      <div><Label>Variable</Label>
        <Input value={data.variable as string || ''} onChange={v => onChange('variable', v)}
          placeholder="e.g. last_choice" />
        <p className="text-[9px] text-white/20 mt-1">Name of the workflow variable to check</p>
      </div>
      <div><Label>Equals Value</Label>
        <Input value={data.value as string || ''} onChange={v => onChange('value', v)} placeholder="match value" />
      </div>
      <p className="text-[10px] text-white/25">
        If <span className="text-white/50">variable == value</span>, the flow routes to <b>IF</b>. Otherwise it routes to <b>ELSE</b>.
      </p>
    </div>
  )
}

// ── Link (🔗) ─────────────────────────────────────────────────
const LINK_TYPES = [
  { value: 'website',     label: 'Website' },
  { value: 'pdf',         label: 'PDF' },
  { value: 'google_maps', label: 'Google Maps' },
  { value: 'whatsapp',    label: 'WhatsApp' },
  { value: 'email',       label: 'Email' },
  { value: 'phone',       label: 'Phone' },
]

function LinkEditor({ data, onChange }: { data: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  const linkType = (data.linkType as string) || 'website'
  const urlLabel = linkType === 'email' ? 'Email Address' : linkType === 'phone' ? 'Phone Number' : 'URL'
  const urlPlaceholder =
    linkType === 'email' ? 'name@example.com' :
    linkType === 'phone' ? '+1 555 123 4567' :
    linkType === 'whatsapp' ? 'https://wa.me/15551234567' :
    linkType === 'google_maps' ? 'https://maps.google.com/...' :
    linkType === 'pdf' ? 'https://example.com/file.pdf' :
    'https://example.com'

  return (
    <div className="space-y-4">
      <div><Label>Node Label</Label>
        <Input value={data.label as string || ''} onChange={v => onChange('label', v)} placeholder="Link" />
      </div>
      <div><Label>Link Type</Label>
        <Select value={linkType} onChange={v => onChange('linkType', v)}>
          {LINK_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </Select>
      </div>
      <div><Label>{urlLabel}</Label>
        <Input value={data.url as string || ''} onChange={v => onChange('url', v)} placeholder={urlPlaceholder} />
      </div>
      <div><Label>Button Text</Label>
        <Input value={data.buttonText as string || ''} onChange={v => onChange('buttonText', v)} placeholder="Open Link" />
      </div>
      <div className="flex items-center gap-2">
        <input type="checkbox" id="openInNewTab" checked={data.openInNewTab as boolean ?? true}
          onChange={e => onChange('openInNewTab', e.target.checked)} className="accent-[#0ea5e9]" />
        <label htmlFor="openInNewTab" className="text-xs text-white/40">Open in new tab</label>
      </div>
    </div>
  )
}

// ── Rating (⭐) ────────────────────────────────────────────────
function RatingEditor({ data, onChange }: { data: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  return (
    <div className="space-y-4">
      <div><Label>Node Label</Label>
        <Input value={data.label as string || ''} onChange={v => onChange('label', v)} placeholder="Rating" />
      </div>
      <div><Label>Question</Label>
        <Textarea value={data.question as string || ''} onChange={v => onChange('question', v)}
          placeholder="Rate your experience" rows={2} />
      </div>
      <div className="flex items-center gap-2">
        <input type="checkbox" id="allowFeedback" checked={data.allowFeedback as boolean ?? true}
          onChange={e => onChange('allowFeedback', e.target.checked)} className="accent-[#eab308]" />
        <label htmlFor="allowFeedback" className="text-xs text-white/40">Allow optional feedback text</label>
      </div>
      {data.allowFeedback ? (
        <div><Label>Feedback Placeholder</Label>
          <Input value={data.feedbackPlaceholder as string || ''} onChange={v => onChange('feedbackPlaceholder', v)}
            placeholder="Tell us more (optional)..." />
        </div>
      ) : null}
      <div><Label>Store Rating In Variable</Label>
        <Input value={data.variableName as string || ''} onChange={v => onChange('variableName', v)} placeholder="rating" />
        <p className="text-[9px] text-white/20 mt-1">The selected 1–5 star value is saved to this workflow variable</p>
      </div>
    </div>
  )
}

// ── Location (📍) ─────────────────────────────────────────────
function LocationEditor({ data, onChange }: { data: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  return (
    <div className="space-y-4">
      <div><Label>Node Label</Label>
        <Input value={data.label as string || ''} onChange={v => onChange('label', v)} placeholder="Location" />
      </div>
      <div><Label>Address</Label>
        <Textarea value={data.address as string || ''} onChange={v => onChange('address', v)}
          placeholder="123 Main St, Springfield" rows={2} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div><Label>Latitude</Label>
          <Input type="number" value={(data.latitude as number) ?? ''} onChange={v => onChange('latitude', v === '' ? null : Number(v))}
            placeholder="37.7749" />
        </div>
        <div><Label>Longitude</Label>
          <Input type="number" value={(data.longitude as number) ?? ''} onChange={v => onChange('longitude', v === '' ? null : Number(v))}
            placeholder="-122.4194" />
        </div>
      </div>
      <div><Label>Button Text</Label>
        <Input value={data.buttonText as string || ''} onChange={v => onChange('buttonText', v)} placeholder="Open Maps" />
      </div>
    </div>
  )
}

// ── Video (🎥) ─────────────────────────────────────────────────
const VIDEO_TYPES = [
  { value: 'youtube', label: 'YouTube' },
  { value: 'vimeo',   label: 'Vimeo' },
  { value: 'mp4',     label: 'MP4' },
]

function VideoEditor({ data, onChange }: { data: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  const videoType = (data.videoType as string) || 'youtube'
  const placeholder =
    videoType === 'youtube' ? 'https://www.youtube.com/watch?v=...' :
    videoType === 'vimeo' ? 'https://vimeo.com/...' :
    'https://example.com/video.mp4'
  return (
    <div className="space-y-4">
      <div><Label>Node Label</Label>
        <Input value={data.label as string || ''} onChange={v => onChange('label', v)} placeholder="Video" />
      </div>
      <div><Label>Video Type</Label>
        <Select value={videoType} onChange={v => onChange('videoType', v)}>
          {VIDEO_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </Select>
      </div>
      <div><Label>Video URL</Label>
        <Input value={data.url as string || ''} onChange={v => onChange('url', v)} placeholder={placeholder} />
      </div>
      <p className="text-[10px] text-white/25">
        Plays inline in chat when the format is supported, otherwise opens externally.
      </p>
    </div>
  )
}

// ── Panel ─────────────────────────────────────────────────────
const NODE_LABELS: Record<string, string> = {
  start: 'Start Node', text_card: 'Text Card', multiple_choice: 'Multiple Choice',
  ai_agent: 'AI Agent', transition: 'Transition', end: 'End Node',
  condition: 'Condition', link: 'Link', rating: 'Rating', location: 'Location', video: 'Video',
}

export function NodeConfigPanel() {
  // Selecting the resolved node directly (rather than the whole `nodes`
  // array + `selectedNodeId` separately) means this panel only re-renders
  // when the SELECTED node's own object reference changes. Dragging any
  // *other* node on the canvas creates a new `nodes` array each frame,
  // but leaves untouched node objects referentially identical — so with
  // this selector zustand's default equality check correctly skips the
  // re-render instead of re-running this whole config form every frame.
  const node = useWorkflowStore(s => s.nodes.find(n => n.id === s.selectedNodeId))
  const updateNodeData = useWorkflowStore(s => s.updateNodeData)
  const deleteNode = useWorkflowStore(s => s.deleteNode)
  const duplicateNode = useWorkflowStore(s => s.duplicateNode)
  const workflowId = useWorkflowStore(s => s.workflowId)

  if (!node) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-center p-6">
        <Settings size={26} className="text-white/8 mb-3" />
        <p className="text-xs text-white/20">Select a node to configure it</p>
        <p className="text-[10px] text-white/12 mt-1">Click any node on the canvas</p>
      </div>
    )
  }

  const onChange = (key: string, value: unknown) => updateNodeData(node.id, { [key]: value })
  const editorProps = { data: node.data as Record<string, unknown>, onChange }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1a1a1a] flex-shrink-0">
        <div>
          <p className="text-xs font-semibold text-white/80">{(node.type ? NODE_LABELS[node.type] : undefined) || node.type}</p>
          <p className="text-[9px] text-white/25 font-mono mt-0.5">{node.id}</p>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => duplicateNode(node.id)} title="Duplicate"
            className="p-1.5 text-white/20 hover:text-white/60 transition rounded">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
            </svg>
          </button>
          <button onClick={() => deleteNode(node.id)} title="Delete"
            className="p-1.5 text-white/20 hover:text-red-400 transition rounded">
            <Trash2 size={13} />
          </button>
          <button onClick={() => useWorkflowStore.getState().setSelectedNode(null)}
            className="p-1.5 text-white/20 hover:text-white/60 transition rounded">
            <X size={13} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {node.type === 'start'           && <StartEditor {...editorProps} />}
        {node.type === 'text_card'       && <TextCardEditor {...editorProps} />}
        {node.type === 'multiple_choice' && <MultipleChoiceEditor {...editorProps} workflowId={workflowId} />}
        {node.type === 'ai_agent'        && <AIAgentEditor {...editorProps} />}
        {node.type === 'transition'      && <TransitionEditor {...editorProps} />}
        {node.type === 'end'             && <EndEditor {...editorProps} />}
        {node.type === 'condition'       && <ConditionEditor {...editorProps} />}
        {node.type === 'link'            && <LinkEditor {...editorProps} />}
        {node.type === 'rating'          && <RatingEditor {...editorProps} />}
        {node.type === 'location'        && <LocationEditor {...editorProps} />}
        {node.type === 'video'           && <VideoEditor {...editorProps} />}
      </div>
    </div>
  )
}

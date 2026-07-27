'use client'
import { memo } from 'react'
import { NodeProps, Handle, Position } from 'reactflow'
import {
  Play, MessageSquare, List, Bot, GitBranch, Square, Zap,
  GitFork, Link2, Star, MapPin, Video,
} from 'lucide-react'
import { BaseNode } from './BaseNode'

// ── VIBRANT GRADIENT PALETTE (unique per node type) ─────────────────────────
// Purely a visual/UI concern — used only for node chrome (outline, header
// wash, corner bloom, glow). Does not affect data, routing, or behavior.
const GRADIENTS = {
  start: ['#34eea0', '#059669'] as [string, string],           // Emerald Green
  text: ['#38bdf8', '#2563eb'] as [string, string],             // Electric Blue
  multipleChoice: ['#fbbf24', '#ea580c'] as [string, string],   // Orange
  aiAgent: ['#c4b5fd', '#7c3aed'] as [string, string],          // Purple
  transition: ['#f9a8d4', '#db2777'] as [string, string],       // Pink
  end: ['#fb7185', '#9f1239'] as [string, string],              // Crimson
  // New node types (v29) — each gets its own accent, soft-glow only.
  condition: ['#fdba74', '#c2410c'] as [string, string],        // 🟠 Amber-Orange
  link: ['#7dd3fc', '#0369a1'] as [string, string],             // 🔵 Sky Blue
  rating: ['#fde68a', '#a16207'] as [string, string],           // 🟡 Gold Yellow
  location: ['#f87171', '#7f1d1d'] as [string, string],         // 🔴 Deep Red
  video: ['#e9d5ff', '#7e22ce'] as [string, string],            // 🟣 Violet-Purple
}

// ── START ─────────────────────────────────────────────────────────────────────

export const StartNode = memo((props: NodeProps) => (
  <BaseNode
    {...props}
    icon={<Play size={12} />}
    label="Start"
    accentColor="#22c55e"
    gradient={GRADIENTS.start}
    shape="octagon"
    stacked
    handles={
      <Handle type="source" position={Position.Bottom} id="output_0" className="tb-handle"
        style={{ background: '#22c55e', borderColor: '#166534' }} />
    }
  >
    <p className="text-xs text-white/60 leading-relaxed">
      {props.data.welcomeMessage || 'Workflow entry point'}
    </p>
  </BaseNode>
))
StartNode.displayName = 'StartNode'

// ── TEXT CARD ─────────────────────────────────────────────────────────────────

export const TextCardNode = memo((props: NodeProps) => (
  <BaseNode
    {...props}
    icon={<MessageSquare size={12} />}
    label="Text Card"
    accentColor="#3b82f6"
    gradient={GRADIENTS.text}
    shape="rounded"
    handles={
      <>
        <Handle type="target" position={Position.Top} id="input" className="tb-handle"
          style={{ background: '#3b82f6', borderColor: '#1d4ed8' }} />
        <Handle type="source" position={Position.Bottom} id="output_0" className="tb-handle"
          style={{ background: '#3b82f6', borderColor: '#1d4ed8' }} />
      </>
    }
  >
    <p className="text-sm font-medium text-white/90 truncate">
      {props.data.label || 'Text Card'}
    </p>
    <p className="text-xs text-white/40 line-clamp-2 leading-relaxed">
      {props.data.content || 'No content'}
    </p>
  </BaseNode>
))
TextCardNode.displayName = 'TextCardNode'

// ── MULTIPLE CHOICE ───────────────────────────────────────────────────────────

export const MultipleChoiceNode = memo((props: NodeProps) => {
  const choices: Array<{ label: string }> = props.data.choices || []
  const image: { url: string } | null | undefined = props.data.image
  return (
    <BaseNode
      {...props}
      icon={<List size={12} />}
      label="Multiple Choice"
      accentColor="#f59e0b"
      gradient={GRADIENTS.multipleChoice}
      shape="rounded"
      handles={
        <>
          <Handle type="target" position={Position.Top} id="input" className="tb-handle"
            style={{ background: '#f59e0b', borderColor: '#b45309' }} />
          {choices.map((_, i) => (
            <Handle key={i} type="source" position={Position.Bottom} id={`choice_${i}`} className="tb-handle"
              style={{ background: '#f59e0b', borderColor: '#b45309', left: `${((i + 1) / (choices.length + 1)) * 100}%` }} />
          ))}
        </>
      }
    >
      {image?.url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={image.url} alt="" className="w-full h-16 object-cover rounded-md mb-1 border border-[#f59e0b]/20" />
      )}
      <p className="text-sm font-medium text-white/90 truncate">
        {props.data.question || 'Select an option'}
      </p>
      <div className="space-y-1 mt-1">
        {choices.slice(0, 3).map((c, i) => (
          <div key={i} className="text-xs px-2 py-1 rounded bg-[#f59e0b]/10 text-[#fbbf24] border border-[#f59e0b]/20 truncate">
            {c.label}
          </div>
        ))}
        {choices.length > 3 && (
          <p className="text-[10px] text-white/30">+{choices.length - 3} more</p>
        )}
      </div>
    </BaseNode>
  )
})
MultipleChoiceNode.displayName = 'MultipleChoiceNode'

// ── AI AGENT ──────────────────────────────────────────────────────────────────

const PROVIDER_COLORS: Record<string, string> = {
  gemini: '#4285f4',
}

export const AIAgentNode = memo((props: NodeProps) => {
  const { data } = props
  const providerColor = PROVIDER_COLORS[data.provider] || '#818cf8'
  return (
    <BaseNode
      {...props}
      icon={<Bot size={12} />}
      label="AI Agent"
      accentColor="#818cf8"
      gradient={GRADIENTS.aiAgent}
      shape="rounded"
      premium
      handles={
        <>
          <Handle type="target" position={Position.Top} id="input" className="tb-handle"
            style={{ background: '#818cf8', borderColor: '#4338ca' }} />
          <Handle type="source" position={Position.Bottom} id="output_0" className="tb-handle"
            style={{ background: '#818cf8', borderColor: '#4338ca' }} />
        </>
      }
    >
      <p className="text-sm font-medium text-white/90 truncate">
        {data.label || 'AI Agent'}
      </p>
      {data.systemPrompt && (
        <p className="text-xs text-white/35 line-clamp-2 leading-relaxed">
          {data.systemPrompt}
        </p>
      )}
      <div className="flex gap-1.5 flex-wrap mt-1">
        <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
          style={{ background: `${providerColor}18`, color: providerColor, border: `1px solid ${providerColor}30` }}>
          {data.provider || 'auto (my default)'}
        </span>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-white/35">
          {data.model || 'default'}
        </span>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-white/35">
          t:{data.temperature ?? 0.7}
        </span>
        {data.knowledgeBaseId && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            KB
          </span>
        )}
      </div>
    </BaseNode>
  )
})
AIAgentNode.displayName = 'AIAgentNode'

// ── TRANSITION ────────────────────────────────────────────────────────────────

export const TransitionNode = memo((props: NodeProps) => {
  const conditions: unknown[] = props.data.conditions || []
  return (
    <BaseNode
      {...props}
      icon={<GitBranch size={12} />}
      label="Transition"
      accentColor="#ec4899"
      gradient={GRADIENTS.transition}
      shape="rounded"
      handles={
        <>
          <Handle type="target" position={Position.Top} id="input" className="tb-handle"
            style={{ background: '#ec4899', borderColor: '#9d174d' }} />
          <Handle type="source" position={Position.Bottom} id="output_0" className="tb-handle"
            style={{ background: '#ec4899', borderColor: '#9d174d', left: '33%' }} />
          <Handle type="source" position={Position.Bottom} id="default" className="tb-handle"
            style={{ background: '#6b7280', borderColor: '#374151', left: '66%' }} />
        </>
      }
    >
      <p className="text-sm font-medium text-white/90">{props.data.label || 'Transition'}</p>
      <p className="text-xs text-white/40">
        {conditions.length > 0 ? `${conditions.length} condition${conditions.length > 1 ? 's' : ''}` : 'No conditions — routes to default'}
      </p>
    </BaseNode>
  )
})
TransitionNode.displayName = 'TransitionNode'

// ── END ───────────────────────────────────────────────────────────────────────

export const EndNode = memo((props: NodeProps) => (
  <BaseNode
    {...props}
    icon={<Square size={12} />}
    label="End"
    accentColor="#ef4444"
    gradient={GRADIENTS.end}
    shape="rounded"
    handles={
      <Handle type="target" position={Position.Top} id="input" className="tb-handle"
        style={{ background: '#ef4444', borderColor: '#991b1b' }} />
    }
  >
    <p className="text-xs text-white/60 leading-relaxed">
      {props.data.message || 'Conversation ends here'}
    </p>
  </BaseNode>
))
EndNode.displayName = 'EndNode'

// ── CONDITION (🔀) ────────────────────────────────────────────────────────────

export const ConditionNode = memo((props: NodeProps) => {
  const { data } = props
  return (
    <BaseNode
      {...props}
      icon={<GitFork size={12} />}
      label="Condition"
      accentColor="#f97316"
      gradient={GRADIENTS.condition}
      shape="rounded"
      handles={
        <>
          <Handle type="target" position={Position.Top} id="input" className="tb-handle"
            style={{ background: '#f97316', borderColor: '#9a3412' }} />
          <Handle type="source" position={Position.Bottom} id="if" className="tb-handle"
            style={{ background: '#f97316', borderColor: '#9a3412', left: '33%' }} />
          <Handle type="source" position={Position.Bottom} id="else" className="tb-handle"
            style={{ background: '#6b7280', borderColor: '#374151', left: '66%' }} />
        </>
      }
    >
      <p className="text-sm font-medium text-white/90 truncate">{data.label || 'Condition'}</p>
      <p className="text-xs text-white/40 truncate">
        {data.variable ? <span className="text-[#fdba74]">{'{{' + data.variable + '}}'}</span> : 'variable'}
        <span className="text-white/25"> == </span>
        <span className="text-white/60">{data.value || '""'}</span>
      </p>
      <div className="flex gap-2 mt-1">
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#f97316]/10 text-[#fdba74] border border-[#f97316]/20">IF</span>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-white/35 border border-white/10">ELSE</span>
      </div>
    </BaseNode>
  )
})
ConditionNode.displayName = 'ConditionNode'

// ── LINK (🔗) ─────────────────────────────────────────────────────────────────

const LINK_TYPE_LABELS: Record<string, string> = {
  website: 'Website', pdf: 'PDF', google_maps: 'Google Maps',
  whatsapp: 'WhatsApp', email: 'Email', phone: 'Phone',
}

export const LinkNode = memo((props: NodeProps) => {
  const { data } = props
  return (
    <BaseNode
      {...props}
      icon={<Link2 size={12} />}
      label="Link"
      accentColor="#0ea5e9"
      gradient={GRADIENTS.link}
      shape="rounded"
      handles={
        <>
          <Handle type="target" position={Position.Top} id="input" className="tb-handle"
            style={{ background: '#0ea5e9', borderColor: '#075985' }} />
          <Handle type="source" position={Position.Bottom} id="output_0" className="tb-handle"
            style={{ background: '#0ea5e9', borderColor: '#075985' }} />
        </>
      }
    >
      <p className="text-sm font-medium text-white/90 truncate">
        {data.buttonText || 'Open Link'}
      </p>
      <p className="text-xs text-white/40 truncate">{data.url || 'No URL set'}</p>
      <div className="flex gap-1.5 flex-wrap mt-1">
        <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-[#0ea5e9]/10 text-[#7dd3fc] border border-[#0ea5e9]/20">
          {LINK_TYPE_LABELS[data.linkType] || 'Website'}
        </span>
        {data.openInNewTab && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-white/35">New tab</span>
        )}
      </div>
    </BaseNode>
  )
})
LinkNode.displayName = 'LinkNode'

// ── RATING (⭐) ────────────────────────────────────────────────────────────────

export const RatingNode = memo((props: NodeProps) => (
  <BaseNode
    {...props}
    icon={<Star size={12} />}
    label="Rating"
    accentColor="#eab308"
    gradient={GRADIENTS.rating}
    shape="rounded"
    handles={
      <>
        <Handle type="target" position={Position.Top} id="input" className="tb-handle"
          style={{ background: '#eab308', borderColor: '#854d0e' }} />
        <Handle type="source" position={Position.Bottom} id="output_0" className="tb-handle"
          style={{ background: '#eab308', borderColor: '#854d0e' }} />
      </>
    }
  >
    <p className="text-sm font-medium text-white/90 truncate">
      {props.data.question || 'Rate your experience'}
    </p>
    <div className="flex items-center gap-0.5 mt-1">
      {Array.from({ length: 5 }).map((_, i) => (
        <Star key={i} size={12} className="text-[#fde68a]" fill="#fde68a" />
      ))}
    </div>
    {props.data.allowFeedback && (
      <p className="text-[10px] text-white/30 mt-1">+ optional feedback text</p>
    )}
  </BaseNode>
))
RatingNode.displayName = 'RatingNode'

// ── LOCATION (📍) ─────────────────────────────────────────────────────────────

export const LocationNode = memo((props: NodeProps) => {
  const { data } = props
  const hasCoords = data.latitude != null && data.longitude != null
  return (
    <BaseNode
      {...props}
      icon={<MapPin size={12} />}
      label="Location"
      accentColor="#dc2626"
      gradient={GRADIENTS.location}
      shape="rounded"
      handles={
        <>
          <Handle type="target" position={Position.Top} id="input" className="tb-handle"
            style={{ background: '#dc2626', borderColor: '#7f1d1d' }} />
          <Handle type="source" position={Position.Bottom} id="output_0" className="tb-handle"
            style={{ background: '#dc2626', borderColor: '#7f1d1d' }} />
        </>
      }
    >
      <p className="text-sm font-medium text-white/90 truncate">
        {data.address || 'No address set'}
      </p>
      <p className="text-xs text-white/40 truncate">
        {hasCoords ? `${data.latitude}, ${data.longitude}` : 'Lat/Lng not set'}
      </p>
      <div className="text-[10px] px-1.5 py-0.5 mt-1 rounded bg-[#dc2626]/10 text-[#f87171] border border-[#dc2626]/20 inline-block">
        {data.buttonText || 'Open Maps'}
      </div>
    </BaseNode>
  )
})
LocationNode.displayName = 'LocationNode'

// ── VIDEO (🎥) ─────────────────────────────────────────────────────────────────

const VIDEO_TYPE_LABELS: Record<string, string> = { youtube: 'YouTube', vimeo: 'Vimeo', mp4: 'MP4' }

export const VideoNode = memo((props: NodeProps) => {
  const { data } = props
  return (
    <BaseNode
      {...props}
      icon={<Video size={12} />}
      label="Video"
      accentColor="#a855f7"
      gradient={GRADIENTS.video}
      shape="rounded"
      handles={
        <>
          <Handle type="target" position={Position.Top} id="input" className="tb-handle"
            style={{ background: '#a855f7', borderColor: '#6b21a8' }} />
          <Handle type="source" position={Position.Bottom} id="output_0" className="tb-handle"
            style={{ background: '#a855f7', borderColor: '#6b21a8' }} />
        </>
      }
    >
      <p className="text-sm font-medium text-white/90 truncate">
        {data.label || 'Video'}
      </p>
      <p className="text-xs text-white/40 truncate">{data.url || 'No URL set'}</p>
      <span className="text-[10px] px-1.5 py-0.5 mt-1 rounded-full font-medium bg-[#a855f7]/10 text-[#e9d5ff] border border-[#a855f7]/20 inline-block">
        {VIDEO_TYPE_LABELS[data.videoType] || 'YouTube'}
      </span>
    </BaseNode>
  )
})
VideoNode.displayName = 'VideoNode'

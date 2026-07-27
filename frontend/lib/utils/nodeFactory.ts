import { v4 as uuidv4 } from 'uuid'
import type { WorkflowNode, NodeType } from '@/types'

const NODE_DEFAULTS: Record<NodeType, Partial<WorkflowNode['data']>> = {
  start: { label: 'Start', welcomeMessage: 'Hello! How can I help you today?' },
  text_card: { label: 'Text Card', content: 'Enter your message here...' },
  multiple_choice: {
    label: 'Multiple Choice',
    question: 'Please select an option:',
    choices: [
      { label: 'Option 1', value: 'option_1' },
      { label: 'Option 2', value: 'option_2' },
    ],
  },
  ai_agent: {
    label: 'AI Agent',
    // ROOT CAUSE FIX: this used to hardcode 'openai'/'gpt-4o-mini' as the
    // default provider/model for every newly-added AI Agent node. Because
    // an explicit provider set on a node always wins over the user's own
    // configured default (see resolve_agent_provider in
    // app/services/ai_engine.py), this silently locked every new node to
    // OpenAI regardless of what the user set as their default provider —
    // Gemini included. Leaving these unset matches NodeConfigPanel's own
    // "Use my default provider" convention and lets it resolve at run time.
    provider: undefined,
    model: '',
    systemPrompt: 'You are a helpful assistant.',
    instructions: '',
    temperature: 0.7,
    maxTokens: 1000,
    contextWindow: 10,
    memoryEnabled: true,
    stayOnNode: true,
  },
  transition: {
    label: 'Transition',
    conditions: [],
  },
  end: { label: 'End', message: 'Thank you! Have a great day.' },
  condition: {
    label: 'Condition',
    variable: '',
    value: '',
  },
  link: {
    label: 'Link',
    linkType: 'website',
    url: '',
    buttonText: 'Open Link',
    openInNewTab: true,
  },
  rating: {
    label: 'Rating',
    question: 'Rate your experience',
    allowFeedback: true,
    feedbackPlaceholder: 'Tell us more (optional)...',
    variableName: 'rating',
  },
  location: {
    label: 'Location',
    address: '',
    latitude: null,
    longitude: null,
    buttonText: 'Open Maps',
  },
  video: {
    label: 'Video',
    videoType: 'youtube',
    url: '',
  },
}

export function createNode(
  type: NodeType,
  position: { x: number; y: number },
  overrides: Partial<WorkflowNode['data']> = {}
): WorkflowNode {
  return {
    id: `${type}_${uuidv4().replace(/-/g, '').slice(0, 8)}`,
    type,
    position,
    data: { ...NODE_DEFAULTS[type], ...overrides } as WorkflowNode['data'],
  }
}

export const NODE_LIBRARY = [
  {
    type: 'start' as NodeType,
    label: 'Start',
    description: 'Entry point of your workflow',
    icon: 'Play',
    color: '#22c55e',
  },
  {
    type: 'text_card' as NodeType,
    label: 'Text Card',
    description: 'Send a message with rich text and variables',
    icon: 'MessageSquare',
    color: '#3b82f6',
  },
  {
    type: 'multiple_choice' as NodeType,
    label: 'Multiple Choice',
    description: 'Present buttons for the user to click',
    icon: 'List',
    color: '#f59e0b',
  },
  {
    type: 'ai_agent' as NodeType,
    label: 'AI Agent',
    description: 'Intelligent AI-powered response node',
    icon: 'Bot',
    color: '#818cf8',
  },
  {
    type: 'transition' as NodeType,
    label: 'Transition',
    description: 'Conditional routing between nodes',
    icon: 'GitBranch',
    color: '#ec4899',
  },
  {
    type: 'end' as NodeType,
    label: 'End',
    description: 'Close the conversation',
    icon: 'Square',
    color: '#ef4444',
  },
  {
    type: 'condition' as NodeType,
    label: 'Condition',
    description: 'Branch with a variable == value check (IF / ELSE)',
    icon: 'GitFork',
    color: '#f97316',
  },
  {
    type: 'link' as NodeType,
    label: 'Link',
    description: 'Website, PDF, Maps, WhatsApp, Email or Phone link button',
    icon: 'Link2',
    color: '#0ea5e9',
  },
  {
    type: 'rating' as NodeType,
    label: 'Rating',
    description: 'Collect a 1-5 star rating with optional feedback',
    icon: 'Star',
    color: '#eab308',
  },
  {
    type: 'location' as NodeType,
    label: 'Location',
    description: 'Show an address / map location with an Open Maps button',
    icon: 'MapPin',
    color: '#dc2626',
  },
  {
    type: 'video' as NodeType,
    label: 'Video',
    description: 'Play a YouTube, Vimeo, or MP4 video inside chat',
    icon: 'Video',
    color: '#a855f7',
  },
]

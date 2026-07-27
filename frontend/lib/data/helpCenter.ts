// ============================================================
// ThunderBots — Help Center content (data-driven)
// ------------------------------------------------------------
// To add or edit an FAQ: just add/edit an object in FAQS below.
// To add a category: add it to CATEGORIES and use its `id` as
// the `category` field on any FAQ entry.
// No component changes are required for either.
// ============================================================
import {
  Rocket, Bot, GitBranch, Wand2, Database, Store,
  UploadCloud, Users, CreditCard, UserCog, type LucideIcon,
} from 'lucide-react'

export interface HelpCategory {
  id: string
  label: string
  description: string
  icon: LucideIcon
}

export interface FAQEntry {
  id: string
  category: string
  question: string
  answer: string
  keywords?: string[]
}

export const CATEGORIES: HelpCategory[] = [
  { id: 'getting-started', label: 'Getting Started', description: 'Set up your account and build your first bot', icon: Rocket },
  { id: 'ai-agents', label: 'AI Agents', description: 'Configure providers, models, and agent behavior', icon: Bot },
  { id: 'workflow-builder', label: 'Workflow Builder', description: 'Nodes, connections, and the visual canvas', icon: GitBranch },
  { id: 'thunderguide', label: 'ThunderGuide', description: 'AI-assisted guidance while you build', icon: Wand2 },
  { id: 'knowledge-base', label: 'Knowledge Base', description: 'Documents, embeddings, and retrieval', icon: Database },
  { id: 'marketplace', label: 'Marketplace', description: 'Publishing, buying, and installing templates', icon: Store },
  { id: 'deploy', label: 'Deploy', description: 'Publishing your bot and sharing it with users', icon: UploadCloud },
  { id: 'teams', label: 'Teams', description: 'Collaborators, roles, and permissions', icon: Users },
  { id: 'billing', label: 'Billing', description: 'Plans, invoices, and payment methods', icon: CreditCard },
  { id: 'account', label: 'Account', description: 'Profile, security, and preferences', icon: UserCog },
]

export const FAQS: FAQEntry[] = [
  // Getting Started
  {
    id: 'gs-1',
    category: 'getting-started',
    question: 'How do I create my first chatbot?',
    answer: 'Go to Workflows on your dashboard and click "New Workflow". You\'ll land in the Builder where you can drag nodes onto the canvas to define how your bot responds. Start from a blank canvas or a template.',
    keywords: ['create', 'new', 'first bot', 'start'],
  },
  {
    id: 'gs-2',
    category: 'getting-started',
    question: 'What is a "workflow" in ThunderBots?',
    answer: 'A workflow is the visual definition of your chatbot: a graph of nodes (triggers, AI responses, logic, actions) connected together. When you deploy a workflow, it becomes a live chatbot.',
    keywords: ['workflow', 'definition'],
  },
  {
    id: 'gs-3',
    category: 'getting-started',
    question: 'Is there a recommended order to set things up?',
    answer: 'Most people: 1) create a workflow, 2) connect an AI provider, 3) add a Knowledge Base if the bot needs custom knowledge, 4) test in the chat preview, 5) deploy. See the Quick Start Guide on this page for a walkthrough.',
    keywords: ['setup', 'order', 'quick start'],
  },

  // AI Agents
  {
    id: 'ai-1',
    category: 'ai-agents',
    question: 'Which AI providers are supported?',
    answer: 'ThunderBots is powered by Google Gemini. Add your Gemini API key under Settings → AI Providers.',
    keywords: ['provider', 'gemini', 'api key'],
  },
  {
    id: 'ai-2',
    category: 'ai-agents',
    question: 'Can one workflow use multiple AI models?',
    answer: 'Yes. Each AI node in your workflow can be configured with its own Gemini model, so different steps of a conversation can use different models depending on speed or reasoning needs.',
    keywords: ['multiple', 'model', 'switch model'],
  },
  {
    id: 'ai-3',
    category: 'ai-agents',
    question: 'Why is my agent responding slowly?',
    answer: 'Response time depends mostly on the selected model and provider load. Try a faster/smaller model for latency-sensitive steps, and reserve larger models for complex reasoning nodes.',
    keywords: ['slow', 'latency', 'performance'],
  },

  // Workflow Builder
  {
    id: 'wb-1',
    category: 'workflow-builder',
    question: 'How do I connect two nodes?',
    answer: 'Drag from the small connector dot on the edge of a node to the connector on another node. Invalid connections are rejected automatically to keep your workflow valid.',
    keywords: ['connect', 'node', 'edge'],
  },
  {
    id: 'wb-2',
    category: 'workflow-builder',
    question: 'Can I undo changes in the Builder?',
    answer: 'Yes, use Ctrl+Z / Cmd+Z to undo and Ctrl+Shift+Z / Cmd+Shift+Z to redo while the canvas is focused.',
    keywords: ['undo', 'redo', 'history'],
  },
  {
    id: 'wb-3',
    category: 'workflow-builder',
    question: 'My changes aren\'t saving — what should I check?',
    answer: 'The Builder autosaves a few seconds after you stop editing. Check the save indicator near the top of the canvas; if it shows an error, verify your connection and try again.',
    keywords: ['save', 'autosave', 'not saving'],
  },

  // ThunderGuide
  {
    id: 'tg-1',
    category: 'thunderguide',
    question: 'What is ThunderGuide?',
    answer: 'ThunderGuide is the built-in AI assistant that helps you design workflows — suggesting nodes, explaining errors, and answering "how do I…" questions right inside the Builder.',
    keywords: ['guide', 'assistant', 'ai help'],
  },
  {
    id: 'tg-2',
    category: 'thunderguide',
    question: 'How do I open ThunderGuide while building?',
    answer: 'Click the ThunderGuide icon in the Builder toolbar, or use the "Create with AI" entry point from the main navigation to generate a workflow from a text description.',
    keywords: ['open', 'toolbar', 'create with ai'],
  },

  // Knowledge Base
  {
    id: 'kb-1',
    category: 'knowledge-base',
    question: 'What file types can I upload to a Knowledge Base?',
    answer: 'Common document formats such as PDF, DOCX, TXT, and Markdown are supported. Uploaded documents are chunked and embedded so your bot can retrieve relevant passages at answer time.',
    keywords: ['upload', 'file types', 'document'],
  },
  {
    id: 'kb-2',
    category: 'knowledge-base',
    question: 'Why did my document fail to process?',
    answer: 'Processing can fail due to a temporary embedding-provider or storage hiccup. The pipeline automatically retries transient errors; if it still fails, try re-uploading the document.',
    keywords: ['failed', 'processing', 'error', 'embedding'],
  },
  {
    id: 'kb-3',
    category: 'knowledge-base',
    question: 'How do I connect a Knowledge Base to my bot?',
    answer: 'Add a Knowledge Base node to your workflow and select the knowledge base you want it to query, then connect it to the AI node that should use it as context.',
    keywords: ['connect', 'attach', 'node'],
  },

  // Marketplace
  {
    id: 'mp-1',
    category: 'marketplace',
    question: 'How do I install a template from the Marketplace?',
    answer: 'Open Marketplace from the main navigation, find a template you like, and click "Use Template". It will be copied into your workflows so you can customize it freely.',
    keywords: ['install', 'template', 'use template'],
  },
  {
    id: 'mp-2',
    category: 'marketplace',
    question: 'Can I publish my own workflow to the Marketplace?',
    answer: 'Yes. From a workflow\'s settings, choose "Publish to Marketplace", add a title and description, and submit it for listing.',
    keywords: ['publish', 'sell', 'list'],
  },

  // Deploy
  {
    id: 'dp-1',
    category: 'deploy',
    question: 'How do I deploy my chatbot?',
    answer: 'Open your workflow, go to the Deploy panel, customize branding if you\'d like, and click Publish. You\'ll get a shareable chat link and an embeddable widget snippet.',
    keywords: ['deploy', 'publish', 'go live'],
  },
  {
    id: 'dp-2',
    category: 'deploy',
    question: 'Can I embed my bot on my own website?',
    answer: 'Yes. The Deploy panel provides a widget.js snippet and an iframe embed option, both of which you can paste directly into your site.',
    keywords: ['embed', 'widget', 'iframe', 'website'],
  },
  {
    id: 'dp-3',
    category: 'deploy',
    question: 'How do I customize my bot\'s branding before deploying?',
    answer: 'Use Deploy Page Customization to set colors, logo, and messaging. Changes are saved as a draft and previewed live before you publish them.',
    keywords: ['branding', 'customize', 'colors', 'logo'],
  },

  // Teams
  {
    id: 'tm-1',
    category: 'teams',
    question: 'How do I invite teammates?',
    answer: 'Go to Teams, open your team, and click "Invite Member". Enter their email and choose a role; they\'ll receive an invite to join.',
    keywords: ['invite', 'member', 'collaborator'],
  },
  {
    id: 'tm-2',
    category: 'teams',
    question: 'What permissions do different team roles have?',
    answer: 'Roles typically range from Viewer (read-only) to Editor (can modify workflows) to Admin (can manage members and billing). Exact permissions are shown on the team\'s Members page.',
    keywords: ['roles', 'permissions', 'admin', 'editor'],
  },

  // Billing
  {
    id: 'bl-1',
    category: 'billing',
    question: 'Where can I see my current plan and usage?',
    answer: 'Your plan, usage, and invoices are available under Settings → Billing. You can upgrade, downgrade, or update your payment method there.',
    keywords: ['plan', 'usage', 'invoice'],
  },
  {
    id: 'bl-2',
    category: 'billing',
    question: 'How do I update my payment method?',
    answer: 'Go to Settings → Billing → Payment Method and click "Update". Changes take effect immediately for your next billing cycle.',
    keywords: ['payment', 'card', 'update'],
  },

  // Account
  {
    id: 'ac-1',
    category: 'account',
    question: 'How do I change my password?',
    answer: 'Go to Settings → Account → Security and choose "Change Password". You\'ll need to confirm your current password first.',
    keywords: ['password', 'security', 'change'],
  },
  {
    id: 'ac-2',
    category: 'account',
    question: 'How do I update my profile information?',
    answer: 'Open Settings → Account to edit your name, email, and preferences such as theme and language.',
    keywords: ['profile', 'update', 'preferences'],
  },
]

export interface QuickStartStep {
  title: string
  description: string
}

export const QUICK_START_STEPS: QuickStartStep[] = [
  { title: 'Create a workflow', description: 'From your dashboard, click "New Workflow" to open the visual Builder.' },
  { title: 'Add an AI node', description: 'Drag an AI node onto the canvas and connect your preferred provider under Settings.' },
  { title: 'Add a Knowledge Base (optional)', description: 'Upload documents so your bot can answer from your own content.' },
  { title: 'Test in preview', description: 'Use the built-in chat preview to try your bot before going live.' },
  { title: 'Deploy', description: 'Open the Deploy panel, customize branding, and publish to get your shareable link and widget.' },
]

export function searchFAQs(query: string, categoryId?: string): FAQEntry[] {
  const q = query.trim().toLowerCase()
  return FAQS.filter(faq => {
    if (categoryId && faq.category !== categoryId) return false
    if (!q) return true
    return (
      faq.question.toLowerCase().includes(q) ||
      faq.answer.toLowerCase().includes(q) ||
      (faq.keywords || []).some(k => k.toLowerCase().includes(q))
    )
  })
}

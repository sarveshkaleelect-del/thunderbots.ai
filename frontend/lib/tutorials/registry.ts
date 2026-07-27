import type { TutorialConfig } from './types'

/**
 * Central tutorial registry.
 *
 * Each entry is looked up two ways:
 *  1. Path-based, automatic — TutorialProvider watches the route and
 *     auto-starts the best-matching config's tutorial on first visit.
 *  2. Feature-key based, manual — a mounting panel/component (e.g. the
 *     Knowledge Base or Chat Tester panel inside the Builder, which share
 *     a route with other panels) calls `useFeatureTutorial('knowledge-base')`
 *     directly instead of relying on route matching.
 *
 * Adding a new feature later is just adding another entry here + tagging
 * its real elements with `data-tutorial="<step id>"` — no core-engine
 * changes required.
 */
export const TUTORIAL_REGISTRY: TutorialConfig[] = [
  {
    featureKey: 'dashboard',
    label: 'Dashboard',
    paths: ['/dashboard'],
    steps: [
      { id: 'dashboard-new-workflow', title: 'Start a new bot', body: 'Click here to create a new AI workflow from scratch.', gesture: 'click', placement: 'bottom' },
      { id: 'dashboard-quick-actions', title: 'Quick actions', body: 'Jump straight into AI generation, the Marketplace, or a channel.', gesture: 'try', placement: 'bottom' },
      { id: 'dashboard-search', title: 'Find a workflow', body: 'Search your workflows by name any time.', gesture: 'click', placement: 'bottom' },
    ],
  },
  {
    featureKey: 'workflow-builder',
    label: 'Workflow Builder',
    paths: [/^\/builder\//],
    steps: [
      { id: 'builder-node-library', title: 'Node library', body: 'Drag a node from here onto the canvas.', gesture: 'drag', placement: 'right' },
      { id: 'builder-drag-node', title: 'Pick a node', body: 'Drag this onto the canvas to add it.', gesture: 'drag', placement: 'right' },
      { id: 'builder-canvas', title: 'Drop it here', body: 'Drop nodes anywhere on the canvas, then connect them by dragging between their handles.', gesture: 'drop', placement: 'top' },
      { id: 'builder-save', title: 'Save your work', body: 'Save here whenever you want to keep your changes.', gesture: 'save', placement: 'bottom' },
      { id: 'builder-panel-switcher', title: 'More tools', body: 'Switch between Knowledge Base, Chat Tester, Deploy, and more.', gesture: 'click', placement: 'bottom' },
    ],
  },
  {
    featureKey: 'knowledge-base',
    label: 'Knowledge Base',
    paths: [], // panel-scoped — triggered manually, see KnowledgePanel.tsx
    steps: [
      { id: 'kb-upload', title: 'Upload a document', body: 'Click here to upload a PDF, DOCX, TXT, or Markdown file.', gesture: 'click', placement: 'bottom' },
      { id: 'kb-documents', title: 'Processing', body: 'Your file appears here while it processes — then it\u2019s ready to use.', gesture: 'none', placement: 'top' },
    ],
  },
  {
    featureKey: 'ai-chat',
    label: 'AI Chat',
    paths: [], // panel-scoped — triggered manually, see ChatTesterPanel.tsx
    steps: [
      { id: 'chat-start', title: 'Start a conversation', body: 'Click Start to begin chatting with your workflow.', gesture: 'click', placement: 'left' },
      { id: 'chat-messages', title: 'Your conversation', body: 'Messages appear here, including Markdown formatting from the AI.', gesture: 'none', placement: 'top' },
      { id: 'chat-input', title: 'Say something', body: 'Type here and press Enter to send.', gesture: 'try', placement: 'top' },
    ],
  },
  {
    featureKey: 'shop-assistant',
    label: 'Smart Shop Assistant',
    paths: ['/shop-assistant'],
    steps: [
      { id: 'shop-launcher-create', title: 'Create a shop', body: 'Name your shop and create it to get a public QR code.', gesture: 'try', placement: 'bottom' },
      { id: 'shop-launcher-list', title: 'Your shops', body: 'Open Shop Admin any time to manage inventory and reservations.', gesture: 'click', placement: 'top' },
    ],
  },
  {
    featureKey: 'shop-assistant-admin',
    label: 'Shop Admin',
    paths: [/^\/shop-assistant\/[^/]+\/admin/],
    steps: [
      { id: 'shop-add-product', title: 'Add a product', body: 'Click here to add a product to your inventory.', gesture: 'click', placement: 'top' },
      { id: 'shop-upload-images', title: 'Upload images', body: 'Drag & drop or click to add product photos.', gesture: 'drop', placement: 'top', optional: true },
      { id: 'shop-reservations', title: 'Reservations', body: 'Confirm, ready, and complete customer reservations here.', gesture: 'none', placement: 'top' },
    ],
  },
  {
    featureKey: 'call-agent',
    label: 'AI Calls',
    paths: ['/call-agent/agents'],
    steps: [
      { id: 'call-agent-create', title: 'Create a voice agent', body: 'Click here to create a new AI Call Agent.', gesture: 'click', placement: 'bottom' },
      { id: 'call-agent-nav', title: 'Configure, test, publish', body: 'Use this bar to add instructions, test, and publish your agent.', gesture: 'try', placement: 'bottom' },
      { id: 'call-agent-embed', title: 'Embed code', body: 'Copy your embed code from here once you\u2019re ready to publish.', gesture: 'click', placement: 'bottom' },
    ],
  },
  {
    featureKey: 'analytics',
    label: 'Analytics',
    paths: ['/analytics'],
    steps: [
      { id: 'page-header', title: 'Analytics', body: 'Track conversations, messages, and engagement across every channel here.', gesture: 'none', placement: 'bottom' },
    ],
  },
  {
    featureKey: 'ai-supervisor',
    label: 'AI Customer Insights',
    paths: ['/ai-supervisor'],
    steps: [
      { id: 'page-header', title: 'AI Customer Insights', body: 'Monitor live conversations, review AI responses, and step in when needed.', gesture: 'none', placement: 'bottom' },
    ],
  },
  {
    featureKey: 'business-advisor',
    label: 'AI Business Advisor',
    paths: [/^\/shop-assistant\/[^/]+\/advisor/],
    steps: [
      { id: 'page-header', title: 'AI Business Advisor', body: 'Get AI-powered recommendations, predictions, and alerts for your shop.', gesture: 'none', placement: 'bottom' },
    ],
  },
  {
    featureKey: 'teams',
    label: 'Team Workspace',
    paths: ['/teams'],
    steps: [
      { id: 'page-header', title: 'Team Workspace', body: 'Collaborate with your team, separate from your personal workflows.', gesture: 'none', placement: 'bottom' },
      { id: 'teams-new', title: 'Create a team', body: 'Click here to create a new team and invite members.', gesture: 'click', placement: 'bottom' },
    ],
  },
  {
    featureKey: 'settings',
    label: 'Settings',
    paths: ['/settings'],
    steps: [
      { id: 'page-header', title: 'Settings', body: 'Manage your AI providers, API keys, theme, and language here.', gesture: 'none', placement: 'bottom' },
    ],
  },
  {
    featureKey: 'profile',
    label: 'Profile',
    paths: ['/profile'],
    steps: [
      { id: 'page-header', title: 'Your profile', body: 'Update your account details and security settings here.', gesture: 'none', placement: 'bottom' },
    ],
  },
  {
    featureKey: 'billing',
    label: 'Billing',
    paths: ['/billing'],
    steps: [
      { id: 'page-header', title: 'Billing', body: 'View your plan and manage billing details here.', gesture: 'none', placement: 'bottom' },
    ],
  },
]

export function findConfigForPath(pathname: string): TutorialConfig | null {
  let best: TutorialConfig | null = null
  let bestScore = -1
  for (const config of TUTORIAL_REGISTRY) {
    for (const pattern of config.paths) {
      const matches = typeof pattern === 'string' ? pathname === pattern || pathname.startsWith(pattern + '/') : pattern.test(pathname)
      if (!matches) continue
      const score = typeof pattern === 'string' ? pattern.length : 10_000
      if (score > bestScore) {
        best = config
        bestScore = score
      }
    }
  }
  return best
}

export function findConfigForFeature(featureKey: string): TutorialConfig | null {
  return TUTORIAL_REGISTRY.find(c => c.featureKey === featureKey) ?? null
}

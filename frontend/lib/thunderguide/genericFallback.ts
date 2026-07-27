// ============================================================
// ThunderGuide — Generic Customer Support Fallback
//
// The requirement is explicit: "Never return incomplete or broken
// workflows" and "If intent is still unclear after all retries, generate a
// generic Customer Support chatbot instead of failing." Every other path in
// buildWorkflowFromPrompt() depends on a network call to a model, which can
// still fail validation after every retry (bad output, an odd domain, a
// flaky provider response). This module is the last-resort path: a static,
// hand-built, always-structurally-valid workflow with zero network
// dependency, so ThunderGuide can guarantee completion no matter what.
//
// It is intentionally built directly against the GeneratedWorkflow shape
// (not generated text) so its validity doesn't depend on anything that can
// fail at runtime — it's correct by construction.
// ============================================================
import type { GeneratedWorkflow } from './types'

export function buildGenericSupportWorkflow(): GeneratedWorkflow {
  return {
    nodes: [
      { type: 'start', label: 'Start', data: {} },
      {
        type: 'text_card',
        label: 'Greeting',
        data: { content: "Hi! I'm your support assistant. How can I help you today?" },
      },
      {
        type: 'multiple_choice',
        label: 'Main menu',
        data: {
          question: 'What do you need help with?',
          choices: [
            { label: 'Billing & Payments', value: 'billing' },
            { label: 'Technical Support', value: 'technical' },
            { label: 'General Question', value: 'general' },
            { label: 'Talk to a Human', value: 'human' },
          ],
        },
      },
      {
        type: 'ai_agent',
        label: 'Billing assistant',
        data: {
          systemPrompt:
            'You are a billing support assistant. Help the user with payment, invoice, refund, and ' +
            'subscription questions using the company knowledge base. Be clear, concise, and reassuring.',
          temperature: 0.7,
          maxTokens: 800,
          contextWindow: 10,
          memoryEnabled: true,
          stayOnNode: true,
        },
      },
      {
        type: 'ai_agent',
        label: 'Technical support assistant',
        data: {
          systemPrompt:
            'You are a technical support assistant. Help the user troubleshoot issues step by step ' +
            'using the company knowledge base, and suggest escalating to a human agent if the issue ' +
            'cannot be resolved in chat.',
          temperature: 0.7,
          maxTokens: 800,
          contextWindow: 10,
          memoryEnabled: true,
          stayOnNode: true,
        },
      },
      {
        type: 'ai_agent',
        label: 'General FAQ assistant',
        data: {
          systemPrompt:
            'You are a friendly general-purpose support assistant. Answer open-ended questions using ' +
            "the company's knowledge base, and be upfront when you don't have enough information.",
          temperature: 0.7,
          maxTokens: 800,
          contextWindow: 10,
          memoryEnabled: true,
          stayOnNode: true,
        },
      },
      {
        type: 'end',
        label: 'Human handoff',
        data: { message: "Connecting you with a member of our team — they'll be with you shortly." },
      },
      {
        type: 'end',
        label: 'Conversation complete',
        data: { message: 'Thanks for reaching out — is there anything else I can help with?' },
      },
    ],
    edges: [
      { from: 0, to: 1 },
      { from: 1, to: 2 },
      { from: 2, to: 3, choiceIndex: 0 },
      { from: 2, to: 4, choiceIndex: 1 },
      { from: 2, to: 5, choiceIndex: 2 },
      { from: 2, to: 6, choiceIndex: 3 },
      { from: 3, to: 7 },
      { from: 4, to: 7 },
      { from: 5, to: 7 },
    ],
  }
}

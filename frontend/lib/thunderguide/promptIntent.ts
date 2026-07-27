// ============================================================
// ThunderGuide — Prompt Understanding
//
// ROOT CAUSE this module fixes:
// buildWorkflowFromPrompt() (aiActions.ts) used to hand the user's raw text
// straight to the model as the only signal of what to build. That's fine
// for a detailed paragraph, but a one- or two-word prompt like "restaurant"
// or "banking" carries almost no structural signal — the model was left to
// invent scope from nothing, so short prompts produced thin, inconsistent,
// sometimes incomplete graphs (missing FAQ/AI-fallback paths, no branching,
// no Knowledge-Base-aware agent) while a long, explicit prompt produced a
// much better result purely because it happened to spell everything out.
// "The user should never need to write a perfect prompt" requires ThunderGuide
// itself to fill that gap, locally, before the request ever reaches the model.
//
// This module is a pure, 100% local, client-side text-in/text-out expander —
// no network calls, no API keys, mirroring analyzer.ts's "free tier" design.
// It never talks to the Builder/Runtime/Backend; it only changes what text
// buildWorkflowFromPrompt sends to the AI provider it already calls.
// ============================================================

export interface IntentProfile {
  /** Human-readable domain name, used in the expanded brief. */
  label: string
  /** Keywords/phrases that identify this domain in free text (lowercase). */
  keywords: string[]
  /** Full requirements brief injected as the effective prompt to the model. */
  brief: string
}

// Each brief intentionally over-specifies: recommended branches, an
// AI-agent-with-Knowledge-Base fallback, and an explicit End node — this is
// exactly the "intelligent defaults" a short keyword prompt is missing.
// Keyed by domain so callers/tests can reference a match by name.
export const INTENT_LIBRARY: Record<string, IntentProfile> = {
  restaurant: {
    label: 'Restaurant',
    keywords: ['restaurant', 'diner', 'cafe', 'café', 'eatery', 'bistro', 'हॉटेल', 'रेस्टॉरंट', 'रेस्तरां', 'भोजनालय'],
    brief: `Build a complete restaurant chatbot. Greet the user, then branch into: browsing the menu
(with categories such as starters, mains, and desserts), booking a table (party size, date, time,
contact details), placing a takeaway or home delivery order, and a Frequently Asked Questions path
(hours, location, parking, allergens, payment methods). Include an AI Agent fallback with a system
prompt describing it as a helpful restaurant assistant that can answer open-ended questions the
other branches don't cover, drawing on the restaurant's own knowledge base. Every branch must end
cleanly with a friendly End node (confirmation for bookings/orders, or a closing message for FAQs).`,
  },
  ecommerce: {
    label: 'E-commerce',
    keywords: ['ecommerce', 'e-commerce', 'online store', 'online shop', 'retail', 'shopping'],
    brief: `Build a complete e-commerce customer support and shopping assistant chatbot. Greet the
user, then branch into: order tracking (order number lookup), returns and refunds, product
questions and recommendations, shipping and delivery FAQs, and live-agent handoff for anything
unresolved. Include an AI Agent fallback describing it as a knowledgeable store assistant that can
answer open-ended product and policy questions using the store's knowledge base. Every branch must
end at a clear End node, and the returns/refunds and order-tracking branches should feel like a
real guided flow (ask for the information needed, then confirm next steps) rather than a single
message.`,
  },
  school: {
    label: 'School / Education',
    keywords: ['school', 'college', 'university', 'academy', 'student', 'admissions', 'education', 'शाळा', 'विद्यालय', 'महाविद्यालय', 'स्कूल', 'विद्यार्थी', 'शिक्षा'],
    brief: `Build a complete school/education chatbot for prospective and current students and
parents. Greet the user, then branch into: admissions and enrollment info, course/program
information, fee and scholarship questions, academic calendar and timings, and contacting a
specific department (administration, academics, exams). Include an AI Agent fallback positioned as
a helpful school assistant that can answer open-ended questions using the institution's knowledge
base (policies, handbooks, FAQs). Every branch must terminate at an End node with a clear next step
(e.g. "an admissions officer will follow up").`,
  },
  hospital: {
    label: 'Hospital / Healthcare',
    keywords: ['hospital', 'clinic', 'healthcare', 'health care', 'medical center', 'medical centre', 'doctor', 'हॉस्पिटल', 'अस्पताल', 'रुग्णालय', 'दवाखाना', 'डॉक्टर'],
    brief: `Build a complete hospital/healthcare chatbot. Greet the user, then branch into:
appointment booking (department/doctor, preferred date/time), department and doctor directory,
visiting hours and location info, insurance and billing questions, and an emergency-guidance
message that clearly tells the user to call local emergency services or go to the nearest ER for
anything urgent (never attempt to give medical advice itself). Include an AI Agent fallback
positioned as a general-information assistant that answers non-clinical questions using the
hospital's knowledge base, with a system prompt that explicitly instructs it not to give medical
diagnoses or treatment advice. Every branch must end at a clear End node.`,
  },
  banking: {
    label: 'Banking / Financial Services',
    keywords: ['banking', 'bank', 'finance', 'financial services', 'fintech', 'loan', 'credit card', 'बँक', 'बैंक', 'वित्त', 'कर्ज', 'ऋण'],
    brief: `Build a complete banking/financial-services chatbot. Greet the user, then branch into:
account balance and transaction queries, card services (block/replace a card, report fraud),
loan and credit card inquiries, branch/ATM locator info, and a security-sensitive handoff path
that routes anything requiring identity verification or account changes to a human agent rather
than handling it in-chat. Include an AI Agent fallback positioned as a general banking-FAQ
assistant using the bank's knowledge base, with a system prompt that explicitly avoids ever asking
for or repeating full account numbers, passwords, PINs, or OTPs. Every branch must end at a clear
End node.`,
  },
  support: {
    label: 'Customer Support',
    keywords: ['support', 'customer support', 'customer service', 'helpdesk', 'help desk'],
    brief: `Build a complete customer support chatbot for a general product/service business. Greet
the user, then branch into: billing and payment questions, technical/troubleshooting help, order or
account status, general FAQs, and a live-agent handoff for anything unresolved. Include an AI Agent
fallback positioned as a knowledgeable support assistant that answers open-ended questions using the
business's knowledge base. Every branch must end at a clear End node that confirms resolution or
sets expectations for a human follow-up.`,
  },
  travel: {
    label: 'Travel / Booking',
    keywords: ['travel', 'trip', 'flight', 'airline', 'hotel booking', 'vacation', 'tour'],
    brief: `Build a complete travel/booking chatbot. Greet the user, then branch into: flight or
hotel search and booking (destination, dates, travelers), managing an existing booking
(view/change/cancel), travel FAQs (baggage, check-in, visa/documentation), and a live-agent handoff
for complex itinerary issues. Include an AI Agent fallback positioned as a helpful travel assistant
that answers open-ended destination and policy questions using the company's knowledge base. Every
branch must end at a clear End node confirming the booking or next step.`,
  },
  hr: {
    label: 'HR / Employee Services',
    keywords: ['hr', 'human resources', 'employee', 'payroll', 'onboarding', 'recruitment'],
    brief: `Build a complete HR/employee-services chatbot. Greet the user, then branch into: leave
and time-off requests, payroll and benefits questions, onboarding info for new hires, policy and
handbook FAQs, and escalation to an HR representative for sensitive matters. Include an AI Agent
fallback positioned as an internal HR assistant that answers open-ended policy questions using the
company's HR knowledge base. Every branch must end at a clear End node.`,
  },
  faq: {
    label: 'FAQ',
    keywords: ['faq', 'frequently asked questions', 'q&a', 'q and a'],
    brief: `Build a complete FAQ chatbot. Greet the user, then present a Multiple Choice menu of the
most common topics (account, pricing/billing, features, troubleshooting, contact/other), each
leading to a short, clear text answer, with an AI Agent fallback (positioned as a knowledge-base-
aware assistant) for anything outside the listed topics so no question dead-ends unanswered. Every
branch must end at a clear End node, and the "contact/other" branch should offer a way to reach a
human.`,
  },
  food_delivery: {
    label: 'Food Delivery',
    keywords: ['food delivery', 'delivery app', 'meal delivery', 'takeaway', 'take-away', 'takeout'],
    brief: `Build a complete food delivery chatbot. Greet the user, then branch into: browsing
restaurants/menu and starting an order, tracking an existing order, delivery issues (late order,
missing items, wrong order), payment and refund questions, and a live-agent handoff for unresolved
issues. Include an AI Agent fallback positioned as a delivery-support assistant using the platform's
knowledge base. Every branch must end at a clear End node.`,
  },
  whatsapp: {
    label: 'WhatsApp Bot',
    keywords: ['whatsapp', 'whats app', 'wa bot'],
    brief: `Build a complete general-purpose WhatsApp-style conversational bot. Greet the user
concisely (WhatsApp conversations are short and message-driven), then branch into: answering common
questions, checking status/order/request info, and a live-agent handoff for anything unresolved.
Keep text_card and multiple_choice content short and mobile-friendly (WhatsApp messages are read on
a phone). Include an AI Agent fallback with a knowledge-base-aware system prompt for open-ended
questions. Every branch must end at a clear End node.`,
  },
  ai_assistant: {
    label: 'General AI Assistant',
    keywords: ['ai assistant', 'virtual assistant', 'chatbot assistant', 'general assistant'],
    brief: `Build a complete general-purpose AI assistant chatbot. Greet the user, then branch into
a small Multiple Choice menu of common intents (ask a question, get help with something specific,
talk to a human) and route the open-ended "ask a question" path into a capable AI Agent with a
knowledge-base-aware system prompt describing it as a friendly, broadly helpful assistant. Every
branch must end at a clear End node.`,
  },
}

// Order matters only for tie-breaking on equal keyword length below, so a
// stable, explicit iteration order keeps matching deterministic.
const PROFILE_ENTRIES = Object.entries(INTENT_LIBRARY)

function normalize(raw: string): string {
  return raw.toLowerCase().trim().replace(/\s+/g, ' ')
}

/**
 * Finds the best-matching domain profile for free text. Prefers the longest
 * matching keyword (so "food delivery" beats a generic "delivery" match,
 * and "customer support" beats a bare "support" substring inside some other
 * word) and is otherwise substring-based so both a bare keyword ("banking")
 * and a keyword embedded in a longer sentence ("...for our banking app...")
 * are recognized.
 */
export function classifyIntent(raw: string): { key: string; profile: IntentProfile } | null {
  const text = normalize(raw)
  if (!text) return null

  let best: { key: string; profile: IntentProfile; matchLength: number } | null = null
  for (const [key, profile] of PROFILE_ENTRIES) {
    for (const kw of profile.keywords) {
      if (text.includes(kw) && (!best || kw.length > best.matchLength)) {
        best = { key, profile, matchLength: kw.length }
      }
    }
  }
  return best ? { key: best.key, profile: best.profile } : null
}

// A prompt this short is treated as a "keyword-style" prompt rather than a
// fully-specified description — it's the exact shape of the short-prompt
// examples this feature targets ("restaurant", "food delivery", "WhatsApp bot").
const SHORT_PROMPT_WORD_THRESHOLD = 4

export function looksLikeShortPrompt(raw: string): boolean {
  const words = normalize(raw).split(' ').filter(Boolean)
  return words.length > 0 && words.length <= SHORT_PROMPT_WORD_THRESHOLD
}

// Standing structural reminder appended to every generation prompt — short
// or long — so the model always includes the node types the requirements
// call for wherever they're actually needed, regardless of how the person
// phrased their request.
const STRUCTURAL_DEFAULTS_FOOTER = `
Regardless of how this request is phrased, the generated workflow must:
- Start with exactly one Start node.
- Use Text Card nodes for greetings/informational messages and Multiple Choice nodes to branch
  based on user intent.
- Include at least one AI Agent node for open-ended questions the explicit branches don't cover,
  positioned to draw on a knowledge base where the domain implies one (support, FAQs, policies,
  product info).
- Use a Transition node only where a branch genuinely needs to loop back or gate re-entry.
- Ensure every path — including every Multiple Choice option — reaches an End node.
- Never leave a branch incomplete, dangling, or without a defined next step.`

/**
 * Expands the person's raw prompt into the requirements brief actually sent
 * to the model. Short, keyword-style prompts ("restaurant", "HR") are
 * replaced outright with a full domain brief with intelligent defaults. A
 * longer, already-detailed prompt is passed through largely as written (the
 * person already did the narrowing) but still gets the same structural
 * completeness reminder, plus any domain brief detected in their text
 * layered in as additional context — never overriding what they actually
 * asked for, only filling gaps they didn't mention.
 */
export function expandPrompt(raw: string): {
  expandedDescription: string
  matchedDomain: string | null
  wasShortPrompt: boolean
} {
  const wasShortPrompt = looksLikeShortPrompt(raw)
  const match = classifyIntent(raw)

  if (wasShortPrompt) {
    if (match) {
      return {
        expandedDescription: `${match.profile.brief}${STRUCTURAL_DEFAULTS_FOOTER}`,
        matchedDomain: match.key,
        wasShortPrompt,
      }
    }
    // Short prompt with no recognized domain — intent is unclear from the
    // text alone. Fall back to a broad, still-complete generic assistant
    // brief rather than sending an under-specified fragment to the model.
    return {
      expandedDescription: `${INTENT_LIBRARY.ai_assistant.brief}${STRUCTURAL_DEFAULTS_FOOTER}`,
      matchedDomain: null,
      wasShortPrompt,
    }
  }

  // Long/detailed prompt: respect what the person wrote, just reinforce
  // structural completeness and (if a domain is recognizable) note it as
  // additional context the model can use to fill in anything unstated.
  const domainHint = match
    ? `\n\nAdditional context: this reads like a ${match.profile.label} chatbot. Where the ` +
      `request above doesn't specify something a real ${match.profile.label} chatbot would need, ` +
      `use sensible defaults for that domain.`
    : ''
  return {
    expandedDescription: `${raw.trim()}${domainHint}${STRUCTURAL_DEFAULTS_FOOTER}`,
    matchedDomain: match?.key ?? null,
    wasShortPrompt,
  }
}

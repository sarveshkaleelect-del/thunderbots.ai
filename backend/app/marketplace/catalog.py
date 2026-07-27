"""
Thunder Marketplace — template catalog.

Design goals (perf-first, independent module):
- Pure Python data + a small generator function. No DB tables, no new
  SQLAlchemy models, no startup-time work.
- Metadata (list view) is tiny; the full node/edge graph for a template is
  built on-demand only when a template is previewed or imported, never
  preloaded or computed at import time.
- Completely decoupled from workflow engine / builder / AI agent logic. It
  only ever *produces* a standard nodes/edges payload shaped exactly like
  what the Workflow Builder already saves — nothing here is read by, or
  changes the behaviour of, the runtime, ThunderGuide, or the AI engine.
"""
import uuid
from typing import Any


# ── Categories (fixed order shown in the UI) ──────────────────────────────────
CATEGORIES: list[str] = [
    "Customer Support",
    "Restaurant",
    "Hospital",
    "Education",
    "E-commerce",
    "Banking",
    "HR",
    "Hotel",
    "Travel",
    "Real Estate",
    "Business",
    "General Assistant",
]

DIFFICULTIES = {"beginner": "Beginner", "intermediate": "Intermediate", "advanced": "Advanced"}


def _tpl(
    tid: str,
    name: str,
    description: str,
    category: str,
    difficulty: str,
    setup_time: str,
    features: list[str],
    welcome: str,
    question: str,
    choices: list[str],
    system_prompt: str,
    closing: str,
    icon: str = "Bot",
    featured: bool = False,
    added: str = "2026-01-01",
) -> dict[str, Any]:
    return {
        "id": tid,
        "name": name,
        "description": description,
        "category": category,
        "industry": category,
        "difficulty": DIFFICULTIES[difficulty],
        "setup_time": setup_time,
        "features": features,
        "icon": icon,
        "featured": featured,
        "added_at": added,
        # kept out of the list/metadata response — only used by the graph builder
        "_welcome": welcome,
        "_question": question,
        "_choices": choices,
        "_system_prompt": system_prompt,
        "_closing": closing,
    }


# ── Catalog (2 templates per category = 24 total) ─────────────────────────────
TEMPLATES: list[dict[str, Any]] = [
    _tpl("cs-helpdesk", "Support Helpdesk Bot",
         "Tier-1 support triage that answers FAQs and routes complex issues to a human.",
         "Customer Support", "beginner", "5 min",
         ["FAQ handling", "Ticket routing", "Sentiment-aware replies", "Human handoff"],
         "Hi! I'm your support assistant. What do you need help with today?",
         "Please choose a topic:",
         ["Billing issue", "Technical problem", "Order status", "Talk to a human"],
         "You are a calm, empathetic tier-1 support agent. Resolve common issues clearly, "
         "ask clarifying questions when needed, and offer to escalate to a human for anything "
         "you can't fully resolve.",
         "Thanks for reaching out — anything else I can help with?",
         icon="LifeBuoy", featured=True, added="2026-02-10"),
    _tpl("cs-feedback", "Customer Feedback Collector",
         "Collects structured feedback and routes negative sentiment for follow-up.",
         "Customer Support", "beginner", "5 min",
         ["CSAT survey flow", "Sentiment routing", "Follow-up flagging"],
         "Hey there! Got 60 seconds to share feedback about your experience?",
         "What's this feedback about?",
         ["Product", "Support experience", "Delivery", "Something else"],
         "You are a friendly feedback-collection assistant. Ask 2-3 short follow-up questions, "
         "thank the user warmly, and flag anything negative for the support team to review.",
         "Really appreciate you taking the time — this helps us improve!",
         icon="MessageSquareHeart", added="2026-03-02"),

    _tpl("rest-reservation", "Restaurant Reservation Bot",
         "Takes table bookings, answers menu questions, and shares hours & location.",
         "Restaurant", "beginner", "5 min",
         ["Table booking flow", "Menu Q&A", "Hours & location", "Special requests"],
         "Welcome! I can help you book a table or answer questions about our menu.",
         "What would you like to do?",
         ["Book a table", "See the menu", "Hours & location", "Dietary questions"],
         "You are a warm restaurant host. Help guests book tables (ask party size, date, time), "
         "answer menu and dietary questions accurately, and share hours/location when asked.",
         "Looking forward to serving you — see you soon!",
         icon="UtensilsCrossed", featured=True, added="2026-01-18"),
    _tpl("rest-order", "Food Ordering Assistant",
         "Guides customers through takeout/delivery ordering with upsells.",
         "Restaurant", "intermediate", "10 min",
         ["Menu browsing", "Order building", "Upsell suggestions", "Order summary"],
         "Hungry? Let's get your order started!",
         "Pickup or delivery?",
         ["Pickup", "Delivery", "See specials", "Track an order"],
         "You are a friendly food-ordering assistant. Help the guest build an order from the "
         "menu, suggest a popular add-on once, and summarize the final order clearly before closing.",
         "Your order's on its way to the kitchen — thank you!",
         icon="ChefHat", added="2026-04-05"),

    _tpl("hosp-appointment", "Hospital Appointment Scheduler",
         "Helps patients book appointments and understand department options.",
         "Hospital", "intermediate", "10 min",
         ["Department routing", "Appointment booking", "Insurance FAQ", "Emergency redirect"],
         "Hello, I'm here to help you schedule a visit or answer general questions.",
         "What do you need today?",
         ["Book an appointment", "Department info", "Insurance questions", "This is an emergency"],
         "You are a professional hospital front-desk assistant. Help patients pick the right "
         "department and book appointments. If the user indicates a medical emergency, immediately "
         "tell them to call local emergency services or go to the nearest ER — do not attempt to "
         "give medical advice.",
         "Take care, and we'll see you at your visit.",
         icon="Stethoscope", featured=True, added="2026-01-25"),
    _tpl("hosp-info", "Patient Info Assistant",
         "Answers visiting hours, billing, and general facility questions.",
         "Hospital", "beginner", "5 min",
         ["Visiting hours", "Billing FAQ", "Facility directions"],
         "Hi! I can answer questions about visiting hours, billing, or getting around the hospital.",
         "What can I help with?",
         ["Visiting hours", "Billing question", "Directions on-site", "Something else"],
         "You are a hospital information assistant. Answer general, non-medical facility questions "
         "clearly. Never provide diagnoses or treatment advice — redirect clinical questions to staff.",
         "Wishing you or your loved one well.",
         icon="HeartPulse", added="2026-05-12"),

    _tpl("edu-admissions", "Admissions Inquiry Bot",
         "Answers prospective student questions and captures leads for follow-up.",
         "Education", "intermediate", "10 min",
         ["Program info", "Lead capture", "Application deadlines", "Financial aid FAQ"],
         "Hi! Thinking about applying? I can help with programs, deadlines, and more.",
         "What are you curious about?",
         ["Programs offered", "Application deadlines", "Financial aid", "Talk to admissions"],
         "You are a friendly admissions assistant for a school. Answer questions about programs, "
         "deadlines and financial aid, and gently capture the student's name/email/interest area for "
         "the admissions team when relevant.",
         "Good luck with your application — we're excited to hear from you!",
         icon="GraduationCap", featured=True, added="2026-02-01"),
    _tpl("edu-tutor", "Study Buddy Tutor Bot",
         "A friendly subject-matter tutor that explains concepts and quizzes students.",
         "Education", "advanced", "15 min",
         ["Concept explanations", "Practice quizzing", "Progress-friendly tone"],
         "Hey! I'm your study buddy. What subject are we working on today?",
         "Pick a subject:",
         ["Math", "Science", "Languages", "Something else"],
         "You are a patient, encouraging tutor. Explain concepts step by step at the student's "
         "level, check understanding with short questions, and never just give final answers to "
         "graded work without explaining the reasoning.",
         "Great work today — keep it up!",
         icon="BookOpen", added="2026-03-20"),

    _tpl("ecom-shopping", "Shopping Assistant",
         "Helps shoppers find products, track orders, and process returns.",
         "E-commerce", "intermediate", "10 min",
         ["Product discovery", "Order tracking", "Returns & exchanges", "Size/fit help"],
         "Hi! Looking for something specific, or need help with an order?",
         "How can I help?",
         ["Find a product", "Track my order", "Start a return", "Sizing help"],
         "You are a helpful e-commerce shopping assistant. Help customers find products, check on "
         "orders, and walk through returns/exchanges clearly and reassuringly.",
         "Happy shopping — let me know if you need anything else!",
         icon="ShoppingBag", featured=True, added="2026-01-30"),
    _tpl("ecom-abandoned", "Cart Recovery Assistant",
         "Re-engages shoppers who left items in cart with helpful nudges, not spam.",
         "E-commerce", "advanced", "15 min",
         ["Cart recovery flow", "Discount offer logic", "Objection handling"],
         "Hey! Noticed you left something in your cart — need any help deciding?",
         "What's holding you back?",
         ["Price concern", "Still comparing", "Shipping question", "Just browsing"],
         "You are a low-pressure cart-recovery assistant. Address the specific hesitation the "
         "shopper mentions honestly, mention any active promotion at most once, and never sound "
         "pushy.",
         "No pressure — your cart will be waiting when you're ready!",
         icon="ShoppingCart", added="2026-04-18"),

    _tpl("bank-support", "Banking Support Bot",
         "Answers account questions and routes sensitive requests to secure channels.",
         "Banking", "advanced", "15 min",
         ["Account FAQ", "Card lost/stolen routing", "Branch/ATM locator", "Fraud escalation"],
         "Hello, I can help with general account questions.",
         "What do you need?",
         ["Account question", "Lost/stolen card", "Find a branch/ATM", "Report fraud"],
         "You are a banking support assistant. Never ask for or accept full card numbers, PINs, "
         "passwords, or OTPs in chat. For lost/stolen cards or fraud, instruct the user to call the "
         "official support number on the back of their card immediately.",
         "Your security is our priority — thanks for banking with us.",
         icon="Landmark", featured=True, added="2026-02-14"),
    _tpl("bank-loan", "Loan Inquiry Assistant",
         "Pre-qualifies loan interest and explains products at a high level.",
         "Banking", "intermediate", "10 min",
         ["Product overview", "Eligibility FAQ", "Lead capture for advisors"],
         "Hi! Exploring loan options? I can share the basics and connect you with an advisor.",
         "Which product interests you?",
         ["Personal loan", "Home loan", "Auto loan", "Not sure yet"],
         "You are a loan-information assistant. Give general, non-binding product information "
         "only — never quote a guaranteed rate or approval. Offer to connect the user with a "
         "licensed advisor for specifics.",
         "An advisor will be able to give you exact numbers — thanks for your interest!",
         icon="HandCoins", added="2026-05-01"),

    _tpl("hr-onboarding", "Employee Onboarding Bot",
         "Guides new hires through first-week logistics and policy FAQs.",
         "HR", "beginner", "5 min",
         ["Onboarding checklist", "Policy FAQ", "IT setup pointers"],
         "Welcome to the team! I'm here to help with onboarding basics.",
         "What do you need first?",
         ["First-week checklist", "Benefits questions", "IT/equipment setup", "Company policies"],
         "You are a warm HR onboarding assistant for new employees. Answer common first-week "
         "questions clearly and point to the employee handbook or HR contact for anything "
         "company-specific you're unsure of.",
         "Excited to have you on the team — welcome aboard!",
         icon="Users", featured=True, added="2026-01-22"),
    _tpl("hr-recruiting", "Recruiting FAQ Bot",
         "Answers candidate questions about roles, process, and culture.",
         "HR", "beginner", "5 min",
         ["Role FAQ", "Interview process overview", "Culture questions"],
         "Hi! Thinking of joining us? Happy to answer questions about our roles and process.",
         "What would you like to know?",
         ["Open roles", "Interview process", "Company culture", "Application status"],
         "You are a friendly recruiting assistant. Describe the hiring process and culture "
         "honestly and encouragingly, and direct application-status questions to the recruiter "
         "the candidate is working with.",
         "Thanks for your interest — good luck with your application!",
         icon="UserPlus", added="2026-03-28"),

    _tpl("hotel-concierge", "Hotel Concierge Bot",
         "Handles bookings, room service requests, and local recommendations.",
         "Hotel", "intermediate", "10 min",
         ["Room booking", "Room service", "Local recommendations", "Checkout help"],
         "Welcome! I'm your virtual concierge — how can I help make your stay great?",
         "What can I help with?",
         ["Book a room", "Room service", "Local recommendations", "Checkout question"],
         "You are a gracious hotel concierge. Help guests book rooms, place room-service requests, "
         "and recommend nearby restaurants/attractions matching their preferences.",
         "Have a wonderful stay with us!",
         icon="BedDouble", featured=True, added="2026-02-05"),
    _tpl("hotel-feedback", "Guest Experience Bot",
         "Collects in-stay feedback and quickly surfaces urgent issues to staff.",
         "Hotel", "beginner", "5 min",
         ["In-stay feedback", "Urgent issue flagging", "Amenity questions"],
         "Hi! Hope you're enjoying your stay. Anything I can help with right now?",
         "What's this about?",
         ["Room issue", "Amenities question", "General feedback", "Urgent — need staff now"],
         "You are a hotel guest-experience assistant. For anything urgent (safety, maintenance "
         "emergencies, medical), tell the guest to call the front desk immediately. Otherwise "
         "help warmly and log feedback.",
         "Thank you for staying with us — we hope to see you again!",
         icon="ConciergeBell", added="2026-04-22"),

    _tpl("travel-booking", "Travel Booking Assistant",
         "Helps travelers explore destinations and start booking flights/stays.",
         "Travel", "intermediate", "10 min",
         ["Destination discovery", "Flight/stay search intake", "Itinerary tips"],
         "Hi there! Planning a trip? Let's find you something great.",
         "Where are you in the planning process?",
         ["Need destination ideas", "Ready to book flights", "Need a hotel", "Itinerary help"],
         "You are an enthusiastic travel-planning assistant. Ask about budget, dates, and "
         "preferences, suggest destinations or next steps, and keep recommendations realistic.",
         "Bon voyage — have an amazing trip!",
         icon="Plane", featured=True, added="2026-01-15"),
    _tpl("travel-support", "Trip Support Bot",
         "Answers questions about existing bookings, changes, and cancellations.",
         "Travel", "intermediate", "10 min",
         ["Booking lookup", "Change/cancel FAQ", "Travel document reminders"],
         "Hi! I can help with an existing booking — changes, cancellations, or general questions.",
         "What do you need?",
         ["Change a booking", "Cancel a booking", "Travel document questions", "Something else"],
         "You are a travel support assistant. Explain change/cancellation policies clearly in "
         "general terms and remind travelers to check passport/visa validity, while directing "
         "account-specific changes to the booking portal or support line.",
         "Safe travels, and reach out anytime you need help!",
         icon="Luggage", added="2026-05-08"),

    _tpl("re-listings", "Property Inquiry Bot",
         "Qualifies buyer/renter leads and answers listing questions.",
         "Real Estate", "intermediate", "10 min",
         ["Listing Q&A", "Lead qualification", "Viewing scheduling"],
         "Hi! Looking for a place, or have questions about a listing?",
         "What's your goal?",
         ["Buying", "Renting", "Ask about a listing", "Schedule a viewing"],
         "You are a knowledgeable real-estate assistant. Ask about budget, location and must-haves, "
         "answer listing questions honestly, and offer to schedule a viewing with an agent.",
         "Happy house hunting — talk soon!",
         icon="Home", featured=True, added="2026-02-20"),
    _tpl("re-tenant", "Tenant Support Bot",
         "Handles maintenance requests and lease FAQs for current tenants.",
         "Real Estate", "beginner", "5 min",
         ["Maintenance request intake", "Lease FAQ", "Urgent issue flagging"],
         "Hi! Need help with a maintenance issue or a lease question?",
         "What's going on?",
         ["Maintenance request", "Lease question", "Rent payment question", "Urgent — emergency"],
         "You are a property-management assistant for tenants. Collect clear details for "
         "maintenance requests (what/where/how urgent), answer general lease questions, and tell "
         "tenants to call the emergency line for anything urgent like flooding or no heat.",
         "Thanks — we'll get this sorted out for you.",
         icon="KeyRound", added="2026-04-10"),

    _tpl("biz-leadgen", "Lead Qualification Bot",
         "Qualifies inbound website leads before handing off to sales.",
         "Business", "advanced", "15 min",
         ["Lead qualification questions", "CRM-ready summary", "Sales handoff"],
         "Hi! Thanks for stopping by — want help finding the right solution for your business?",
         "What brings you here today?",
         ["Exploring options", "Ready to talk to sales", "Pricing question", "Support issue"],
         "You are a B2B lead-qualification assistant. Ask about company size, use case, and "
         "timeline concisely, then summarize the lead clearly for the sales team before handing off.",
         "Thanks for your interest — someone from our team will follow up soon!",
         icon="Briefcase", featured=True, added="2026-01-28"),
    _tpl("biz-internal", "Internal Ops Assistant",
         "Answers common internal process and policy questions for staff.",
         "Business", "beginner", "5 min",
         ["Process FAQ", "Policy lookup", "Ticket creation prompts"],
         "Hi! I can help answer common internal process or policy questions.",
         "What do you need?",
         ["Expense process", "IT request", "Policy question", "Something else"],
         "You are an internal operations assistant for employees. Give clear, concise answers "
         "about common internal processes and point to the right internal team for anything "
         "requiring approval or account access.",
         "Let me know if anything else comes up!",
         icon="Building2", added="2026-03-15"),

    _tpl("gen-assistant", "General Assistant Bot",
         "A flexible, all-purpose assistant template for any use case.",
         "General Assistant", "beginner", "5 min",
         ["Open-ended Q&A", "Friendly onboarding", "Easy to customize"],
         "Hi there! I'm your assistant — what can I help you with today?",
         "How can I help?",
         ["Ask a question", "Get recommendations", "Report an issue", "Something else"],
         "You are a helpful, friendly general-purpose assistant. Answer clearly and concisely, "
         "ask clarifying questions when needed, and stay on-topic for the business you represent.",
         "Glad I could help — have a great day!",
         icon="Sparkles", featured=True, added="2026-01-10"),
    _tpl("gen-faq", "FAQ Answering Bot",
         "A simple template for answering a static list of frequently asked questions.",
         "General Assistant", "beginner", "5 min",
         ["FAQ matching", "Simple menu flow", "Easy to extend"],
         "Hello! Ask me anything, or pick a common question below.",
         "Pick a topic or type your own question:",
         ["Pricing", "How it works", "Contact info", "Something else"],
         "You are an FAQ assistant. Answer using the information you've been given about this "
         "business, and be upfront when something is outside what you know.",
         "Thanks for asking — anything else?",
         icon="HelpCircle", added="2026-03-08"),
]

_BY_ID: dict[str, dict[str, Any]] = {t["id"]: t for t in TEMPLATES}


def list_templates() -> list[dict[str, Any]]:
    """Lightweight metadata only — safe for the marketplace grid/list view."""
    return [
        {k: v for k, v in t.items() if not k.startswith("_")}
        for t in TEMPLATES
    ]


def get_template_meta(template_id: str) -> dict[str, Any] | None:
    t = _BY_ID.get(template_id)
    if not t:
        return None
    return {k: v for k, v in t.items() if not k.startswith("_")}


def build_workflow_graph(template_id: str) -> tuple[list[dict], list[dict]] | None:
    """
    Builds a standard {nodes, edges} graph for a template, in the exact shape
    the Workflow Builder / engine already understands (start -> multiple_choice
    -> ai_agent -> end). Generated on demand only — never cached or precomputed
    at startup.
    """
    t = _BY_ID.get(template_id)
    if not t:
        return None

    def nid(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    start_id, menu_id, agent_id, end_id = (
        nid("start"), nid("multiple_choice"), nid("ai_agent"), nid("end")
    )

    nodes = [
        {
            "id": start_id, "type": "start",
            "position": {"x": 0, "y": 0},
            "data": {"label": "Start", "welcomeMessage": t["_welcome"]},
        },
        {
            "id": menu_id, "type": "multiple_choice",
            "position": {"x": 0, "y": 180},
            "data": {
                "label": "Menu",
                "question": t["_question"],
                "choices": [
                    {"label": c, "value": f"choice_{i}"}
                    for i, c in enumerate(t["_choices"])
                ],
            },
        },
        {
            "id": agent_id, "type": "ai_agent",
            "position": {"x": 0, "y": 400},
            "data": {
                "label": "AI Agent",
                # ROOT CAUSE FIX: templates used to hardcode "provider": "openai"
                # (and a matching "gpt-4o-mini" model) directly into the generated
                # node data. Every imported template therefore ignored whichever
                # provider the importing user actually had configured — a user
                # whose only working key was Gemini or Claude got a hard failure
                # the instant they tried an imported template, even though their
                # own workflows built by hand worked fine. Leaving both fields
                # unset means AIAgentNodeHandler resolves the provider at RUN
                # TIME (see resolve_agent_provider in app/services/ai_engine.py),
                # always against the user's CURRENT default — never a value
                # baked in at import time — and each provider's own default
                # model, rather than a model that may not even exist on the
                # provider the user ends up using.
                "provider": None,
                "model": None,
                "systemPrompt": t["_system_prompt"],
                "instructions": "",
                "temperature": 0.7,
                "maxTokens": 1000,
                "contextWindow": 10,
                "memoryEnabled": True,
                "stayOnNode": True,
            },
        },
        {
            "id": end_id, "type": "end",
            "position": {"x": 0, "y": 620},
            "data": {"label": "End", "message": t["_closing"]},
        },
    ]

    edges = [
        {
            "id": nid("edge"), "source": start_id, "target": menu_id,
            "sourceHandle": "output_0", "targetHandle": "input",
        },
        *[
            {
                "id": nid("edge"), "source": menu_id, "target": agent_id,
                "sourceHandle": f"choice_{i}", "targetHandle": "input",
            }
            for i in range(len(t["_choices"]))
        ],
        {
            "id": nid("edge"), "source": agent_id, "target": end_id,
            "sourceHandle": "output_0", "targetHandle": "input",
        },
    ]

    return nodes, edges

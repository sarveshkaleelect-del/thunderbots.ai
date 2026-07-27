'use client'
// ThunderBots AI Business Advisor — Dashboard (NEW, additive)
//
// Reuses the existing Smart Shop Assistant, AI Inventory Intelligence,
// Analytics chart components, and AI Engine — nothing here duplicates or
// modifies existing business logic. Every number comes from
// business_advisor_service, which itself reuses shop_inventory_intelligence_service.
import { useState } from 'react'
import { useParams } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Sparkles, TrendingUp, TrendingDown, DollarSign, ShoppingBag, Users, UserPlus,
  AlertTriangle, PackageX, Zap, Archive, Award, Send, Bot, FileDown, FileSpreadsheet,
  RefreshCw, Store, BadgeCheck, Loader2,
} from 'lucide-react'
import { Card, Badge } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Field'
import { SubPageBar } from '@/components/ui/TopBar'
import { Footer } from '@/components/ui/Footer'
import { useToast } from '@/components/ui/Toast'
import { ChartCard } from '@/components/analytics/ChartCard'
import { shopAssistantApi } from '@/lib/api/shopAssistant'
import { businessAdvisorApi } from '@/lib/api/businessAdvisor'
import type {
  Recommendation, RecommendationPriority, AdvisorAlert, AdvisorOverview, AdvisorPredictions,
  ChatMessage, ReportPeriod,
} from '@/types/businessAdvisor'

const PRIORITY_TONE: Record<RecommendationPriority, 'danger' | 'warning' | 'default'> = {
  high: 'danger', medium: 'warning', low: 'default',
}

const money = (v: number) => `₹${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`

export default function BusinessAdvisorPage() {
  const { shopId } = useParams<{ shopId: string }>()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [reportPeriod, setReportPeriod] = useState<ReportPeriod>('daily')
  const [exporting, setExporting] = useState<'pdf' | 'xlsx' | null>(null)

  const { data: shop } = useQuery({
    queryKey: ['shop-assistant', 'shop', shopId],
    queryFn: () => shopAssistantApi.getShop(shopId),
    enabled: !!shopId,
  })

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['business-advisor', 'overview', shopId],
    queryFn: () => businessAdvisorApi.getOverview(shopId),
    enabled: !!shopId,
    refetchInterval: 60_000,
  })

  const { data: recommendations, isLoading: recsLoading } = useQuery({
    queryKey: ['business-advisor', 'recommendations', shopId],
    queryFn: () => businessAdvisorApi.getRecommendations(shopId),
    enabled: !!shopId,
  })

  const { data: predictions, isLoading: predictionsLoading } = useQuery({
    queryKey: ['business-advisor', 'predictions', shopId],
    queryFn: () => businessAdvisorApi.getPredictions(shopId),
    enabled: !!shopId,
  })

  const { data: alerts } = useQuery({
    queryKey: ['business-advisor', 'alerts', shopId],
    queryFn: () => businessAdvisorApi.getAlerts(shopId),
    enabled: !!shopId,
  })

  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ['business-advisor'] })
    toast('success', 'Refreshing AI Business Advisor…')
  }

  const handleExport = async (format: 'pdf' | 'xlsx') => {
    if (!shop) return
    setExporting(format)
    try {
      if (format === 'pdf') await businessAdvisorApi.exportReportPdf(shopId, reportPeriod, shop.name)
      else await businessAdvisorApi.exportReportXlsx(shopId, reportPeriod, shop.name)
      toast('success', `${reportPeriod} report exported`)
    } catch {
      toast('error', 'Could not export report')
    } finally {
      setExporting(null)
    }
  }

  const revenueChange = overview?.revenue_change_pct ?? null

  return (
    <div className="min-h-screen flex flex-col">
      <SubPageBar
        backHref={`/shop-assistant/${shopId}/admin`}
        crumb={shop ? `${shop.name} — AI Business Advisor` : 'AI Business Advisor'}
        crumbIcon={<Sparkles size={14} />}
        right={
          <Button variant="ghost" size="sm" icon={<RefreshCw className="w-3.5 h-3.5" />} onClick={refreshAll}>
            Refresh
          </Button>
        }
      />

      <div className="flex-1 px-4 sm:px-5 py-6 sm:py-8 max-w-6xl mx-auto w-full space-y-6">
        <div>
          <h1 className="text-lg font-semibold text-white flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-[#a5b4fc]" /> AI Business Advisor
          </h1>
          <p className="text-xs text-white/40 mt-1">
            Daily performance, AI recommendations, and predictions for {shop?.name ?? 'your shop'} — all computed from real inventory and reservation data.
          </p>
        </div>

        <AlertsBanner alerts={alerts} />

        <MetricsGrid overview={overview} loading={overviewLoading} revenueChange={revenueChange} />

        <div className="grid lg:grid-cols-2 gap-6">
          <ProductPanels overview={overview} />
          <div className="space-y-6">
            <RecommendationsPanel recommendations={recommendations} loading={recsLoading} />
          </div>
        </div>

        <PredictionsPanel predictions={predictions} loading={predictionsLoading} />

        <div className="grid lg:grid-cols-2 gap-6">
          <ChatPanel shopId={shopId} />
          <ReportsPanel
            period={reportPeriod} setPeriod={setReportPeriod}
            onExport={handleExport} exporting={exporting}
          />
        </div>
      </div>

      <Footer />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Alerts
// ─────────────────────────────────────────────────────────────────────────────

function AlertsBanner({ alerts }: { alerts?: AdvisorAlert[] }) {
  if (!alerts || alerts.length === 0) return null
  return (
    <div className="space-y-2">
      {alerts.map((a, i) => (
        <div
          key={i}
          className={`rounded-xl border px-4 py-2.5 flex items-center gap-2.5 text-xs ${
            a.severity === 'high'
              ? 'bg-red-500/10 border-red-500/25 text-red-300'
              : a.severity === 'medium'
              ? 'bg-amber-500/10 border-amber-500/25 text-amber-300'
              : 'bg-cyan-500/10 border-cyan-500/20 text-cyan-200'
          }`}
        >
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
          <span>{a.message}</span>
        </div>
      ))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Metrics
// ─────────────────────────────────────────────────────────────────────────────

function MetricsGrid({
  overview, loading, revenueChange,
}: { overview?: AdvisorOverview; loading: boolean; revenueChange: number | null }) {
  const cards = [
    { icon: <DollarSign className="w-4 h-4 text-emerald-400" />, label: "Today's Revenue", value: overview ? money(overview.today_revenue) : '—' },
    { icon: <DollarSign className="w-4 h-4 text-white/40" />, label: "Yesterday's Revenue", value: overview ? money(overview.yesterday_revenue) : '—' },
    { icon: <TrendingUp className="w-4 h-4 text-[#a5b4fc]" />, label: 'Profit', value: overview ? money(overview.profit) : '—' },
    { icon: <ShoppingBag className="w-4 h-4 text-cyan-300" />, label: 'Orders', value: overview ? overview.orders : '—' },
    { icon: <UserPlus className="w-4 h-4 text-emerald-400" />, label: 'New Customers', value: overview ? overview.new_customers : '—' },
    { icon: <Users className="w-4 h-4 text-white/40" />, label: 'Returning Customers', value: overview ? overview.returning_customers : '—' },
  ]

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      {cards.map((c, i) => (
        <Card key={i} className="p-3.5">
          <div className="flex items-center gap-1.5 mb-2">{c.icon}<span className="text-[10px] text-white/40 uppercase tracking-wide truncate">{c.label}</span></div>
          {loading ? (
            <Loader2 className="w-4 h-4 text-white/20 animate-spin" />
          ) : (
            <p className="text-lg font-semibold text-white">{c.value}</p>
          )}
          {i === 0 && revenueChange !== null && !loading && (
            <div className={`flex items-center gap-1 mt-1 text-[10px] font-medium ${revenueChange >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {revenueChange >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
              {Math.abs(revenueChange)}% vs yesterday
            </div>
          )}
        </Card>
      ))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Product panels — low/out of stock, fast/slow moving, best sellers
// ─────────────────────────────────────────────────────────────────────────────

function ProductPanels({ overview }: { overview?: AdvisorOverview }) {
  return (
    <Card className="p-4 space-y-4">
      <h2 className="text-sm font-semibold text-white flex items-center gap-2">
        <Store className="w-4 h-4 text-[#a5b4fc]" /> Product Performance
      </h2>

      <MiniList icon={<PackageX className="w-3.5 h-3.5 text-red-400" />} title="Out of Stock"
        empty="None — fully stocked" items={(overview?.out_of_stock_products ?? []).map((p) => ({
          key: p.product_id, left: p.product_name, right: <Badge tone="danger">0 left</Badge>,
        }))} />

      <MiniList icon={<AlertTriangle className="w-3.5 h-3.5 text-amber-400" />} title="Low Stock"
        empty="All good" items={(overview?.low_stock_products ?? []).map((p) => ({
          key: p.product_id, left: p.product_name, right: <Badge tone="warning">{p.quantity_available} left</Badge>,
        }))} />

      <MiniList icon={<Zap className="w-3.5 h-3.5 text-emerald-400" />} title="Fast Moving"
        empty="No sales data yet" items={(overview?.fast_moving_products ?? []).map((p) => ({
          key: p.product_id, left: p.product_name, right: <span className="text-emerald-400 text-xs font-medium">{p.units_sold}/{p.window_days}d</span>,
        }))} />

      <MiniList icon={<Archive className="w-3.5 h-3.5 text-white/40" />} title="Slow Moving"
        empty="Nothing slow right now" items={(overview?.slow_moving_products ?? []).map((p) => ({
          key: p.product_id, left: p.product_name, right: <span className="text-white/40 text-xs">{p.units_sold} sold</span>,
        }))} />

      <MiniList icon={<Award className="w-3.5 h-3.5 text-[#a5b4fc]" />} title="Best Selling"
        empty="No sales yet" items={(overview?.best_selling_products ?? []).map((p) => ({
          key: p.product_id, left: p.product_name, right: <span className="text-[#a5b4fc] text-xs font-medium">{p.units_sold} sold</span>,
        }))} />
    </Card>
  )
}

function MiniList({ icon, title, items, empty }: { icon: React.ReactNode; title: string; items: { key: string; left: string; right: React.ReactNode }[]; empty: string }) {
  return (
    <div className="rounded-xl bg-white/[0.03] border border-white/10 p-3">
      <div className="flex items-center gap-1.5 mb-2">{icon}<h3 className="text-[11px] font-semibold text-white/60 uppercase tracking-wide">{title}</h3></div>
      <div className="space-y-1.5">
        {items.length === 0 && <p className="text-xs text-white/30">{empty}</p>}
        {items.slice(0, 5).map((it) => (
          <div key={it.key} className="flex items-center justify-between text-xs gap-2">
            <span className="text-white/70 truncate">{it.left}</span>
            {it.right}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Recommendations
// ─────────────────────────────────────────────────────────────────────────────

function RecommendationsPanel({ recommendations, loading }: { recommendations?: Recommendation[]; loading: boolean }) {
  return (
    <Card className="p-4">
      <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
        <Sparkles className="w-4 h-4 text-[#a5b4fc]" /> AI Recommendations
      </h2>
      <div className="space-y-2.5">
        {loading && <Loader2 className="w-4 h-4 text-white/20 animate-spin" />}
        {!loading && (recommendations ?? []).length === 0 && (
          <p className="text-xs text-white/30">No recommendations right now.</p>
        )}
        {(recommendations ?? []).map((r, i) => (
          <div key={i} className="rounded-xl bg-white/[0.03] border border-white/10 p-3">
            <div className="flex items-center justify-between gap-2 mb-1">
              <p className="text-sm font-medium text-white">{r.title}</p>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <Badge tone={PRIORITY_TONE[r.priority]}>{r.priority}</Badge>
                <Badge tone="accent"><BadgeCheck className="w-2.5 h-2.5" /> {r.confidence}%</Badge>
              </div>
            </div>
            <p className="text-xs text-white/50 mb-1">{r.reason}</p>
            <p className="text-xs text-[#a5b4fc]">→ {r.suggested_action}</p>
          </div>
        ))}
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Predictions
// ─────────────────────────────────────────────────────────────────────────────

function PredictionsPanel({ predictions, loading }: { predictions?: AdvisorPredictions; loading: boolean }) {
  return (
    <Card className="p-4">
      <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
        <TrendingUp className="w-4 h-4 text-[#a5b4fc]" /> Predictions
      </h2>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <StatBox label="Tomorrow's Sales" value={predictions ? money(predictions.tomorrow_sales_estimate) : '—'} loading={loading} />
        <StatBox label="Next Week Revenue" value={predictions ? money(predictions.next_week_revenue_estimate) : '—'} loading={loading} />
        <StatBox label="Expected Demand (7d)" value={predictions ? `${predictions.expected_demand_next_7_days_units} units` : '—'} loading={loading} />
        <StatBox label="Products at Stockout Risk" value={predictions ? predictions.low_stock_risk.length : '—'} loading={loading} />
      </div>

      <ChartCard
        title="Revenue Trend (last 7 days)"
        data={predictions?.revenue_history}
        loading={loading}
        color="#6366f1"
        valueFormatter={(v) => money(v)}
      />

      {predictions && predictions.predicted_best_sellers.length > 0 && (
        <div className="mt-4">
          <h3 className="text-[11px] font-semibold text-white/60 uppercase tracking-wide mb-2">Predicted Best Sellers</h3>
          <div className="flex flex-wrap gap-2">
            {predictions.predicted_best_sellers.map((p) => (
              <Badge key={p.product_id} tone="accent">{p.product_name} · {p.units_sold} sold</Badge>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}

function StatBox({ label, value, loading }: { label: string; value: string | number; loading: boolean }) {
  return (
    <div className="rounded-xl bg-white/[0.03] border border-white/10 p-3">
      <p className="text-[10px] text-white/40 uppercase tracking-wide mb-1">{label}</p>
      {loading ? <Loader2 className="w-3.5 h-3.5 text-white/20 animate-spin" /> : <p className="text-base font-semibold text-white">{value}</p>}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// AI Chat
// ─────────────────────────────────────────────────────────────────────────────

function ChatPanel({ shopId }: { shopId: string }) {
  const { toast } = useToast()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [question, setQuestion] = useState('')
  const [sending, setSending] = useState(false)

  const suggestions = [
    'Why did sales decrease?',
    'Which products make the most profit?',
    'What should I restock?',
    'How can I increase revenue?',
  ]

  const send = async (q?: string) => {
    const text = (q ?? question).trim()
    if (!text || sending) return
    setMessages((m) => [...m, { role: 'user', content: text }])
    setQuestion('')
    setSending(true)
    try {
      const res = await businessAdvisorApi.chat(shopId, text)
      setMessages((m) => [...m, { role: 'assistant', content: res.answer }])
    } catch {
      toast('error', 'Could not reach the AI advisor')
      setMessages((m) => [...m, { role: 'assistant', content: "Sorry, I couldn't answer that right now." }])
    } finally {
      setSending(false)
    }
  }

  const summarize = async () => {
    setSending(true)
    try {
      const res = await businessAdvisorApi.getDailySummary(shopId)
      setMessages((m) => [...m, { role: 'user', content: "Generate today's business summary." }, { role: 'assistant', content: res.answer }])
    } catch {
      toast('error', 'Could not generate summary')
    } finally {
      setSending(false)
    }
  }

  return (
    <Card className="p-4 flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2">
          <Bot className="w-4 h-4 text-[#a5b4fc]" /> Ask Your AI Advisor
        </h2>
        <Button variant="ghost" size="sm" onClick={summarize} loading={sending}>Daily Summary</Button>
      </div>

      <div className="flex flex-wrap gap-1.5 mb-3">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => send(s)}
            className="text-[11px] px-2.5 py-1 rounded-full bg-white/[0.04] border border-white/10 text-white/60 hover:text-white hover:border-white/20 transition"
          >
            {s}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-[180px] max-h-[320px] overflow-y-auto space-y-2.5 mb-3 pr-1">
        {messages.length === 0 && <p className="text-xs text-white/30">Ask anything about today's business — grounded in your real numbers.</p>}
        {messages.map((m, i) => (
          <div key={i} className={`text-xs rounded-xl px-3 py-2 max-w-[90%] ${m.role === 'user' ? 'bg-[#6366f1]/15 text-white ml-auto' : 'bg-white/[0.04] text-white/75 border border-white/10'}`}>
            {m.content}
          </div>
        ))}
        {sending && <Loader2 className="w-3.5 h-3.5 text-white/30 animate-spin" />}
      </div>

      <div className="flex gap-2">
        <Input
          placeholder="Ask a question…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
        />
        <Button size="md" icon={<Send className="w-4 h-4" />} onClick={() => send()} loading={sending} disabled={!question.trim()} />
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Reports
// ─────────────────────────────────────────────────────────────────────────────

function ReportsPanel({
  period, setPeriod, onExport, exporting,
}: { period: ReportPeriod; setPeriod: (p: ReportPeriod) => void; onExport: (f: 'pdf' | 'xlsx') => void; exporting: 'pdf' | 'xlsx' | null }) {
  const periods: ReportPeriod[] = ['daily', 'weekly', 'monthly']
  return (
    <Card className="p-4">
      <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
        <FileDown className="w-4 h-4 text-[#a5b4fc]" /> Reports
      </h2>

      <div className="flex gap-1.5 mb-4">
        {periods.map((p) => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className={`text-xs px-3 py-1.5 rounded-lg border capitalize transition ${
              period === p
                ? 'bg-[#6366f1]/15 border-[#6366f1]/30 text-[#a5b4fc] font-medium'
                : 'bg-white/[0.03] border-white/10 text-white/50 hover:text-white/80'
            }`}
          >
            {p}
          </button>
        ))}
      </div>

      <p className="text-xs text-white/40 mb-4">
        Export the {period} revenue, profit, orders, and customer breakdown as a formatted report.
      </p>

      <div className="flex gap-2">
        <Button variant="secondary" size="sm" icon={<FileDown className="w-3.5 h-3.5" />} loading={exporting === 'pdf'} onClick={() => onExport('pdf')}>
          Export PDF
        </Button>
        <Button variant="secondary" size="sm" icon={<FileSpreadsheet className="w-3.5 h-3.5" />} loading={exporting === 'xlsx'} onClick={() => onExport('xlsx')}>
          Export Excel
        </Button>
      </div>
    </Card>
  )
}

// ThunderBots AI Business Advisor — Types (NEW, additive)

export interface MoverStat {
  product_id: string
  product_name: string
  quantity_available: number
  units_sold: number
  window_days: number
}

export interface StockAlertItem {
  product_id: string
  product_name: string
  quantity_available: number
  threshold: number
  severity: 'low' | 'out_of_stock'
}

export interface AdvisorOverview {
  today_revenue: number
  yesterday_revenue: number
  revenue_change_pct: number | null
  profit: number
  orders: number
  new_customers: number
  returning_customers: number
  low_stock_products: StockAlertItem[]
  out_of_stock_products: StockAlertItem[]
  fast_moving_products: MoverStat[]
  slow_moving_products: MoverStat[]
  best_selling_products: MoverStat[]
  generated_at: string
}

export type RecommendationPriority = 'high' | 'medium' | 'low'

export interface Recommendation {
  type: string
  priority: RecommendationPriority
  confidence: number
  title: string
  reason: string
  suggested_action: string
  product_id: string | null
  product_name: string | null
}

export interface LowStockRiskItem {
  product_id: string
  product_name: string
  quantity_available: number
  avg_daily_demand: number
  estimated_days_to_stockout: number
}

export interface AdvisorPredictions {
  tomorrow_sales_estimate: number
  next_week_revenue_estimate: number
  trend_factor: number
  revenue_history: { date: string; value: number }[]
  low_stock_risk: LowStockRiskItem[]
  expected_demand_next_7_days_units: number
  predicted_best_sellers: MoverStat[]
}

export type AlertSeverity = 'high' | 'medium' | 'low'
export type AlertType = 'low_stock' | 'revenue_drop' | 'slow_sales' | 'high_demand' | 'inventory_issues'

export interface AdvisorAlert {
  type: AlertType
  severity: AlertSeverity
  message: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatResponse {
  answer: string
  grounded: boolean
  error?: string
}

export type ReportPeriod = 'daily' | 'weekly' | 'monthly'

export interface ReportDayRow {
  date: string
  revenue: number
  profit: number
  orders: number
  new_customers: number
  returning_customers: number
}

export interface BusinessReport {
  shop_name: string
  period: ReportPeriod
  start_date: string
  end_date: string
  total_revenue: number
  total_profit: number
  total_orders: number
  daily_breakdown: ReportDayRow[]
}

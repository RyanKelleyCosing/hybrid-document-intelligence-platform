export type PublicCostContributor = {
  amount: number;
  name: string;
};

export type PublicCostAnomaly = {
  amount: number;
  baseline_amount: number;
  delta_amount: number;
  direction: "drop" | "spike";
  severity: "high" | "medium";
  summary: string;
  usage_date: string;
};

export type PublicCostDailyPoint = {
  amount: number;
  usage_date: string;
};

export type PublicCostForecast = {
  based_on_days: number;
  projected_additional_cost: number;
  projected_month_end_cost: number;
  remaining_days_in_period: number;
  trailing_daily_average: number;
};

export type PublicCostTrendPoint = {
  amount: number;
  label: string;
  period_end: string;
  period_start: string;
};

export type PublicCostMetricsSummary = {
  anomalies: PublicCostAnomaly[];
  collection_mode: string;
  collection_window: string;
  currency: string | null;
  daily_cost_trend: PublicCostTrendPoint[];
  day_over_day_delta: number;
  forecast: PublicCostForecast | null;
  generated_at_utc: string;
  history_row_count: number;
  history_source: string;
  month_to_date_cost: number;
  monthly_cost_trend: PublicCostTrendPoint[];
  previous_day_cost: number;
  recent_daily_costs: PublicCostDailyPoint[];
  today_cost: number;
  top_resource_groups: PublicCostContributor[];
  top_resources: PublicCostContributor[];
  top_service_families: PublicCostContributor[];
  week_to_date_cost: number;
  weekly_cost_trend: PublicCostTrendPoint[];
  year_to_date_cost: number;
  yesterday_cost: number;
};

const publicCostApiBaseUrl =
  import.meta.env.VITE_PUBLIC_COST_API_BASE_URL?.replace(/\/$/, "") ||
  import.meta.env.VITE_PUBLIC_TRAFFIC_API_BASE_URL?.replace(/\/$/, "") ||
  "";

export async function fetchPublicCostSummary(): Promise<PublicCostMetricsSummary | null> {
  if (!publicCostApiBaseUrl) {
    return null;
  }

  const response = await fetch(`${publicCostApiBaseUrl}/public-cost-summary`, {
    cache: "no-store",
    headers: {
      Accept: "application/json",
    },
    method: "GET",
  });

  if (!response.ok) {
    throw new Error(`Public cost summary failed with status ${response.status}`);
  }

  const payload = (await response.json()) as Partial<PublicCostMetricsSummary>;
  if (!payload || typeof payload !== "object") {
    throw new Error("Public cost summary response must be a JSON object.");
  }

  return payload as PublicCostMetricsSummary;
}

export function getPublicCostExportUrl(kind: "csv" | "json"): string | null {
  if (!publicCostApiBaseUrl) {
    return null;
  }

  return kind === "csv"
    ? `${publicCostApiBaseUrl}/public-cost-history`
    : `${publicCostApiBaseUrl}/public-cost-latest`;
}
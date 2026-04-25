import { useEffect, useMemo, useState } from "react";

import {
  DEMO_PATH,
  HOME_PATH,
  SECURITY_PATH,
  navigateToAppPath,
} from "../appRoutes";
import {
  fetchPublicCostSummary,
  getPublicCostExportUrl,
  type PublicCostAnomaly,
  type PublicCostContributor,
  type PublicCostDailyPoint,
  type PublicCostForecast,
  type PublicCostMetricsSummary,
  type PublicCostTrendPoint,
} from "../api/publicCostApi";
import {
  fetchPublicHealth,
  getPublicTrafficSessionId,
  recordPublicTrafficEvent,
  type PublicHealthStatus,
} from "../api/publicTrafficApi";
import { PublicSiteLayout } from "./PublicSiteLayout";
import {
  SurfaceBarRow,
  SectionHeading,
  StatusBadge,
  SurfaceCard,
  SurfaceColumnChart,
  SurfaceDrawer,
  SurfaceMetricCard,
  SurfacePanel,
  type StatusBadgeTone,
} from "./SurfacePrimitives";

type PublicCostLoadState = "error" | "idle" | "loading" | "ready" | "unavailable";

type CostDriverGroup = {
  emptyState: string;
  id: "resourceGroups" | "resources" | "serviceFamilies";
  items: PublicCostContributor[];
  title: string;
};

type CostTrendGroup = {
  description: string;
  emptyState: string;
  id: "daily" | "monthly" | "weekly";
  items: PublicCostTrendPoint[];
  title: string;
};

type CostDriverFilter = "all" | CostDriverGroup["id"];
type CostDriverLimitFilter = "3" | "5" | "all";
type CostRecentDayWindowFilter = "2" | "5" | "all";
type CostTrendFilter = "all" | CostTrendGroup["id"];

type CostReadingNote = {
  badge: string;
  body: string;
  title: string;
  tone: StatusBadgeTone;
};

function handleInternalNavigation(
  event: React.MouseEvent<HTMLAnchorElement>,
  nextPath: string,
) {
  event.preventDefault();
  navigateToAppPath(nextPath);
}

function formatCurrency(amount: number, currency: string | null) {
  try {
    return new Intl.NumberFormat("en-US", {
      currency: currency || "USD",
      maximumFractionDigits: 2,
      minimumFractionDigits: 2,
      style: "currency",
    }).format(amount);
  } catch {
    return `${currency || "USD"} ${amount.toFixed(2)}`;
  }
}

function formatSignedCurrency(amount: number, currency: string | null) {
  const formattedAmount = formatCurrency(Math.abs(amount), currency);
  if (amount > 0) {
    return `+${formattedAmount}`;
  }

  if (amount < 0) {
    return `-${formattedAmount}`;
  }

  return formattedAmount;
}

function formatGeneratedAtLabel(value: string | null) {
  if (!value) {
    return "Awaiting retained snapshot";
  }

  const parsedValue = new Date(value);
  if (Number.isNaN(parsedValue.valueOf())) {
    return value;
  }

  return parsedValue.toLocaleString("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  });
}

function formatTrendLabel(point: PublicCostTrendPoint) {
  if (point.label) {
    return point.label;
  }

  if (point.period_start === point.period_end) {
    return point.period_start;
  }

  return `${point.period_start} to ${point.period_end}`;
}

function buildLoadStatusMessage(
  loadState: PublicCostLoadState,
  summary: PublicCostMetricsSummary | null,
) {
  if (loadState === "ready" && summary) {
    return (
      `Live public-safe cost history is connected from ${summary.history_source}. ` +
      `The retained dashboard currently reflects ${summary.history_row_count} CSV rows ` +
      `plus daily, weekly, and monthly trend slices.`
    );
  }

  if (loadState === "loading") {
    return "Loading the latest public-safe cost snapshot, KPI cards, and retained trend slices.";
  }

  if (loadState === "error") {
    return "The public cost API did not respond. The route stays available, but live cost KPIs are temporarily unavailable.";
  }

  if (loadState === "unavailable") {
    return "This build is not connected to a public cost API base URL yet, so the route is showing a safe offline state.";
  }

  return "The route is ready for a retained public cost snapshot once the API base URL is connected.";
}

function isFlatSnapshot(summary: PublicCostMetricsSummary | null) {
  if (!summary) {
    return false;
  }

  const contributorAmounts = [
    ...summary.top_resources,
    ...summary.top_resource_groups,
    ...summary.top_service_families,
  ].map((item) => item.amount);
  const trendAmounts = [
    ...summary.daily_cost_trend,
    ...summary.weekly_cost_trend,
    ...summary.monthly_cost_trend,
  ].map((item) => item.amount);

  return (
    summary.today_cost === 0 &&
    summary.week_to_date_cost === 0 &&
    summary.month_to_date_cost === 0 &&
    summary.year_to_date_cost === 0 &&
    summary.yesterday_cost === 0 &&
    summary.day_over_day_delta === 0 &&
    contributorAmounts.every((amount) => amount === 0) &&
    trendAmounts.every((amount) => amount === 0)
  );
}

function getTrendFillWidth(items: PublicCostTrendPoint[], amount: number) {
  const maxAmount = Math.max(...items.map((item) => item.amount), 0);
  if (maxAmount <= 0) {
    return 0;
  }

  return Math.max(14, Math.round((amount / maxAmount) * 100));
}

function getContributorFillWidth(
  items: ReadonlyArray<PublicCostContributor>,
  amount: number,
) {
  const maxAmount = Math.max(...items.map((item) => item.amount), 0);
  if (maxAmount <= 0) {
    return 0;
  }

  return Math.max(14, Math.round((amount / maxAmount) * 100));
}

function getAmountColumnHeight(
  items: ReadonlyArray<{ amount: number }>,
  amount: number,
) {
  const maxAmount = Math.max(...items.map((item) => item.amount), 0);
  if (maxAmount <= 0) {
    return 0;
  }

  return Math.max(18, Math.round((amount / maxAmount) * 100));
}

function getAnomalyTone(severity: PublicCostAnomaly["severity"]): StatusBadgeTone {
  return severity === "high" ? "danger" : "warning";
}

function getForecastConfidence(forecast: PublicCostForecast | null): {
  label: string;
  note: string;
  tone: StatusBadgeTone;
} | null {
  if (!forecast) {
    return null;
  }

  const retainedDaysLabel = `${forecast.based_on_days} retained day${
    forecast.based_on_days === 1 ? "" : "s"
  }`;
  const remainingDaysLabel = `${forecast.remaining_days_in_period} remaining day${
    forecast.remaining_days_in_period === 1 ? "" : "s"
  }`;

  if (forecast.based_on_days >= 7 && forecast.remaining_days_in_period <= 14) {
    return {
      label: "Higher confidence",
      note: `Built from ${retainedDaysLabel} with only ${remainingDaysLabel} left in the active period.`,
      tone: "success",
    };
  }

  if (forecast.based_on_days >= 4) {
    return {
      label: "Moderate confidence",
      note: `Uses ${retainedDaysLabel} to project ${remainingDaysLabel}, so treat it as a run-rate signal rather than a committed budget.`,
      tone: "warning",
    };
  }

  return {
    label: "Early estimate",
    note: `Only ${retainedDaysLabel} are retained so far, which makes the current run-rate projection directionally useful but still volatile.`,
    tone: "accent",
  };
}

function sortAnomaliesByRecency(
  anomalies: ReadonlyArray<PublicCostAnomaly>,
): PublicCostAnomaly[] {
  return [...anomalies].sort((left, right) => {
    const severityDelta =
      Number(right.severity === "high") - Number(left.severity === "high");

    if (severityDelta !== 0) {
      return severityDelta;
    }

    return right.usage_date.localeCompare(left.usage_date);
  });
}

function buildCostReadingNotes(
  summary: PublicCostMetricsSummary | null,
): CostReadingNote[] {
  const currency = summary?.currency || null;
  const forecast = summary?.forecast || null;
  const forecastConfidence = getForecastConfidence(forecast);
  const leadingServiceFamily = summary?.top_service_families[0] || null;

  return [
    {
      badge: summary ? "In-flight day" : "Snapshot pending",
      body: summary
        ? `${formatCurrency(summary.today_cost, currency)} is the current in-progress day. Compare it with ${formatCurrency(summary.yesterday_cost, currency)} yesterday before treating it as settled spend.`
        : "Today updates as retained history refreshes, so read it as an in-progress signal instead of a closed invoice line.",
      title: "Today stays provisional",
      tone: summary ? "warning" : "neutral",
    },
    {
      badge: forecastConfidence?.label || "Run-rate",
      body:
        forecast && summary
          ? `${forecastConfidence?.note || "Month-end projections stay directional until more retained daily history accumulates."} Current run rate points to ${formatCurrency(forecast.projected_month_end_cost, currency)} if the retained pace holds.`
          : "Month-end projections appear once enough retained daily history is available to support a basic run-rate estimate.",
      title: "Forecasts are directional",
      tone: forecastConfidence?.tone || "accent",
    },
    {
      badge: leadingServiceFamily ? "Public-safe labels" : "Public-safe contract",
      body: leadingServiceFamily
        ? `Service families stay verbatim, with ${leadingServiceFamily.name} currently leading at ${formatCurrency(leadingServiceFamily.amount, currency)}. Resource and environment rows use role-based labels so the public exports explain spend without exposing tenant identifiers.`
        : "Service-family rankings stay verbatim, while resource and environment rows use role-based labels so the public exports explain spend without exposing tenant identifiers.",
      title: "Contributor names stay generic on purpose",
      tone: "success",
    },
  ];
}

export function CostOverviewSite() {
  const [trafficSessionId] = useState(() => getPublicTrafficSessionId());
  const [costSummary, setCostSummary] = useState<PublicCostMetricsSummary | null>(
    null,
  );
  const [costLoadState, setCostLoadState] = useState<PublicCostLoadState>("idle");
  const [selectedTrendFilter, setSelectedTrendFilter] =
    useState<CostTrendFilter>("all");
  const [selectedDriverFilter, setSelectedDriverFilter] =
    useState<CostDriverFilter>("all");
  const [selectedDriverLimit, setSelectedDriverLimit] =
    useState<CostDriverLimitFilter>("all");
  const [selectedRecentDayWindow, setSelectedRecentDayWindow] =
    useState<CostRecentDayWindowFilter>("all");
  const [healthStatus, setHealthStatus] = useState<PublicHealthStatus | null>(null);

  useEffect(() => {
    let isCancelled = false;

    const probeHealth = async () => {
      const nextStatus = await fetchPublicHealth();
      if (!isCancelled) {
        setHealthStatus(nextStatus);
      }
    };

    void probeHealth();

    const rawPollMs = Number.parseInt(
      import.meta.env.VITE_PUBLIC_HEALTH_POLL_MS_COST
        ?? import.meta.env.VITE_PUBLIC_HEALTH_POLL_MS
        ?? "",
      10,
    );
    const pollMs = Number.isFinite(rawPollMs) && rawPollMs > 0 ? rawPollMs : 60_000;
    const intervalId = window.setInterval(probeHealth, pollMs);

    return () => {
      isCancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const csvExportUrl = getPublicCostExportUrl("csv");
  const jsonExportUrl = getPublicCostExportUrl("json");

  const summaryCards = useMemo(() => {
    const currency = costSummary?.currency || null;
    const todayDelta = costSummary
      ? costSummary.today_cost - costSummary.yesterday_cost
      : null;

    const deltaBadge =
      costSummary && todayDelta !== null && costSummary.yesterday_cost !== 0 ? (
        <span
          className={
            todayDelta > 0
              ? "cost-delta-chip cost-delta-chip-up"
              : todayDelta < 0
                ? "cost-delta-chip cost-delta-chip-down"
                : "cost-delta-chip cost-delta-chip-flat"
          }
          title="Today vs yesterday (lower spend is green)."
        >
          <span aria-hidden="true" className="cost-delta-chip-arrow">
            {todayDelta > 0 ? "▲" : todayDelta < 0 ? "▼" : "◆"}
          </span>
          {formatSignedCurrency(todayDelta, currency)}
        </span>
      ) : null;

    const ytdDailyAverage = (() => {
      if (!costSummary) {
        return null;
      }

      const snapshotAt = new Date(costSummary.generated_at_utc);
      if (Number.isNaN(snapshotAt.valueOf())) {
        return null;
      }

      const startOfYear = Date.UTC(snapshotAt.getUTCFullYear(), 0, 1);
      const elapsedDays = Math.max(
        1,
        Math.floor((snapshotAt.valueOf() - startOfYear) / 86_400_000) + 1,
      );
      return costSummary.year_to_date_cost / elapsedDays;
    })();

    return [
      {
        badge: deltaBadge,
        detail: costSummary
          ? `Vs yesterday: ${formatSignedCurrency(todayDelta || 0, currency)}. As of ${formatGeneratedAtLabel(costSummary.generated_at_utc)} UTC.`
          : "Shows the current retained day against the last completed day.",
        label: "Today",
        value: costSummary
          ? formatCurrency(costSummary.today_cost, currency)
          : "Snapshot pending",
      },
      {
        badge: null,
        detail: costSummary
          ? `Bound to the active retained week ending ${formatGeneratedAtLabel(costSummary.generated_at_utc)} UTC.`
          : "Current-week rollup appears with the retained snapshot.",
        label: "Week to date",
        value: costSummary
          ? formatCurrency(costSummary.week_to_date_cost, currency)
          : "Awaiting data",
      },
      {
        badge: null,
        detail: costSummary
          ? `${costSummary.collection_mode}. ${costSummary.collection_window}`
          : "Public-safe retained cost history will populate this card once the API is connected.",
        label: "Month to date",
        value: costSummary
          ? formatCurrency(costSummary.month_to_date_cost, currency)
          : "Snapshot pending",
      },
      {
        badge: null,
        detail: costSummary && ytdDailyAverage !== null
          ? `≈ ${formatCurrency(ytdDailyAverage, currency)} per day on average — a full document-intelligence stack running at the price of two coffees.`
          : costSummary
            ? "Derived from the retained public-safe history window without exposing tenant internals."
            : "Year rollups appear once retained history is connected.",
        label: "Year to date",
        value: costSummary
          ? formatCurrency(costSummary.year_to_date_cost, currency)
          : "Awaiting data",
      },
    ];
  }, [costSummary]);

  const trendGroups = useMemo<CostTrendGroup[]>(
    () => [
      {
        description:
          "Latest retained days, including the current snapshot day when it is available.",
        emptyState:
          "Daily spend points will appear once the retained history includes a live cost snapshot.",
        id: "daily",
        items: costSummary?.daily_cost_trend || [],
        title: "Daily spend",
      },
      {
        description:
          "Rolling week buckets derived from the retained public-safe history.",
        emptyState:
          "Weekly rollups will appear once the retained history spans more than one daily point.",
        id: "weekly",
        items: costSummary?.weekly_cost_trend || [],
        title: "Weekly rollup",
      },
      {
        description:
          "Month buckets retained in the current public-safe history window.",
        emptyState:
          "Monthly rollups will appear once retained history spans multiple month periods.",
        id: "monthly",
        items: costSummary?.monthly_cost_trend || [],
        title: "Monthly rollup",
      },
    ],
    [costSummary],
  );

  const driverGroups = useMemo<CostDriverGroup[]>(
    () => [
      {
        emptyState: "No public-safe resource contributors were retained in the latest snapshot.",
        id: "resources",
        items: costSummary?.top_resources || [],
        title: "Top resources",
      },
      {
        emptyState: "No public-safe resource-group contributors were retained in the latest snapshot.",
        id: "resourceGroups",
        items: costSummary?.top_resource_groups || [],
        title: "Top resource groups",
      },
      {
        emptyState: "Service-family breakdowns will appear once that optional query succeeds in retained history.",
        id: "serviceFamilies",
        items: costSummary?.top_service_families || [],
        title: "Top service families",
      },
    ],
    [costSummary],
  );

  const filteredTrendGroups = useMemo(() => {
    if (selectedTrendFilter === "all") {
      return trendGroups;
    }

    return trendGroups.filter((group) => group.id === selectedTrendFilter);
  }, [selectedTrendFilter, trendGroups]);

  const filteredDriverGroups = useMemo(() => {
    const contributorLimit =
      selectedDriverLimit === "all" ? null : Number(selectedDriverLimit);

    return driverGroups
      .filter(
        (group) =>
          selectedDriverFilter === "all" || group.id === selectedDriverFilter,
      )
      .map((group) => ({
        ...group,
        items:
          contributorLimit === null
            ? group.items
            : group.items.slice(0, contributorLimit),
      }));
  }, [driverGroups, selectedDriverFilter, selectedDriverLimit]);

  const filteredRecentDailyCosts = useMemo(() => {
    const recentDailyCosts = costSummary?.recent_daily_costs || [];
    if (selectedRecentDayWindow === "all") {
      return recentDailyCosts;
    }

    return recentDailyCosts.slice(-Number(selectedRecentDayWindow));
  }, [costSummary, selectedRecentDayWindow]);

  const forecastSummary = costSummary?.forecast || null;
  const anomalyHighlights = costSummary?.anomalies || [];
  const anomalyHistory = useMemo(
    () => sortAnomaliesByRecency(anomalyHighlights),
    [anomalyHighlights],
  );
  const costReadingNotes = useMemo(
    () => buildCostReadingNotes(costSummary),
    [costSummary],
  );
  const primaryAnomaly = anomalyHistory[0] || null;
  const forecastConfidence = getForecastConfidence(forecastSummary);

  const activeFilterChips = useMemo(
    () => [
      `Trend view: ${
        selectedTrendFilter === "all"
          ? "All slices"
          : selectedTrendFilter === "daily"
            ? "Daily only"
            : selectedTrendFilter === "weekly"
              ? "Weekly only"
              : "Monthly only"
      }`,
      `Contributor view: ${
        selectedDriverFilter === "all"
          ? "All groups"
          : selectedDriverFilter === "resources"
            ? "Resources only"
            : selectedDriverFilter === "resourceGroups"
              ? "Resource groups only"
              : "Service families only"
      }`,
      `Contributor depth: ${
        selectedDriverLimit === "all"
          ? "All retained contributors"
          : `Top ${selectedDriverLimit} per group`
      }`,
      `Recent days: ${
        selectedRecentDayWindow === "all"
          ? "All retained days"
          : `Latest ${selectedRecentDayWindow} days`
      }`,
    ],
    [
      selectedDriverFilter,
      selectedDriverLimit,
      selectedRecentDayWindow,
      selectedTrendFilter,
    ],
  );

  const hasActiveFilters =
    selectedTrendFilter !== "all" ||
    selectedDriverFilter !== "all" ||
    selectedDriverLimit !== "all" ||
    selectedRecentDayWindow !== "all";

  const loadStatusMessage = useMemo(
    () => buildLoadStatusMessage(costLoadState, costSummary),
    [costLoadState, costSummary],
  );

  useEffect(() => {
    void recordPublicTrafficEvent({
      event_type: "page_view",
      page_title: "Cost overview",
      referrer: document.referrer || undefined,
      route: "cost",
      session_id: trafficSessionId,
      site_mode: "simulation",
    });
  }, [trafficSessionId]);

  useEffect(() => {
    let isCancelled = false;

    const loadCostSummary = async () => {
      setCostLoadState("loading");

      try {
        const summary = await fetchPublicCostSummary();
        if (isCancelled) {
          return;
        }

        if (summary === null) {
          setCostSummary(null);
          setCostLoadState("unavailable");
          return;
        }

        setCostSummary(summary);
        setCostLoadState("ready");
      } catch (error) {
        console.warn("Unable to load public cost summary.", error);
        if (!isCancelled) {
          setCostSummary(null);
          setCostLoadState("error");
        }
      }
    };

    void loadCostSummary();

    return () => {
      isCancelled = true;
    };
  }, []);

  const resetFilters = () => {
    setSelectedTrendFilter("all");
    setSelectedDriverFilter("all");
    setSelectedDriverLimit("all");
    setSelectedRecentDayWindow("all");
  };

  return (
    <PublicSiteLayout activeRoute="cost">
      <header className="hero hero-wide public-hero">
        <div className="public-hero-copy">
          <p className="eyebrow">Cost transparency</p>
          <h1>Public cost dashboard for the document platform.</h1>
          {healthStatus ? (
            <p
              aria-live="polite"
              className={`landing-live-status landing-live-status-${healthStatus.status}`}
            >
              <span aria-hidden="true" className="landing-live-status-dot" />
              {healthStatus.status === "online"
                ? `Public API online · ${healthStatus.latencyMs ?? "?"} ms`
                : healthStatus.status === "degraded"
                  ? "Public API degraded · retrying"
                  : "Public API unreachable · retrying"}
            </p>
          ) : null}
          <p className="hero-copy public-hero-text">
            This route now pulls the latest retained public-safe cost snapshot,
            surfaces real dollar values across today, week, month, and year,
            and exposes trend slices plus raw CSV and JSON exports with
            role-based contributor labels instead of tenant identifiers or
            private admin detail.
          </p>
          <div className="hero-actions">
            <a
              className="button-link"
              href={HOME_PATH}
              onClick={(event) => {
                handleInternalNavigation(event, HOME_PATH);
              }}
            >
              Back to public landing
            </a>
            <a
              className="button-link secondary-link"
              href={SECURITY_PATH}
              onClick={(event) => {
                handleInternalNavigation(event, SECURITY_PATH);
              }}
            >
              Open security route
            </a>
            <a
              className="button-link secondary-link"
              href={DEMO_PATH}
              onClick={(event) => {
                handleInternalNavigation(event, DEMO_PATH);
              }}
            >
              Open workflow walkthrough
            </a>
          </div>
        </div>

        <div className="hero-panel public-status-panel">
          <span>Current delivery state</span>
          <strong>
            {costSummary
              ? `${formatCurrency(costSummary.today_cost, costSummary.currency)} today / ${formatCurrency(costSummary.month_to_date_cost, costSummary.currency)} month`
              : "Waiting on public cost snapshot"}
          </strong>
          <p>{loadStatusMessage}</p>
        </div>
      </header>

      <section className="metrics-grid" aria-label="cost snapshot metrics">
        {summaryCards.map((card) => (
          <SurfaceMetricCard
            as="article"
            badge={card.badge}
            className="metric-card"
            detail={card.detail}
            eyebrow={card.label}
            key={card.label}
            value={card.value}
          />
        ))}
      </section>

      <SurfacePanel aria-label="cost dashboard filters" className="queue-filter-panel">
        <SectionHeading
          actions={
            <div className="queue-filter-actions">
              <button className="secondary-button" onClick={resetFilters} type="button">
                Reset filters
              </button>
            </div>
          }
          description="Narrow the retained snapshot shown on this page by trend horizon, contributor grouping, and recent-day window. The CSV and JSON exports always open the full retained contract."
          title="View filters"
        />

        <div className="queue-filter-grid">
          <label className="filter-field">
            <span>Trend focus</span>
            <select
              onChange={(event) => {
                setSelectedTrendFilter(event.target.value as CostTrendFilter);
              }}
              value={selectedTrendFilter}
            >
              <option value="all">All trend slices</option>
              <option value="daily">Daily spend</option>
              <option value="weekly">Weekly rollup</option>
              <option value="monthly">Monthly rollup</option>
            </select>
          </label>

          <label className="filter-field">
            <span>Contributor focus</span>
            <select
              onChange={(event) => {
                setSelectedDriverFilter(event.target.value as CostDriverFilter);
              }}
              value={selectedDriverFilter}
            >
              <option value="all">All contributor groups</option>
              <option value="resources">Top resources</option>
              <option value="resourceGroups">Top resource groups</option>
              <option value="serviceFamilies">Top service families</option>
            </select>
          </label>

          <label className="filter-field">
            <span>Contributor depth</span>
            <select
              onChange={(event) => {
                setSelectedDriverLimit(event.target.value as CostDriverLimitFilter);
              }}
              value={selectedDriverLimit}
            >
              <option value="all">All retained contributors</option>
              <option value="3">Top 3 per group</option>
              <option value="5">Top 5 per group</option>
            </select>
          </label>

          <label className="filter-field">
            <span>Recent day window</span>
            <select
              onChange={(event) => {
                setSelectedRecentDayWindow(
                  event.target.value as CostRecentDayWindowFilter,
                );
              }}
              value={selectedRecentDayWindow}
            >
              <option value="all">All retained days</option>
              <option value="2">Latest 2 days</option>
              <option value="5">Latest 5 days</option>
            </select>
          </label>
        </div>

        <ul className="chip-list public-chip-list" aria-label="active cost filters">
          {activeFilterChips.map((chip) => (
            <li className="reason-chip" key={chip}>
              {chip}
            </li>
          ))}
          {hasActiveFilters ? (
            <li className="reason-chip">Filtered view active</li>
          ) : (
            <li className="reason-chip">Showing the full retained page view</li>
          )}
        </ul>
      </SurfacePanel>

      <section className="workbench-layout public-layout">
        <div className="queue-column simulation-main public-main section-stack">
          <SurfacePanel id="cost-snapshot">
            <SectionHeading
              description="The dashboard reads the same retained JSON and CSV history used by the validation path, so the public route now reflects durable cost artifacts instead of placeholder copy."
              title="Live cost snapshot"
            />

            {costSummary ? (
              <div className="workspace-card-grid">
                <SurfaceCard>
                  <p className="queue-card-label">Snapshot source</p>
                  <div className="workspace-field-list">
                    <div className="workspace-field-row">
                      <small>Retention path</small>
                      <strong>{costSummary.history_source}</strong>
                      <span>{costSummary.collection_window}</span>
                    </div>
                    <div className="workspace-field-row">
                      <small>Snapshot captured</small>
                      <strong>{formatGeneratedAtLabel(costSummary.generated_at_utc)}</strong>
                      <span>{costSummary.history_row_count} retained CSV rows</span>
                    </div>
                    <div className="workspace-field-row">
                      <small>Refresh cadence</small>
                      <strong>Every 6 hours</strong>
                      <span>
                        Driven by the deploy script&apos;s
                        {" "}
                        <code>-EnablePublicCostRefresh</code> switch.
                      </span>
                    </div>
                  </div>
                </SurfaceCard>

                <SurfaceCard>
                  <p className="queue-card-label">Daily comparison</p>
                  <div className="workspace-field-list">
                    <div className="workspace-field-row">
                      <small>Today vs yesterday</small>
                      <strong>
                        {formatSignedCurrency(
                          costSummary.today_cost - costSummary.yesterday_cost,
                          costSummary.currency,
                        )}
                      </strong>
                      <span>
                        {formatCurrency(costSummary.today_cost, costSummary.currency)} today against {" "}
                        {formatCurrency(costSummary.yesterday_cost, costSummary.currency)} yesterday.
                      </span>
                    </div>
                    <div className="workspace-field-row">
                      <small>Yesterday vs previous day</small>
                      <strong>
                        {formatSignedCurrency(
                          costSummary.day_over_day_delta,
                          costSummary.currency,
                        )}
                      </strong>
                      <span>
                        Previous day was {formatCurrency(costSummary.previous_day_cost, costSummary.currency)}.
                      </span>
                    </div>
                  </div>
                </SurfaceCard>

                <SurfaceCard>
                  <p className="queue-card-label">Retained trend coverage</p>
                  <div className="workspace-field-list">
                    <div className="workspace-field-row">
                      <small>Daily points</small>
                      <strong>{costSummary.daily_cost_trend.length}</strong>
                      <span>Latest retained daily slices rendered on the public page.</span>
                    </div>
                    <div className="workspace-field-row">
                      <small>Weekly and monthly rollups</small>
                      <strong>
                        {costSummary.weekly_cost_trend.length} / {costSummary.monthly_cost_trend.length}
                      </strong>
                      <span>Trend slices remain bounded to public-safe retained history.</span>
                    </div>
                  </div>
                </SurfaceCard>
              </div>
            ) : (
              <div className="status-panel">{loadStatusMessage}</div>
            )}

            {isFlatSnapshot(costSummary) ? (
              <p className="status-panel">
                The live retained snapshot is connected, but the latest observed sample is currently flat at zero-cost levels.
              </p>
            ) : null}
          </SurfacePanel>

          <SurfacePanel>
            <SectionHeading
              description="These notes keep the recent billing lessons visible on the page so live numbers are easier to interpret during demos and status reviews."
              title="How to read this page"
            />

            <div className="workspace-card-grid">
              {costReadingNotes.map((note) => (
                <SurfaceCard key={note.title}>
                  <div className="mini-card-header">
                    <p className="queue-card-label">{note.title}</p>
                    <StatusBadge tone={note.tone}>{note.badge}</StatusBadge>
                  </div>
                  <p className="workspace-copy">{note.body}</p>
                </SurfaceCard>
              ))}
            </div>
          </SurfacePanel>

          <SurfacePanel id="cost-trend">
            <SectionHeading
              description="Daily, weekly, and monthly rollups are derived from the same retained public-safe history that drives the KPI cards."
              title="Trend slices"
            />

            <div className="cost-trend-grid">
              {filteredTrendGroups.map((group) => (
                <SurfaceCard className="surface-chart-card cost-trend-card" key={group.title}>
                  <p className="queue-card-label">{group.title}</p>
                  <p className="workspace-copy">{group.description}</p>
                  {group.items.length > 0 ? (
                    <div className="cost-trend-list">
                      {group.items.map((item) => (
                        <SurfaceBarRow
                          className="cost-trend-row"
                          detail={`${group.title} retained slice`}
                          key={`${group.title}-${item.period_start}-${item.period_end}`}
                          label={formatTrendLabel(item)}
                          progress={getTrendFillWidth(group.items, item.amount)}
                          value={formatCurrency(item.amount, costSummary?.currency || null)}
                        />
                      ))}
                    </div>
                  ) : (
                    <p className="workspace-copy">{group.emptyState}</p>
                  )}
                </SurfaceCard>
              ))}
            </div>
          </SurfacePanel>

          <SurfacePanel id="cost-anomalies">
            <SectionHeading
              description="Lightweight public-safe heuristics flag unusual daily moves and project a simple month-end run rate from the retained daily history."
              title="Anomaly watch and forecast"
            />

            <div className="workspace-card-grid">
              <SurfaceCard>
                <p className="queue-card-label">Month-end run rate</p>
                {forecastSummary ? (
                  <>
                    {forecastConfidence ? (
                      <StatusBadge tone={forecastConfidence.tone}>
                        {forecastConfidence.label}
                      </StatusBadge>
                    ) : null}
                    <div className="workspace-field-list">
                      <div className="workspace-field-row">
                        <small>Projected month end</small>
                        <strong>
                          {formatCurrency(
                            forecastSummary.projected_month_end_cost,
                            costSummary?.currency || null,
                          )}
                        </strong>
                        <span>
                          {formatCurrency(
                            forecastSummary.projected_additional_cost,
                            costSummary?.currency || null,
                          )}{" "}
                          additional spend projected across {forecastSummary.remaining_days_in_period}{" "}
                          remaining days.
                        </span>
                      </div>
                      <div className="workspace-field-row">
                        <small>Trailing average</small>
                        <strong>
                          {formatCurrency(
                            forecastSummary.trailing_daily_average,
                            costSummary?.currency || null,
                          )}
                        </strong>
                        <span>
                          Based on the latest {forecastSummary.based_on_days} retained day
                          {forecastSummary.based_on_days === 1 ? "" : "s"}.
                        </span>
                      </div>
                    </div>
                    {forecastConfidence ? (
                      <p className="surface-panel-copy">{forecastConfidence.note}</p>
                    ) : null}
                  </>
                ) : (
                  <p className="workspace-copy">
                    A month-end run-rate forecast appears once the retained snapshot includes daily history.
                  </p>
                )}
              </SurfaceCard>

              <SurfaceCard>
                <p className="queue-card-label">Anomaly watch</p>
                {primaryAnomaly ? (
                  <>
                    <StatusBadge tone={getAnomalyTone(primaryAnomaly.severity)}>
                      {`${primaryAnomaly.severity === "high" ? "High" : "Medium"} ${primaryAnomaly.direction}`}
                    </StatusBadge>
                    <div className="workspace-field-list">
                      <div className="workspace-field-row">
                        <small>Most recent retained signal</small>
                        <strong>
                          {primaryAnomaly.usage_date} · {formatCurrency(primaryAnomaly.amount, costSummary?.currency || null)}
                        </strong>
                        <span>
                          Latest retained medium or high day-level deviation surfaced for quick operator-style scanning.
                        </span>
                      </div>
                      <div className="workspace-field-row">
                        <small>Baseline and delta</small>
                        <strong>
                          {formatSignedCurrency(
                            primaryAnomaly.delta_amount,
                            costSummary?.currency || null,
                          )}
                        </strong>
                        <span>
                          Baseline {formatCurrency(primaryAnomaly.baseline_amount, costSummary?.currency || null)}.
                        </span>
                      </div>
                    </div>
                  </>
                ) : (
                  <p className="workspace-copy">
                    No medium or high retained daily anomalies crossed the current trailing-average threshold.
                  </p>
                )}
              </SurfaceCard>

              <SurfaceCard>
                <p className="queue-card-label">Retained anomaly history</p>
                {anomalyHistory.length > 0 ? (
                  <div className="cost-anomaly-history-list">
                    {anomalyHistory.map((anomaly) => (
                      <div className="cost-anomaly-history-row" key={anomaly.usage_date}>
                        <div className="cost-anomaly-history-copy">
                          <div className="cost-anomaly-history-heading">
                            <StatusBadge tone={getAnomalyTone(anomaly.severity)}>
                              {`${anomaly.severity === "high" ? "High" : "Medium"} ${anomaly.direction}`}
                            </StatusBadge>
                            <strong>{anomaly.usage_date}</strong>
                          </div>
                          <span>{anomaly.summary}</span>
                        </div>
                        <div className="cost-anomaly-history-metrics">
                          <small>Delta</small>
                          <strong>
                            {formatSignedCurrency(
                              anomaly.delta_amount,
                              costSummary?.currency || null,
                            )}
                          </strong>
                          <span>
                            Baseline {formatCurrency(anomaly.baseline_amount, costSummary?.currency || null)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="workspace-copy">
                    Retained anomaly history appears automatically when the public cost snapshot includes medium or high day-level deviations.
                  </p>
                )}
              </SurfaceCard>
            </div>
          </SurfacePanel>

          {filteredRecentDailyCosts.length ? (
            <SurfacePanel>
              <SectionHeading
                description="These complete-day points now render as a compact retained shape so day-to-day movement is easier to scan than a stack of isolated cards."
                title="Recent retained days"
              />

              <SurfaceCard className="surface-chart-card cost-recent-days-card">
                <div className="mini-card-header">
                  <p className="queue-card-label">Recent daily shape</p>
                  <StatusBadge
                    tone={selectedRecentDayWindow === "all" ? "accent" : "success"}
                  >
                    {selectedRecentDayWindow === "all"
                      ? "All retained days"
                      : `Latest ${selectedRecentDayWindow} days`}
                  </StatusBadge>
                </div>
                <p className="workspace-copy">
                  Each column is a completed retained day from the public-safe history contract.
                </p>
                <SurfaceColumnChart
                  items={filteredRecentDailyCosts.map((point) => ({
                    detail: "Completed day",
                    height: getAmountColumnHeight(filteredRecentDailyCosts, point.amount),
                    id: point.usage_date,
                    label: point.usage_date,
                    tone: "accent",
                    value: formatCurrency(point.amount, costSummary?.currency || null),
                  }))}
                />
              </SurfaceCard>
            </SurfacePanel>
          ) : null}
        </div>

        <SurfaceDrawer
          as="aside"
          className="operations-panel simulation-aside public-aside"
        >
          <SectionHeading
            description="These lists come from the retained public-safe snapshot and collapse tenant-specific resource and environment names into role-based labels."
            title="Ranked cost drivers"
          />

          {filteredDriverGroups.map((group) => (
            <SurfaceCard as="div" className="surface-chart-card" key={group.title}>
              <p className="queue-card-label">{group.title}</p>
              {group.items.length > 0 ? (
                <div className="cost-trend-list">
                  {group.items.map((item) => (
                    <SurfaceBarRow
                      className="cost-trend-row"
                      detail="Public-safe contributor"
                      key={`${group.title}-${item.name}`}
                      label={item.name}
                      progress={getContributorFillWidth(group.items, item.amount)}
                      value={formatCurrency(item.amount, costSummary?.currency || null)}
                    />
                  ))}
                </div>
              ) : (
                <p className="workspace-copy">{group.emptyState}</p>
              )}
            </SurfaceCard>
          ))}

          <SurfacePanel as="div" id="cost-calculator">
            <SectionHeading
              description="Slide the monthly document volume to estimate stack cost using publicly listed Azure unit prices for AI Document Intelligence (Read tier)."
              title="What would it cost you?"
            />
            <CostScenarioCalculator currency={costSummary?.currency ?? null} />
          </SurfacePanel>

          <SurfacePanel as="div" id="cost-charts">
            <SectionHeading
              description="Lightweight inline-SVG charts derived from the same retained snapshot — daily spend trend, weekly spend buckets, and a run-rate projection. Hover any point or bar for the underlying value."
              title="Spend at a glance"
            />
            <div className="cost-charts-grid">
              <CostDailyLineChart
                currency={costSummary?.currency ?? null}
                points={costSummary?.recent_daily_costs ?? []}
              />
              <CostWeeklyBarChart
                currency={costSummary?.currency ?? null}
                points={costSummary?.weekly_cost_trend ?? []}
              />
              <CostForecastSparkline
                currency={costSummary?.currency ?? null}
                forecast={costSummary?.forecast ?? null}
                recentDailyCosts={costSummary?.recent_daily_costs ?? []}
              />
            </div>
          </SurfacePanel>

          <SurfacePanel as="div" id="cost-history">
            <SectionHeading
              description="The public route now exposes the retained CSV history and latest JSON snapshot directly when a public API base URL is configured."
              title="Exports"
            />
            <p className="workspace-copy">
              Filters change the on-page view only. CSV history and latest JSON always open the full retained public-safe snapshot.
            </p>
            <div className="hero-actions">
              {csvExportUrl ? (
                <a className="button-link secondary-link" href={csvExportUrl} rel="noreferrer" target="_blank">
                  Open CSV history
                </a>
              ) : null}
              {jsonExportUrl ? (
                <a className="button-link secondary-link" href={jsonExportUrl} rel="noreferrer" target="_blank">
                  Open latest JSON
                </a>
              ) : null}
              <button
                className="button-link secondary-link cost-print-button"
                onClick={() => {
                  if (typeof window !== "undefined") {
                    window.print();
                  }
                }}
                type="button"
              >
                Print snapshot (PDF)
              </button>
            </div>
            <p className="workspace-caption">
              Use your browser's "Save as PDF" destination from the print dialog
              to capture the current filtered view as a single demo-friendly PDF.
            </p>
            {!csvExportUrl && !jsonExportUrl ? (
              <p className="workspace-copy">
                Export links appear automatically once the public cost API base URL is configured for this build.
              </p>
            ) : null}
          </SurfacePanel>
        </SurfaceDrawer>
      </section>
    </PublicSiteLayout>
  );
}
const READ_TIER_UNIT_PRICE_USD_PER_PAGE = 0.0015;
const DEFAULT_PAGES_PER_DOCUMENT = 2;
const DEFAULT_MONTHLY_DOCUMENT_VOLUME = 5000;

function CostScenarioCalculator({ currency }: { currency: string | null }) {
  const [monthlyDocuments, setMonthlyDocuments] = useState(
    DEFAULT_MONTHLY_DOCUMENT_VOLUME,
  );

  const estimatedMonthlyCost =
    monthlyDocuments *
    DEFAULT_PAGES_PER_DOCUMENT *
    READ_TIER_UNIT_PRICE_USD_PER_PAGE;
  const estimatedAnnualCost = estimatedMonthlyCost * 12;
  const estimatedPerDocumentCost =
    DEFAULT_PAGES_PER_DOCUMENT * READ_TIER_UNIT_PRICE_USD_PER_PAGE;

  return (
    <div className="cost-calculator">
      <label className="cost-calculator-control">
        <span className="cost-calculator-label">Monthly document volume</span>
        <input
          aria-label="Monthly document volume"
          className="cost-calculator-slider"
          max={100000}
          min={500}
          onChange={(event) =>
            setMonthlyDocuments(Number.parseInt(event.target.value, 10))
          }
          step={500}
          type="range"
          value={monthlyDocuments}
        />
        <span className="cost-calculator-readout">
          {monthlyDocuments.toLocaleString()} documents / month
        </span>
      </label>
      <dl className="cost-calculator-results">
        <div>
          <dt>Estimated monthly cost</dt>
          <dd>{formatCurrency(estimatedMonthlyCost, currency || "USD")}</dd>
        </div>
        <div>
          <dt>Estimated annual cost</dt>
          <dd>{formatCurrency(estimatedAnnualCost, currency || "USD")}</dd>
        </div>
        <div>
          <dt>Per-document cost</dt>
          <dd>{formatCurrency(estimatedPerDocumentCost, currency || "USD")}</dd>
        </div>
      </dl>
      <p className="workspace-caption">
        Assumes {DEFAULT_PAGES_PER_DOCUMENT} pages / document at the Azure AI
        Document Intelligence Read tier list price of $
        {READ_TIER_UNIT_PRICE_USD_PER_PAGE.toFixed(4)} / page. Excludes
        operator review labor and downstream Azure infra.
      </p>
    </div>
  );
}

const COST_CHART_WIDTH = 320;
const COST_CHART_HEIGHT = 96;
const COST_CHART_PADDING = 6;

function formatChartTickLabel(usageDate: string): string {
  const parsed = new Date(usageDate);
  if (Number.isNaN(parsed.valueOf())) {
    return usageDate;
  }
  return parsed.toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

function CostDailyLineChart({
  currency,
  points,
}: {
  currency: string | null;
  points: PublicCostDailyPoint[];
}) {
  if (points.length === 0) {
    return (
      <p className="workspace-caption">
        Daily spend trend appears once retained history is populated.
      </p>
    );
  }

  const ordered = [...points].sort((left, right) =>
    left.usage_date.localeCompare(right.usage_date),
  );
  const maxAmount = Math.max(...ordered.map((point) => point.amount), 0);
  const stepX =
    ordered.length > 1
      ? (COST_CHART_WIDTH - COST_CHART_PADDING * 2) / (ordered.length - 1)
      : 0;
  const usableHeight = COST_CHART_HEIGHT - COST_CHART_PADDING * 2;
  const coordinates = ordered.map((point, index) => {
    const x = COST_CHART_PADDING + stepX * index;
    const y =
      maxAmount > 0
        ? COST_CHART_PADDING + (1 - point.amount / maxAmount) * usableHeight
        : COST_CHART_HEIGHT - COST_CHART_PADDING;
    return { ...point, x, y };
  });
  const linePath = coordinates
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");
  const areaPath = `${linePath} L ${coordinates[coordinates.length - 1].x} ${
    COST_CHART_HEIGHT - COST_CHART_PADDING
  } L ${coordinates[0].x} ${COST_CHART_HEIGHT - COST_CHART_PADDING} Z`;
  const firstLabel = formatChartTickLabel(coordinates[0].usage_date);
  const lastLabel = formatChartTickLabel(
    coordinates[coordinates.length - 1].usage_date,
  );
  const accessibleSummary = `Daily spend over ${ordered.length} retained days from ${firstLabel} to ${lastLabel}, ranging up to ${formatCurrency(maxAmount, currency || "USD")}.`;

  return (
    <figure className="cost-chart">
      <figcaption className="workspace-caption">
        Daily spend (last {ordered.length} retained days)
      </figcaption>
      <svg
        aria-label={accessibleSummary}
        className="cost-chart-svg"
        preserveAspectRatio="none"
        role="img"
        viewBox={`0 0 ${COST_CHART_WIDTH} ${COST_CHART_HEIGHT}`}
      >
        <path className="cost-chart-area" d={areaPath} />
        <path className="cost-chart-line" d={linePath} />
        {coordinates.map((point) => (
          <circle
            className="cost-chart-dot"
            cx={point.x}
            cy={point.y}
            key={point.usage_date}
            r={1.6}
          >
            <title>
              {formatChartTickLabel(point.usage_date)} ·{" "}
              {formatCurrency(point.amount, currency || "USD")}
            </title>
          </circle>
        ))}
      </svg>
      <p className="cost-chart-axis">
        <span>{firstLabel}</span>
        <span>{lastLabel}</span>
      </p>
    </figure>
  );
}

function CostWeeklyBarChart({
  currency,
  points,
}: {
  currency: string | null;
  points: PublicCostTrendPoint[];
}) {
  if (points.length === 0) {
    return (
      <p className="workspace-caption">
        Weekly bar chart appears once retained weekly trend buckets exist.
      </p>
    );
  }

  const maxAmount = Math.max(...points.map((point) => point.amount), 0);
  const usableWidth = COST_CHART_WIDTH - COST_CHART_PADDING * 2;
  const usableHeight = COST_CHART_HEIGHT - COST_CHART_PADDING * 2;
  const barWidth = Math.max(8, usableWidth / points.length - 4);
  const accessibleSummary = `Weekly cost trend covering ${points.length} buckets, peaking at ${formatCurrency(maxAmount, currency || "USD")}.`;

  return (
    <figure className="cost-chart">
      <figcaption className="workspace-caption">
        Weekly spend buckets
      </figcaption>
      <svg
        aria-label={accessibleSummary}
        className="cost-chart-svg"
        preserveAspectRatio="none"
        role="img"
        viewBox={`0 0 ${COST_CHART_WIDTH} ${COST_CHART_HEIGHT}`}
      >
        {points.map((point, index) => {
          const ratio = maxAmount > 0 ? point.amount / maxAmount : 0;
          const barHeight = Math.max(2, ratio * usableHeight);
          const x =
            COST_CHART_PADDING +
            (usableWidth / points.length) * index +
            (usableWidth / points.length - barWidth) / 2;
          const y = COST_CHART_HEIGHT - COST_CHART_PADDING - barHeight;
          return (
            <rect
              className="cost-chart-bar"
              height={barHeight}
              key={point.label || `${point.period_start}-${index}`}
              rx={1.5}
              ry={1.5}
              width={barWidth}
              x={x}
              y={y}
            >
              <title>
                {point.label} ·{" "}
                {formatCurrency(point.amount, currency || "USD")}
              </title>
            </rect>
          );
        })}
      </svg>
      <p className="cost-chart-axis">
        <span>{points[0]?.label}</span>
        <span>{points[points.length - 1]?.label}</span>
      </p>
    </figure>
  );
}

function CostForecastSparkline({
  currency,
  forecast,
  recentDailyCosts,
}: {
  currency: string | null;
  forecast: PublicCostForecast | null;
  recentDailyCosts: PublicCostDailyPoint[];
}) {
  if (!forecast || recentDailyCosts.length < 2) {
    return (
      <p className="workspace-caption">
        Forecast trend appears once at least two retained daily history points
        and a run-rate forecast are available.
      </p>
    );
  }

  const ordered = [...recentDailyCosts].sort((left, right) =>
    left.usage_date.localeCompare(right.usage_date),
  );
  const projectedSegments = Math.max(forecast.remaining_days_in_period, 1);
  const projectionPoints = Array.from({ length: projectedSegments }, (_, index) => ({
    amount: forecast.trailing_daily_average,
    label: `Projected day ${index + 1}`,
  }));
  const allValues = [
    ...ordered.map((point) => point.amount),
    ...projectionPoints.map((point) => point.amount),
  ];
  const maxAmount = Math.max(...allValues, 0);
  const totalPoints = ordered.length + projectionPoints.length;
  const stepX =
    totalPoints > 1
      ? (COST_CHART_WIDTH - COST_CHART_PADDING * 2) / (totalPoints - 1)
      : 0;
  const usableHeight = COST_CHART_HEIGHT - COST_CHART_PADDING * 2;

  const historicalCoords = ordered.map((point, index) => ({
    x: COST_CHART_PADDING + stepX * index,
    y:
      maxAmount > 0
        ? COST_CHART_PADDING + (1 - point.amount / maxAmount) * usableHeight
        : COST_CHART_HEIGHT - COST_CHART_PADDING,
  }));
  const projectionCoords = projectionPoints.map((point, index) => ({
    x: COST_CHART_PADDING + stepX * (ordered.length + index),
    y:
      maxAmount > 0
        ? COST_CHART_PADDING + (1 - point.amount / maxAmount) * usableHeight
        : COST_CHART_HEIGHT - COST_CHART_PADDING,
  }));
  const historicalPath = historicalCoords
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");
  const projectionPath = [
    `M ${historicalCoords[historicalCoords.length - 1].x} ${historicalCoords[historicalCoords.length - 1].y}`,
    ...projectionCoords.map((point) => `L ${point.x} ${point.y}`),
  ].join(" ");
  const accessibleSummary = `Forecast trend extends ${ordered.length} retained days with ${projectionPoints.length} projected days at the trailing daily average of ${formatCurrency(forecast.trailing_daily_average, currency || "USD")}.`;

  return (
    <figure className="cost-chart">
      <figcaption className="workspace-caption">
        Retained vs. projected (run-rate)
      </figcaption>
      <svg
        aria-label={accessibleSummary}
        className="cost-chart-svg"
        preserveAspectRatio="none"
        role="img"
        viewBox={`0 0 ${COST_CHART_WIDTH} ${COST_CHART_HEIGHT}`}
      >
        <path className="cost-chart-line" d={historicalPath} />
        <path
          className="cost-chart-line cost-chart-line-projected"
          d={projectionPath}
          strokeDasharray="4 3"
        />
      </svg>
      <p className="cost-chart-axis">
        <span>Retained</span>
        <span>{`+${projectionPoints.length}d projection`}</span>
      </p>
    </figure>
  );
}


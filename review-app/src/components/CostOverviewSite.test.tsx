import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CostOverviewSite } from "./CostOverviewSite";

vi.mock("../api/publicTrafficApi", () => ({
  fetchPublicHealth: vi.fn(async () => ({ status: "online", latencyMs: 42 })),
  getPublicTrafficSessionId: () => "cost-session-test",
  recordPublicTrafficEvent: vi.fn(),
}));

vi.mock("../api/publicCostApi", () => ({
  fetchPublicCostSummary: vi.fn(async () => ({
    anomalies: [
      {
        amount: 14.0,
        baseline_amount: 21.4,
        delta_amount: -7.4,
        direction: "drop",
        severity: "high",
        summary: "2026-04-17 landed 35% below the trailing 3-day average.",
        usage_date: "2026-04-17",
      },
      {
        amount: 24.5,
        baseline_amount: 18.25,
        delta_amount: 6.25,
        direction: "spike",
        severity: "medium",
        summary: "2026-04-20 ran 34% above the trailing 3-day average.",
        usage_date: "2026-04-20",
      },
    ],
    collection_mode: "Durable public-safe cost history",
    collection_window:
      "Latest retained snapshot plus 4 persisted CSV history rows, normalized into daily, weekly, and monthly trend slices.",
    currency: "USD",
    daily_cost_trend: [
      {
        amount: 14.0,
        label: "Apr 17",
        period_end: "2026-04-17",
        period_start: "2026-04-17",
      },
      {
        amount: 18.25,
        label: "Apr 18",
        period_end: "2026-04-18",
        period_start: "2026-04-18",
      },
      {
        amount: 22.5,
        label: "Apr 19",
        period_end: "2026-04-19",
        period_start: "2026-04-19",
      },
      {
        amount: 24.5,
        label: "Apr 20",
        period_end: "2026-04-20",
        period_start: "2026-04-20",
      },
    ],
    day_over_day_delta: 4.25,
    forecast: {
      based_on_days: 4,
      projected_additional_cost: 198.125,
      projected_month_end_cost: 382.625,
      remaining_days_in_period: 10,
      trailing_daily_average: 19.8125,
    },
    generated_at_utc: "2026-04-20T17:16:33.262741Z",
    history_row_count: 4,
    history_source: "Retained public cost history",
    month_to_date_cost: 184.5,
    monthly_cost_trend: [
      {
        amount: 126.0,
        label: "Jan 2026",
        period_end: "2026-01-31",
        period_start: "2026-01-01",
      },
      {
        amount: 142.25,
        label: "Feb 2026",
        period_end: "2026-02-28",
        period_start: "2026-02-01",
      },
      {
        amount: 159.5,
        label: "Mar 2026",
        period_end: "2026-03-31",
        period_start: "2026-03-01",
      },
      {
        amount: 184.5,
        label: "Apr 2026",
        period_end: "2026-04-20",
        period_start: "2026-04-01",
      },
    ],
    previous_day_cost: 18.25,
    recent_daily_costs: [
      { amount: 14.0, usage_date: "2026-04-17" },
      { amount: 22.5, usage_date: "2026-04-18" },
      { amount: 24.5, usage_date: "2026-04-19" },
    ],
    today_cost: 24.5,
    top_resource_groups: [{ amount: 82.0, name: "Current platform environment" }],
    top_resources: [{ amount: 57.5, name: "Public API application" }],
    top_service_families: [{ amount: 44.0, name: "Azure AI Services" }],
    week_to_date_cost: 104.75,
    weekly_cost_trend: [
      {
        amount: 96.0,
        label: "Week of Apr 06",
        period_end: "2026-04-12",
        period_start: "2026-04-06",
      },
      {
        amount: 104.75,
        label: "Week of Apr 13",
        period_end: "2026-04-20",
        period_start: "2026-04-13",
      },
    ],
    year_to_date_cost: 612.25,
    yesterday_cost: 22.5,
  })),
  getPublicCostExportUrl: (kind: "csv" | "json") =>
    kind === "csv"
      ? "https://example.com/public-cost-history"
      : "https://example.com/public-cost-latest",
}));

describe("CostOverviewSite", () => {
  it("renders live public-safe cost data and export links", async () => {
    render(<CostOverviewSite />);

    expect(
      screen.getByRole("heading", {
        name: /Public cost dashboard for the document platform/i,
      }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/\$24\.50 today \/ \$184\.50 month/i)).toBeInTheDocument();
    expect(screen.getByText(/Week to date/i)).toBeInTheDocument();
    expect(screen.getByText(/Year to date/i)).toBeInTheDocument();
    expect(screen.getByText(/Projected month end/i)).toBeInTheDocument();
    expect(screen.getAllByText(/\$382\.63/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Moderate confidence/i).length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /Uses 4 retained days to project 10 remaining days, so treat it as a run-rate signal rather than a committed budget/i,
      ).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/2026-04-20 ran 34% above the trailing 3-day average/i)).toBeInTheDocument();
    expect(screen.getByText(/2026-04-17 landed 35% below the trailing 3-day average/i)).toBeInTheDocument();
    expect(screen.getByText(/Retained anomaly history/i, { selector: ".queue-card-label" })).toBeInTheDocument();
    expect(screen.getAllByText(/High drop/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/-\$7\.40/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: /How to read this page/i })).toBeInTheDocument();
    expect(screen.getAllByText(/role-based labels/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Daily spend/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Week of Apr 13/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Recent daily shape/i, { selector: ".queue-card-label" })).toBeInTheDocument();
    expect(screen.getAllByText(/\$612\.25/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Retained public cost history/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Public API application/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Azure AI Services/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Open CSV history/i })).toHaveAttribute(
      "href",
      "https://example.com/public-cost-history",
    );
    expect(screen.getByRole("link", { name: /Open latest JSON/i })).toHaveAttribute(
      "href",
      "https://example.com/public-cost-latest",
    );
  });

  it("filters the visible snapshot without changing the export targets", async () => {
    render(<CostOverviewSite />);

    expect(
      await screen.findByRole("heading", {
        name: /Public cost dashboard for the document platform/i,
      }),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Trend focus/i), {
      target: { value: "daily" },
    });
    expect(screen.getAllByText(/Daily spend/i).length).toBeGreaterThan(0);
    expect(screen.queryAllByText(/Weekly rollup/i).filter(el => el.tagName !== "OPTION").length).toBe(0);
    expect(screen.queryByText(/Monthly rollup/i, { selector: ".queue-card-label" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Contributor focus/i), {
      target: { value: "resources" },
    });
    expect(screen.getByText(/Top resources/i, { selector: ".queue-card-label" })).toBeInTheDocument();
    expect(screen.queryByText(/Top resource groups/i, { selector: ".queue-card-label" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Top service families/i, { selector: ".queue-card-label" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Recent day window/i), {
      target: { value: "2" },
    });
    const recentDaysCard = screen
      .getByText(/Recent daily shape/i, { selector: ".queue-card-label" })
      .closest(".surface-card") as HTMLElement;
    expect(within(recentDaysCard).queryByText("2026-04-17")).not.toBeInTheDocument();
    expect(within(recentDaysCard).getByText("2026-04-18")).toBeInTheDocument();
    expect(within(recentDaysCard).getByText("2026-04-19")).toBeInTheDocument();

    expect(screen.getByText(/Filters change the on-page view only/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open CSV history/i })).toHaveAttribute(
      "href",
      "https://example.com/public-cost-history",
    );
    expect(screen.getByRole("link", { name: /Open latest JSON/i })).toHaveAttribute(
      "href",
      "https://example.com/public-cost-latest",
    );
    expect(screen.getByText(/Contributor names stay generic on purpose/i)).toBeInTheDocument();
    expect(screen.getByText(/Anomaly watch/i, { selector: ".queue-card-label" })).toBeInTheDocument();
    expect(screen.getByText(/Retained anomaly history/i, { selector: ".queue-card-label" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Reset filters/i }));
    expect(screen.getAllByText(/Weekly rollup/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Top service families/i).length).toBeGreaterThan(0);
    expect(within(recentDaysCard).getByText("2026-04-17")).toBeInTheDocument();
  });

  it("renders the cost scenario calculator and updates results when the slider moves", async () => {
    render(<CostOverviewSite />);

    expect(
      await screen.findByRole("heading", {
        name: /What would it cost you\?/i,
      }),
    ).toBeInTheDocument();

    const slider = screen.getByLabelText(/Monthly document volume/i);

    fireEvent.change(slider, { target: { value: "10000" } });

    expect(
      screen.getByText(/10,000 documents \/ month/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Estimated monthly cost/i)).toBeInTheDocument();
    expect(screen.getByText(/Per-document cost/i)).toBeInTheDocument();
  });

  it("invokes window.print when the Print snapshot button is clicked", async () => {
    const printSpy = vi.spyOn(window, "print").mockImplementation(() => undefined);

    render(<CostOverviewSite />);

    const button = await screen.findByRole("button", {
      name: /Print snapshot \(PDF\)/i,
    });

    fireEvent.click(button);

    expect(printSpy).toHaveBeenCalledTimes(1);
    printSpy.mockRestore();
  });

  it("renders the Spend at a glance charts with accessible summaries", async () => {
    render(<CostOverviewSite />);

    expect(
      await screen.findByRole("heading", { name: /Spend at a glance/i }),
    ).toBeInTheDocument();
    const dailyChart = screen.getByLabelText(/Daily spend over .* retained days/i);
    expect(dailyChart.tagName.toLowerCase()).toBe("svg");
    const weeklyChart = screen.getByLabelText(/Weekly cost trend covering/i);
    expect(weeklyChart.tagName.toLowerCase()).toBe("svg");
    expect(
      screen.getByLabelText(/Forecast trend extends/i),
    ).toBeInTheDocument();
  });

  it("mounts cleanly when the URL hash points at an unknown deep-link section", async () => {
    const previousHash = window.location.hash;
    window.location.hash = "#/cost#bogus-section-that-does-not-exist";

    try {
      render(<CostOverviewSite />);

      expect(
        await screen.findByRole("heading", {
          name: /Public cost dashboard for the document platform/i,
        }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: /Spend at a glance/i }),
      ).toBeInTheDocument();
    } finally {
      window.location.hash = previousHash;
    }
  });
});

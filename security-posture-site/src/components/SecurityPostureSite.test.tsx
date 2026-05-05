import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SecurityPostureSite } from "./SecurityPostureSite";

vi.mock("../api/publicTrafficApi", () => ({
  fetchPublicHealth: vi.fn(async () => ({ latencyMs: 12, ok: true, status: "online" })),
  fetchPublicRequestContext: vi.fn(async () => ({
    approximate_location: "US / Ohio",
    client_ip: "203.0.113.77",
    edge_region: "Host region: eastus2",
    enrichment_provider_name: "ipapi.is",
    enrichment_status: "Provider-backed network signals loaded from ipapi.is.",
    forwarded_host: "security.example.test",
    forwarded_proto: "https",
    hosting_provider: "Azure Front Door",
    network_asn: "AS8075",
    network_owner: "Microsoft Corporation",
    public_network_enrichment_enabled: true,
    public_security_globe_enabled: true,
    reputation_summary: "Low observed abuse risk",
    request_id: "req-demo-1234",
    request_timestamp_utc: "2026-05-04T00:00:00Z",
    tls_protocol: "TLSv1.3",
    transport_security: "HTTPS only",
    vpn_proxy_status: null,
  })),
  fetchPublicTrafficMetricsSummary: vi.fn(async () => ({
    availability_percentage: 100,
    availability_source: "External checks",
    availability_window: "Last 7d",
    collection_mode: "Durable aggregate",
    collection_window: "Last 60d",
    current_status: "Healthy",
    current_uptime_seconds: null,
    environment_name: "test",
    generated_at_utc: "2026-05-04T00:00:00Z",
    geography_counts: [{ count: 1, label: "US / Ohio" }],
    last_event_at_utc: "2026-05-04T00:00:00Z",
    latest_alert_configuration_ready: true,
    latest_monitor_name: "monitor",
    last_successful_health_check_at_utc: "2026-05-04T00:00:00Z",
    process_started_at_utc: null,
    recent_activity: [],
    recent_activity_window: "Last 30m",
    recent_health_checks: [],
    route_counts: [{ count: 1, label: "security" }],
    site_mode_counts: [{ count: 1, label: "security" }],
    suppressed_alert_count: 0,
    suppressed_alert_window: "Last 60d",
    total_events: 1,
    traffic_cadence: [],
    traffic_cadence_window: "Last 12h",
    unique_sessions: 1,
  })),
  getPublicTrafficSessionId: vi.fn(() => "session-test"),
  recordPublicTrafficEvent: vi.fn(async () => {}),
}));

describe("SecurityPostureSite", () => {
  it("renders a public-safe security overview", async () => {
    render(<SecurityPostureSite />);

    expect(
      screen.getByRole("heading", {
        name: /Security posture for the Ryan Codes public stack/i,
      }),
    ).toBeInTheDocument();

    expect(await screen.findByText(/Request id: req-demo-1234/i)).toBeInTheDocument();
    expect(await screen.findByText(/Total events: 1/i)).toBeInTheDocument();
    expect(await screen.findByText(/Top route: security/i)).toBeInTheDocument();
  });
});

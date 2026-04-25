import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PublicLandingShell } from "./PublicLandingShell";

vi.mock("../api/publicTrafficApi", () => ({
  fetchPublicHealth: vi.fn(async () => ({
    checkedAtUtc: new Date().toISOString(),
    latencyMs: 42,
    ok: true,
    status: "online",
  })),
  getPublicTrafficSessionId: () => "landing-session-test",
  recordPublicTrafficEvent: vi.fn(),
}));

describe("PublicLandingShell", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    window.history.replaceState({}, "", "/");
  });

  it("renders a public briefing with direct route entry points and a secondary demo route", () => {
    render(<PublicLandingShell />);

    expect(
      screen.getByRole("heading", {
        name: /Messy inbound documents, review-ready work in seconds/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /Direct route entry points/i }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: /Explore demo route/i }).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole("link", { name: /Open protected host/i }),
    ).toHaveAttribute("href", "https://admin.ryancodes.online/admin");

    fireEvent.click(screen.getAllByRole("link", { name: /Open security route/i })[0]);

    expect(window.location.pathname).toBe("/security");
  });

  it("uses a configured public contact email for the demo request CTA", () => {
    vi.stubEnv("VITE_PUBLIC_CONTACT_EMAIL", "demo@example.com");

    render(<PublicLandingShell />);

    const demoRequestLink = screen.getByRole("link", {
      name: /Request demo briefing/i,
    });

    expect(demoRequestLink.getAttribute("href")).toContain(
      "mailto:demo@example.com",
    );
    expect(
      screen.queryByText(/Set VITE_PUBLIC_CONTACT_EMAIL before deployment/i),
    ).not.toBeInTheDocument();
  });

  it("renders deep-link sub-anchors for security and cost route cards", () => {
    render(<PublicLandingShell />);

    const securityDeepLink = screen.getByRole("link", { name: /Standards mapping/i });
    expect(securityDeepLink).toHaveAttribute("href", "/security#security-standards");

    const costDeepLink = screen.getByRole("link", { name: /Anomalies & forecast/i });
    expect(costDeepLink).toHaveAttribute("href", "/cost#cost-anomalies");

    fireEvent.click(securityDeepLink);
    expect(window.location.pathname).toBe("/security");
    expect(window.location.hash).toBe("#security-standards");
  });
});
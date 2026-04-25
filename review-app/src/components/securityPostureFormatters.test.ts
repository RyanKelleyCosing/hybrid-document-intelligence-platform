import { afterEach, describe, expect, it, vi } from "vitest";

import {
  formatAlertReadiness,
  formatCountLabel,
  formatMonitorFreshness,
  formatProviderFieldValue,
  formatRelativeAgeFromIso,
  formatRelativeAgeLabel,
  formatSlugLabel,
  formatUtcDateTimeLabel,
  parseFeatureFlag,
} from "./securityPostureFormatters";

describe("securityPostureFormatters", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("formatCountLabel uses the singular label only when value is exactly one", () => {
    expect(formatCountLabel(1, "minute", "minutes")).toBe("1 minute");
    expect(formatCountLabel(0, "minute", "minutes")).toBe("0 minutes");
    expect(formatCountLabel(7, "minute", "minutes")).toBe("7 minutes");
  });

  it("formatRelativeAgeLabel collapses by minute, hour, and day buckets", () => {
    expect(formatRelativeAgeLabel(0)).toBe("just now");
    expect(formatRelativeAgeLabel(-5)).toBe("just now");
    expect(formatRelativeAgeLabel(45)).toBe("45 minutes ago");
    expect(formatRelativeAgeLabel(60)).toBe("1 hour ago");
    expect(formatRelativeAgeLabel(60 * 24 * 3)).toBe("3 days ago");
  });

  it("parseFeatureFlag respects truthy / falsy strings and falls back to the default", () => {
    expect(parseFeatureFlag(undefined, true)).toBe(true);
    expect(parseFeatureFlag(undefined, false)).toBe(false);
    expect(parseFeatureFlag("0", true)).toBe(false);
    expect(parseFeatureFlag("False", true)).toBe(false);
    expect(parseFeatureFlag("on", false)).toBe(true);
  });

  it("formatSlugLabel title-cases dash and underscore separated segments", () => {
    expect(formatSlugLabel("trust-boundary")).toBe("Trust Boundary");
    expect(formatSlugLabel("alert_readiness")).toBe("Alert Readiness");
    expect(formatSlugLabel("")).toBe("");
  });

  it("formatUtcDateTimeLabel renders a stable UTC string and falls back on bad input", () => {
    expect(formatUtcDateTimeLabel("2026-04-23T12:34:00Z")).toContain("2026");
    expect(formatUtcDateTimeLabel("not-a-date")).toBe("not-a-date");
  });

  it("formatRelativeAgeFromIso uses the frozen clock", () => {
    vi.spyOn(Date, "now").mockReturnValue(
      new Date("2026-04-23T12:30:00Z").valueOf(),
    );
    expect(formatRelativeAgeFromIso("2026-04-23T12:00:00Z")).toBe("30 minutes ago");
    expect(formatRelativeAgeFromIso("not-a-date")).toBe("not-a-date");
  });

  it("formatAlertReadiness reflects the persisted SMTP readiness flag", () => {
    expect(formatAlertReadiness(null)).toContain("Unknown");
    expect(
      formatAlertReadiness({ latest_alert_configuration_ready: true } as never),
    ).toContain("Ready");
    expect(
      formatAlertReadiness({ latest_alert_configuration_ready: false } as never),
    ).toContain("incomplete");
  });

  it("formatMonitorFreshness labels Current, Delayed, and Stale buckets", () => {
    vi.spyOn(Date, "now").mockReturnValue(
      new Date("2026-04-23T12:30:00Z").valueOf(),
    );
    const buildSummary = (checkedAtUtc: string) =>
      ({
        recent_health_checks: [{ checked_at_utc: checkedAtUtc }],
        last_successful_health_check_at_utc: checkedAtUtc,
      }) as never;

    expect(formatMonitorFreshness(buildSummary("2026-04-23T12:00:00Z"))).toContain(
      "Current",
    );
    expect(formatMonitorFreshness(buildSummary("2026-04-23T11:00:00Z"))).toContain(
      "Delayed",
    );
    expect(formatMonitorFreshness(buildSummary("2026-04-23T08:00:00Z"))).toContain(
      "Stale",
    );
    expect(formatMonitorFreshness(null)).toContain("No external health checks");
  });

  it("formatProviderFieldValue prefers the explicit value, then enrichment status, then the public fallback copy", () => {
    expect(formatProviderFieldValue("Comcast", null)).toBe("Comcast");
    expect(formatProviderFieldValue(null, null)).toContain(
      "isolated request-context",
    );
    expect(
      formatProviderFieldValue(null, {
        enrichment_status: "Cached value still warm",
      } as never),
    ).toBe("Cached value still warm");
  });
});

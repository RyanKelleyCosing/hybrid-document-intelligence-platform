/**
 * Pure presentation helpers shared by SecurityPostureSite and its sibling
 * surfaces. Extracted out of SecurityPostureSite.tsx so the component file
 * stays focused on rendering and effects.
 *
 * All functions here are deterministic and side-effect free aside from
 * `formatRelativeAgeFromIso` and `formatMonitorFreshness` which read
 * `Date.now()` on call. Tests freeze `Date.now` via `vi.spyOn`.
 */

import type {
  PublicRequestContextPayload,
  PublicTrafficMetricsSummary,
} from "../api/publicTrafficApi";

export function formatCountLabel(
  value: number,
  singularLabel: string,
  pluralLabel: string,
): string {
  return `${value} ${value === 1 ? singularLabel : pluralLabel}`;
}

export function formatRelativeAgeLabel(totalMinutes: number): string {
  if (totalMinutes <= 0) {
    return "just now";
  }

  if (totalMinutes < 60) {
    return formatCountLabel(totalMinutes, "minute", "minutes") + " ago";
  }

  const totalHours = Math.round(totalMinutes / 60);
  if (totalHours < 48) {
    return formatCountLabel(totalHours, "hour", "hours") + " ago";
  }

  const totalDays = Math.round(totalHours / 24);
  return formatCountLabel(totalDays, "day", "days") + " ago";
}

export function formatMonitorFreshness(
  summary: PublicTrafficMetricsSummary | null,
): string {
  const latestCheckAtUtc =
    summary?.recent_health_checks[0]?.checked_at_utc ||
    summary?.last_successful_health_check_at_utc;

  if (!latestCheckAtUtc) {
    return "No external health checks have been recorded yet.";
  }

  const checkedAt = new Date(latestCheckAtUtc);
  if (Number.isNaN(checkedAt.valueOf())) {
    return "Latest health-check timestamp is unavailable.";
  }

  const elapsedMinutes = Math.max(
    0,
    Math.round((Date.now() - checkedAt.valueOf()) / 60000),
  );
  const freshnessLabel =
    elapsedMinutes <= 45 ? "Current" : elapsedMinutes <= 90 ? "Delayed" : "Stale";

  return `${freshnessLabel} · checked ${formatRelativeAgeLabel(elapsedMinutes)}`;
}

export function formatAlertReadiness(
  summary: PublicTrafficMetricsSummary | null,
): string {
  if (!summary || summary.latest_alert_configuration_ready == null) {
    return "Unknown until a persisted external verifier run reports SMTP readiness.";
  }

  return summary.latest_alert_configuration_ready
    ? "Ready for explicit alert-delivery checks"
    : "SMTP configuration incomplete";
}

export function formatProviderFieldValue(
  value: string | null | undefined,
  requestContext: PublicRequestContextPayload | null,
): string {
  if (value) {
    return value;
  }

  if (!requestContext) {
    return "Provider-backed enrichment appears when the isolated request-context API responds.";
  }

  return requestContext.enrichment_status;
}

export function parseFeatureFlag(
  value: string | undefined,
  defaultValue: boolean,
): boolean {
  if (value == null) {
    return defaultValue;
  }

  return !["0", "false", "no", "off"].includes(value.trim().toLowerCase());
}

export function formatUtcDateTimeLabel(value: string): string {
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

export function formatRelativeAgeFromIso(value: string): string {
  const parsedValue = new Date(value);
  if (Number.isNaN(parsedValue.valueOf())) {
    return value;
  }

  const elapsedMinutes = Math.max(
    0,
    Math.round((Date.now() - parsedValue.valueOf()) / 60000),
  );
  return formatRelativeAgeLabel(elapsedMinutes);
}

export function formatSlugLabel(value: string): string {
  if (!value.trim()) {
    return value;
  }

  return value
    .split(/[-_]/)
    .filter(Boolean)
    .map((segment) => `${segment.charAt(0).toUpperCase()}${segment.slice(1)}`)
    .join(" ");
}

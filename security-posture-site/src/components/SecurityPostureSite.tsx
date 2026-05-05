import { useEffect, useState } from "react";

import {
  fetchPublicHealth,
  fetchPublicRequestContext,
  fetchPublicTrafficMetricsSummary,
  type PublicHealthStatus,
  type PublicRequestContextPayload,
  type PublicTrafficMetricsSummary,
} from "../api/publicTrafficApi";
import { securityHeroHighlights } from "../data/securitySiteContent";

type LoadState = "error" | "idle" | "loading" | "ready";

export function SecurityPostureSite() {
  const [context, setContext] = useState<PublicRequestContextPayload | null>(null);
  const [metrics, setMetrics] = useState<PublicTrafficMetricsSummary | null>(null);
  const [health, setHealth] = useState<PublicHealthStatus | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");

  useEffect(() => {
    let isMounted = true;

    async function load() {
      setLoadState("loading");
      try {
        const [nextContext, nextMetrics, nextHealth] = await Promise.all([
          fetchPublicRequestContext(),
          fetchPublicTrafficMetricsSummary(),
          fetchPublicHealth(),
        ]);
        if (!isMounted) {
          return;
        }

        setContext(nextContext);
        setMetrics(nextMetrics);
        setHealth(nextHealth);
        setLoadState("ready");
      } catch {
        if (!isMounted) {
          return;
        }
        setLoadState("error");
      }
    }

    void load();
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <main className="public-security-site" aria-label="Security posture">
      <header>
        <p>Public security briefing</p>
        <h1>Security posture for the Ryan Codes public stack</h1>
        <p>
          Public-safe telemetry, monitored availability, and request context for
          architecture walkthroughs.
        </p>
      </header>

      <section aria-label="Highlights">
        <h2>What this demonstrates</h2>
        <ul>
          {securityHeroHighlights.map((item, index) => (
            <li key={`${index}-${item}`}>
              {item}
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Live visitor trace">
        <h2>Live visitor trace</h2>
        <p>Load state: {loadState}</p>
        <p>Status: {health?.status ?? "unknown"}</p>
        <p>Request id: {context?.request_id ?? "pending"}</p>
        <p>Client IP: {context?.client_ip ?? "not available"}</p>
        <p>ASN: {context?.network_asn ?? "not available"}</p>
      </section>

      <section aria-label="Recent activity and cadence">
        <h2>Recent activity and cadence</h2>
        <p>Total events: {metrics?.total_events ?? 0}</p>
        <p>Unique sessions: {metrics?.unique_sessions ?? 0}</p>
        <p>Top route: {metrics?.route_counts?.[0]?.label ?? "n/a"}</p>
      </section>
    </main>
  );
}

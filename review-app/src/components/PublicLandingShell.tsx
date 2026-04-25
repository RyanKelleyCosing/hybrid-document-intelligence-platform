import { useEffect, useMemo, useState } from "react";

import {
  COST_PATH,
  DEMO_PATH,
  SECURITY_PATH,
  getAdminNavigationTarget,
  navigateToAppPath,
} from "../appRoutes";
import {
  fetchPublicHealth,
  getPublicTrafficSessionId,
  recordPublicTrafficEvent,
  type PublicHealthStatus,
} from "../api/publicTrafficApi";
import { PublicSiteLayout } from "./PublicSiteLayout";
import {
  SectionHeading,
  StatusBadge,
  SurfaceDrawer,
  SurfaceMetricCard,
  SurfacePanel,
  type StatusBadgeTone,
} from "./SurfacePrimitives";

type FeatureSummary = {
  copy: string;
  eyebrow: string;
  title: string;
  links?: { href: string; label: string }[];
};

type ProductProofPoint = {
  badge: string;
  detail: string;
  eyebrow: string;
  title: string;
  tone: StatusBadgeTone;
  value: string;
};

type RouteEntry = {
  actionLabel: string;
  copy: string;
  deepLinks?: ReadonlyArray<{ label: string; hash: string }>;
  eyebrow: string;
  href: string;
  isExternal: boolean;
  title: string;
  tone: StatusBadgeTone;
};

type ContactOption = {
  href: string;
  label: string;
  note: string;
  opensInNewTab?: boolean;
};

type EngagementTrack = {
  detail: string;
  label: string;
};

const defaultGithubUrl = "https://github.com/RyanKelleyCosing";
const featureSummaries: FeatureSummary[] = [
  {
    copy:
      "Inbound packets can be staged from scans, portals, SFTP drops, and partner flows without splitting the product into disconnected demos.",
    eyebrow: "Intake backbone",
    links: [{ href: DEMO_PATH, label: "Walk through the workflow" }],
    title: "One workflow from raw documents to operator-ready work",
  },
  {
    copy:
      "Classification, OCR, extraction, matching, recommendations, and audit all stay in the same Azure-first stack instead of becoming isolated proof-of-concept pages.",
    eyebrow: "Shared system",
    links: [{ href: DEMO_PATH, label: "See the stack in motion" }],
    title: "Functions, AI services, React, and IaC stay wired together",
  },
  {
    copy:
      "The public routes stay informational and public-safe, while the Microsoft-authenticated live admin host remains the real queue, review, and workspace surface.",
    eyebrow: "Route boundary",
    title: "Public briefing outside, protected operator work inside",
  },
  {
    copy:
      "Security and cost routes expose trust-boundary and spend evidence directly so the homepage does not need to carry the full walkthrough narrative itself.",
    eyebrow: "Public-safe proof",
    links: [
      { href: SECURITY_PATH, label: "Open security route" },
      { href: COST_PATH, label: "Open cost route" },
    ],
    title: "Deep proof moves into dedicated public routes",
  },
];

const productProofPoints: ProductProofPoint[] = [
  {
    badge: "Operational baseline",
    detail:
      "Portal uploads, email-style intake, SFTP-style feeds, and scanned documents are framed as one product surface instead of four mini-demos.",
    eyebrow: "4 intake lanes",
    title: "Multiple inbound channels, one operator workflow",
    tone: "accent",
    value: "4 lanes",
  },
  {
    badge: "Public-safe proof",
    detail:
      "Security and cost each have their own route, so the homepage can stay concise while still sending reviewers directly to live public-safe evidence.",
    eyebrow: "2 public proof routes",
    title: "Security and cost move out of the hero and into dedicated pages",
    tone: "success",
    value: "2 routes",
  },
  {
    badge: "Protected operator path",
    detail:
      "The public shell points toward the live admin host without pretending that the walkthrough is the production operator experience.",
    eyebrow: "1 authenticated host",
    title: "Live admin stays separate and real",
    tone: "neutral",
    value: "1 host",
  },
];

const engagementTracks: EngagementTrack[] = [
  {
    detail:
      "Start with the public overview, trust-boundary review, and cost route before spending time on the operator shell.",
    label: "Public evaluation",
  },
  {
    detail:
      "Use the demo route when you need the narrative flow from intake through review without crossing into the protected operator host.",
    label: "Workflow walkthrough",
  },
  {
    detail:
      "Move to the live admin host only when you are ready to inspect the real queue, packet workspace, and review interactions.",
    label: "Protected live walkthrough",
  },
];

const coreStack = [
  "Azure Functions",
  "Document Intelligence",
  "Azure OpenAI",
  "Cosmos DB",
  "React + Vite",
  "Bicep",
];

function buildDemoRequestHref(contactEmail: string) {
  const subject = encodeURIComponent(
    "Hybrid Document Intelligence demo request",
  );
  const body = encodeURIComponent(
    "Hi Ryan,\n\nI want a short briefing on the Hybrid Document Intelligence platform.\n\nI am most interested in:\n- Public product overview\n- Security route\n- Cost route\n- Live admin walkthrough\n\nThanks,\n",
  );

  return `mailto:${contactEmail}?subject=${subject}&body=${body}`;
}

export function PublicLandingShell() {
  const [trafficSessionId] = useState(() => getPublicTrafficSessionId());
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
      import.meta.env.VITE_PUBLIC_HEALTH_POLL_MS ?? "",
      10,
    );
    const pollMs = Number.isFinite(rawPollMs) && rawPollMs > 0 ? rawPollMs : 60_000;
    if (pollMs === 0) {
      return () => {
        isCancelled = true;
      };
    }
    const intervalId = window.setInterval(probeHealth, pollMs);

    return () => {
      isCancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const navigateTo = (nextPath: string) => {
    navigateToAppPath(nextPath);
  };

  const githubUrl =
    import.meta.env.VITE_PUBLIC_GITHUB_URL?.trim() || defaultGithubUrl;
  const contactEmail = import.meta.env.VITE_PUBLIC_CONTACT_EMAIL?.trim() || "";
  const linkedinUrl = import.meta.env.VITE_PUBLIC_LINKEDIN_URL?.trim() || "";
  const adminNavigationTarget = getAdminNavigationTarget(window.location.origin);
  const demoRequestHref = contactEmail
    ? buildDemoRequestHref(contactEmail)
    : githubUrl;
  const demoRequestLabel = contactEmail
    ? "Request demo briefing"
    : "Review source and contact context";
  const demoRequestNote = contactEmail
    ? `${contactEmail} handles public briefing follow-up and live walkthrough requests.`
    : "Set VITE_PUBLIC_CONTACT_EMAIL before deployment to enable direct public demo requests.";

  const routeEntries = useMemo<RouteEntry[]>(
    () => [
      {
        actionLabel: "Open security route",
        copy:
          "Inspect the public-safe telemetry story, trust boundary, and retention model without reading the walkthrough copy first.",
        deepLinks: [
          { label: "Live visitor trace", hash: "security-transparency" },
          { label: "Activity & cadence", hash: "security-cadence" },
          { label: "CVE & MSRC feeds", hash: "security-feeds" },
          { label: "Standards mapping", hash: "security-standards" },
          { label: "Security FAQ", hash: "security-faq" },
        ],
        eyebrow: "Trust boundary",
        href: SECURITY_PATH,
        isExternal: false,
        title: "Security",
        tone: "accent",
      },
      {
        actionLabel: "Open cost route",
        copy:
          "Go straight to the public cost dashboard for real spend, trend, anomaly, and forecast evidence instead of a static summary.",
        deepLinks: [
          { label: "Snapshot", hash: "cost-snapshot" },
          { label: "Trend rollups", hash: "cost-trend" },
          { label: "Anomalies & forecast", hash: "cost-anomalies" },
          { label: "History export", hash: "cost-history" },
        ],
        eyebrow: "Spend visibility",
        href: COST_PATH,
        isExternal: false,
        title: "Cost",
        tone: "success",
      },
      {
        actionLabel: "Explore demo route",
        copy:
          "Use the walkthrough only when you want the packet narrative. It stays public-safe and secondary to the public product briefing.",
        eyebrow: "Secondary walkthrough",
        href: DEMO_PATH,
        isExternal: false,
        title: "Demo",
        tone: "warning",
      },
      {
        actionLabel: adminNavigationTarget.isExternal
          ? "Open protected host"
          : "Open live admin route",
        copy:
          "The live admin host remains the real queue and review surface. It is presented here as context, not as another public showcase page.",
        eyebrow: "Protected operator path",
        href: adminNavigationTarget.href,
        isExternal: adminNavigationTarget.isExternal,
        title: "Live Admin",
        tone: "neutral",
      },
    ],
    [adminNavigationTarget.href, adminNavigationTarget.isExternal],
  );

  const contactOptions = useMemo<ContactOption[]>(() => {
    const options: ContactOption[] = [];

    if (contactEmail) {
      options.push({
        href: demoRequestHref,
        label: "Email demo request",
        note: "Use the public route first, then request a live operator walkthrough or technical briefing.",
      });
    }

    options.push({
      href: githubUrl,
      label: "GitHub",
      note: "Source repos, implementation choices, and public technical context.",
      opensInNewTab: true,
    });

    if (linkedinUrl) {
      options.push({
        href: linkedinUrl,
        label: "LinkedIn",
        note: "Background, role history, and another public outreach path.",
        opensInNewTab: true,
      });
    }

    return options;
  }, [contactEmail, demoRequestHref, githubUrl, linkedinUrl]);

  useEffect(() => {
    void recordPublicTrafficEvent({
      event_type: "page_view",
      page_title: "Public product briefing",
      referrer: document.referrer || undefined,
      route: "home",
      session_id: trafficSessionId,
      site_mode: "simulation",
    });
  }, [trafficSessionId]);

  return (
    <PublicSiteLayout activeRoute="home">
      <header className="hero hero-wide public-hero public-briefing-hero">
        <div className="public-hero-copy public-briefing-copy">
          <StatusBadge tone="accent">Public informational route</StatusBadge>
          <p className="eyebrow">Operational document intelligence</p>
          <h1>Messy inbound documents, review-ready work in seconds.</h1>
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
            Hybrid Document Intelligence turns messy inbound document packets into
            review-ready work through classification, OCR, extraction, matching,
            recommendations, and protected operator review. The homepage now stays
            focused on product framing, public-safe proof, and the right next route.
          </p>
          <ol className="landing-howitworks" aria-label="how it works">
            <li>
              <span className="landing-howitworks-step">01</span>
              <strong>Ingest</strong>
              <span>Multi-format inbound packets land on the public route without exposing the operator host.</span>
            </li>
            <li>
              <span className="landing-howitworks-step">02</span>
              <strong>Understand</strong>
              <span>Classification, OCR, extraction, and matching turn raw pages into structured signals.</span>
            </li>
            <li>
              <span className="landing-howitworks-step">03</span>
              <strong>Route</strong>
              <span>Recommendations hand off to the protected operator review so decisions stay audited.</span>
            </li>
          </ol>
          <div className="hero-actions">
            <a
              className="button-link"
              href={demoRequestHref}
              rel={contactEmail ? undefined : "noreferrer"}
              target={contactEmail ? undefined : "_blank"}
            >
              {demoRequestLabel}
            </a>
            <a
              className="button-link secondary-link"
              href={SECURITY_PATH}
              onClick={(event) => {
                event.preventDefault();
                navigateTo(SECURITY_PATH);
              }}
            >
              Open security route
            </a>
            <a
              className="button-link secondary-link"
              href={COST_PATH}
              onClick={(event) => {
                event.preventDefault();
                navigateTo(COST_PATH);
              }}
            >
              Open cost route
            </a>
            <a
              className="button-link secondary-link"
              href={DEMO_PATH}
              onClick={(event) => {
                event.preventDefault();
                navigateTo(DEMO_PATH);
              }}
            >
              Explore demo route
            </a>
          </div>
          <ul className="chip-list public-chip-list" aria-label="public site boundaries">
            <li className="reason-chip">Public briefing first</li>
            <li className="reason-chip">Security and cost stay live</li>
            <li className="reason-chip">Demo stays secondary</li>
            <li className="reason-chip">Live admin stays protected</li>
            <li className="reason-chip">Shared Azure and React system</li>
          </ul>
        </div>

        <SurfaceDrawer as="aside" className="public-briefing-drawer">
          <SectionHeading
            description="Use the public route to understand the system shape, the trust boundary, and the evidence routes before deciding whether the protected operator walkthrough is the right next step."
            title="Start with the right surface"
          />
          <div className="public-briefing-drawer-grid">
            <SurfaceMetricCard
              badge={<StatusBadge tone="accent">Public briefing</StatusBadge>}
              detail="Product framing, trust boundary, and route entry points stay on the homepage."
              eyebrow="Overview"
              title="Do the short briefing first"
              value="Brief first"
            />
            <SurfaceMetricCard
              badge={<StatusBadge tone="warning">Secondary demo</StatusBadge>}
              detail="The workflow walkthrough stays available, but it is no longer the default first impression."
              eyebrow="Demo"
              title="Use the walkthrough only when you need the narrative"
              value="Demo later"
            />
            <SurfaceMetricCard
              badge={<StatusBadge tone="neutral">Protected host</StatusBadge>}
              detail="Queue, packet workspace, and live review actions remain on the authenticated admin host."
              eyebrow="Live admin"
              title="Keep the real operator path separate"
              value="Protected"
            />
          </div>
          <p className="surface-panel-copy public-cta-note">{demoRequestNote}</p>
          <ul className="chip-list stack-chip-list" aria-label="core technology stack">
            {coreStack.map((item) => (
              <li className="reason-chip" key={item}>
                {item}
              </li>
            ))}
          </ul>
        </SurfaceDrawer>
      </header>

      <section className="public-proof-grid" aria-label="product proof points">
        {productProofPoints.map((proofPoint) => (
          <SurfaceMetricCard
            badge={<StatusBadge tone={proofPoint.tone}>{proofPoint.badge}</StatusBadge>}
            detail={proofPoint.detail}
            eyebrow={proofPoint.eyebrow}
            key={proofPoint.title}
            title={proofPoint.title}
            value={proofPoint.value}
          />
        ))}
      </section>

      <section className="workbench-layout public-layout public-home-layout">
        <div className="queue-column simulation-main public-main section-stack">
          <SurfacePanel>
            <SectionHeading
              description="The homepage now stays lighter than the walkthrough while still explaining what the product is, how it is structured, and why the public-safe routes exist."
              title="What the product actually covers"
            />
            <div className="public-feature-grid">
              {featureSummaries.map((summary) => (
                <SurfacePanel as="article" className="public-feature-card" key={summary.title}>
                  <p className="queue-card-label">{summary.eyebrow}</p>
                  <h3>{summary.title}</h3>
                  <p className="mini-card-copy">{summary.copy}</p>
                  {summary.links && summary.links.length > 0 ? (
                    <div className="public-feature-card-links">
                      {summary.links.map((link) => (
                        <a
                          className="button-link secondary-link"
                          href={link.href}
                          key={link.href}
                          onClick={(event) => {
                            event.preventDefault();
                            navigateTo(link.href);
                          }}
                        >
                          {link.label}
                        </a>
                      ))}
                    </div>
                  ) : null}
                </SurfacePanel>
              ))}
            </div>
          </SurfacePanel>

          <SurfacePanel>
            <SectionHeading
              description="Jump directly into the public security or cost routes, keep the walkthrough secondary, and surface the live admin host as the real protected operator path."
              title="Direct route entry points"
            />
            <div className="public-route-entry-grid">
              {routeEntries.map((entry) => (
                <SurfacePanel as="article" className="public-route-card" key={entry.title}>
                  <div className="public-route-card-header">
                    <div>
                      <p className="queue-card-label">{entry.eyebrow}</p>
                      <h3>{entry.title}</h3>
                    </div>
                    <StatusBadge tone={entry.tone}>
                      {entry.isExternal ? "Protected host" : "Public route"}
                    </StatusBadge>
                  </div>
                  <p className="mini-card-copy">{entry.copy}</p>
                  <a
                    className="button-link secondary-link public-route-link"
                    href={entry.href}
                    onClick={(event) => {
                      if (!entry.isExternal) {
                        event.preventDefault();
                        navigateTo(entry.href);
                      }
                    }}
                  >
                    {entry.actionLabel}
                  </a>
                  {entry.deepLinks && entry.deepLinks.length > 0 ? (
                    <ul className="public-route-deep-links" aria-label={`${entry.title} sections`}>
                      {entry.deepLinks.map((link) => {
                        const deepHref = `${entry.href}#${link.hash}`;
                        return (
                          <li key={link.hash}>
                            <a
                              className="public-route-deep-link"
                              href={deepHref}
                              onClick={(event) => {
                                if (!entry.isExternal) {
                                  event.preventDefault();
                                  navigateTo(deepHref);
                                }
                              }}
                            >
                              {link.label}
                            </a>
                          </li>
                        );
                      })}
                    </ul>
                  ) : null}
                </SurfacePanel>
              ))}
            </div>
          </SurfacePanel>
        </div>

        <SurfaceDrawer as="aside" className="public-engagement-drawer">
          <SectionHeading
            description="Use the homepage to decide whether you need a quick architecture review, a guided walkthrough, or a protected live-admin session."
            title="Engagement paths"
          />
          <div className="public-engagement-list">
            {engagementTracks.map((track) => (
              <div className="public-engagement-row" key={track.label}>
                <strong>{track.label}</strong>
                <p className="surface-panel-copy">{track.detail}</p>
              </div>
            ))}
          </div>

          <div className="profile-link-list">
            {contactOptions.map((option) => (
              <a
                className="profile-link-card"
                href={option.href}
                key={option.label}
                rel={option.opensInNewTab ? "noreferrer" : undefined}
                target={option.opensInNewTab ? "_blank" : undefined}
              >
                <strong>{option.label}</strong>
                <p>{option.note}</p>
              </a>
            ))}
          </div>

          {!linkedinUrl ? (
            <p className="metric-detail">
              Add VITE_PUBLIC_LINKEDIN_URL before deployment to expose a second public contact path.
            </p>
          ) : null}
        </SurfaceDrawer>
      </section>
    </PublicSiteLayout>
  );
}
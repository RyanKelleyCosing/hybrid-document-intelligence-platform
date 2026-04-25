import { useEffect, useMemo, useState } from "react";

import {
  HOME_PATH,
  getDemoPath,
  getSimulationRouteFromLocation,
  navigateToAppPath,
} from "../appRoutes";
import {
  getPublicTrafficSessionId,
  recordPublicTrafficEvent,
} from "../api/publicTrafficApi";
import { PublicSiteLayout } from "./PublicSiteLayout";
import { listSimulationReviewItems } from "../api/simulationReviewApi";
import type { ReviewQueueItem } from "../api/reviewApi";
import {
  simulationAccountDocuments,
  simulationAccountSummary,
  simulationCards,
  simulationIntroRules,
  simulationPackets,
  simulationProcessingStages,
  simulationRouteOrder,
  simulationSourceMonitors,
  simulationStackLayers,
  simulationViews,
  type SimulationRoute,
} from "../data/simulationData";
import { QueueCard } from "./QueueCard";
import {
  SectionHeading,
  StatusBadge,
  SurfaceCard,
  SurfaceDrawer,
  SurfacePanel,
  SurfaceTimelineItem,
  type StatusBadgeTone,
} from "./SurfacePrimitives";

const simulationStorageKey = "docint-simulation-started";

function formatLabel(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function buildMetrics(route: SimulationRoute, reviewItems: ReviewQueueItem[]) {
  if (route === "ops") {
    return [
      {
        detail: "Cost, incidents, DR, and pipeline posture.",
        label: "Showcase panels",
        value: "4",
      },
      {
        detail: "Public mode never reaches backend services.",
        label: "Live dependencies",
        value: "0",
      },
      {
        detail: "Ops panels stay narrative and safe for HR.",
        label: "Signal story",
        value: "AI triage",
      },
    ];
  }

  if (route === "libraries") {
    return [
      {
        detail: "Reusable modules and governance guardrails.",
        label: "Library tracks",
        value: "2",
      },
      {
        detail: "Catalog pages explain reuse without deploying anything.",
        label: "Sample compositions",
        value: "5",
      },
      {
        detail: "No infrastructure actions run from the public site.",
        label: "Portfolio posture",
        value: "Read-only",
      },
    ];
  }

  if (route === "accounts") {
    return [
      {
        detail: "Synthetic packet artifacts already linked to the account timeline.",
        label: "Linked documents",
        value: String(simulationAccountDocuments.length),
      },
      {
        detail: "The sample account keeps its preflight and reuse signals visible.",
        label: "Preflight signals",
        value: String(simulationAccountSummary.preflightSignals.length),
      },
      {
        detail: "This is the handoff point from queue review into protected account drill-down.",
        label: "Match posture",
        value: simulationAccountSummary.matchConfidence,
      },
    ];
  }

  const profileCount = new Set(
    reviewItems.map((item) => item.prompt_profile.primary_profile_id),
  ).size;
  const averageConfidence =
    reviewItems.length === 0
      ? 0
      : Math.round(
          (reviewItems.reduce(
            (total, item) => total + item.average_confidence,
            0,
          ) /
            reviewItems.length) *
            100,
        );

  return [
    {
      detail: "SFTP, secure upload, email intake, and partner feeds stay visible as watched production-like channels.",
      label: "Watched inputs",
      value: String(simulationSourceMonitors.length),
    },
    {
      detail: `${simulationPackets.length} synthetic packets are already staged into the walkthrough with source lineage attached.`,
      label: "Loaded packets",
      value: String(simulationPackets.length),
    },
    {
      detail: `${simulationStackLayers.length} stack layers explain the services behind routing, extraction, review, and deployment.`,
      label: route === "review" ? "Average confidence" : "Platform layers",
      value: route === "review" ? `${averageConfidence}%` : String(simulationStackLayers.length),
    },
  ];
}

function getProcessingStateTone(
  state: (typeof simulationProcessingStages)[number]["state"],
): StatusBadgeTone {
  switch (state) {
    case "complete":
      return "success";
    case "active":
      return "accent";
    case "queued":
    default:
      return "warning";
  }
}

function getSimulationBadgeTone(label: string): StatusBadgeTone {
  const normalizedLabel = label.toLowerCase();

  if (
    normalizedLabel.includes("loaded") ||
    normalizedLabel.includes("parsed") ||
    normalizedLabel.includes("validated") ||
    normalizedLabel.includes("matched") ||
    normalizedLabel.includes("complete")
  ) {
    return "success";
  }

  if (
    normalizedLabel.includes("gap") ||
    normalizedLabel.includes("unmatched")
  ) {
    return "danger";
  }

  if (
    normalizedLabel.includes("awaiting") ||
    normalizedLabel.includes("queued") ||
    normalizedLabel.includes("ambiguous")
  ) {
    return "warning";
  }

  if (normalizedLabel.includes("review")) {
    return "accent";
  }

  return "neutral";
}

function SourceMonitorsCard() {
  return (
    <SurfacePanel>
      <SectionHeading
        description="These channels mimic where production packets would be discovered and what the system appears to be loading right now."
        title="Active source watchers"
      />
      <div className="source-monitor-grid">
        {simulationSourceMonitors.map((monitor) => (
          <SurfaceCard as="article" className="mini-card" key={monitor.title}>
            <div className="mini-card-header">
              <div>
                <p className="queue-card-label">{monitor.sourceLabel}</p>
                <h3>{monitor.title}</h3>
              </div>
              <StatusBadge tone={getSimulationBadgeTone(monitor.status)}>
                {monitor.status}
              </StatusBadge>
            </div>
            <p className="mini-card-copy">{monitor.summary}</p>
            <dl className="detail-list compact-detail-list">
              <div>
                <dt>Watching</dt>
                <dd>{monitor.path}</dd>
              </div>
              <div>
                <dt>Cadence</dt>
                <dd>{monitor.cadence}</dd>
              </div>
              <div>
                <dt>Current packet</dt>
                <dd>{monitor.currentPacket}</dd>
              </div>
            </dl>
          </SurfaceCard>
        ))}
      </div>
    </SurfacePanel>
  );
}

function StackOverviewCard({
  description,
  title,
}: {
  description: string;
  title: string;
}) {
  return (
    <SurfacePanel>
      <SectionHeading description={description} title={title} />
      <div className="stack-grid">
        {simulationStackLayers.map((layer) => (
          <SurfaceCard as="article" className="mini-card stack-card" key={layer.layer}>
            <p className="queue-card-label">{layer.layer}</p>
            <h3>{layer.tools}</h3>
            <p className="mini-card-copy">{layer.detail}</p>
          </SurfaceCard>
        ))}
      </div>
    </SurfacePanel>
  );
}

function LandingScreen({ onBegin }: { onBegin: () => void }) {
  return (
    <>
      <SourceMonitorsCard />

      <StackOverviewCard
        description="The walkthrough now calls out the real services behind packet intake, AI extraction, state management, and operator review so the public route feels closer to the production shape."
        title="Platform stack behind the walkthrough"
      />

      <SurfacePanel>
        <SectionHeading
          actions={
            <button onClick={onBegin} type="button">
              Begin simulation
            </button>
          }
          description="Visitors can see the packet flow, source watchers, and queue shape without crossing into live operator actions."
          title="Simulation rules"
        />
        <ul className="rule-list">
          {simulationIntroRules.map((rule) => (
            <li key={rule}>{rule}</li>
          ))}
        </ul>
      </SurfacePanel>
    </>
  );
}

function IntakeScreen() {
  return (
    <div className="section-stack">
      <SourceMonitorsCard />

      <SurfacePanel>
        <SectionHeading
          actions={
            <button className="ghost-button" disabled type="button">
              Upload disabled
            </button>
          }
          description="Each packet looks loaded from a live source and queued for pipeline work, but the public route never accepts or mutates a real document."
          title="Staged intake packets"
        />
        <div className="packet-grid">
          {simulationPackets.map((packet) => (
            <SurfaceCard as="article" className="mini-card" key={packet.title}>
              <div className="mini-card-header">
                <div>
                  <p className="queue-card-label">{packet.sourceLabel}</p>
                  <h3>{packet.title}</h3>
                </div>
                <StatusBadge tone="neutral">{packet.packetSize}</StatusBadge>
              </div>
              <p className="mini-card-copy">{packet.summary}</p>
              <dl className="detail-list compact-detail-list">
                <div>
                  <dt>Issuer</dt>
                  <dd>{packet.issuer}</dd>
                </div>
                <div>
                  <dt>Account hint</dt>
                  <dd>{packet.accountHint}</dd>
                </div>
              </dl>
              <ul className="chip-list">
                {packet.tags.map((tag) => (
                  <li className="reason-chip" key={tag}>
                    {tag}
                  </li>
                ))}
              </ul>
            </SurfaceCard>
          ))}
        </div>
      </SurfacePanel>
    </div>
  );
}

function ProcessingScreen() {
  return (
    <div className="section-stack">
      <SurfacePanel>
        <SectionHeading
          description="The simulation shows how a staged packet moves through preflight, OCR, extraction, matching, and routing before an operator ever opens the review queue."
          title="Scripted processing timeline"
        />
        <div className="timeline-list">
          {simulationProcessingStages.map((stage) => (
            <SurfaceTimelineItem
              badge={
                <StatusBadge tone={getProcessingStateTone(stage.state)}>
                  {formatLabel(stage.state)}
                </StatusBadge>
              }
              className="simulation-timeline-item"
              description={stage.summary}
              key={stage.title}
              markerState={stage.state}
              title={stage.title}
            >
              <p className="timeline-detail timeline-detail-secondary">{stage.detail}</p>
            </SurfaceTimelineItem>
          ))}
        </div>
      </SurfacePanel>

      <StackOverviewCard
        description="Each stage below is backed by a concrete service layer in the actual stack, which is why this route now reads more like an operator pipeline board than a generic demo timeline."
        title="Services behind processing and routing"
      />
    </div>
  );
}

function ReviewScreen({ items }: { items: ReviewQueueItem[] }) {
  return (
    <div className="section-stack">
      <StackOverviewCard
        description="The queue sits downstream from watched sources, preflight checks, OCR, AI extraction, and matching. This route keeps that service context visible while the card actions stay disabled."
        title="What feeds the review queue"
      />

      <SurfacePanel>
        <SectionHeading
          description="The queue now behaves like a production operator board with synthetic data. Buttons stay disabled so no review decision can be submitted."
          title="Review queue simulation"
        />
        <div className="queue-grid">
          {items.map((item) => (
            <QueueCard
              actionNote="Simulation only"
              isMutating={false}
              isReadOnly
              item={item}
              key={item.document_id}
            />
          ))}
        </div>
      </SurfacePanel>
    </div>
  );
}

function AccountsScreen() {
  return (
    <div className="section-stack">
      <SurfacePanel>
        <SectionHeading
          description="This view previews what the private site will show after the live account lookup and duplicate checks are implemented."
          title="Account simulation"
        />
        <div className="account-header-row">
          <div>
            <p className="queue-card-label">{simulationAccountSummary.portfolio}</p>
            <h3>{simulationAccountSummary.debtorName}</h3>
            <p className="mini-card-copy">{simulationAccountSummary.accountId}</p>
          </div>
          <span className="confidence-pill">
            {simulationAccountSummary.matchConfidence}
          </span>
        </div>
        <dl className="detail-list">
          {simulationAccountSummary.details.map((detail) => (
            <div key={detail.label}>
              <dt>{detail.label}</dt>
              <dd>{detail.value}</dd>
            </div>
          ))}
        </dl>
        <div className="reason-strip">
          {simulationAccountSummary.preflightSignals.map((signal) => (
            <span className="reason-chip" key={signal}>
              {signal}
            </span>
          ))}
        </div>
      </SurfacePanel>

      <SurfacePanel>
        <SectionHeading
          actions={
            <button className="ghost-button" disabled type="button">
              Download disabled
            </button>
          }
          description="Document previews stay illustrative here. The private site will add secure preview and download after auth is in place."
          title="Linked documents"
        />
        <div className="document-list">
          {simulationAccountDocuments.map((document) => (
            <SurfaceCard as="article" className="mini-card" key={document.fileName}>
              <div className="mini-card-header">
                <div>
                  <p className="queue-card-label">{document.sourceLabel}</p>
                  <h3>{document.fileName}</h3>
                </div>
                <StatusBadge tone={getSimulationBadgeTone(document.status)}>
                  {document.status}
                </StatusBadge>
              </div>
              <p className="mini-card-copy">{document.summary}</p>
            </SurfaceCard>
          ))}
        </div>
      </SurfacePanel>
    </div>
  );
}

function ShowcaseScreen({ route }: { route: "libraries" | "ops" }) {
  return (
    <div className="showcase-grid">
      {simulationCards[route].map((card) => (
        <SurfacePanel as="article" key={card.title}>
          <p className="queue-card-label">{card.eyebrow}</p>
          <h3>{card.title}</h3>
          <p className="mini-card-copy">{card.summary}</p>
          <strong className="showcase-highlight">{card.highlight}</strong>
          <ul className="rule-list compact-rule-list">
            {card.bullets.map((bullet) => (
              <li key={bullet}>{bullet}</li>
            ))}
          </ul>
        </SurfacePanel>
      ))}
    </div>
  );
}

function RouteContent({
  onBegin,
  reviewItems,
  route,
}: {
  onBegin: () => void;
  reviewItems: ReviewQueueItem[];
  route: SimulationRoute;
}) {
  switch (route) {
    case "landing":
      return <LandingScreen onBegin={onBegin} />;
    case "intake":
      return <IntakeScreen />;
    case "processing":
      return <ProcessingScreen />;
    case "review":
      return <ReviewScreen items={reviewItems} />;
    case "accounts":
      return <AccountsScreen />;
    case "ops":
      return <ShowcaseScreen route="ops" />;
    case "libraries":
      return <ShowcaseScreen route="libraries" />;
  }
}

export function SimulationShell() {
  const [route, setRoute] = useState<SimulationRoute>(() =>
    getSimulationRouteFromLocation(window.location.pathname, window.location.hash),
  );
  const [hasStartedSimulation, setHasStartedSimulation] = useState(() =>
    window.sessionStorage.getItem(simulationStorageKey) === "true",
  );
  const [reviewItems, setReviewItems] = useState<ReviewQueueItem[]>([]);
  const [trafficSessionId] = useState(() => getPublicTrafficSessionId());

  useEffect(() => {
    const handleLocationChange = () => {
      setRoute(
        getSimulationRouteFromLocation(
          window.location.pathname,
          window.location.hash,
        ),
      );
    };

    window.addEventListener("hashchange", handleLocationChange);
    window.addEventListener("popstate", handleLocationChange);
    return () => {
      window.removeEventListener("hashchange", handleLocationChange);
      window.removeEventListener("popstate", handleLocationChange);
    };
  }, []);

  useEffect(() => {
    void listSimulationReviewItems().then(setReviewItems);
  }, []);

  const activeRoute = hasStartedSimulation ? route : "landing";
  const activeView = simulationViews[activeRoute];
  const metrics = useMemo(
    () => buildMetrics(activeRoute, reviewItems),
    [activeRoute, reviewItems],
  );

  useEffect(() => {
    void recordPublicTrafficEvent({
      event_type: "page_view",
      page_title: activeView.navLabel,
      referrer: document.referrer || undefined,
      route: activeRoute,
      session_id: trafficSessionId,
      site_mode: "simulation",
    });
  }, [activeRoute, activeView.navLabel, trafficSessionId]);

  const beginSimulation = () => {
    window.sessionStorage.setItem(simulationStorageKey, "true");
    setHasStartedSimulation(true);
    void recordPublicTrafficEvent({
      event_type: "simulation_started",
      page_title: simulationViews.intake.navLabel,
      referrer: document.referrer || undefined,
      route: "intake",
      session_id: trafficSessionId,
      site_mode: "simulation",
    });
    navigateToAppPath(getDemoPath("intake"));
  };

  const returnToLanding = () => {
    window.sessionStorage.removeItem(simulationStorageKey);
    setHasStartedSimulation(false);
    navigateToAppPath(HOME_PATH);
  };

  const navigateTo = (nextRoute: SimulationRoute) => {
    navigateToAppPath(getDemoPath(nextRoute));
  };

  return (
    <PublicSiteLayout activeRoute="demo" className="simulation-shell">
      <header className="hero hero-wide">
        <div>
          <p className="eyebrow">Public simulation</p>
          <h1>{activeView.title}</h1>
          <p className="hero-copy">{activeView.description}</p>
          <div className="hero-actions">
            {!hasStartedSimulation ? (
              <button onClick={beginSimulation} type="button">
                Begin simulation
              </button>
            ) : (
              <>
                <button onClick={beginSimulation} type="button">
                  Run simulation again
                </button>
                {activeRoute !== "intake" ? (
                  <button
                    className="ghost-button"
                    onClick={() => {
                      navigateTo(simulationRouteOrder[1]);
                    }}
                    type="button"
                  >
                    Jump to intake
                  </button>
                ) : null}
                <button
                  className="secondary-button"
                  onClick={returnToLanding}
                  type="button"
                >
                  Return to landing
                </button>
              </>
            )}
            <a
              className="button-link secondary-link"
              href={HOME_PATH}
              onClick={(event) => {
                event.preventDefault();
                returnToLanding();
              }}
            >
              Back to public landing
            </a>
          </div>
        </div>
        <div className="hero-panel">
          <span>{activeView.panelEyebrow}</span>
          <strong>{activeView.panelTitle}</strong>
          <p>{activeView.panelCopy}</p>
          {activeView.panelMetrics && activeView.panelMetrics.length > 0 ? (
            <div className="hero-panel-metric-grid" role="list">
              {activeView.panelMetrics.map((item) => (
                <div className="hero-panel-metric" key={item.label} role="listitem">
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                  <p>{item.detail}</p>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </header>

      <section className="metrics-grid" aria-label="simulation metrics">
        {metrics.map((metric) => (
          <article className="metric-card" key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <p className="metric-detail">{metric.detail}</p>
          </article>
        ))}
      </section>

      <nav aria-label="simulation sections" className="simulation-nav">
        {simulationRouteOrder.map((navRoute) => {
          const view = simulationViews[navRoute];
          const isDisabled = !hasStartedSimulation && navRoute !== "landing";

          return (
            <button
              aria-current={activeRoute === navRoute ? "page" : undefined}
              className={`nav-pill ${activeRoute === navRoute ? "nav-pill-active" : ""}`}
              disabled={isDisabled}
              key={navRoute}
              onClick={() => {
                navigateTo(navRoute);
              }}
              type="button"
            >
              {view.navLabel}
            </button>
          );
        })}
      </nav>

      <section className="workbench-layout simulation-layout">
        <div className="queue-column simulation-main">
          <RouteContent
            onBegin={beginSimulation}
            reviewItems={reviewItems}
            route={activeRoute}
          />
        </div>

        <SurfaceDrawer as="aside" className="operations-panel simulation-aside">
          <SectionHeading
            description={activeView.asideCopy}
            title={activeView.asideTitle}
          />
          <ul className="operations-list">
            {activeView.asidePoints.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </SurfaceDrawer>
      </section>
    </PublicSiteLayout>
  );
}
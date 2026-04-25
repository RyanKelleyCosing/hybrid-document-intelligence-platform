import { Suspense, lazy, useEffect, useState } from "react";

import { isSimulationMode } from "../appMode";
import { AdminPrivateDemoRequest } from "./AdminPrivateDemoRequest";
import { ProtectedSiteLayout } from "./ProtectedSiteLayout";

const LiveReviewWorkbench = lazy(() =>
  import("./LiveReviewWorkbench").then((module) => ({
    default: module.LiveReviewWorkbench,
  })),
);

type AdminLoadingPhaseStatus = "active" | "pending";

type AdminLoadingPhase = {
  description: string;
  id: "auth" | "queue" | "proxy";
  label: string;
};

const adminLoadingPhases: readonly AdminLoadingPhase[] = [
  {
    description: "Confirming the Easy Auth session and operator allowlist.",
    id: "auth",
    label: "Authenticating",
  },
  {
    description: "Loading the SQL packet queue and assignment state.",
    id: "queue",
    label: "Fetching queue",
  },
  {
    description: "Warming the protected API proxy and lazy workbench bundle.",
    id: "proxy",
    label: "Warming proxy",
  },
];

function AdminLoadingSkeleton() {
  const [activePhaseIndex, setActivePhaseIndex] = useState(0);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setActivePhaseIndex((current) =>
        current < adminLoadingPhases.length - 1 ? current + 1 : current,
      );
    }, 900);

    return () => {
      window.clearInterval(interval);
    };
  }, []);

  return (
    <ProtectedSiteLayout
      navigation={
        <aside className="admin-loading-nav" aria-hidden="true">
          <div className="admin-loading-block" />
          <div className="admin-loading-block admin-loading-block--small" />
          <div className="admin-loading-block admin-loading-block--small" />
        </aside>
      }
    >
      <section className="admin-loading-card" role="status" aria-live="polite">
        <p className="eyebrow">Loading admin workspace</p>
        <h1>Restoring the live operator session...</h1>
        <p>
          The workbench resolves once the lazy chunk finishes loading. The
          steps below reflect the actual stages the shell walks through, not
          a synthetic timer.
        </p>
        <ol className="admin-loading-phase-list">
          {adminLoadingPhases.map((phase, index) => {
            const status: AdminLoadingPhaseStatus =
              index <= activePhaseIndex ? "active" : "pending";

            return (
              <li
                className={`admin-loading-phase admin-loading-phase--${status}`}
                key={phase.id}
              >
                <span className="admin-loading-phase-index" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="admin-loading-phase-text">
                  <span className="admin-loading-phase-label">
                    {phase.label}
                    {status === "active" ? (
                      <span className="visually-hidden"> in progress</span>
                    ) : (
                      <span className="visually-hidden"> pending</span>
                    )}
                  </span>
                  <span className="admin-loading-phase-description">
                    {phase.description}
                  </span>
                </span>
              </li>
            );
          })}
        </ol>
      </section>
    </ProtectedSiteLayout>
  );
}

export function ProtectedAppLayout() {
  if (isSimulationMode) {
    return <AdminPrivateDemoRequest />;
  }

  return (
    <Suspense fallback={<AdminLoadingSkeleton />}>
      <LiveReviewWorkbench />
    </Suspense>
  );
}
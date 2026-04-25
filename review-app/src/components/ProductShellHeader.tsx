import { useEffect, useState } from "react";

import type { AppMode } from "../appMode";
import {
  getAdminNavigationTarget,
  getProductRouteDefinition,
  getPublicLandingTarget,
  navigateToAppPath,
  productRouteOrder,
  type ProductRouteId,
  type PublicAppRoute,
} from "../appRoutes";
import { StatusBadge, type StatusBadgeTone } from "./SurfacePrimitives";

type ProductShellHeaderProps = {
  activeRoute: ProductRouteId;
  mode: AppMode;
  operatorEmail?: string | null;
};

type RouteGroupId = "briefing" | "protected" | "walkthrough";

type RouteGroup = {
  id: RouteGroupId;
  label: string;
  summary: string;
  routeIds: ProductRouteId[];
  tone: StatusBadgeTone;
};

function getRouteGroups(mode: AppMode): RouteGroup[] {
  return [
    {
      id: "briefing",
      label: "Public briefing",
      routeIds: ["home", "security", "cost"],
      summary:
        "Overview, Security, and Cost explain the product, the trust boundary, and the public-safe dashboards.",
      tone: "accent",
    },
    {
      id: "walkthrough",
      label: "Guided walkthrough",
      routeIds: ["demo"],
      summary:
        "Demo keeps the packet story public-safe and action-disabled without pretending to be the live operator shell.",
      tone: "warning",
    },
    {
      id: "protected",
      label: mode === "live" ? "Protected live admin" : "Live admin entry",
      routeIds: ["admin"],
      summary:
        mode === "live"
          ? "The live admin host stays authenticated and separate from the public briefing shell."
          : "The live admin host is the real operator path for queue and packet work, not another public demo tab.",
      tone: "neutral",
    },
  ];
}

function getDefaultExpandedGroupIds(
  routeGroups: readonly RouteGroup[],
  activeRoute: ProductRouteId,
) {
  const activeGroupId = routeGroups.find((group) =>
    group.routeIds.includes(activeRoute),
  )?.id;

  return activeGroupId ? [activeGroupId] : [routeGroups[0].id];
}

function getSurfaceEyebrow(activeRoute: ProductRouteId, mode: AppMode) {
  if (mode === "live") {
    return "Protected live admin route";
  }

  switch (activeRoute) {
    case "demo":
      return "Secondary demo route";
    case "security":
      return "Public security route";
    case "cost":
      return "Public cost route";
    case "home":
    default:
      return "Public informational route";
  }
}

function getSurfaceSummary(
  activeRoute: ProductRouteId,
  mode: AppMode,
  operatorEmail?: string | null,
) {
  if (mode === "live") {
    return operatorEmail
      ? `Authenticated live admin host for ${operatorEmail}.`
      : "Microsoft-authenticated live admin host for the real operator workflow.";
  }

  return getProductRouteDefinition(activeRoute).navSummary;
}

function getSurfaceTone(
  activeRoute: ProductRouteId,
  mode: AppMode,
): StatusBadgeTone {
  if (mode === "live") {
    return "neutral";
  }

  switch (activeRoute) {
    case "cost":
      return "success";
    case "security":
      return "accent";
    case "demo":
      return "warning";
    case "admin":
      return "neutral";
    case "home":
    default:
      return "accent";
  }
}

function getRouteBrandIdentity(
  activeRoute: ProductRouteId,
  mode: AppMode,
): { eyebrow: string; title: string; iconPath: string; iconLabel: string } {
  if (mode === "live") {
    return {
      eyebrow: "Protected live admin",
      title: "Operator workbench \u2014 packets, queues, decisions.",
      iconLabel: "shield",
      // shield with check
      iconPath:
        "M16 3 5 7v6c0 6 4.5 10.5 11 13 6.5-2.5 11-7 11-13V7L16 3zm-1.4 18.5-5.6-5.6 2-2 3.6 3.6 7.4-7.4 2 2-9.4 9.4z",
    };
  }

  switch (activeRoute) {
    case "security":
      return {
        eyebrow: "Public security route",
        title: "Security posture \u2014 telemetry, geography, and the trust boundary.",
        iconLabel: "globe",
        // globe
        iconPath:
          "M16 3a13 13 0 1 0 0 26 13 13 0 0 0 0-26zm0 2.2c2.4 0 4.6 2.6 5.7 6.4H10.3c1.1-3.8 3.3-6.4 5.7-6.4zM5.4 14h5.1c-.1 1-.2 2.1-.2 3s.1 2 .2 3H5.4a10.8 10.8 0 0 1 0-6zm1 8.2h4.3c.7 1.7 1.6 3.2 2.7 4.3a10.8 10.8 0 0 1-7-4.3zM12.7 20H19.3c.1-.9.2-1.9.2-3s-.1-2.1-.2-3H12.7c-.1.9-.2 2-.2 3s.1 2.1.2 3zm3.3 6.7c-1.1-.9-2-2.5-2.7-4.5h5.4c-.7 2-1.6 3.6-2.7 4.5zm5.6-1.5a13.7 13.7 0 0 0 2.7-4.3h-4.3c-.5 1.7-1.1 3.2-1.9 4.3.6 0 1.2-.1 1.8-.4 1-.5 1.5 .4 1.7 .4zm4-5.2h-5.1c.1-1 .2-2 .2-3s-.1-2-.2-3h5.1a10.8 10.8 0 0 1 0 6zm-2.1-8h-4.3c-.7-1.7-1.6-3.2-2.7-4.3 2.8.6 5.3 2.2 7 4.3z",
      };
    case "cost":
      return {
        eyebrow: "Public cost route",
        title: "Cost transparency \u2014 daily spend, drivers, and unit economics.",
        iconLabel: "chart",
        // bar chart
        iconPath:
          "M4 26V6h3v20H4zm6 0V12h3v14h-3zm6 0v-9h3v9h-3zm6 0V4h3v22h-3zM4 28h24v2H4z",
      };
    case "demo":
      return {
        eyebrow: "Guided walkthrough",
        title: "Packet walkthrough \u2014 how a document moves through the pipeline.",
        iconLabel: "play",
        // play in circle
        iconPath:
          "M16 3a13 13 0 1 0 0 26 13 13 0 0 0 0-26zm-3 8 9 5-9 5V11z",
      };
    case "admin":
      return {
        eyebrow: "Live admin entry",
        title: "Live admin entry \u2014 sign-in path to the protected operator host.",
        iconLabel: "key",
        iconPath:
          "M21 4a7 7 0 0 0-6.7 9L3 24.3V29h4.7l11.3-11.3A7 7 0 1 0 21 4zm0 4a3 3 0 1 1 0 6 3 3 0 0 1 0-6z",
      };
    case "home":
    default:
      return {
        eyebrow: "Public informational route",
        title: "Hybrid document intelligence \u2014 messy inbound \u2192 review-ready work.",
        iconLabel: "document",
        iconPath:
          "M7 3h12l6 6v20H7V3zm11 1.5V10h5.5L18 4.5zM10 16h12v2H10v-2zm0 4h12v2H10v-2zm0 4h8v2h-8v-2z",
      };
  }
}

export function ProductShellHeader({
  activeRoute,
  mode,
  operatorEmail,
}: ProductShellHeaderProps) {
  const routeGroups = getRouteGroups(mode);
  const [isNavigationExpanded, setIsNavigationExpanded] = useState(false);
  const [expandedGroupIds, setExpandedGroupIds] = useState<RouteGroupId[]>(() =>
    getDefaultExpandedGroupIds(routeGroups, activeRoute),
  );
  const activeRouteDefinition = getProductRouteDefinition(activeRoute);
  const brandIdentity = getRouteBrandIdentity(activeRoute, mode);
  const adminNavigationTarget =
    mode === "simulation"
      ? getAdminNavigationTarget(window.location.origin)
      : null;

  useEffect(() => {
    setIsNavigationExpanded(false);
    setExpandedGroupIds(getDefaultExpandedGroupIds(getRouteGroups(mode), activeRoute));
  }, [activeRoute, mode]);

  const activeRouteGroupId =
    routeGroups.find((group) => group.routeIds.includes(activeRoute))?.id ??
    routeGroups[0].id;

  const toggleRouteGroup = (groupId: RouteGroupId) => {
    setExpandedGroupIds((currentGroupIds) =>
      currentGroupIds.includes(groupId)
        ? currentGroupIds.filter((currentGroupId) => currentGroupId !== groupId)
        : [...currentGroupIds, groupId],
    );
  };

  const renderRouteItem = (routeId: ProductRouteId) => {
    const routeDefinition = getProductRouteDefinition(routeId);
    const isActive = routeId === activeRoute;

    if (mode === "simulation" && routeDefinition.isPubliclyNavigable) {
      return (
        <button
          aria-current={isActive ? "page" : undefined}
          className={
            isActive
              ? "product-route-pill product-route-pill-active"
              : "product-route-pill"
          }
          key={routeId}
          onClick={() => {
            navigateToAppPath(routeDefinition.path);
          }}
          type="button"
        >
          {routeDefinition.label}
        </button>
      );
    }

    if (mode === "simulation" && routeId === "admin" && adminNavigationTarget) {
      return (
        <a
          aria-current={isActive ? "page" : undefined}
          className={
            isActive
              ? "product-route-pill product-route-pill-active"
              : "product-route-pill product-route-pill-locked"
          }
          href={adminNavigationTarget.href}
          key={routeId}
          onClick={(event) => {
            if (!adminNavigationTarget.isExternal) {
              event.preventDefault();
              navigateToAppPath(adminNavigationTarget.href);
            }
          }}
        >
          {routeDefinition.label}
        </a>
      );
    }

    if (mode === "live" && routeDefinition.isPubliclyNavigable) {
      const publicTarget = getPublicLandingTarget(
        window.location.origin,
        routeId as PublicAppRoute,
      );
      return (
        <a
          aria-current={isActive ? "page" : undefined}
          className={
            isActive
              ? "product-route-pill product-route-pill-active"
              : "product-route-pill product-route-pill-locked"
          }
          href={publicTarget.href}
          key={routeId}
          onClick={(event) => {
            if (!publicTarget.isExternal) {
              event.preventDefault();
              navigateToAppPath(publicTarget.href);
            }
          }}
        >
          {routeDefinition.label}
        </a>
      );
    }

    return (
      <span
        className={
          isActive
            ? "product-route-pill product-route-pill-active"
            : routeId === "admin"
              ? "product-route-pill product-route-pill-locked"
              : "product-route-pill product-route-pill-muted"
        }
        key={routeId}
      >
        {routeDefinition.label}
      </span>
    );
  };

  return (
    <div className="product-shell-header" data-route-brand={activeRoute} data-route-mode={mode}>
      <div className="product-shell-brand">
        <div className="product-shell-brand-mark" aria-hidden="true">
          <svg viewBox="0 0 32 32" focusable="false" role="presentation">
            <path d={brandIdentity.iconPath} />
          </svg>
        </div>
        <div className="product-shell-brand-copy">
          <p className="eyebrow">{brandIdentity.eyebrow}</p>
          <strong>{brandIdentity.title}</strong>
        </div>
        <p className="product-shell-note">
          {getSurfaceSummary(activeRoute, mode, operatorEmail)}
        </p>
      </div>

      <nav aria-label="Product navigation" className="product-shell-nav">
        <button
          aria-controls="product-nav-groups"
          aria-expanded={isNavigationExpanded}
          className="product-nav-toggle"
          onClick={() => {
            setIsNavigationExpanded((currentValue) => !currentValue);
          }}
          type="button"
        >
          <strong>{isNavigationExpanded ? "Hide route directory" : "Show route directory"}</strong>
          <small>
            {mode === "live"
              ? "Expand briefing and live-admin groups without leaving the protected host."
              : "Expand public briefing, walkthrough, and live-admin groups separately."}
          </small>
        </button>

        <div
          className="product-nav-groups"
          data-expanded={isNavigationExpanded ? "true" : "false"}
          id="product-nav-groups"
        >
          {routeGroups.map((group) => (
            <section className="product-route-group" key={group.id}>
              <button
                aria-controls={`product-route-group-body-${group.id}`}
                aria-expanded={expandedGroupIds.includes(group.id)}
                aria-label={`${group.label} routes`}
                className="product-route-group-toggle"
                onClick={() => {
                  toggleRouteGroup(group.id);
                }}
                type="button"
              >
                <div className="product-route-group-heading">
                  <div className="product-route-group-copy-block">
                    <p className="product-route-group-label">{group.label}</p>
                    <p className="product-route-group-copy">{group.summary}</p>
                  </div>
                  <div className="product-route-group-meta">
                    <StatusBadge
                      tone={
                        activeRouteGroupId === group.id ? group.tone : "neutral"
                      }
                    >
                      {activeRouteGroupId === group.id
                        ? "Current route"
                        : `${group.routeIds.length} route${group.routeIds.length === 1 ? "" : "s"}`}
                    </StatusBadge>
                    <span className="product-route-group-state">
                      {expandedGroupIds.includes(group.id) ? "Collapse" : "Expand"}
                    </span>
                  </div>
                </div>
              </button>
              <div
                className="product-route-group-body"
                data-expanded={expandedGroupIds.includes(group.id) ? "true" : "false"}
                id={`product-route-group-body-${group.id}`}
              >
                <div className="product-route-group-grid">
                  {group.routeIds.map((routeId) => renderRouteItem(routeId))}
                </div>
              </div>
            </section>
          ))}
        </div>
      </nav>

      <div className="surface-mode-badge" data-surface={activeRoute}>
        <StatusBadge tone={getSurfaceTone(activeRoute, mode)}>
          {getSurfaceEyebrow(activeRoute, mode)}
        </StatusBadge>
        <strong>{activeRouteDefinition.label}</strong>
      </div>
    </div>
  );
}
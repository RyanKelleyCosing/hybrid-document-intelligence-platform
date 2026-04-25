import {
  simulationRouteOrder,
  type SimulationRoute,
} from "./data/simulationData";
import type { AppMode } from "./appMode";
import type { PacketQueueFilters } from "./api/packetQueueApi";
import type { AdminSectionId } from "./components/AdminNavigation";
import type { WorkspaceTabId } from "./components/PacketWorkspacePanel";

export type PublicAppRoute = "cost" | "demo" | "home" | "security";
export type ProductRouteId = PublicAppRoute | "admin";

export const HOME_PATH = "/";
export const SECURITY_PATH = "/security";
export const COST_PATH = "/cost";
export const DEMO_PATH = "/demo";
export const ADMIN_PATH = "/admin";

const defaultAdminAppUrl = "https://admin.ryancodes.online";
const defaultAdminAppFallbackUrl =
  "https://admin-doc-test-nwigok.azurewebsites.net";

const configuredAdminAppUrl =
  import.meta.env.VITE_ADMIN_APP_URL?.trim() || defaultAdminAppUrl;
const configuredAdminAppFallbackUrl =
  import.meta.env.VITE_ADMIN_APP_FALLBACK_URL?.trim() ||
  defaultAdminAppFallbackUrl;

const defaultPublicSiteUrl = "https://www.ryancodes.online";
const configuredPublicSiteUrl =
  import.meta.env.VITE_PUBLIC_SITE_URL?.trim() || defaultPublicSiteUrl;

type ProductRouteDefinition = {
  id: ProductRouteId;
  isPubliclyNavigable: boolean;
  label: string;
  navSummary: string;
  path: string;
};

const productRouteDefinitions: Record<ProductRouteId, ProductRouteDefinition> = {
  home: {
    id: "home",
    isPubliclyNavigable: true,
    label: "Overview",
    navSummary: "Public product framing, contact context, and route entry points.",
    path: HOME_PATH,
  },
  security: {
    id: "security",
    isPubliclyNavigable: true,
    label: "Security",
    navSummary:
      "Public-safe telemetry, retention, and trust-boundary briefing.",
    path: SECURITY_PATH,
  },
  cost: {
    id: "cost",
    isPubliclyNavigable: true,
    label: "Cost",
    navSummary:
      "Public-safe spend, trend, anomaly, and forecast dashboard slices.",
    path: COST_PATH,
  },
  demo: {
    id: "demo",
    isPubliclyNavigable: true,
    label: "Demo",
    navSummary:
      "Secondary walkthrough route for the packet and workflow story.",
    path: DEMO_PATH,
  },
  admin: {
    id: "admin",
    isPubliclyNavigable: false,
    label: "Live Admin",
    navSummary:
      "Protected live admin host for the real queue, workspace, and review flow.",
    path: ADMIN_PATH,
  },
};

export const productRouteOrder: readonly ProductRouteId[] = [
  "home",
  "security",
  "cost",
  "demo",
  "admin",
] as const;

export type AdminQueueFilterUrlState = Pick<
  PacketQueueFilters,
  | "assigned_user_email"
  | "classification_key"
  | "document_type_key"
  | "min_queue_age_hours"
  | "page"
  | "source"
  | "stage_name"
  | "status"
>;

type AdminSectionUrlOptions = {
  packetId?: string | null;
  queueFilters?: AdminQueueFilterUrlState | null;
  tab?: WorkspaceTabId | null;
};

const adminSectionRouteOrder: readonly AdminSectionId[] = [
  "review",
  "intake",
  "pipeline",
  "viewer",
  "accounts",
  "rules_doctypes",
  "sources",
  "recommendations",
  "audit",
] as const;

const workspaceTabRouteOrder: readonly WorkspaceTabId[] = [
  "overview",
  "intake",
  "documents",
  "viewer",
  "ocr",
  "extraction",
  "matching",
  "review",
  "pipeline",
  "rules_doctypes",
  "recommendations",
  "audit",
] as const;

const simulationRoutes = new Set<string>(simulationRouteOrder);
const adminSectionRoutes = new Set<string>(adminSectionRouteOrder);
const workspaceTabRoutes = new Set<string>(workspaceTabRouteOrder);

function getCanonicalPathHead(path: string) {
  return path.replace(/^\//, "").toLowerCase();
}

function getNormalizedPathSegments(pathname: string) {
  return pathname
    .trim()
    .toLowerCase()
    .split("/")
    .filter(Boolean);
}

function getNormalizedHashSegments(hash: string) {
  const normalizedHash = hash.replace(/^#\/?/, "").trim().toLowerCase();
  return normalizedHash.split("/").filter(Boolean);
}

function getNormalizedOrigin(value: string) {
  try {
    return new URL(value).origin.toLowerCase();
  } catch {
    return value.trim().replace(/\/$/, "").toLowerCase();
  }
}

function buildAdminEntryUrl(baseUrl: string) {
  const parsedUrl = new URL(baseUrl);
  const normalizedPath = parsedUrl.pathname.replace(/\/$/, "");

  if (!normalizedPath || normalizedPath === "/") {
    parsedUrl.pathname = ADMIN_PATH;
  } else if (!normalizedPath.startsWith(ADMIN_PATH)) {
    parsedUrl.pathname = `${normalizedPath}${ADMIN_PATH}`;
  }

  parsedUrl.hash = "";
  parsedUrl.search = "";

  return parsedUrl.toString().replace(/\/$/, "");
}

function asSimulationRoute(value: string | undefined): SimulationRoute | null {
  if (!value || !simulationRoutes.has(value)) {
    return null;
  }

  return value as SimulationRoute;
}

function normalizeAdminPacketId(packetId: string | null | undefined) {
  const normalizedPacketId = packetId?.trim();
  return normalizedPacketId ? normalizedPacketId : null;
}

function normalizeAdminSearchText(value: string | null | undefined) {
  const normalizedValue = value?.trim();
  return normalizedValue ? normalizedValue : undefined;
}

function normalizeAdminSearchNumber(value: string | null | undefined) {
  const normalizedValue = value?.trim();
  if (!normalizedValue) {
    return undefined;
  }

  const parsedValue = Number(normalizedValue);
  return Number.isFinite(parsedValue) ? parsedValue : undefined;
}

export function resolvePublicAppRoute(
  pathname: string,
  hash: string,
): PublicAppRoute {
  const pathSegments = getNormalizedPathSegments(pathname);
  const hashSegments = getNormalizedHashSegments(hash);

  const firstPathSegment = pathSegments[0] ?? "";
  const firstHashSegment = hashSegments[0] ?? "";
  const routeCandidate = firstPathSegment || firstHashSegment;

  if (routeCandidate === getCanonicalPathHead(SECURITY_PATH)) {
    return "security";
  }

  if (routeCandidate === getCanonicalPathHead(COST_PATH)) {
    return "cost";
  }

  if (
    routeCandidate === getCanonicalPathHead(DEMO_PATH) ||
    routeCandidate === "simulation"
  ) {
    return "demo";
  }

  if (simulationRoutes.has(routeCandidate)) {
    return "demo";
  }

  return "home";
}

export function getSimulationRouteFromLocation(
  pathname: string,
  hash: string,
): SimulationRoute {
  const pathSegments = getNormalizedPathSegments(pathname);
  const hashSegments = getNormalizedHashSegments(hash);

  const firstPathSegment = pathSegments[0] ?? "";
  const secondPathSegment = pathSegments[1] ?? "";
  const firstHashSegment = hashSegments[0] ?? "";
  const secondHashSegment = hashSegments[1] ?? "";

  if (
    firstPathSegment === getCanonicalPathHead(DEMO_PATH) ||
    firstPathSegment === "simulation"
  ) {
    return asSimulationRoute(secondPathSegment) ?? "landing";
  }

  if (simulationRoutes.has(firstPathSegment)) {
    return firstPathSegment as SimulationRoute;
  }

  if (
    firstHashSegment === getCanonicalPathHead(DEMO_PATH) ||
    firstHashSegment === "simulation"
  ) {
    return asSimulationRoute(secondHashSegment) ?? "landing";
  }

  return asSimulationRoute(firstHashSegment) ?? "landing";
}

export function getProductRouteDefinition(
  routeId: ProductRouteId,
): ProductRouteDefinition {
  return productRouteDefinitions[routeId];
}

export function isAdminPath(pathname: string) {
  return getNormalizedPathSegments(pathname)[0] === getCanonicalPathHead(ADMIN_PATH);
}

export function getAdminAppUrl(options?: { preferFallback?: boolean }) {
  return buildAdminEntryUrl(
    options?.preferFallback
      ? configuredAdminAppFallbackUrl
      : configuredAdminAppUrl,
  );
}

export function resolveAdminSectionFromPath(pathname: string): AdminSectionId {
  const pathSegments = getNormalizedPathSegments(pathname);

  if (pathSegments[0] !== getCanonicalPathHead(ADMIN_PATH)) {
    return "review";
  }

  const sectionCandidate = pathSegments[1] ?? "review";

  if (!adminSectionRoutes.has(sectionCandidate)) {
    return "review";
  }

  return sectionCandidate as AdminSectionId;
}

export function getAdminSectionPath(sectionId: AdminSectionId) {
  return `${ADMIN_PATH}/${sectionId}`;
}

export function getAdminSectionUrl(
  sectionId: AdminSectionId,
  options?: AdminSectionUrlOptions,
) {
  const searchParams = new URLSearchParams();

  if (options?.tab && workspaceTabRoutes.has(options.tab)) {
    searchParams.set("tab", options.tab);
  }

  const packetId = normalizeAdminPacketId(options?.packetId);
  if (packetId) {
    searchParams.set("packet", packetId);
  }

  if (
    options?.queueFilters?.page !== undefined &&
    options.queueFilters.page > 1
  ) {
    searchParams.set("page", String(Math.trunc(options.queueFilters.page)));
  }

  if (options?.queueFilters?.stage_name) {
    searchParams.set("stage", options.queueFilters.stage_name);
  }

  if (options?.queueFilters?.source) {
    searchParams.set("source", options.queueFilters.source);
  }

  if (options?.queueFilters?.status) {
    searchParams.set("status", options.queueFilters.status);
  }

  if (options?.queueFilters?.assigned_user_email) {
    searchParams.set("assignment", options.queueFilters.assigned_user_email);
  }

  if (options?.queueFilters?.classification_key) {
    searchParams.set("classification", options.queueFilters.classification_key);
  }

  if (options?.queueFilters?.document_type_key) {
    searchParams.set("documentType", options.queueFilters.document_type_key);
  }

  if (options?.queueFilters?.min_queue_age_hours !== undefined) {
    searchParams.set(
      "minAgeHours",
      String(options.queueFilters.min_queue_age_hours),
    );
  }

  const search = searchParams.toString();
  return `${getAdminSectionPath(sectionId)}${search ? `?${search}` : ""}`;
}

export function resolveAdminWorkspaceTabFromSearch(
  search: string,
): WorkspaceTabId | null {
  const tabCandidate = new URLSearchParams(search).get("tab")?.trim().toLowerCase();

  if (!tabCandidate || !workspaceTabRoutes.has(tabCandidate)) {
    return null;
  }

  return tabCandidate as WorkspaceTabId;
}

export function resolveAdminPacketIdFromSearch(search: string) {
  return normalizeAdminPacketId(new URLSearchParams(search).get("packet"));
}

export function resolveAdminQueueFiltersFromSearch(
  search: string,
): AdminQueueFilterUrlState {
  const searchParams = new URLSearchParams(search);
  const queueFilters: AdminQueueFilterUrlState = {};

  const page = normalizeAdminSearchNumber(searchParams.get("page"));
  if (page !== undefined && page > 1) {
    queueFilters.page = Math.trunc(page);
  }

  const assignedUserEmail = normalizeAdminSearchText(
    searchParams.get("assignment"),
  );
  if (assignedUserEmail) {
    queueFilters.assigned_user_email = assignedUserEmail;
  }

  const classificationKey = normalizeAdminSearchText(
    searchParams.get("classification"),
  );
  if (classificationKey) {
    queueFilters.classification_key = classificationKey;
  }

  const documentTypeKey = normalizeAdminSearchText(
    searchParams.get("documentType"),
  );
  if (documentTypeKey) {
    queueFilters.document_type_key = documentTypeKey;
  }

  const minQueueAgeHours = normalizeAdminSearchNumber(
    searchParams.get("minAgeHours"),
  );
  if (minQueueAgeHours !== undefined) {
    queueFilters.min_queue_age_hours = minQueueAgeHours;
  }

  const source = normalizeAdminSearchText(searchParams.get("source"));
  if (source) {
    queueFilters.source = source;
  }

  const stageName = normalizeAdminSearchText(searchParams.get("stage"));
  if (stageName) {
    queueFilters.stage_name = stageName;
  }

  const status = normalizeAdminSearchText(searchParams.get("status"));
  if (status) {
    queueFilters.status = status;
  }

  return queueFilters;
}

export function isConfiguredAdminOrigin(origin: string) {
  const normalizedOrigin = getNormalizedOrigin(origin);

  return (
    normalizedOrigin === getNormalizedOrigin(configuredAdminAppUrl) ||
    normalizedOrigin === getNormalizedOrigin(configuredAdminAppFallbackUrl)
  );
}

export function shouldRenderProtectedApp(
  pathname: string,
  origin: string,
  mode: AppMode,
) {
  if (mode === "live") {
    return true;
  }

  return isAdminPath(pathname) || isConfiguredAdminOrigin(origin);
}

export function resolveProductRouteFromLocation(
  pathname: string,
  hash: string,
  origin: string,
  mode: AppMode,
): ProductRouteId {
  if (shouldRenderProtectedApp(pathname, origin, mode)) {
    return "admin";
  }

  return resolvePublicAppRoute(pathname, hash);
}

export function getAdminNavigationTarget(currentOrigin: string) {
  if (isConfiguredAdminOrigin(currentOrigin)) {
    return {
      href: ADMIN_PATH,
      isExternal: false,
    };
  }

  return {
    href: getAdminAppUrl(),
    isExternal: true,
  };
}

export function getPublicLandingTarget(
  currentOrigin: string,
  route: PublicAppRoute = "home",
) {
  const path = getPublicRoutePath(route);
  if (!isConfiguredAdminOrigin(currentOrigin)) {
    return { href: path, isExternal: false };
  }

  const trimmedSiteUrl = configuredPublicSiteUrl.replace(/\/+$/, "");
  return {
    href: `${trimmedSiteUrl}${path}`,
    isExternal: true,
  };
}

export function getPublicRoutePath(route: PublicAppRoute) {
  return productRouteDefinitions[route].path;
}

export function getDemoPath(route: SimulationRoute) {
  return route === "landing" ? DEMO_PATH : `${DEMO_PATH}/${route}`;
}

function updateAppPath(
  nextPath: string,
  historyMode: "push" | "replace" = "push",
) {
  const normalizedPath = nextPath.startsWith("/") ? nextPath : `/${nextPath}`;
  const nextLocation = new URL(normalizedPath, window.location.origin);
  const nextHash = nextLocation.hash;
  const nextPathSearchHash =
    `${nextLocation.pathname}${nextLocation.search}${nextHash}`;
  const currentPathAndSearch = `${window.location.pathname}${window.location.search}`;
  const nextPathAndSearch = `${nextLocation.pathname}${nextLocation.search}`;

  if (
    currentPathAndSearch === nextPathAndSearch &&
    window.location.hash === nextHash &&
    nextHash.length === 0
  ) {
    return;
  }

  if (historyMode === "replace") {
    window.history.replaceState({}, "", nextPathSearchHash);
  } else {
    window.history.pushState({}, "", nextPathSearchHash);
  }
  window.dispatchEvent(new PopStateEvent("popstate"));

  if (nextHash.length > 1) {
    const anchorId = nextHash.slice(1);
    requestAnimationFrame(() => {
      const target = document.getElementById(anchorId);
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
}

export function navigateToAppPath(nextPath: string) {
  updateAppPath(nextPath, "push");
}

export function navigateToAdminSection(
  sectionId: AdminSectionId,
  options?: AdminSectionUrlOptions,
) {
  navigateToAppPath(getAdminSectionUrl(sectionId, options));
}

export function replaceAdminSection(
  sectionId: AdminSectionId,
  options?: AdminSectionUrlOptions,
) {
  updateAppPath(getAdminSectionUrl(sectionId, options), "replace");
}
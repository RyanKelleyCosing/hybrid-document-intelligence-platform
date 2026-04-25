/**
 * Centralized feature-flag boot module.
 *
 * Reads every public feature toggle from `import.meta.env` once at module load
 * and freezes the result so the rest of the SPA gets a consistent view of which
 * experiments are on. Components SHOULD prefer `getFeatureFlag` over reading
 * `import.meta.env` directly so flag rollouts can be inspected from one file.
 *
 * Runtime override (admin-only):
 *   The admin route may persist a `docint-feature-overrides` entry in
 *   `localStorage` (JSON object of flag-name -> boolean). Overrides are applied
 *   only when `getFeatureFlag` is called with `{ allowOverride: true }` or when
 *   the document URL resolves to the admin route (`pathname` starts with
 *   `/admin/` or location is on the admin host). Overrides intentionally do NOT
 *   leak to the public surfaces.
 */

import { parseFeatureFlag } from "./components/securityPostureFormatters";

export type FeatureFlagName =
  | "publicSecurityEnrichmentEnabled"
  | "publicSecurityGlobeEnabled";

interface FeatureFlagDefinition {
  readonly defaultValue: boolean;
  readonly envKey: keyof ImportMetaEnv;
}

const FEATURE_FLAG_DEFINITIONS: Readonly<Record<FeatureFlagName, FeatureFlagDefinition>> = {
  publicSecurityEnrichmentEnabled: {
    defaultValue: true,
    envKey: "VITE_PUBLIC_SECURITY_ENRICHMENT_ENABLED",
  },
  publicSecurityGlobeEnabled: {
    defaultValue: true,
    envKey: "VITE_PUBLIC_SECURITY_GLOBE_ENABLED",
  },
};

const FEATURE_OVERRIDE_STORAGE_KEY = "docint-feature-overrides";

function snapshotBootFlags(): Readonly<Record<FeatureFlagName, boolean>> {
  const env = (import.meta.env || {}) as ImportMetaEnv;
  const snapshot = {} as Record<FeatureFlagName, boolean>;
  for (const flagName of Object.keys(FEATURE_FLAG_DEFINITIONS) as FeatureFlagName[]) {
    const definition = FEATURE_FLAG_DEFINITIONS[flagName];
    const rawValue = env[definition.envKey];
    snapshot[flagName] = parseFeatureFlag(rawValue, definition.defaultValue);
  }
  return Object.freeze(snapshot);
}

const BOOT_FLAGS = snapshotBootFlags();

function isAdminRouteContext(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const { pathname, hostname } = window.location;
  if (pathname.startsWith("/admin/") || pathname === "/admin") {
    return true;
  }
  return hostname.startsWith("admin.") || hostname.startsWith("admin-");
}

function readOverrideMap(): Record<string, unknown> {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const rawValue = window.localStorage.getItem(FEATURE_OVERRIDE_STORAGE_KEY);
    if (!rawValue) {
      return {};
    }
    const parsedValue = JSON.parse(rawValue);
    if (parsedValue && typeof parsedValue === "object" && !Array.isArray(parsedValue)) {
      return parsedValue as Record<string, unknown>;
    }
  } catch {
    return {};
  }
  return {};
}

export interface FeatureFlagLookupOptions {
  /** Force the override map to be consulted even outside the admin route. */
  readonly allowOverride?: boolean;
}

export function getFeatureFlag(
  flagName: FeatureFlagName,
  options: FeatureFlagLookupOptions = {},
): boolean {
  const bootValue = BOOT_FLAGS[flagName];
  if (!options.allowOverride && !isAdminRouteContext()) {
    return bootValue;
  }
  const overrideMap = readOverrideMap();
  const overrideValue = overrideMap[flagName];
  if (typeof overrideValue === "boolean") {
    return overrideValue;
  }
  return bootValue;
}

export function getBootFeatureFlags(): Readonly<Record<FeatureFlagName, boolean>> {
  return BOOT_FLAGS;
}

export function setFeatureFlagOverride(
  flagName: FeatureFlagName,
  value: boolean | null,
): void {
  if (typeof window === "undefined") {
    return;
  }
  const overrideMap = readOverrideMap();
  if (value === null) {
    delete overrideMap[flagName];
  } else {
    overrideMap[flagName] = value;
  }
  window.localStorage.setItem(FEATURE_OVERRIDE_STORAGE_KEY, JSON.stringify(overrideMap));
}

export const FEATURE_OVERRIDE_STORAGE_KEY_FOR_TESTS = FEATURE_OVERRIDE_STORAGE_KEY;

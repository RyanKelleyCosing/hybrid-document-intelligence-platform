import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  FEATURE_OVERRIDE_STORAGE_KEY_FOR_TESTS,
  getBootFeatureFlags,
  getFeatureFlag,
  setFeatureFlagOverride,
} from "./featureFlags";

const originalLocation = window.location;

function setLocationPathname(pathname: string, hostname = "localhost") {
  // jsdom forbids assigning to window.location directly; replace the descriptor.
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...originalLocation, hostname, pathname },
  });
}

describe("featureFlags", () => {
  beforeEach(() => {
    window.localStorage.removeItem(FEATURE_OVERRIDE_STORAGE_KEY_FOR_TESTS);
  });

  afterEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });

  it("returns the boot snapshot for known flags", () => {
    const snapshot = getBootFeatureFlags();
    expect(snapshot).toHaveProperty("publicSecurityEnrichmentEnabled");
    expect(snapshot).toHaveProperty("publicSecurityGlobeEnabled");
    expect(typeof snapshot.publicSecurityEnrichmentEnabled).toBe("boolean");
  });

  it("ignores localStorage overrides on public routes", () => {
    setLocationPathname("/security");
    setFeatureFlagOverride("publicSecurityGlobeEnabled", false);
    expect(getFeatureFlag("publicSecurityGlobeEnabled")).toBe(
      getBootFeatureFlags().publicSecurityGlobeEnabled,
    );
  });

  it("applies localStorage overrides on the admin route", () => {
    setLocationPathname("/admin/queue");
    setFeatureFlagOverride("publicSecurityGlobeEnabled", false);
    expect(getFeatureFlag("publicSecurityGlobeEnabled")).toBe(false);
  });

  it("applies overrides on admin host even from a non-admin pathname", () => {
    setLocationPathname("/", "admin.ryancodes.online");
    setFeatureFlagOverride("publicSecurityEnrichmentEnabled", false);
    expect(getFeatureFlag("publicSecurityEnrichmentEnabled")).toBe(false);
  });

  it("returns the boot value when an override is cleared", () => {
    setLocationPathname("/admin/queue");
    setFeatureFlagOverride("publicSecurityGlobeEnabled", false);
    setFeatureFlagOverride("publicSecurityGlobeEnabled", null);
    expect(getFeatureFlag("publicSecurityGlobeEnabled")).toBe(
      getBootFeatureFlags().publicSecurityGlobeEnabled,
    );
  });

  it("honors allowOverride even outside the admin route", () => {
    setLocationPathname("/security");
    setFeatureFlagOverride("publicSecurityGlobeEnabled", false);
    expect(getFeatureFlag("publicSecurityGlobeEnabled", { allowOverride: true })).toBe(false);
  });
});

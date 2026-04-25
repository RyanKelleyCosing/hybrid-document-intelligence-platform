import { describe, expect, it } from "vitest";

import {
  ADMIN_PATH,
  COST_PATH,
  DEMO_PATH,
  HOME_PATH,
  SECURITY_PATH,
  type AdminQueueFilterUrlState,
  getAdminAppUrl,
  getAdminNavigationTarget,
  getAdminSectionPath,
  getAdminSectionUrl,
  getDemoPath,
  getProductRouteDefinition,
  getPublicRoutePath,
  resolveAdminPacketIdFromSearch,
  resolveAdminQueueFiltersFromSearch,
  resolveAdminWorkspaceTabFromSearch,
  getSimulationRouteFromLocation,
  resolveAdminSectionFromPath,
  resolveProductRouteFromLocation,
  resolvePublicAppRoute,
  shouldRenderProtectedApp,
} from "./appRoutes";

describe("appRoutes", () => {
  it("prefers direct security and cost paths", () => {
    expect(resolvePublicAppRoute("/security", "")).toBe("security");
    expect(resolvePublicAppRoute("/cost", "")).toBe("cost");
  });

  it("maps demo paths and legacy simulation hashes to the demo surface", () => {
    expect(resolvePublicAppRoute("/demo", "")).toBe("demo");
    expect(resolvePublicAppRoute("/", "#/simulation/review")).toBe("demo");
    expect(resolvePublicAppRoute("/", "#/processing")).toBe("demo");
  });

  it("resolves simulation subroutes from paths before legacy hashes", () => {
    expect(getSimulationRouteFromLocation("/demo/review", "")).toBe("review");
    expect(getSimulationRouteFromLocation("/demo", "")).toBe("landing");
    expect(getSimulationRouteFromLocation("/", "#/simulation/accounts")).toBe(
      "accounts",
    );
    expect(getSimulationRouteFromLocation("/", "#/ops")).toBe("ops");
  });

  it("builds canonical demo paths", () => {
    expect(getDemoPath("landing")).toBe(DEMO_PATH);
    expect(getDemoPath("review")).toBe("/demo/review");
  });

  it("exposes canonical product route metadata", () => {
    expect(getPublicRoutePath("home")).toBe(HOME_PATH);
    expect(getPublicRoutePath("security")).toBe(SECURITY_PATH);
    expect(getPublicRoutePath("cost")).toBe(COST_PATH);
    expect(getPublicRoutePath("demo")).toBe(DEMO_PATH);
    expect(getProductRouteDefinition("admin").path).toBe(ADMIN_PATH);
    expect(getProductRouteDefinition("admin").isPubliclyNavigable).toBe(false);
    expect(getProductRouteDefinition("admin").label).toBe("Live Admin");
  });

  it("builds canonical admin URLs for the protected host and fallback host", () => {
    expect(getAdminAppUrl()).toBe("https://admin.ryancodes.online/admin");
    expect(getAdminAppUrl({ preferFallback: true })).toBe(
      "https://admin-doc-test-nwigok.azurewebsites.net/admin",
    );
  });

  it("resolves admin section subroutes and builds canonical admin section paths", () => {
    expect(resolveAdminSectionFromPath("/admin")).toBe("review");
    expect(resolveAdminSectionFromPath("/admin/viewer")).toBe("viewer");
    expect(resolveAdminSectionFromPath("/admin/unknown")).toBe("review");
    expect(getAdminSectionPath("review")).toBe("/admin/review");
    expect(getAdminSectionPath("rules_doctypes")).toBe(
      "/admin/rules_doctypes",
    );
  });

  it("supports deep-linkable workspace tab, packet, and queue-filter queries for admin sections", () => {
    const expectedQueueFilters: AdminQueueFilterUrlState = {
      assigned_user_email: "ops@example.com",
      classification_key: "bank_correspondence",
      document_type_key: "bank_statement",
      min_queue_age_hours: 4.5,
      page: 3,
      source: "azure_blob",
      stage_name: "ocr",
      status: "failed",
    };

    expect(resolveAdminWorkspaceTabFromSearch("")).toBeNull();
    expect(resolveAdminWorkspaceTabFromSearch("?tab=ocr")).toBe("ocr");
    expect(resolveAdminWorkspaceTabFromSearch("?tab=unknown")).toBeNull();
    expect(resolveAdminPacketIdFromSearch("")).toBeNull();
    expect(resolveAdminPacketIdFromSearch("?packet=pkt_001")).toBe("pkt_001");
    expect(resolveAdminPacketIdFromSearch("?packet=   ")).toBeNull();
    expect(
      resolveAdminQueueFiltersFromSearch(
        "?page=3&stage=ocr&source=azure_blob&status=failed&assignment=ops@example.com&classification=bank_correspondence&documentType=bank_statement&minAgeHours=4.5",
      ),
    ).toEqual(expectedQueueFilters);
    expect(getAdminSectionUrl("review")).toBe("/admin/review");
    expect(getAdminSectionUrl("review", { tab: "audit" })).toBe(
      "/admin/review?tab=audit",
    );
    expect(
      getAdminSectionUrl("review", { packetId: "pkt_001", tab: "audit" }),
    ).toBe("/admin/review?tab=audit&packet=pkt_001");
    expect(
      getAdminSectionUrl("review", {
        packetId: "pkt_001",
        queueFilters: expectedQueueFilters,
        tab: "audit",
      }),
    ).toBe(
      "/admin/review?tab=audit&packet=pkt_001&page=3&stage=ocr&source=azure_blob&status=failed&assignment=ops%40example.com&classification=bank_correspondence&documentType=bank_statement&minAgeHours=4.5",
    );
  });

  it("treats configured admin paths and origins as protected entry points", () => {
    expect(shouldRenderProtectedApp("/admin", "http://localhost:5173", "simulation")).toBe(true);
    expect(
      shouldRenderProtectedApp(
        "/",
        "https://admin.ryancodes.online",
        "simulation",
      ),
    ).toBe(true);
    expect(
      resolveProductRouteFromLocation(
        "/admin/review",
        "",
        "http://localhost:5173",
        "simulation",
      ),
    ).toBe("admin");
    expect(
      resolveProductRouteFromLocation(
        "/",
        "",
        "https://admin-doc-test-nwigok.azurewebsites.net",
        "simulation",
      ),
    ).toBe("admin");
  });

  it("returns an internal admin path on the protected host and an external URL elsewhere", () => {
    expect(getAdminNavigationTarget("https://admin.ryancodes.online")).toEqual({
      href: ADMIN_PATH,
      isExternal: false,
    });
    expect(getAdminNavigationTarget("https://www.ryancodes.online")).toEqual({
      href: "https://admin.ryancodes.online/admin",
      isExternal: true,
    });
  });
});
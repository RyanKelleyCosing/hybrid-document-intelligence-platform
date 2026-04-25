import { describe, expect, it } from "vitest";

import { simulationRouteOrder, simulationViews } from "./simulationData";

describe("simulationViews panelMetrics shape", () => {
  it("declares exactly three panel metrics on every simulation view", () => {
    for (const route of simulationRouteOrder) {
      const view = simulationViews[route];
      expect(view, `simulationViews missing entry for route ${route}`).toBeDefined();
      expect(
        view.panelMetrics,
        `simulationViews[${route}].panelMetrics must be present`,
      ).toBeDefined();
      expect(
        view.panelMetrics?.length,
        `simulationViews[${route}].panelMetrics must have exactly 3 entries`,
      ).toBe(3);
    }
  });

  it("populates label, value, and detail strings on every panel metric entry", () => {
    for (const route of simulationRouteOrder) {
      const metrics = simulationViews[route].panelMetrics ?? [];
      metrics.forEach((metric, index) => {
        const where = `simulationViews[${route}].panelMetrics[${index}]`;
        expect(metric.label.trim(), `${where}.label must be non-empty`).not.toBe("");
        expect(metric.value.trim(), `${where}.value must be non-empty`).not.toBe("");
        expect(metric.detail.trim(), `${where}.detail must be non-empty`).not.toBe("");
      });
    }
  });
});


describe("simulationViews demo hero snapshot", () => {
  it("locks the demo route landing hero title and description copy", () => {
    const landing = simulationViews.landing;

    expect(landing.title).toBe(
      "See how the document workflow is wired before the first live run.",
    );
    expect(landing.description.startsWith(
      "A guided view of how inbound document packets move",
    )).toBe(true);
    expect(landing.panelEyebrow).toBe("Production-style simulation");
    expect(landing.panelTitle).toBe(
      "Watched sources, staged packets, disabled controls",
    );
  });
});

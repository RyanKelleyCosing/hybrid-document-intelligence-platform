import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SecurityTelemetryGlobe } from "./SecurityTelemetryGlobe";

describe("SecurityTelemetryGlobe", () => {
  it("renders coarse geography markers and labels", () => {
    render(
      <SecurityTelemetryGlobe
        aggregateCounts={[
          { count: 7, label: "US / Ohio" },
          { count: 2, label: "CA" },
        ]}
        currentLocation="US / Ohio"
        recentActivity={[
          {
            geography_bucket: "US / Ohio",
            recorded_at_utc: "2026-04-16T12:18:00Z",
            route: "security",
            session_label: "session-1a2b3c4d",
            site_mode: "security",
          },
        ]}
      />,
    );

    expect(screen.getByLabelText(/Coarse geography globe/i)).toBeInTheDocument();
    expect(screen.getAllByText(/US \/ Ohio/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/^CA$/i)).toBeInTheDocument();
    expect(screen.getAllByText(/^Current viewer$/i).length).toBeGreaterThan(0);
  });
});
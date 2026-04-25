import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("./LiveReviewWorkbench", () => ({
  LiveReviewWorkbench: () => <div data-testid="live-review-workbench" />,
}));

vi.mock("../appMode", () => ({
  appMode: "live",
  isSimulationMode: false,
}));

import { ProtectedAppLayout } from "./ProtectedAppLayout";

describe("ProtectedAppLayout", () => {
  it("renders the lazy workbench once the chunk resolves", async () => {
    render(<ProtectedAppLayout />);

    expect(
      await screen.findByTestId("live-review-workbench"),
    ).toBeInTheDocument();
  });
});

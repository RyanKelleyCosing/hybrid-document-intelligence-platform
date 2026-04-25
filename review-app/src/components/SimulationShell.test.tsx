import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SimulationShell } from "./SimulationShell";

vi.mock("../api/publicTrafficApi", () => ({
  getPublicTrafficSessionId: () => "simulation-session-test",
  recordPublicTrafficEvent: vi.fn(),
}));

vi.mock("../api/simulationReviewApi", () => ({
  listSimulationReviewItems: vi.fn(async () => []),
}));

describe("SimulationShell", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.history.replaceState({}, "", "/demo");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.sessionStorage.clear();
    window.history.replaceState({}, "", "/");
  });

  it("renders the landing view and advances into the intake route", async () => {
    render(<SimulationShell />);

    expect(
      screen.getByRole("heading", {
        name: /See how the document workflow is wired before the first live run/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Intake$/i })).toBeDisabled();

    fireEvent.click(screen.getAllByRole("button", { name: /Begin simulation/i })[0]);

    expect(
      await screen.findByRole("heading", {
        name: /Watched intake channels and staged document packets/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Recurring collector drop/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Packet loaded/i).length).toBeGreaterThan(0);
    expect(window.location.pathname).toBe("/demo/intake");
  });
});
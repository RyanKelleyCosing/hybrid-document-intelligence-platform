import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AdminPrivateDemoRequest } from "./AdminPrivateDemoRequest";

describe("AdminPrivateDemoRequest", () => {
  it("renders the request form with the expected fields and submit button", () => {
    render(<AdminPrivateDemoRequest />);

    expect(
      screen.getByRole("heading", { name: /Request a private admin demo/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Your name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Work email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Company \/ team/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Primary use case/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Estimated monthly document volume/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Send private demo request/i }),
    ).toBeInTheDocument();
  });

  it("renders Back to public landing escape links pointing at /", () => {
    render(<AdminPrivateDemoRequest />);

    const escapes = screen
      .getAllByRole("link", { name: /Back to public landing/i })
      .map((node) => node.getAttribute("href"));
    expect(escapes.length).toBeGreaterThanOrEqual(2);
    expect(escapes.every((href) => href === "/")).toBe(true);
  });

  it("opens a prefilled mailto link on submit and surfaces a confirmation", () => {
    const originalLocation = window.location;
    const assignedHrefs: string[] = [];
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        ...originalLocation,
        get href() {
          return assignedHrefs[assignedHrefs.length - 1] || "";
        },
        set href(value: string) {
          assignedHrefs.push(value);
        },
      },
    });

    render(<AdminPrivateDemoRequest />);

    fireEvent.change(screen.getByLabelText(/Your name/i), {
      target: { value: "Alex Reviewer" },
    });
    fireEvent.change(screen.getByLabelText(/Work email/i), {
      target: { value: "alex@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/Company \/ team/i), {
      target: { value: "Northwind Loans" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Send private demo request/i }),
    );

    expect(assignedHrefs).toHaveLength(1);
    expect(assignedHrefs[0]).toMatch(/^mailto:/);
    expect(assignedHrefs[0]).toContain("Northwind%20Loans");
    expect(assignedHrefs[0]).toContain("alex%40example.com");
    expect(screen.getByRole("status")).toHaveTextContent(/your mail client should now be open/i);

    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
    vi.restoreAllMocks();
  });
});

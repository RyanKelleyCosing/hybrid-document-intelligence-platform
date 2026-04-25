import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProductShellHeader } from "./ProductShellHeader";

describe("ProductShellHeader", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/security");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState({}, "", "/");
  });

  it("groups public routes separately from the live admin entry", () => {
    render(<ProductShellHeader activeRoute="security" mode="simulation" />);

    expect(screen.getByText(/^Public briefing$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Guided walkthrough$/i)).toBeInTheDocument();
    expect(screen.getByText(/Live admin entry/i)).toBeInTheDocument();

    const adminLink = screen.getByRole("link", { name: /^Live Admin$/i });
    expect(adminLink).toHaveAttribute("href", "https://admin.ryancodes.online/admin");
    expect(
      screen.getByText(/real operator path.*not another public demo tab/i),
    ).toBeInTheDocument();
  });

  it("toggles the grouped navigation container", () => {
    render(<ProductShellHeader activeRoute="home" mode="simulation" />);

    const toggleButton = screen.getByRole("button", {
      name: /Show route directory/i,
    });
    const navGroups = document.getElementById("product-nav-groups");

    expect(toggleButton).toHaveAttribute("aria-expanded", "false");
    expect(navGroups).toHaveAttribute("data-expanded", "false");

    fireEvent.click(toggleButton);

    expect(toggleButton).toHaveAttribute("aria-expanded", "true");
    expect(navGroups).toHaveAttribute("data-expanded", "true");
    expect(screen.getByRole("button", { name: /Hide route directory/i })).toBeInTheDocument();
  });

  it("uses per-group disclosures to keep non-active route groups denser by default", () => {
    render(<ProductShellHeader activeRoute="security" mode="simulation" />);

    const briefingToggle = screen.getByRole("button", {
      name: /Public briefing routes/i,
    });
    const walkthroughToggle = screen.getByRole("button", {
      name: /Guided walkthrough routes/i,
    });
    const walkthroughBody = document.getElementById(
      "product-route-group-body-walkthrough",
    );

    expect(briefingToggle).toHaveAttribute("aria-expanded", "true");
    expect(walkthroughToggle).toHaveAttribute("aria-expanded", "false");
    expect(walkthroughBody).toHaveAttribute("data-expanded", "false");

    fireEvent.click(walkthroughToggle);

    expect(walkthroughToggle).toHaveAttribute("aria-expanded", "true");
    expect(walkthroughBody).toHaveAttribute("data-expanded", "true");
  });
});
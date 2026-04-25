import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProtectedSiteLayout } from "./ProtectedSiteLayout";
import { PublicSiteLayout } from "./PublicSiteLayout";

describe("Site layouts", () => {
  it("applies the active public route as the theme variant hook", () => {
    const { container } = render(
      <PublicSiteLayout activeRoute="security">
        <div>Security route body</div>
      </PublicSiteLayout>,
    );

    expect(container.firstElementChild).toHaveAttribute(
      "data-route-theme",
      "security",
    );
  });

  it("pins the protected layout to the admin theme variant", () => {
    const { container } = render(
      <ProtectedSiteLayout navigation={<nav>Admin nav</nav>}>
        <div>Admin route body</div>
      </ProtectedSiteLayout>,
    );

    expect(container.firstElementChild).toHaveAttribute(
      "data-route-theme",
      "admin",
    );
  });
});
import { resolvePublicAppRoute } from "../appRoutes";
import { CostOverviewSite } from "./CostOverviewSite";
import { PublicLandingShell } from "./PublicLandingShell";
import { SecurityPostureSite } from "./SecurityPostureSite";
import { SimulationShell } from "./SimulationShell";

type PublicAppLayoutProps = {
  hash: string;
  pathname: string;
};

export function PublicAppLayout({
  hash,
  pathname,
}: PublicAppLayoutProps) {
  switch (resolvePublicAppRoute(pathname, hash)) {
    case "security":
      return <SecurityPostureSite />;
    case "cost":
      return <CostOverviewSite />;
    case "demo":
      return <SimulationShell />;
    case "home":
    default:
      return <PublicLandingShell />;
  }
}
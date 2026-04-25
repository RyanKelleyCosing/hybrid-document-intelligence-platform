import { useEffect, useState } from "react";

import { appMode } from "./appMode";
import { resolveProductRouteFromLocation } from "./appRoutes";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ProtectedAppLayout } from "./components/ProtectedAppLayout";
import { PublicAppLayout } from "./components/PublicAppLayout";

function App() {
  const [locationSnapshot, setLocationSnapshot] = useState(() => ({
    hash: window.location.hash,
    origin: window.location.origin,
    pathname: window.location.pathname,
  }));

  useEffect(() => {
    const handleLocationChange = () => {
      setLocationSnapshot({
        hash: window.location.hash,
        origin: window.location.origin,
        pathname: window.location.pathname,
      });
    };

    window.addEventListener("hashchange", handleLocationChange);
    window.addEventListener("popstate", handleLocationChange);
    return () => {
      window.removeEventListener("hashchange", handleLocationChange);
      window.removeEventListener("popstate", handleLocationChange);
    };
  }, []);

  const isAdminRoute =
    resolveProductRouteFromLocation(
      locationSnapshot.pathname,
      locationSnapshot.hash,
      locationSnapshot.origin,
      appMode,
    ) === "admin";

  return (
    <ErrorBoundary>
      {isAdminRoute ? (
        <ProtectedAppLayout />
      ) : (
        <PublicAppLayout
          hash={locationSnapshot.hash}
          pathname={locationSnapshot.pathname}
        />
      )}
    </ErrorBoundary>
  );
}

export default App;
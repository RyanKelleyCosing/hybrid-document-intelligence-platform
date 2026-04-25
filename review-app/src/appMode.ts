export type AppMode = "live" | "simulation";

function normalizeAppMode(value: string | undefined): AppMode {
  if (import.meta.env.MODE === "playwright") {
    return "live";
  }

  return value?.trim().toLowerCase() === "live" ? "live" : "simulation";
}

export const appMode = normalizeAppMode(import.meta.env.VITE_APP_MODE);

export const isSimulationMode = appMode === "simulation";
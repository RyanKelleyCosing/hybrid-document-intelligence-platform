export type LiveSession = {
  authenticated: boolean;
  authorized: boolean;
  email: string | null;
  identityProvider: string | null;
};

type LiveSessionErrorPayload = {
  message?: string;
  status?: string;
};

async function parseLiveSession(response: Response): Promise<LiveSession> {
  if (response.ok) {
    return (await response.json()) as LiveSession;
  }

  let errorMessage = `Request failed with status ${response.status}`;

  try {
    const payload = (await response.json()) as LiveSessionErrorPayload;
    if (typeof payload.message === "string" && payload.message.length > 0) {
      errorMessage = payload.message;
    }
  } catch {
    // Keep the fallback error message.
  }

  throw new Error(errorMessage);
}

export async function getLiveSession(): Promise<LiveSession> {
  const response = await fetch("/api/session", {
    headers: { Accept: "application/json" },
  });

  return parseLiveSession(response);
}
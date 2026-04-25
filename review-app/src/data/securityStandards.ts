/**
 * Static, build-time mapping of platform controls onto reputable external
 * security standards. No runtime egress: every entry is curated against the
 * pinned source and refreshed only on a deliberate dependency bump.
 *
 * Sources (license / version):
 *  - OWASP Top 10 (2021) — https://owasp.org/Top10/ (CC BY-SA 4.0)
 *  - NIST Cybersecurity Framework 2.0 (Feb 2024) —
 *    https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf (public domain)
 *  - NIST SP 800-53 Rev.5 — https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53r5.pdf
 *    (public domain)
 *
 * Each "platformControl" string describes a real platform layer this stack
 * already enforces or wires (Entra ID, Managed Identity, Key Vault, App
 * Service auth, function-level auth, route boundary, etc.). Avoid speculative
 * controls — only list controls that the codebase or infra demonstrably
 * implements.
 */

export type OwaspTop10Entry = {
  id: string;
  category: string;
  platformControl: string;
};

export const owaspTop10: ReadonlyArray<OwaspTop10Entry> = [
  {
    id: "A01",
    category: "Broken access control",
    platformControl:
      "Protected admin host requires Entra ID sign-in; public routes are read-only and never expose mutate/approve/delete actions.",
  },
  {
    id: "A02",
    category: "Cryptographic failures",
    platformControl:
      "All public-facing traffic terminates on HTTPS at Static Web Apps + Azure Functions; secrets live in Key Vault, never in repo or in the SPA bundle.",
  },
  {
    id: "A03",
    category: "Injection",
    platformControl:
      "Pydantic models validate every public request body and header; no string-concatenated SQL or shell calls in the public traffic, review, or cost endpoints.",
  },
  {
    id: "A04",
    category: "Insecure design",
    platformControl:
      "Trust-boundary documented: public surface is sanitized + cached; private operator data and Defender/Graph alerts stay behind the protected admin host.",
  },
  {
    id: "A05",
    category: "Security misconfiguration",
    platformControl:
      "Bicep-deployed Function App + Storage with diagnostic settings, system-assigned managed identity, and explicit RBAC role assignments — no portal-only drift.",
  },
  {
    id: "A06",
    category: "Vulnerable and outdated components",
    platformControl:
      "Pinned dependencies in pyproject.toml + requirements.txt and review-app package.json; CI runs vitest + pytest on every change.",
  },
  {
    id: "A07",
    category: "Identification and authentication failures",
    platformControl:
      "Admin queue/review actions go through Entra ID auth on the protected host; the public site never accepts a credential.",
  },
  {
    id: "A08",
    category: "Software and data integrity failures",
    platformControl:
      "SWA + Functions deployments use Microsoft-issued tokens (no long-lived shared keys in source); zip-deploy uses az-managed credentials.",
  },
  {
    id: "A09",
    category: "Security logging and monitoring failures",
    platformControl:
      "Application Insights wired on the function app; structured logging on every public endpoint with sanitized client IP + user agent summary.",
  },
  {
    id: "A10",
    category: "Server-side request forgery",
    platformControl:
      "External enrichment calls (ipapi.is) use a fixed allow-listed base URL via settings; no caller-controlled URLs reach the function app.",
  },
];

export type NistCsfFunction = "Identify" | "Protect" | "Detect" | "Respond" | "Recover";

export type NistCsfEntry = {
  function: NistCsfFunction;
  outcome: string;
  platformControl: string;
};

export const nistCsf2: ReadonlyArray<NistCsfEntry> = [
  {
    function: "Identify",
    outcome: "Asset inventory and trust boundary",
    platformControl:
      "Bicep modules describe every Azure resource by name; the public surface and protected admin host are documented separately in the architecture map.",
  },
  {
    function: "Protect",
    outcome: "Identity, data, and platform protection",
    platformControl:
      "Managed identity + RBAC for Function → Storage / Key Vault; Entra ID on the admin host; public routes stay read-only by design.",
  },
  {
    function: "Detect",
    outcome: "Continuous monitoring",
    platformControl:
      "Application Insights traces and live `/api/health` polling on the public site; sanitized cadence + globe show traffic in near-real-time.",
  },
  {
    function: "Respond",
    outcome: "Incident response and communications",
    platformControl:
      "Public traffic alert email pipeline (with bot/self suppression + parsed client summary) plus structured log lines that include event_type, route, masked IP.",
  },
  {
    function: "Recover",
    outcome: "Backups and continuity",
    platformControl:
      "Stateless Function App + redeploy from versioned source; Static Web App ships from a deterministic build artifact and can be re-deployed in minutes.",
  },
];

export type NistSp80053Entry = {
  id: string;
  title: string;
  platformControl: string;
};

export const nistSp80053Highlights: ReadonlyArray<NistSp80053Entry> = [
  {
    id: "AC-2",
    title: "Account management",
    platformControl:
      "Admin reviewer accounts are managed in Entra ID; public routes have no account model and accept no credentials.",
  },
  {
    id: "AC-6",
    title: "Least privilege",
    platformControl:
      "Function App identity holds only the storage + Key Vault RBAC roles it needs; no Owner/Contributor at app-identity scope.",
  },
  {
    id: "AU-2",
    title: "Event logging",
    platformControl:
      "Structured logging on every public endpoint (event_type, route, masked client IP, user-agent summary) plus Application Insights traces.",
  },
  {
    id: "IR-4",
    title: "Incident handling",
    platformControl:
      "Public traffic alert emails fire on real visitor events with deny-list suppression for known bots and self-traffic IP prefixes.",
  },
  {
    id: "SC-7",
    title: "Boundary protection",
    platformControl:
      "Public surface terminates on HTTPS at Static Web Apps; only sanitized JSON crosses to the SPA. The admin host sits behind Entra auth on a separate boundary.",
  },
  {
    id: "SI-4",
    title: "System monitoring",
    platformControl:
      "Live cadence + globe + freshness indicators on `/security`, plus `/api/health` polling driven by `VITE_PUBLIC_HEALTH_POLL_MS`.",
  },
];

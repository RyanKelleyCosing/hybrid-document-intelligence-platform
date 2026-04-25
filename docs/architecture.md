# Architecture

This document describes the trust boundary, data flow, and component
responsibilities of the Hybrid Document Intelligence Platform at a level safe
for a public audience. It intentionally omits live resource names, tenant
identifiers, and operator-only telemetry surfaces.

## High-level shape

The platform is a serverless-first document ingestion and review pipeline. It
splits cleanly into three planes:

1. **Public plane** — anonymous, sanitized, read-only. Surfaces a landing
   page, a security posture page, a cost-transparency page, and a
   walkthrough/demo page. All payloads are filtered through dedicated
   sanitization formatters before they leave the function host.
2. **Protected plane** — operator-only. Sits behind Easy Auth on a separate
   admin host. Handles intake review, manual queue work, packet workspace
   inspection, and account-matching overrides. **No protected route is part
   of the public repo's runtime surface.**
3. **Background plane** — Durable Functions orchestrations and timers that
   normalize intake, run extraction adapters, persist operator state, and
   refresh public-facing rollups (cost, traffic cadence, security feeds).

## Components

### Front end (`review-app/`)

A Vite + React 19 SPA. The same build serves both the public and protected
hosts; route-level layout components (`PublicSiteLayout` /
`ProtectedSiteLayout`) gate which navigation, telemetry, and API calls a
visitor sees.

Key public-facing components:

- `PublicLandingShell` — landing page with the live API status pill.
- `SecurityPostureSite` — `/security` page. Renders the security globe,
  recent activity ticker, traffic cadence panel, NVD CVE feed, MSRC bulletin
  feed, and the OWASP / NIST CSF / NIST SP 800-53 standards mapping.
- `CostOverviewSite` — `/cost` page. Renders aggregated public-safe cost
  rollups with downloadable CSV / JSON exports.
- `SimulationShell` — `/demo` walkthrough.

### Function host (`function_app.py` + `src/document_intelligence/`)

Python 3.11 Azure Functions app. Public HTTP routes follow the
`/api/public-*` convention and are also documented in the OpenAPI builder
(`src/document_intelligence/api_contracts.py`). Every public route returns a
sanitized contract — the raw operator-only data never leaves the host.

Notable modules:

- `settings.py` — Pydantic v2 `AppSettings`. All knobs are explicit, typed,
  and validated; secrets come from app settings only, never from code.
- `public_traffic_metrics.py` — durable + in-memory hybrid store for
  sanitized public visit telemetry. Survives cold starts via blob-backed
  ndjson history.
- `public_cost_metrics.py` / `public_cost_refresh.py` — daily cost rollups
  with placeholder labels for line items.
- `traffic_alerts.py` — public-traffic alerting with two suppression layers:
  datacenter / VPN / Tor / hosting enrichment, and no-referrer deep links.
  Enrichment is fetched from ipapi.is (free tier, optional API key).
- `public_security_feeds.py` — cached NVD CVE + MSRC CVRF mirrors with
  stale-while-error fallback.
- `public_network_enrichment.py` — port-stripping + ipapi.is integration
  used by the traffic alerts pipeline and the public request-context probe.

### Storage and state

- **Azure Blob Storage** — durable history files (`public-security/`,
  `cost/`, telemetry rollups). Default 60-day retention.
- **Azure SQL** — operator-state system of record (account matches, packet
  workspace state, intake-source last-seen timestamps). Strictly behind the
  protected plane.
- **Cosmos DB** — retained for legacy manual-review compatibility and a
  future queue-cache. Not on the critical path for the public surface.

### Infrastructure (`infra/main.bicep`)

A single entry-point Bicep module provisions the storage account, optional
SFTP-enabled landing zone, Service Bus, optional Cosmos / Azure SQL,
optional Azure AI accounts, Key Vault, monitoring, and the Python Function
App. All parameter defaults use placeholder names like
`rg-doc-intel-<env>` and `func-doc-<env>-<suffix>`.

## Trust boundary

The single sentence to internalize:

> A response only leaves the public plane after passing through a
> sanitization formatter that strips operator identifiers, tenant ids, raw
> source IPs, and non-public cost line items.

Concretely:

- Public traffic events store a salted `session_hash` (64 chars) instead of
  raw IPs. The session label rendered on `/security` is the first 8 chars,
  so the server-side hash is never exposed.
- Cost rollups expose aggregate dollar amounts and category labels only.
  Resource IDs and subscription metadata stay server-side.
- The OpenAPI document served at `/api/public-openapi.json` is asserted by
  unit test to expose **only** the routes tagged `Public`. A regression
  there fails CI.

## Public deploy / mirror flow

This repository is a sanitized snapshot of an internal working tree. The
mirror cadence is:

1. Internal tree is the source of truth.
2. `scripts/mirror_to_public.ps1` (private repo only) stages an explicit
   allow-list of files and runs four sanitization regexes (real resource
   names, custom domains, self-IP / personal emails, GUIDs).
3. The script hard-fails on any hit. Only after a clean dry-run does the
   public repo get the new commit.

## What is intentionally out of scope here

- Defender for Cloud / Defender XDR alert wiring (requires tenant-private
  data; documented as protected-admin follow-up).
- DR drill automation.
- Azure AI Search indexing and retrieval layers.
- Live customer-shaped sample data — the public repo ships only synthetic
  Lorem-ipsum equivalents.

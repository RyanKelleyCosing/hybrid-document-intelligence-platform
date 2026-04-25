# Hybrid Document Intelligence Platform

Serverless-first document ingestion and review platform for high-volume scanned packets and bulk file drops. The public repo stays safe for GitHub by using synthetic sample data only while still demonstrating Azure Functions, Bicep, React, security gates, and hybrid Azure/AWS operator workflows.

## Current Status

- Azure Functions Durable workflow for request normalization, OCR/LLM extraction, account matching, and manual-review routing, with a synchronous fallback path for Flex-host debugging
- Source-aware prompt profile selection for banks, courts, collectors, utilities, healthcare, and generic correspondence
- Strict `.gitignore` baseline for keys, document payloads, OCR artifacts, and operational exports
- Core Azure Bicep foundation for storage, an opt-in SFTP-ready landing zone, Service Bus, optional Cosmos-backed queue-cache and legacy review storage, optional Azure SQL operator-state resources, optional Azure AI accounts, Key Vault, monitoring, and a Python Function App
- React and TypeScript review workbench wired to the live Functions review APIs instead of synthetic fixtures
- Azure Document Intelligence and Azure OpenAI adapters wired behind environment settings so the same workflow can run locally, fall back safely, or use deployed AI endpoints
- Azure SQL account matching and SQL-backed operator-state persistence wired into the backend workflow contract, with Cosmos retained only for legacy/manual-review compatibility and future queue-cache use
- Protected packet-workspace execution now covers classification, OCR, extraction, and recommendation, with SQL-backed classification-prior reuse ahead of Azure OpenAI fallback classification
- Protected intake-source execution now covers watched Azure Blob prefixes and configured folders, with SQL-backed last-seen, last-success, and last-error tracking around the normal packet staging path
- Archive handling now explicitly supports readable single-file ZIP64 packets and quarantines multipart or spanned ZIP sets as unsupported instead of trying partial reconstruction
- Synthetic workbook bundle generation and a workflow smoke-test runner for Azure-backed sample validation
- Azure, AWS, and GitHub OIDC runbooks to remove setup ambiguity before the deeper integrations land

## What Is Not Wired Yet

- DR drill automation
- Azure AI Search indexing and retrieval layers
- Azure OpenAI model deployment automation inside the OpenAI account

This implementation pass now covers the first real end-to-end slices: classification-first packet execution, watched Blob and configured-folder intake-source execution, extraction adapters, recommendation outputs, storage-backed review state, queue-backed APIs, and a live operator UI. The remaining work is around retrieval, automation depth, and production-hardening rather than basic plumbing.

## Architecture Direction

1. Azure Blob uploads and optional Azure Storage SFTP land raw documents.
2. Event-driven orchestration normalizes metadata, detects issuer profile, pulls OCR text, and executes the right extraction prompt strategy.
3. Azure SQL resolves the best account candidate and now acts as the durable operator-state system of record, while Cosmos stays available only for legacy/manual-review compatibility or future queue-cache scenarios.
4. Low-confidence, missing-field, or ambiguous documents move into a manual review queue and live review API.
5. Reviewers confirm fields and account matches in the React workbench, which reads and updates the real backend contract.
6. Later iterations attach search indexing, richer downstream automation, and DR drills.

## GitHub Safety And Cost Posture

- GitHub only gets synthetic or fully redacted samples. Real debt-relief paperwork and PII stay out of this repo.
- The `.gitignore` blocks common document and export formats by default so accidental commits are harder.
- Generated bundles, run results, and downloaded documents stay local-only under `samples/synthetic/generated/` and are intentionally excluded from Git.
- Gitleaks is part of the validation workflow to catch secrets before deployment.
- The infrastructure baseline stays on the cheapest practical serverless path for an MVP. Cosmos DB review storage deploys by default, while Azure SQL and Azure AI resources stay behind deployment flags so you only enable them when you are ready to test that path.
- Azure Storage SFTP stays off by default because it adds a fixed hourly storage feature charge. Turn it on only for demos that specifically need the landing-zone workflow.

Epic 6 treats this repo as the private operational codebase rather than the public showcase surface. To review which paths should stay private, which are secret-bearing, and which public security-site assets are extractable into a curated derivative, run:

```powershell
python scripts/build_repo_boundary_report.py --format markdown
```

The source of truth for that report lives in `docs/private-repo-boundary-manifest.json`.

To extract the first real public derivative package for the security posture site,
run:

```powershell
python scripts/extract_public_security_site_package.py
```

That command refreshes `public-derivatives/security-posture-site/`, a standalone
Vite package seeded only from manifest-approved public security-site sources plus
public-safe scaffolding.

To extract the matching backend public API slice, run:

```powershell
python scripts/extract_public_security_api_package.py
```

That command refreshes `public-derivatives/security-posture-api/`, a standalone
Azure Functions package containing only the anonymous public telemetry routes,
sanitized monitoring helpers, SMTP-backed public alert logic, and the public-safe
verification workflow.

To stage both extracted packages into a repo-splittable public subtree, run:

```powershell
python scripts/build_public_security_posture_subtree.py
```

That command refreshes `public-subtrees/security-posture-platform/`, which keeps
the public site and public API together without dragging the private operator
shell, protected review routes, or tenant-specific deployment wiring. The
subtree now carries a standalone-repo validation workflow at
`.github/workflows/validate.yml` so it can be lifted into its own repo without
adding CI by hand.

To export that staged subtree into a standalone public-repo working tree, run:

```powershell
python scripts/export_public_security_posture_repo.py
```

That command refreshes `public-repo-staging/security-posture-platform/`, a
clean repo-shaped copy of the subtree used to sync the published public demo
repo at `https://github.com/RyanKelleyCosing/security-posture-platform`.
That GitHub repo is demonstration-only; this private repo remains the live
operational source of truth.

To refresh the derivative packages, rebuild the subtree, export the repo-shaped
working tree, and push the published public demo repo in one command, run:

```powershell
python scripts/sync_public_security_posture_repo.py
```

That command requires an authenticated GitHub CLI session, defaults to
`main`, uses the staged export as the public sync source without turning this
private repo into the public remote, and should replace manual clone, amend,
or force-push steps for future public repo updates.

To generate the Epic 6 Phase 3 portfolio modernization review across the
surrounding portfolio repos, run:

```powershell
python scripts/build_portfolio_modernization_report.py
```

That command scans the current workspace repos listed in the Epic 6 Phase 3
roadmap, writes `docs/portfolio-modernization-review.md`, and records which
public demos should be treated as first-class showcase entries versus
supporting demos that still need modernization work.

## Repository Layout

```text
hybrid-document-intelligence-platform/
├── .github/workflows/          # Validation and security gates
├── docs/runbooks/              # Azure, AWS, and GitHub setup guides
├── infra/                      # Core Azure deployment scaffold
│   └── parameters/             # Bicep parameter files
├── public-derivatives/         # Extracted public-safe packages staged for split-out
├── public-repo-staging/        # Local export surface used to sync the public demo repo
├── public-subtrees/            # Clean combined public surfaces staged for repo split
├── review-app/                 # Static Web Apps frontend scaffold
├── samples/synthetic/          # Public-safe sample requests only
├── src/document_intelligence/  # Shared Python models and orchestration helpers
├── tests/unit/                 # Pure logic unit tests
├── function_app.py             # Azure Functions durable entrypoint
├── host.json                   # Azure Functions host configuration
├── local.settings.example.json # Safe local settings template
├── pyproject.toml              # Python project metadata and tooling config
└── requirements.txt            # Python runtime dependencies
```

## Local Development

### Backend

Use Python 3.14.x for the local backend and the supported Flex Consumption Functions deployment path.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .[dev]
pytest tests/unit tests/integration
func start
```

Copy `local.settings.example.json` to `local.settings.json` and populate the AI, SQL, and Cosmos values you want to test. When those values are blank, the workflow falls back safely and still exercises the review contract.

Keep `DOCINT_ENABLE_DURABLE_WORKFLOWS=true` for local Durable-host testing. The deployed Flex Function App path sets it to `false` so HTTP routes and inline ingestion remain usable while Durable host indexing is being isolated.

Generate the public-safe sample workbook bundle with:

```powershell
python scripts/generate_synthetic_sample_bundle.py
```

### Review App

```powershell
Set-Location review-app
npm install
npm run dev
```

The review app now supports two frontend modes from the same codebase:

- `simulation` mode opens on a recruiter-safe landing page at the root URL. The deeper walkthrough remains available behind the `#/simulation` hash route and now behaves more like a production operator preview: watched intake sources, staged packets, pipeline status, stack detail, and disabled actions over synthetic data.
- `live` mode preserves the internal review workbench, adds the protected multi-file manual upload surface, and is the seam for the later protected admin deployment.

Create `review-app/.env.local` and set the mode you want:

```dotenv
VITE_APP_MODE=simulation
VITE_PUBLIC_GITHUB_URL=https://github.com/RyanKelleyCosing
VITE_PUBLIC_LINKEDIN_URL=https://www.linkedin.com/in/<your-profile>
VITE_PUBLIC_TRAFFIC_API_BASE_URL=http://localhost:7071/api
VITE_REVIEW_API_BASE_URL=http://localhost:7071/api
```

Use `VITE_APP_MODE=live` when you want the existing review workbench instead of the public simulation shell.

The public simulation currently models four primary intake channels so the visitor can see where packets appear to come from in a production-style flow:

- Azure Storage SFTP
- secure web upload
- email intake
- partner API feed

When `VITE_PUBLIC_LINKEDIN_URL` is omitted, the public landing page still shows GitHub and the simulation route, but it suppresses the LinkedIn button so you do not ship a broken public link.

The deployed private admin host uses the same live bundle, but it serves it behind App Service authentication and a same-origin `/api` proxy. The deployment script now enables ID token issuance on the backing app registration and normalizes `authsettingsV2` so the private host stays pinned to Azure AD rather than a mixed-provider Easy Auth configuration. Local Vite development still points straight at the Function App when `VITE_REVIEW_API_BASE_URL` is set, so the signed-in session banner only appears on the protected deployed host.

### API Contracts

The live hosts now publish generated OpenAPI and Redoc surfaces for the current public and protected API boundaries:

- Anonymous public contract: `/api/docs/public-openapi.json` and `/api/docs/public-api`
- Protected operator contract: `/docs/operator-openapi.json` and `/docs/operator-api`

The public contract only covers the anonymous health, telemetry, request-context, and public-cost routes. Queue, packet, intake, review, and recommendation APIs remain documented only on the authenticated admin host.

The private intake surface now covers the remaining Epic 2 ingress seams as well:

- multi-file drag and drop posts through `/api/packets/manual-intake` from the live review workbench
- email connector execution now stages `.eml` attachments or staged mailbox documents through the durable intake-source execute route
- partner API feeds can POST staged packet payloads through `/api/intake-sources/{source_id}/ingest`

If you want local email alerts for public-site traffic, copy `local.settings.example.json` to `local.settings.json` and provide the SMTP settings under the `DOCINT_PUBLIC_TRAFFIC_ALERTS_ENABLED`, `DOCINT_PUBLIC_ALERT_RECIPIENT_EMAIL`, `DOCINT_SMTP_*` values before starting the Functions host.

If you want the public security route to show real provider-backed ASN, hosting, VPN/proxy, reputation, and coarse location fallback signals, configure the optional enrichment settings as well. The current abstraction supports anonymous `ipapi.is` lookups for low-volume deployments and keyed `ipqualityscore` lookups when you want a different provider contract. When edge geolocation headers are absent, the request-context route now falls back to provider-backed coarse location if the active provider returns it. Two rollout flags now sit on top of that contract: set `DOCINT_PUBLIC_NETWORK_ENRICHMENT_ENABLED` to `false` to hide provider-backed request enrichment without removing the provider settings, and set `DOCINT_PUBLIC_SECURITY_GLOBE_ENABLED` to `false` to keep the coarse globe layer off the public route.

```json
{
  "DOCINT_PUBLIC_NETWORK_ENRICHMENT_ENABLED": "true",
  "DOCINT_PUBLIC_NETWORK_ENRICHMENT_PROVIDER": "ipapi.is",
  "DOCINT_PUBLIC_NETWORK_ENRICHMENT_API_KEY": "",
  "DOCINT_PUBLIC_NETWORK_ENRICHMENT_BASE_URL": "https://api.ipapi.is",
  "DOCINT_PUBLIC_NETWORK_ENRICHMENT_TIMEOUT_SECONDS": "3.0",
  "DOCINT_PUBLIC_SECURITY_GLOBE_ENABLED": "true"
}
```

If you prefer IPQualityScore, set `DOCINT_PUBLIC_NETWORK_ENRICHMENT_PROVIDER` to `ipqualityscore`, provide `DOCINT_PUBLIC_NETWORK_ENRICHMENT_API_KEY`, and point `DOCINT_PUBLIC_NETWORK_ENRICHMENT_BASE_URL` back to `https://www.ipqualityscore.com/api/json/ip`.

To verify that route without handcrafting a request, run the helper script from the repo root. When `--function-base-url` is omitted, the script uses `Host.LocalHttpPort` from `local.settings.json` and otherwise falls back to `http://localhost:7071/api`.

```powershell
python scripts/send_public_traffic_event.py --event-type simulation_started --route intake --forwarded-for 203.0.113.10
```

You can also point the same helper at a deployed Function App by passing `--function-base-url https://<your-function-app>.azurewebsites.net/api`.

For a fuller Phase 1 check after deployment, use the stack verifier. It can confirm that the public site URL responds, that the anonymous public request-context and traffic routes respond, and that the alert settings are populated either from `local.settings.json` or from deployed Function App settings.

```powershell
python scripts/verify_public_simulation_stack.py \
  --public-site-url https://<your-public-site>.z22.web.core.windows.net \
  --settings-source azure \
  --resource-group-name rg-doc-intel-dev \
  --persist-public-history \
  --require-alert-ready
```

When `--settings-source azure` is used and `--function-base-url` is omitted, the verifier resolves the Function App host from Azure CLI.

The Azure-backed validator at `scripts/run_portfolio_cost_reporting_validation.py` now auto-publishes its freshly generated retained history into the public `cost-optimizer-history` Blob contract by default, so the live `#/cost` route stays current without a second manual step. The deployed Function App also now owns a six-hour timer trigger that refreshes the same public-safe contract natively when `DOCINT_PUBLIC_COST_SUBSCRIPTION_ID` or `AZURE_SUBSCRIPTION_ID` is configured and the app identity can run Azure Cost Management queries for that subscription. Run `scripts/publish_public_cost_history.py` directly only when you need to republish an existing retained-history directory or seed a fresh environment before the timer has produced its first snapshot.

To prove the public cost slice against retained history, publish the latest validated cost artifacts into Blob storage and then enable the cost checks on the same verifier run.

```powershell
python scripts/publish_public_cost_history.py \
  --history-directory outputs/epic7-azure-backed-postyaml-20260419/cost-report/history \
  --resource-group-name rg-doc-intel-dev \
  --function-app-name func-doc-test-nwigok \
  --output-file outputs/published-public-cost-history.json

python scripts/verify_public_simulation_stack.py \
  --public-site-url https://www.ryancodes.online \
  --settings-source azure \
  --resource-group-name rg-doc-intel-dev \
  --function-app-name func-doc-test-nwigok \
  --persist-public-history \
  --require-alert-ready \
  --verify-public-cost \
  --require-azure-cost-history \
  --minimum-cost-history-rows 1 \
  --output-file outputs/public-site-verifier-cost.json
```

To verify actual SMTP delivery once, add `--require-alert-sent`. Do not use that flag for the scheduled health probe, because it intentionally sends a real mailbox alert.

If you want the deployed Function App to own its own SMTP relay for those one-off checks, use the Azure Communication Services helper below. It provisions or reuses an Email Service, Azure-managed domain, Communication Service, sender username, SMTP identity, Entra app, and the live `DOCINT_PUBLIC_ALERT_RECIPIENT_EMAIL` plus `DOCINT_SMTP_*` settings on the Function App. Add `-VerifyDelivery` to run the same one-off verifier after the relay is wired.

```powershell
pwsh ./scripts/provision-public-alert-smtp.ps1 \
  -ResourceGroupName rg-doc-intel-dev \
  -FunctionAppName func-doc-test-nwigok \
  -RecipientEmail you@example.com \
  -PublicSiteUrl https://www.ryancodes.online \
  -VerifyDelivery
```

The repo now includes a scheduled workflow at `.github/workflows/verify-public-simulation.yml` that runs every 30 minutes, probes the public site with a spam-safe `health_probe` event, and persists sanitized availability history for the `#/security` page. Configure these GitHub secrets before enabling the schedule:

- `DOCINT_PUBLIC_VERIFY_AZURE_CLIENT_ID`
- `DOCINT_PUBLIC_VERIFY_AZURE_TENANT_ID`
- `DOCINT_PUBLIC_VERIFY_AZURE_SUBSCRIPTION_ID`

Optional repository variables:

- `DOCINT_PUBLIC_SITE_URL`
- `DOCINT_RESOURCE_GROUP_NAME`
- `DOCINT_FUNCTION_APP_NAME`

The deployed Function App now also includes a native timer-trigger verifier that runs every 30 minutes and writes the same sanitized availability history. The supported deployment script stamps `DOCINT_PUBLIC_SITE_URL` into the Function App automatically after a public-site publish, preferring the custom domain when one is configured.

When `www.<your-domain>` is hosted on Azure Static Web Apps, Azure manages the TLS certificate after the hostname association succeeds. An external wildcard certificate from IONOS is still useful for App Service or Front Door scenarios, but it is not imported into the Static Web App deployment path.

If you want the lowest-cost public hosting path, use Azure Static Web Apps Free instead of Azure Storage plus Front Door. This gives the public HR-safe site a managed default hostname, free SSL, and cheaper custom-domain support.

```powershell
pwsh ./scripts/deploy-azure-function-stack.ps1 \
  -EnvironmentName test \
  -Location eastus2 \
  -UseFlexConsumption \
  -DeployPublicStaticWebApp
```

To prepare `www.<your-domain>` on the cheaper path, pass `-PublicSimulationCustomDomainName <public-hostname>`. The deployment output will include the Static Web App hostname that your registrar should target with a CNAME.

```powershell
pwsh ./scripts/deploy-azure-function-stack.ps1 \
  -EnvironmentName test \
  -Location eastus2 \
  -UseFlexConsumption \
  -DeployPublicStaticWebApp \
  -PublicSimulationCustomDomainName www.contoso.com
```

After the CNAME is live, rerun the same command with `-AssociatePublicSimulationCustomDomain` to bind the hostname inside Azure Static Web Apps.

If you specifically want Azure Front Door in front of the public simulation site, add `-DeployPublicFrontDoor`. This keeps the storage static website as the origin, gives you a Front Door default hostname, and prepares the custom-domain path for HTTPS.

```powershell
pwsh ./scripts/deploy-azure-function-stack.ps1 \
  -EnvironmentName test \
  -Location eastus2 \
  -UseFlexConsumption \
  -DeployPublicSimulationSite \
  -DeployPublicFrontDoor
```

To prepare a custom domain, pass `-PublicSimulationCustomDomainName <your-domain>`. The deployment outputs will include the Front Door hostname, the `_dnsauth` TXT record name, and the validation token that you can add at your external DNS provider before associating the domain with the route.

```powershell
pwsh ./scripts/deploy-azure-function-stack.ps1 \
  -EnvironmentName test \
  -Location eastus2 \
  -UseFlexConsumption \
  -DeployPublicSimulationSite \
  -DeployPublicFrontDoor \
  -PublicSimulationCustomDomainName www.contoso.com
```

After the TXT validation is approved, rerun the deployment with `-AssociatePublicSimulationCustomDomain` to bind the domain to the public route.

### Infra Validation

```powershell
pwsh ./tests/validate-infra.ps1
```

## Deployment Start Point

```powershell
az group create --name rg-doc-intel-dev --location eastus

az deployment group create \
  --resource-group rg-doc-intel-dev \
  --template-file infra/main.bicep \
  --parameters infra/parameters/dev.bicepparam \
  --parameters deployFunctionApp=true
```

If you only want to pre-stage the shared foundation without the Function App, set `deployFunctionApp=false` explicitly.

To enable the full matching and extraction path in Azure, add the optional flags and secure SQL password at deployment time.

```powershell
az deployment group create \
  --resource-group rg-doc-intel-dev \
  --template-file infra/main.bicep \
  --parameters infra/parameters/dev.bicepparam \
  --parameters deploySql=true deployAiServices=true \
  --parameters sqlAdministratorPassword="<strong-password>"
```

Use the runbooks under [docs/runbooks](docs/runbooks) before deploying any cloud resources.

For the current low-friction Azure test path, use the deployment script instead of hand-building the CLI command. The cheapest default run leaves the AI settings blank so the workflow uses its fallback path, and the template now provisions the Function App directly on Flex Consumption.

For the supported Python 3.14 Functions baseline, use the deployment script. The `-UseFlexConsumption` switch is still accepted for compatibility with existing runbooks, but the in-template Bicep resource is now already Flex-native.

```powershell
pwsh ./scripts/deploy-azure-function-stack.ps1 -EnvironmentName test -Location eastus2 -UseFlexConsumption
```

To reuse existing Azure Document Intelligence and Azure OpenAI accounts, pass both account names explicitly.

```powershell
pwsh ./scripts/deploy-azure-function-stack.ps1 \
  -EnvironmentName test \
  -Location eastus2 \
  -UseFlexConsumption \
  -ExistingDocumentIntelligenceAccountName didocint10589 \
  -ExistingOpenAIAccountName aoaidocint-eastus2
```

To create dedicated Azure AI resources instead of reusing existing ones, add `-DeployAiServices`.

If you specifically want to demo the SFTP landing-zone path, add `-EnableStorageSftp`. Leave it off for the cheapest default deployment.

To get early warning when the demo starts drifting above the target cost envelope, create a small monthly budget for the resource group. The helper script defaults to the signed-in Azure account email and 50/80/100 percent alert thresholds.

```powershell
pwsh ./scripts/set-resource-group-budget-alert.ps1 -ResourceGroupName rg-doc-intel-dev -Amount 25
```

To publish the public HR-safe simulation site with the cheapest default hosting path, add the `-DeployPublicStaticWebApp` switch. The script will build the React app in `simulation` mode, deploy the generated `dist` output to Azure Static Web Apps Free, and register that site origin on the Function App CORS list for the public traffic endpoint.

```powershell
pwsh ./scripts/deploy-azure-function-stack.ps1 \
  -EnvironmentName test \
  -Location eastus2 \
  -UseFlexConsumption \
  -DeployPublicStaticWebApp \
  -PublicSimulationGitHubUrl https://github.com/RyanKelleyCosing \
  -PublicSimulationLinkedInUrl https://www.linkedin.com/in/ryan-kelley-it/
```

The public site host remains separate from the document-processing storage account. The `-PublicSimulationGitHubUrl` and `-PublicSimulationLinkedInUrl` switches are optional, but they let you stamp the public landing page links into the deployed build without relying on temporary shell environment variables. The same deployment path now also resolves and stamps `DOCINT_PUBLIC_NETWORK_ENRICHMENT_*` plus `DOCINT_PUBLIC_SECURITY_GLOBE_ENABLED` on the Function App, and it builds the review app with matching fallback flags. If you explicitly want the older storage-site path, keep using `-DeployPublicSimulationSite`, and add `-DeployPublicFrontDoor` only when you need Front Door. The private live admin site is still a later phase and is not deployed by the public-site switches.

To roll the public security route out selectively, pass `-PublicNetworkEnrichmentEnabled false` to hide provider-backed request enrichment or `-PublicSecurityGlobeEnabled false` to hold back the globe layer while the rest of the route stays live. When you are ready for the full provider-backed rollout, add `-PublicNetworkEnrichmentProvider ipapi.is` for the anonymous `ipapi.is` path, or use `-PublicNetworkEnrichmentProvider ipqualityscore -PublicNetworkEnrichmentApiKey <provider-key>` for IPQualityScore.

If the live Function App and Static Web App already exist and you only want to roll forward code plus public-cost settings, target those resources directly instead of re-running the Bicep provisioning path.

```powershell
pwsh ./scripts/deploy-azure-function-stack.ps1 \
  -ResourceGroupName rg-doc-intel-dev \
  -ExistingFunctionAppName func-doc-test-nwigok \
  -DeployPublicStaticWebApp \
  -ExistingPublicStaticWebAppName swa-doc-test-nwigok \
  -PublicSimulationCustomDomainName www.ryancodes.online \
  -PublicCostSubscriptionId cc0ebf93-82c2-41ac-8514-fb9ae969f943 \
  -EnablePublicCostRefresh \
  -AssignPublicCostReaderRole
```

That direct-rollout mode zip-deploys the current Function App package, redeploys the existing Static Web App in `simulation` mode, keeps the public CORS list aligned, stamps `DOCINT_PUBLIC_SITE_URL`, and can also enable the six-hour public-cost refresh with the required managed identity role assignment.

To deploy the private live admin site, add `-DeployPrivateLiveSite` and pass the single allowed Microsoft account email. The script will deploy a separate Linux App Service, create or update the Microsoft app registration with personal-account support, rotate a server-side review API admin key, configure Easy Auth, and publish the React app in `live` mode behind the authenticated proxy host.

```powershell
pwsh ./scripts/deploy-azure-function-stack.ps1 \
  -EnvironmentName test \
  -Location eastus2 \
  -UseFlexConsumption \
  -DeployPrivateLiveSite \
  -PrivateLiveAllowedUserEmail ryankelley1992@outlook.com \
  -PrivateLiveCustomDomainName admin.contoso.com
```

When regional App Service quota is tight, add `-PrivateLiveLocation <region>` to place only the private admin host in a different region while keeping the shared backend where it is. When `-PrivateLiveCustomDomainName` is supplied, the deployment outputs include the App Service hostname, the `asuid.<hostname>` TXT record name, and the verification token needed before the hostname can be bound. After DNS is ready, rerun the same command with `-AssociatePrivateLiveCustomDomain` to add the hostname and request the managed certificate.

For a browser-level proof on the deployed private host, point Playwright at the custom domain or fallback Azure hostname instead of the local mocked suite.

```powershell
Set-Location review-app
$env:PLAYWRIGHT_BASE_URL = "https://admin.ryancodes.online"
npm run test:e2e -- e2e/deployed-private-admin-auth.spec.ts --project=chromium
```

If you already have an allowlisted signed-in browser storage state, set `PLAYWRIGHT_ADMIN_STORAGE_STATE` as well to prove the signed-in banner on the live host.

## Hosting And Domain Notes

- The cheapest public HR-safe site path is Azure Static Web Apps Free for the React app and Azure Functions for the traffic endpoint.
- The private live admin site now uses a separate Azure App Service host, not the public storage site. That host is intended for Microsoft-authenticated access only and proxies review traffic to the Function App with a server-side admin key.
- AWS is still only an optional ingestion-side bridge in this repo. It is not part of the site hosting path.
- You do not need to register a domain to launch Phase 1. Azure gives the public site a default Static Web Apps hostname and the Function App a default `*.azurewebsites.net` URL.
- If you want the cheapest path, use the Azure-provided default URL first and defer domain purchase until the public simulation is stable.
- For the cheapest custom-domain path, point `www.<your-domain>` at the Azure Static Web Apps default hostname with a CNAME and then associate the hostname in Azure.
- Azure Storage static websites still support a storage-origin path, but HTTPS custom domains there require Azure Front Door or Azure CDN in front of the storage endpoint.
- Azure can also sell and manage domains through App Service Domains, and AWS can do the same through Route 53 Domains, but those are convenience options rather than the guaranteed cheapest option.
- If lowest cost is the priority, an external registrar is usually the better place to buy the domain, then point DNS at Azure.
- For Azure Static Web Apps subdomain cutover, the cheapest path is usually a direct `www` CNAME to the Static Web Apps default hostname.
- For Azure Front Door custom domains hosted outside Azure DNS, Azure Front Door validates ownership with a TXT record in the form `_dnsauth.<hostname>` and then expects a CNAME to the Front Door endpoint hostname.
- Apex root domains can be awkward with external DNS providers because many registrars do not support a true CNAME at the zone root. If your registrar does not support apex aliasing or flattening, use `www` for the public site and redirect the root domain.
- A sensible split for this project is a public hostname for the HR-safe simulation and a separate admin hostname reserved for the later private live site. Do not point the admin hostname until the Phase 2 auth and allowlist work is in place.
- Use [docs/runbooks/private-admin-site-cutover.md](docs/runbooks/private-admin-site-cutover.md) for the private admin hostname once you are ready to bind `admin.<your-domain>` and validate Microsoft-only access.

To wire the minimal AWS bridge path from S3 into Azure Blob without waiting on the hosted ingestion callback, deploy the copy-only Lambda bridge.

```powershell
pwsh ./scripts/deploy-s3-blob-bridge.ps1 \
  -BucketName <your-s3-bucket> \
  -AwsProfile dev \
  -AwsRegion us-east-2 \
  -AzureResourceGroupName rg-doc-intel-dev \
  -StorageAccountName <azure-storage-account> \
  -ContainerName raw-documents \
  -LambdaFunctionName docintel-s3-to-blob-bridge-test \
  -PythonExecutable <python-path> \
  -SkipIngestionTrigger
```

## Safe Sample Request

The initial preview route accepts the synthetic requests in [samples/synthetic/review-preview-request.json](samples/synthetic/review-preview-request.json) and [samples/synthetic/review-preview-request-court.json](samples/synthetic/review-preview-request-court.json). They let you verify routing behavior, issuer-aware prompt selection, and review contract shaping before you point the workflow at live Azure resources.

For a fuller Azure-backed test, generate the workbook bundle and then use [docs/runbooks/synthetic-test-drive.md](docs/runbooks/synthetic-test-drive.md). That path creates messy synthetic Excel workbooks for a banker-box intake case and an SFTP-drop case, then pushes them through the live ingestion workflow. The smoke-test client now accepts either Durable status URLs or a direct completed response from the Flex-safe synchronous fallback.

For the protected packet-workspace path, use `scripts/run_packet_pipeline_smoke_test.py` to generate nested ZIP, ZIP64, duplicate-member, corrupt, encrypted, unsupported-member, spanned, and unsafe-archive payloads on the fly, post them to manual intake, run the packet classification, OCR, extraction, and recommendation execution routes where applicable, and verify the SQL-backed workspace transitions and quarantine routing without rebuilding the payloads by hand.

The first real non-manual source slices are also live through protected `POST /api/intake-sources/{source_id}/execute` for watched Blob prefixes and configured folders. Watched Blob execution lists blobs under the configured prefix, downloads each candidate, pushes it through the existing manual packet intake path for duplicate detection and staging, and records last-seen, last-success, and last-error state back to SQL. Configured-folder execution applies the configured glob and recursion policy against a stable local or mounted path, imports each matching file through the same packet intake path, and records the same SQL-backed execution state.

Use `scripts/run_intake_source_execute_smoke_test.py` when you need to re-run the hosted watched-Blob smoke against the current Function App without rebuilding an ad hoc one-liner. Configured-folder execution is validated locally and on any worker that has a real mounted path available; hosted App Service runs should still avoid relying on ephemeral local disk.

```powershell
python scripts/run_packet_pipeline_smoke_test.py \
  --function-base-url https://<function-app-name>.azurewebsites.net/api \
  --admin-key <review-api-admin-key>
```

The runner stops after recommendation by default and writes `outputs/packet-pipeline-smoke-results.json`. Use `--stop-after extraction` or `--stop-after ocr` when you only need to validate an environment that has not yet picked up the later routes.
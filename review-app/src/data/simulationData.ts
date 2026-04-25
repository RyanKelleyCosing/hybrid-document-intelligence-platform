import type { ReviewQueueItem } from "../api/reviewApi";

export type SimulationRoute =
  | "landing"
  | "intake"
  | "processing"
  | "review"
  | "accounts"
  | "ops"
  | "libraries";

type SimulationView = {
  asideCopy: string;
  asidePoints: string[];
  asideTitle: string;
  description: string;
  navLabel: string;
  panelCopy: string;
  panelEyebrow: string;
  panelMetrics?: ReadonlyArray<{ detail: string; label: string; value: string }>;
  panelTitle: string;
  title: string;
};

type PacketScenario = {
  accountHint: string;
  issuer: string;
  packetSize: string;
  sourceLabel: string;
  summary: string;
  tags: string[];
  title: string;
};

type ProcessingStage = {
  detail: string;
  state: "active" | "complete" | "queued";
  summary: string;
  title: string;
};

type AccountDetail = {
  label: string;
  value: string;
};

type AccountSummary = {
  accountId: string;
  debtorName: string;
  details: AccountDetail[];
  matchConfidence: string;
  portfolio: string;
  preflightSignals: string[];
};

type AccountDocument = {
  fileName: string;
  sourceLabel: string;
  status: string;
  summary: string;
};

type ShowcaseCard = {
  bullets: string[];
  eyebrow: string;
  highlight: string;
  summary: string;
  title: string;
};

type SourceMonitor = {
  cadence: string;
  currentPacket: string;
  path: string;
  sourceLabel: string;
  status: string;
  summary: string;
  title: string;
};

type StackLayer = {
  detail: string;
  layer: string;
  tools: string;
};

function createReviewItem(
  documentId: string,
  values: {
    accountCandidates: string[];
    accountId: string | null;
    accountStatus: string;
    averageConfidence: number;
    extractedFields: Array<{ confidence: number; name: string; value: string }>;
    fileName: string;
    issuerCategory: string;
    issuerName: string;
    profileId: string;
    reasons: string[];
    source: string;
    sourceUri: string;
  },
): ReviewQueueItem {
  return {
    account_candidates: values.accountCandidates,
    account_match: {
      candidates: values.accountId
        ? [
            {
              account_id: values.accountId,
              account_number: "MED-45678",
              debtor_name: "Jordan Patel",
              issuer_name: values.issuerName,
              matched_on: ["account_number_exact", "debtor_name_fuzzy"],
              score: 91.2,
            },
          ]
        : [],
      rationale: "Simulation-only account hint derived from dummy extracted fields.",
      selected_account_id: values.accountId,
      status: values.accountStatus,
    },
    average_confidence: values.averageConfidence,
    created_at_utc: "2026-04-02T15:11:00Z",
    document_id: documentId,
    document_type: "correspondence",
    extracted_fields: values.extractedFields,
    file_name: values.fileName,
    issuer_category: values.issuerCategory,
    issuer_name: values.issuerName,
    minimum_confidence: 0.58,
    ocr_text_excerpt:
      "Simulation excerpt only. The public site never loads real OCR output or private account context.",
    prompt_profile: {
      candidates: [
        {
          issuer_category: values.issuerCategory,
          profile_id: values.profileId,
          rationale: ["Synthetic issuer family match", "Simulation-only keyword hints"],
          score: 88,
        },
      ],
      document_type_hints: ["collection notice"],
      issuer_category: values.issuerCategory,
      keyword_hints: ["account number", "balance due", "collector"],
      primary_profile_id: values.profileId,
      prompt_focus: ["issuer-aware extraction", "account reuse preview"],
      rationale: ["Public-safe simulation path"],
      selection_mode: "heuristic",
      system_prompt: "Simulation-only prompt profile.",
    },
    reasons: values.reasons,
    received_at_utc: "2026-04-02T14:57:00Z",
    reviewed_at_utc: null,
    reviewer_name: null,
    review_notes: null,
    selected_account_id: values.accountId,
    source: values.source,
    source_uri: values.sourceUri,
    status: "pending_review",
    updated_at_utc: "2026-04-02T15:12:00Z",
  };
}

export const simulationRouteOrder: SimulationRoute[] = [
  "landing",
  "intake",
  "processing",
  "review",
  "accounts",
  "ops",
  "libraries",
];

export const simulationViews: Record<SimulationRoute, SimulationView> = {
  landing: {
    asideCopy: "The walkthrough is framed like a production operator preview, but every packet, status, and action remains simulated.",
    asidePoints: [
      "Watched intake lanes show where packets would land in production.",
      "Buttons stay disabled so the public route never mutates data.",
      "The sample dataset uses a debt-servicing scenario to make the workflow concrete.",
    ],
    asideTitle: "Operator preview",
    description:
      "A guided view of how inbound document packets move from watched intake sources through OCR, AI extraction, matching, and human review, using a debt-servicing workflow as the sample scenario.",
    navLabel: "Landing",
    panelCopy:
      "The public route now reads more like a production operations preview: watched sources, staged packets, and system layers, all backed by synthetic data and disabled actions.",
    panelEyebrow: "Production-style simulation",
    panelMetrics: [
      {
        detail:
          "SFTP, secure upload, email intake, and partner feeds stay visible as watched production-like channels.",
        label: "Watched inputs",
        value: "4",
      },
      {
        detail:
          "4 synthetic packets are already staged into the walkthrough with source lineage attached.",
        label: "Loaded packets",
        value: "4",
      },
      {
        detail:
          "Intake, OCR, extraction, matching, and review are mapped to the same Azure stack the live operator path uses.",
        label: "Platform layers",
        value: "5",
      },
    ],
    panelTitle: "Watched sources, staged packets, disabled controls",
    title: "See how the document workflow is wired before the first live run.",
  },
  intake: {
    asideCopy: "Each input channel is presented the way an operator would expect to see it: watched source, cadence, and currently staged packet.",
    asidePoints: [
      "Primary simulated inputs now focus on SFTP, secure upload, email intake, and partner API feeds.",
      "Packet summaries show where files appear to have landed and what the system would load next.",
      "Uploads stay disabled even while the screen mimics the production intake surface.",
    ],
    asideTitle: "Ingestion notes",
    description:
      "The intake view shows watched channels, staged packets, and load state so visitors can see where production packets would originate before OCR and AI extraction begin.",
    navLabel: "Intake",
    panelCopy:
      "This is intentionally closer to an operator intake board than a portfolio mockup: transport, source path, cadence, and staged packet are all visible.",
    panelEyebrow: "Ingestion board",
    panelMetrics: [
      { detail: "SFTP, secure upload, email intake, and partner API feeds.", label: "Channels watched", value: "4" },
      { detail: "Synthetic packets staged across all four intake lanes.", label: "Staged packets", value: "4" },
      { detail: "Upload, approve, and reject actions remain disabled on the public surface.", label: "Public-safe actions", value: "Read-only" },
    ],
    panelTitle: "Production-like inputs with public-safe controls",
    title: "Watched intake channels and staged document packets.",
  },
  processing: {
    asideCopy: "The processing timeline is paired with the actual platform layers behind each stage so the walkthrough shows implementation depth, not just UI states.",
    asidePoints: [
      "Preflight highlights source recognition, dedupe checks, and queue shaping.",
      "OCR and extraction are mapped directly to Azure AI services used in the real stack.",
      "Manual review remains the final gate when packet confidence or matching stays uncertain.",
    ],
    asideTitle: "Processing notes",
    description:
      "A staged processing timeline shows how packets move through preflight, OCR, extraction, matching, and review routing, with the Azure services behind each layer called out explicitly.",
    navLabel: "Processing",
    panelCopy:
      "This route now explains both the packet state and the platform services behind it, which is much closer to what an operator would need before a live run.",
    panelEyebrow: "Pipeline view",
    panelMetrics: [
      { detail: "Preflight, OCR, extraction, matching, and review routing.", label: "Pipeline stages", value: "5" },
      { detail: "Document Intelligence, Azure OpenAI, and managed storage are mapped per stage.", label: "Azure services", value: "3+" },
      { detail: "Manual review remains the final gate when confidence stays uncertain.", label: "Human gates", value: "1" },
    ],
    panelTitle: "Workflow stages mapped to real stack layers",
    title: "Pipeline timing, queueing, and AI services in one view.",
  },
  review: {
    asideCopy: "The review view keeps the same card grammar as the admin site so the public walkthrough feels like the real operator surface, just with actions disabled.",
    asidePoints: [
      "Buttons remain disabled and cannot submit review actions.",
      "Confidence, routing reasons, and account hints stay synthetic but production-shaped.",
      "The surrounding stack notes explain which backend services feed this queue.",
    ],
    asideTitle: "Queue rules",
    description:
      "The review queue behaves like a read-only operator dashboard: extracted fields, confidence, routing reasons, and candidate account evidence are visible, but every action remains disabled.",
    navLabel: "Review",
    panelCopy:
      "The public queue should now feel like a production control plane preview rather than a generic demo board.",
    panelEyebrow: "Read-only queue",
    panelMetrics: [
      { detail: "Synthetic review items shaped like the live operator queue.", label: "Queue items", value: "4" },
      { detail: "Approve, reject, edit, and resubmit are disabled on the public route.", label: "Disabled actions", value: "4" },
      { detail: "Confidence, routing reasons, and account hints stay visible.", label: "Visible signals", value: "3" },
    ],
    panelTitle: "Operator-grade queue, public-safe controls",
    title: "Review cards that look real, while staying fully simulated.",
  },
  accounts: {
    asideCopy: "The account view is framed as the next protected step after a reviewer opens a queue item and traces packet lineage back through the intake system.",
    asidePoints: [
      "Account reuse and duplicate suspicion are called out explicitly.",
      "Linked documents show source lineage and status instead of live previews.",
      "No account search or document download is available on the public route.",
    ],
    asideTitle: "Account preview notes",
    description:
      "The account view shows how linked documents, source history, and preflight outcomes will appear once the protected admin surface turns on the real data model.",
    navLabel: "Accounts",
    panelCopy:
      "This view is the seam between simulated public walkthroughs and the first real admin run, where protected account history and packet linkage need to work cleanly.",
    panelEyebrow: "Protected drill-down",
    panelMetrics: [
      { detail: "Synthetic account profile linked to staged packets.", label: "Linked accounts", value: "1" },
      { detail: "Document lineage shown without live previews or downloads.", label: "Linked documents", value: "3" },
      { detail: "Account search and document download stay protected on the live admin host.", label: "Protected actions", value: "2" },
    ],
    panelTitle: "Account lineage and linked packet history",
    title: "Trace the packet back to the account story it belongs to.",
  },
  ops: {
    asideCopy: "Supporting repos remain narrative panels in Phase 1, not live dependencies.",
    asidePoints: [
      "KQL posture is described as platform health, not Azure global status.",
      "AI anomaly detection maps to extraction and matching exceptions.",
      "Pipeline, failover, and cost stories stay safe for public viewing.",
    ],
    asideTitle: "Operations framing",
    description:
      "Platform operations stay present on the public site as supporting context for cost, deployment, failover, and incident posture without exposing live telemetry.",
    navLabel: "Platform Ops",
    panelCopy:
      "These panels deliberately support the flagship workflow instead of turning the public site into a loose portfolio index.",
    panelEyebrow: "Supporting story",
    panelMetrics: [
      { detail: "KQL posture, AI anomaly detection, and cost optimization summaries.", label: "Ops panels", value: "3" },
      { detail: "Each panel is read-only narrative, not a live telemetry feed.", label: "Live telemetry", value: "None" },
      { detail: "Failover, deployment, and incident-response stories stay public-safe.", label: "Public-safe stories", value: "3" },
    ],
    panelTitle: "Operational context panels",
    title: "Platform posture without live platform access.",
  },
  libraries: {
    asideCopy: "Libraries are shown as reusable building blocks and guardrail patterns rather than runtime features.",
    asidePoints: [
      "Module and policy stories stay read-only and reference-oriented.",
      "This helps the site feel intentional instead of dumping repo links.",
      "The public site explains reuse without exposing deployment controls.",
    ],
    asideTitle: "Library framing",
    description:
      "Reusable Bicep modules and governance guardrails become catalog pages that support the main product story while staying firmly non-operational.",
    navLabel: "Libraries",
    panelCopy:
      "The same shared shell can later sit beside a protected live admin deployment without blurring what is public and what is real.",
    panelEyebrow: "Reference-only",
    panelMetrics: [
      { detail: "Reusable Bicep modules surfaced as a catalog, not a launcher.", label: "Module families", value: "3+" },
      { detail: "Policy and guardrail patterns shown as governance reference material.", label: "Policy patterns", value: "4+" },
      { detail: "No deploy buttons or runtime controls live on the public surface.", label: "Runtime controls", value: "None" },
    ],
    panelTitle: "Catalogs, not consoles",
    title: "Reusable infrastructure presented as a library, not a launcher.",
  },
};

export const simulationIntroRules = [
  "Every packet, queue item, and account link shown here is synthetic but shaped like production data.",
  "The public route never uploads, mutates, approves, rejects, or downloads real documents.",
  "Source watchers, staged packets, and pipeline status are visible so visitors can see how the real system is meant to operate.",
  "The protected admin site handles the live run behind Microsoft sign-in and server-side API access.",
];

export const simulationSourceMonitors: SourceMonitor[] = [
  {
    cadence: "Every 2 minutes",
    currentPacket: "regional-medical-drop-2026-04-04-0902.zip",
    path: "sftp://stdoc/raw/servicing/collectors/regional-medical/2026/04/04/",
    sourceLabel: "Azure Storage SFTP",
    status: "Packet loaded",
    summary: "Recurring collector packets are staged from a watched landing zone and expanded into reviewable documents.",
    title: "Recurring collector drop",
  },
  {
    cadence: "Event-driven",
    currentPacket: "portal-upload-2026-04-04-0910.json",
    path: "https://portal.ryancodes.online/api/intake/upload",
    sourceLabel: "Secure web upload",
    status: "Awaiting OCR",
    summary: "Portal submissions enter through a protected upload path and land with source metadata already attached.",
    title: "Borrower portal upload",
  },
  {
    cadence: "Mailbox poll every 5 minutes",
    currentPacket: "servicing-inbox-attachment-441.eml",
    path: "debtops-intake@ryancodes.online / Inbox/Servicing/Needs-Triage",
    sourceLabel: "Email intake",
    status: "Attachments parsed",
    summary: "Email attachments are normalized into packet manifests before OCR and profile selection begin.",
    title: "Servicing mailbox intake",
  },
  {
    cadence: "Webhook + retry queue",
    currentPacket: "partner-referral-cc-118-2026.json",
    path: "POST /api/intake/partner-referrals/v1",
    sourceLabel: "Partner API feed",
    status: "Schema validated",
    summary: "Partner referrals arrive as structured JSON and attach document references that the workflow resolves downstream.",
    title: "Partner referral feed",
  },
];

export const simulationStackLayers: StackLayer[] = [
  {
    detail: "Watched SFTP folders, secure portal uploads, inbox ingestion, and partner APIs all land as normalized packet manifests.",
    layer: "Ingress",
    tools: "Azure Storage, portal API, mailbox intake, partner feed",
  },
  {
    detail: "Azure Functions coordinate source normalization, dedupe checks, and queue shaping before extraction runs.",
    layer: "Orchestration",
    tools: "Azure Functions, queue workflows, preflight checks",
  },
  {
    detail: "OCR and field extraction combine layout parsing with issuer-aware LLM prompt selection.",
    layer: "Document AI",
    tools: "Azure Document Intelligence, Azure OpenAI",
  },
  {
    detail: "Match candidates, routing state, and operator decisions are persisted for review and replay.",
    layer: "State and matching",
    tools: "Cosmos DB, SQL matching, Service Bus",
  },
  {
    detail: "The public site shows the workflow, while the private host runs the same surface behind Microsoft-authenticated admin access.",
    layer: "Operator surface",
    tools: "React, App Service, Static Web Apps, Easy Auth",
  },
  {
    detail: "Bicep and guardrail modules keep the deployment repeatable and aligned with the rest of the platform repos.",
    layer: "Infrastructure",
    tools: "Bicep, policy guardrails, monitoring modules",
  },
];

export const simulationPackets: PacketScenario[] = [
  {
    accountHint: "acct-3001-med-45678",
    issuer: "Regional Medical Collections",
    packetSize: "4 documents",
    sourceLabel: "Azure Storage SFTP",
    summary:
      "A recurring collector packet loaded from the watched SFTP landing zone and staged into a multi-document review bundle.",
    tags: ["recurring source", "packet expanded", "manual review candidate"],
    title: "Collector packet from recurring SFTP drop",
  },
  {
    accountHint: "acct-1109-bank-90013",
    issuer: "Summit Bank",
    packetSize: "2 documents",
    sourceLabel: "Secure web upload",
    summary:
      "A secure portal upload containing a statement and hardship note, staged with source metadata before OCR begins.",
    tags: ["portal upload", "low confidence", "ocr variance"],
    title: "Borrower packet from secure portal upload",
  },
  {
    accountHint: "acct-2407-mail-82114",
    issuer: "Northline Recovery",
    packetSize: "3 attachments",
    sourceLabel: "Email intake",
    summary:
      "An intake email with multiple attachments already split into packet artifacts and ready for routing checks.",
    tags: ["mailbox intake", "attachment split", "triage ready"],
    title: "Servicing email packet with attachments",
  },
  {
    accountHint: "partner-case-118",
    issuer: "County Civil Court",
    packetSize: "1 referral payload",
    sourceLabel: "Partner API feed",
    summary:
      "A structured partner referral with linked document references, staged after schema validation and duplicate checks.",
    tags: ["partner api", "schema validated", "referral packet"],
    title: "Partner referral staged from API feed",
  },
];

export const simulationProcessingStages: ProcessingStage[] = [
  {
    detail:
      "The live site will confirm whether the source is already known before it creates or updates any source metadata.",
    state: "complete",
    summary: "Recognize the intake lane and normalize the source fingerprint.",
    title: "Source preflight",
  },
  {
    detail:
      "A content hash and field-overlap check will help the private site stop obvious duplicates from pretending to be new work.",
    state: "active",
    summary: "Run duplicate checks before the document is treated as net new.",
    title: "Duplicate detection",
  },
  {
    detail:
      "OCR remains simulated here, but the final live stage will pull text from supported file types and show completion status in the same timeline.",
    state: "queued",
    summary: "Extract text from supported inputs and retain fallback behavior for unsupported ones.",
    title: "OCR and document text",
  },
  {
    detail:
      "The eventual live path will use issuer-aware profiles and show why a specific extraction strategy was selected.",
    state: "queued",
    summary: "Apply AI extraction and profile selection to normalized document text.",
    title: "AI extraction",
  },
  {
    detail:
      "Account number stays the strongest key, while debtor and issuer context support reuse or manual review when the match is ambiguous.",
    state: "queued",
    summary: "Reuse an existing account when the evidence is strong enough.",
    title: "Account reuse",
  },
  {
    detail:
      "Manual review remains the final safety valve when duplicate signals, extraction quality, or account evidence stay uncertain.",
    state: "queued",
    summary: "Route the packet into review only when the live workflow actually needs a human decision.",
    title: "Manual review routing",
  },
];

export const simulationAccountSummary: AccountSummary = {
  accountId: "acct-3001-med-45678",
  debtorName: "Jordan Patel",
  details: [
    { label: "Issuer family", value: "Collection agency" },
    { label: "Latest source", value: "Azure Storage SFTP / raw/servicing/collectors/regional-medical" },
    { label: "Linked documents", value: "4 synthetic packet artifacts" },
    { label: "Last operator action", value: "Queued after packet dedupe and account confirmation" },
  ],
  matchConfidence: "91% likely account reuse",
  portfolio: "Debt-servicing operations sample",
  preflightSignals: ["existing source", "account reuse", "duplicate watch"],
};

export const simulationAccountDocuments: AccountDocument[] = [
  {
    fileName: "acct-3001-demand-letter.pdf",
    sourceLabel: "Azure Storage SFTP",
    status: "Review queued",
    summary: "Synthetic demand letter preview tied to the recurring source fingerprint.",
  },
  {
    fileName: "acct-3001-hardship-upload.pdf",
    sourceLabel: "Secure web upload",
    status: "OCR gap",
    summary: "Example of a low-confidence scan that would stay protected until the private site is live.",
  },
  {
    fileName: "acct-3001-servicing-email.eml",
    sourceLabel: "Email intake",
    status: "Attachments parsed",
    summary: "Email intake remains visible here as packet lineage rather than a raw document preview.",
  },
];

export const simulationCards: Record<"libraries" | "ops", ShowcaseCard[]> = {
  libraries: [
    {
      bullets: [
        "Explain reusable monitor modules with inputs, outputs, and example compositions.",
        "Keep the public site focused on catalog exploration instead of deployment actions.",
      ],
      eyebrow: "Bicep module library",
      highlight: "Reusable monitoring stack patterns",
      summary:
        "Transforms the module repo into a browsable library tab that complements the main product story.",
      title: "Infrastructure building blocks",
    },
    {
      bullets: [
        "Surface guardrail categories and remediation stories.",
        "Show policy intent without exposing tenant-level controls.",
      ],
      eyebrow: "Governance guardrails",
      highlight: "Subscription policy baseline",
      summary:
        "Presents governance patterns as reference material that reinforces your platform engineering narrative.",
      title: "Policy and compliance catalog",
    },
  ],
  ops: [
    {
      bullets: [
        "Connect the cost story to keeping recurring ops overhead low.",
        "Keep metrics illustrative until the private site turns on live telemetry.",
      ],
      eyebrow: "Azure cost optimizer",
      highlight: "Modeled monthly savings views",
      summary:
        "Shows how cost visibility supports the platform without turning the HR site into a billing console.",
      title: "Spend posture panel",
    },
    {
      bullets: [
        "Frame incidents as platform posture rather than Azure global health.",
        "Use KQL and anomaly stories to explain exception handling.",
      ],
      eyebrow: "KQL + AI operations",
      highlight: "Operational triage story",
      summary:
        "Combines KQL dashboard and anomaly detection themes into a single platform-health panel.",
      title: "Incident and extraction posture",
    },
    {
      bullets: [
        "Explain why gated deployment matters before the live admin site is opened.",
        "Show security checks as a flow, not raw pipeline logs.",
      ],
      eyebrow: "Zero-trust CI/CD",
      highlight: "Deployment safety narrative",
      summary:
        "Uses the pipeline repo as supporting evidence for how the live site will be controlled and shipped.",
      title: "Pipeline and security lane",
    },
    {
      bullets: [
        "Keep failover and remediation public-safe and diagrammatic.",
        "Reserve live drills and protected metrics for the private site.",
      ],
      eyebrow: "DR + self-healing",
      highlight: "Resilience showcase",
      summary:
        "Pairs the failover demo with self-healing infrastructure to round out the platform story.",
      title: "Recovery and remediation panel",
    },
  ],
};

export const simulationReviewItems: ReviewQueueItem[] = [
  createReviewItem("doc-sim-3001", {
    accountCandidates: ["acct-3001-med-45678"],
    accountId: "acct-3001-med-45678",
    accountStatus: "matched",
    averageConfidence: 0.74,
    extractedFields: [
      { confidence: 0.94, name: "debtor_name", value: "Jordan Patel" },
      { confidence: 0.91, name: "issuer_name", value: "Regional Medical Collections" },
      { confidence: 0.87, name: "account_number", value: "MED-45678" },
      { confidence: 0.62, name: "balance_due", value: "$3,182.40" },
    ],
    fileName: "acct-3001-demand-letter.pdf",
    issuerCategory: "collection_agency",
    issuerName: "Regional Medical Collections",
    profileId: "collection_notice",
    reasons: ["low_confidence", "multiple_account_candidates"],
    source: "azure_sftp",
    sourceUri: "az://raw-documents/medical/2026/04/acct-3001-demand-letter.pdf",
  }),
  createReviewItem("doc-sim-4109", {
    accountCandidates: [],
    accountId: null,
    accountStatus: "unmatched",
    averageConfidence: 0.69,
    extractedFields: [
      { confidence: 0.73, name: "debtor_name", value: "Taylor Brooks" },
      { confidence: 0.58, name: "statement_date", value: "Needs confirmation" },
      { confidence: 0.67, name: "issuer_name", value: "Summit Bank" },
      { confidence: 0.6, name: "document_type", value: "Monthly statement" },
    ],
    fileName: "summit-statement-scan.jpg",
    issuerCategory: "bank",
    issuerName: "Summit Bank",
    profileId: "bank_statement",
    reasons: ["missing_required_field", "unmatched_account"],
    source: "secure_web_upload",
    sourceUri: "upload://portal/intake/2026/04/04/summit-statement-scan.jpg",
  }),
  createReviewItem("doc-sim-4402", {
    accountCandidates: ["acct-2407-mail-82114"],
    accountId: "acct-2407-mail-82114",
    accountStatus: "matched",
    averageConfidence: 0.81,
    extractedFields: [
      { confidence: 0.88, name: "debtor_name", value: "Avery Jordan" },
      { confidence: 0.85, name: "issuer_name", value: "Northline Recovery" },
      { confidence: 0.77, name: "account_number", value: "NR-82114" },
      { confidence: 0.74, name: "document_type", value: "Servicing email packet" },
    ],
    fileName: "northline-email-intake.eml",
    issuerCategory: "collection_agency",
    issuerName: "Northline Recovery",
    profileId: "collection_notice",
    reasons: ["low_confidence"],
    source: "email_intake",
    sourceUri: "mail://debtops-intake/inbox/2026/04/04/northline-email-intake.eml",
  }),
  createReviewItem("doc-sim-5207", {
    accountCandidates: ["acct-5207-court-118"],
    accountId: "acct-5207-court-118",
    accountStatus: "ambiguous",
    averageConfidence: 0.78,
    extractedFields: [
      { confidence: 0.82, name: "court_name", value: "County Civil Court" },
      { confidence: 0.79, name: "case_number", value: "CC-118-2026" },
      { confidence: 0.74, name: "debtor_name", value: "Morgan Lee" },
      { confidence: 0.66, name: "account_reference", value: "PKT-17" },
    ],
    fileName: "court-packet-17.zip",
    issuerCategory: "court",
    issuerName: "County Civil Court",
    profileId: "court_filing",
    reasons: ["low_confidence"],
    source: "partner_api",
    sourceUri: "api://partner-referrals/v1/cases/cc-118-2026",
  }),
];
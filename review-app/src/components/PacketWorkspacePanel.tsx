import { useEffect, useRef, useState, type ReactNode } from "react";

import type {
  ManagedClassificationDefinitionRecord,
  ManagedDocumentTypeDefinitionRecord,
  ManagedPromptProfileRecord,
  OperatorContractsResponse,
  PromptProfileVersionRecord,
} from "../api/operatorContractsApi";
import type { PacketQueueItem } from "../api/packetQueueApi";
import {
  buildPacketDocumentContentUrl,
  type DocumentAssetRecord,
  type PacketProcessingStageName,
  type RecommendationReviewDisposition,
} from "../api/packetWorkspaceApi";
import type {
  AccountMatchRunRecord,
  AuditEventRecord,
  ClassificationResultRecord,
  ExtractionResultRecord,
  OcrResultRecord,
  OperatorNoteRecord,
  PacketEventRecord,
  PacketDocumentRecord,
  PacketWorkspaceSnapshot,
  ProcessingJobRecord,
  RecommendationResultRecord,
  RecommendationRunRecord,
  ReviewDecisionRecord,
  ReviewTaskRecord,
} from "../api/packetWorkspaceApi";
import {
  SectionHeading,
  StatusBadge,
  SurfaceCard,
  SurfaceTimelineItem,
  SurfacePanel,
  type StatusBadgeTone,
} from "./SurfacePrimitives";

export type WorkspaceTabId =
  | "overview"
  | "intake"
  | "documents"
  | "viewer"
  | "ocr"
  | "extraction"
  | "matching"
  | "review"
  | "pipeline"
  | "rules_doctypes"
  | "recommendations"
  | "audit";

export type PacketWorkspaceReviewDecisionStatus = "approved" | "rejected";

export type PacketWorkspaceReviewDecisionInput = {
  decision_reason_code?: string;
  decision_status: PacketWorkspaceReviewDecisionStatus;
  expected_row_version: string;
  review_notes?: string;
  review_task_id: string;
  selected_account_id?: string | null;
};

export type PacketWorkspaceExtractionFieldEditInput = {
  field_name: string;
  value: string;
};

export type PacketWorkspaceExtractionEditInput = {
  expected_row_version: string;
  field_edits: PacketWorkspaceExtractionFieldEditInput[];
  review_task_id: string;
};

export type PacketWorkspaceReviewNoteInput = {
  expected_row_version: string;
  is_private?: boolean;
  note_text: string;
  review_task_id: string;
};

export type PacketWorkspaceReviewAssignmentInput = {
  assigned_user_email?: string | null;
  assigned_user_id?: string | null;
  expected_row_version: string;
  review_task_id: string;
};

export type PacketWorkspaceReviewTaskCreateInput = {
  assigned_user_email?: string | null;
  assigned_user_id?: string | null;
  document_id: string;
  notes_summary?: string | null;
  selected_account_id?: string | null;
};

type PacketWorkspacePanelProps = {
  assignmentErrorMessage: string | null;
  assignmentSuccessMessage: string | null;
  createTaskErrorMessage: string | null;
  createTaskSuccessMessage: string | null;
  decisionErrorMessage: string | null;
  errorMessage: string | null;
  extractionEditErrorMessage: string | null;
  extractionEditSuccessMessage: string | null;
  intakeActionErrorMessage: string | null;
  intakeActionSuccessMessage: string | null;
  isAssignmentSubmitting: boolean;
  isExtractionEditSubmitting: boolean;
  isDecisionSubmitting: boolean;
  isNoteSubmitting: boolean;
  isReviewTaskCreateSubmitting: boolean;
  isLoading: boolean;
  isOperatorContractsLoading: boolean;
  isReplayingPacket: boolean;
  noteErrorMessage: string | null;
  noteSuccessMessage: string | null;
  onExecuteStage?: (stageName: PacketProcessingStageName) => Promise<void> | void;
  onRefresh: () => void;
  onSelectTab?: (tabId: WorkspaceTabId) => Promise<void> | void;
  onReplayPacket?: () => Promise<void> | void;
  onReviewRecommendation?: (
    recommendationResultId: string,
    disposition: RecommendationReviewDisposition,
  ) => Promise<void> | void;
  onRetryStage?: (stageName: PacketProcessingStageName) => Promise<void> | void;
  onSubmitReviewDecision?: (
    decision: PacketWorkspaceReviewDecisionInput,
  ) => Promise<void> | void;
  onSubmitExtractionEdits?: (
    extractionEdit: PacketWorkspaceExtractionEditInput,
  ) => Promise<void> | void;
  onSubmitReviewAssignment?: (
    assignment: PacketWorkspaceReviewAssignmentInput,
  ) => Promise<void> | void;
  onSubmitReviewNote?: (
    note: PacketWorkspaceReviewNoteInput,
  ) => Promise<void> | void;
  onSubmitReviewTaskCreate?: (
    reviewTask: PacketWorkspaceReviewTaskCreateInput,
  ) => Promise<void> | void;
  operatorContracts: OperatorContractsResponse | null;
  operatorContractsErrorMessage: string | null;
  panelDescription: string;
  panelTitle: string;
  pipelineActionErrorMessage: string | null;
  pipelineActionSuccessMessage: string | null;
  preferredTab: WorkspaceTabId;
  processingRecommendationReview: string | null;
  processingPipelineAction: string | null;
  recommendationActionErrorMessage: string | null;
  recommendationActionSuccessMessage: string | null;
  reviewerEmail: string | null;
  selectedPacketSummary: PacketQueueItem | null;
  tabPriorityAnchor?: WorkspaceTabId;
  workspace: PacketWorkspaceSnapshot | null;
  workspaceLastLoadedAt: string | null;
};

type ExtractedField = {
  confidence?: number;
  name: string;
  value: string;
};

type ReviewFieldChange = {
  confidence?: number;
  currentValue: string;
  fieldName: string;
  originalValue: string;
};

type AuditEventFilterMode = "all" | "field-edits";

type ExtractionReviewEditMetadata = {
  changeCount: number;
  changedFieldNames: string[];
  editedAtUtc: string | null;
  reviewTaskId: string | null;
  sourceExtractionResultId: string | null;
};

type RefreshDeltaDetail = {
  current: string;
  previous: string;
};

type DocumentRefreshDelta = {
  accountDetail?: RefreshDeltaDetail;
  hasAccountChange: boolean;
  attentionDetail?: RefreshDeltaDetail;
  hasAttentionChange: boolean;
  contractDetail?: RefreshDeltaDetail;
  hasContractChange: boolean;
  extractionDetail?: RefreshDeltaDetail;
  hasExtractionChange: boolean;
  ocrDetail?: RefreshDeltaDetail;
  hasOcrChange: boolean;
  processingDetail?: RefreshDeltaDetail;
  hasProcessingChange: boolean;
  recommendationDetail?: RefreshDeltaDetail;
  hasRecommendationChange: boolean;
  reviewDetail?: RefreshDeltaDetail;
  hasReviewChange: boolean;
};

type DocumentRefreshComparisonKey = {
  accountKey: string;
  accountSummary: string;
  attentionKey: string;
  attentionSummary: string;
  contractKey: string;
  contractSummary: string;
  extractionKey: string;
  extractionSummary: string;
  ocrKey: string;
  ocrSummary: string;
  processingKey: string;
  processingSummary: string;
  recommendationKey: string;
  recommendationSummary: string;
  reviewKey: string;
  reviewSummary: string;
};

type DocumentContractStatus = {
  classificationLabel: string;
  documentTypeLabel: string;
  missingRequiredFields: string[];
  promptProfileLabel: string;
  requiredFieldCount: number;
};

type DocumentAttentionState = {
  detail: string;
  summary: string;
  tone: StatusBadgeTone;
};

type DocumentProgressStage = {
  detail?: string;
  hasRefreshChange?: boolean;
  label: string;
  refreshDetail?: string;
  status: string;
  tone: StatusBadgeTone;
};

type DocumentSummarySubcard = {
  collapsedSummary?: string;
  detail: string;
  hasRefreshChange?: boolean;
  id: string;
  refreshCopy?: string;
  refreshDetail?: string;
  summary: string;
  title: string;
  tone?: StatusBadgeTone;
};

type DocumentWorkspaceState = {
  accountComparison?: AccountComparisonRow;
  auditEventCount: number;
  contractStatus?: DocumentContractStatus;
  extractionReviewEditMetadata: ExtractionReviewEditMetadata | null;
  latestExtraction?: ExtractionResultRecord;
  latestJob?: ProcessingJobRecord;
  latestOcr?: OcrResultRecord;
  latestPacketEvent?: PacketEventRecord;
  latestRecommendation?: RecommendationResultRecord;
  operatorNoteCount: number;
  refreshDelta?: DocumentRefreshDelta;
  reviewDecision?: ReviewDecisionRecord;
  reviewTask?: ReviewTaskRecord;
};

type WorkspaceTabPreview = {
  id: WorkspaceTabId;
  label: string;
  tone: StatusBadgeTone;
  urgencyReason?: string;
};

type ViewerPreviewMode = "download" | "image" | "pdf";

type AccountComparisonRow = {
  document: PacketDocumentRecord;
  finalAccountId: string | null;
  hasOverride: boolean;
  matchRun?: AccountMatchRunRecord;
  reviewDecision?: ReviewDecisionRecord;
  reviewTask?: ReviewTaskRecord;
  suggestedAccountId: string | null;
  taskAccountId: string | null;
};

type WorkspaceTimelineEntry = {
  actor: string | null;
  detail: string;
  id: string;
  payload?: Record<string, unknown> | null;
  state: "active" | "complete";
  timestamp: string;
  title: string;
};

type IntakeReplayState = {
  buttonLabel: string;
  description: string;
  disabledReason: string | null;
};

type ReviewTaskActionability = {
  isActionable: boolean;
  message: string | null;
};

type ReviewViewerReturnTarget = {
  focusFieldName: string | null;
  reviewTaskId: string;
};

type PipelineStageDefinition = {
  description: string;
  id: PacketProcessingStageName;
};

const workspaceTabs: readonly { id: WorkspaceTabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "intake", label: "Intake" },
  { id: "documents", label: "Documents" },
  { id: "viewer", label: "Viewer" },
  { id: "ocr", label: "OCR" },
  { id: "extraction", label: "Extraction" },
  { id: "matching", label: "Matching" },
  { id: "review", label: "Review" },
  { id: "pipeline", label: "Pipeline" },
  { id: "rules_doctypes", label: "Rules + Doctypes" },
  { id: "recommendations", label: "Recommendations" },
  { id: "audit", label: "Audit" },
] as const;

const defaultVisibleWorkspaceTabCount = 5;
const defaultVisibleDocumentSubcardCount = 5;
const statusBadgeTonePriority: Record<StatusBadgeTone, number> = {
  accent: 2,
  danger: 0,
  neutral: 4,
  success: 3,
  warning: 1,
};

const workspaceTabPriorityByAnchor: Partial<
  Record<WorkspaceTabId, readonly WorkspaceTabId[]>
> = {
  audit: ["audit", "review", "recommendations", "documents", "pipeline"],
  documents: ["documents", "viewer", "intake", "pipeline", "audit"],
  intake: ["intake", "documents", "pipeline", "overview", "audit"],
  matching: ["matching", "review", "documents", "recommendations", "audit"],
  overview: ["overview", "documents", "review", "pipeline", "audit"],
  pipeline: ["pipeline", "ocr", "extraction", "documents", "audit"],
  recommendations: [
    "recommendations",
    "review",
    "matching",
    "documents",
    "audit",
  ],
  review: ["review", "viewer", "matching", "documents", "audit"],
  rules_doctypes: [
    "rules_doctypes",
    "documents",
    "extraction",
    "review",
    "recommendations",
  ],
  viewer: ["viewer", "documents", "ocr", "extraction", "review"],
};

function getWorkspaceTabLabel(tabId: WorkspaceTabId) {
  return workspaceTabs.find((tab) => tab.id === tabId)?.label ?? toLabel(tabId);
}

function getPrioritizedWorkspaceTabs(anchorTab: WorkspaceTabId) {
  const prioritizedIds = workspaceTabPriorityByAnchor[anchorTab] ?? [anchorTab];
  const seen = new Set(prioritizedIds);

  return [
    ...prioritizedIds.map((tabId) => ({ id: tabId, label: getWorkspaceTabLabel(tabId) })),
    ...workspaceTabs.filter((tab) => !seen.has(tab.id)),
  ];
}

function formatTabPrioritySummary(anchorTab: WorkspaceTabId) {
  const prioritizedTabs = getPrioritizedWorkspaceTabs(anchorTab)
    .slice(0, 5)
    .map((tab) => tab.label);
  const summary = prioritizedTabs.reduce<string[]>((items, label, index) => {
    if (index === 0) {
      return [...items, label];
    }

    if (index === prioritizedTabs.length - 1) {
      return [...items, `and ${label}`];
    }

    return [...items, label];
  }, []);

  return `${getWorkspaceTabLabel(anchorTab)} lane keeps ${summary.join(", ")} first.`;
}

function getWorkspaceTabUrgency(options: {
  selectedPacketSummary: PacketQueueItem | null;
  tabId: WorkspaceTabId;
  workspace: PacketWorkspaceSnapshot | null;
}): Pick<WorkspaceTabPreview, "tone" | "urgencyReason"> {
  switch (options.tabId) {
    case "pipeline": {
      const latestJobStageName = options.selectedPacketSummary?.latest_job_stage_name;
      const latestJobStatus = options.selectedPacketSummary?.latest_job_status;
      const packetStatus = options.selectedPacketSummary?.status;

      if (latestJobStatus === "failed" || latestJobStatus === "blocked") {
        return { tone: "danger", urgencyReason: "Pipeline failure" };
      }

      if (packetStatus === "failed" || packetStatus === "blocked") {
        return { tone: "danger", urgencyReason: "Pipeline failure" };
      }

      if (
        latestJobStageName &&
        latestJobStageName !== "review" &&
        (latestJobStatus === "queued" ||
          latestJobStatus === "running" ||
          latestJobStatus === "ocr_running")
      ) {
        return {
          tone: getWorkflowStatusTone(latestJobStatus),
          urgencyReason:
            latestJobStatus === "queued" ? "Pipeline queued" : "Pipeline running",
        };
      }

      return { tone: "neutral" };
    }
    case "audit": {
      const hasAuditSignal =
        (options.selectedPacketSummary?.audit_event_count ?? 0) > 0 ||
        (options.selectedPacketSummary?.operator_note_count ?? 0) > 0 ||
        (options.workspace?.audit_events.length ?? 0) > 0 ||
        (options.workspace?.operator_notes.length ?? 0) > 0 ||
        (options.workspace?.review_decisions.length ?? 0) > 0;

      return hasAuditSignal
        ? { tone: "accent", urgencyReason: "Fresh audit activity" }
        : { tone: "neutral" };
    }
    default:
      return { tone: "neutral" };
  }
}

function getVisibleWorkspaceTabs(options: {
  activeTab: WorkspaceTabId;
  prioritizedTabs: readonly { id: WorkspaceTabId; label: string }[];
  showAllTabs: boolean;
}) {
  if (
    options.showAllTabs ||
    options.prioritizedTabs.length <= defaultVisibleWorkspaceTabCount
  ) {
    return options.prioritizedTabs;
  }

  const primaryTabs = options.prioritizedTabs.slice(0, defaultVisibleWorkspaceTabCount);

  if (primaryTabs.some((tab) => tab.id === options.activeTab)) {
    return primaryTabs;
  }

  const activeTab = options.prioritizedTabs.find(
    (tab) => tab.id === options.activeTab,
  );

  return activeTab ? [...primaryTabs, activeTab] : primaryTabs;
}

function prioritizeHiddenWorkspaceTabs(hiddenTabs: readonly WorkspaceTabPreview[]) {
  return hiddenTabs
    .map((tab, index) => ({
      index,
      priority: statusBadgeTonePriority[tab.tone],
      tab,
    }))
    .sort((left, right) => {
      if (left.priority !== right.priority) {
        return left.priority - right.priority;
      }

      return left.index - right.index;
    })
    .map((item) => item.tab);
}

function formatWorkspaceTabToggleLabel(hiddenTabs: readonly WorkspaceTabPreview[]) {
  const baseLabel = `More views (${hiddenTabs.length})`;

  if (hiddenTabs.length === 0) {
    return baseLabel;
  }

  const prioritizedHiddenTabs = prioritizeHiddenWorkspaceTabs(hiddenTabs);
  const bestNextTab = prioritizedHiddenTabs[0]?.label;
  const bestNextUrgencyReason = prioritizedHiddenTabs[0]?.urgencyReason;
  const secondaryPreviewTab = prioritizedHiddenTabs[1]?.label;
  const remainingCount = prioritizedHiddenTabs.length - (secondaryPreviewTab ? 2 : 1);
  const bestNextTabLabel = bestNextUrgencyReason
    ? `${bestNextTab} (${bestNextUrgencyReason})`
    : bestNextTab;

  if (!bestNextTab) {
    return baseLabel;
  }

  if (!secondaryPreviewTab) {
    return `${baseLabel} · Best next: ${bestNextTabLabel}`;
  }

  return remainingCount > 0
    ? `${baseLabel} · Best next: ${bestNextTabLabel} · ${secondaryPreviewTab} and ${remainingCount} more`
    : `${baseLabel} · Best next: ${bestNextTabLabel} · ${secondaryPreviewTab}`;
}

function getVisibleDocumentSummarySubcards(options: {
  isExpanded: boolean;
  subcards: readonly DocumentSummarySubcard[];
}) {
  if (
    options.isExpanded ||
    options.subcards.length <= defaultVisibleDocumentSubcardCount
  ) {
    return options.subcards;
  }

  return options.subcards.slice(0, defaultVisibleDocumentSubcardCount);
}

function prioritizeHiddenDocumentSummarySubcards(
  hiddenSubcards: readonly DocumentSummarySubcard[],
) {
  return hiddenSubcards
    .map((subcard, index) => ({
      index,
      priority: statusBadgeTonePriority[subcard.tone ?? "neutral"],
      subcard,
    }))
    .sort((left, right) => {
      if (left.priority !== right.priority) {
        return left.priority - right.priority;
      }

      return left.index - right.index;
    })
    .map((item) => item.subcard);
}

function formatHiddenDocumentSummaryToggleLabel(options: {
  hiddenSubcards: readonly DocumentSummarySubcard[];
}) {
  const baseLabel = `More status cards (${options.hiddenSubcards.length})`;

  if (options.hiddenSubcards.length === 0) {
    return baseLabel;
  }

  const prioritizedHiddenSubcards = prioritizeHiddenDocumentSummarySubcards(
    options.hiddenSubcards,
  );

  const hiddenConcernSummaries = prioritizedHiddenSubcards
    .flatMap((subcard) => (subcard.collapsedSummary ? [subcard.collapsedSummary] : []))
    .slice(0, 2);

  if (hiddenConcernSummaries.length > 0) {
    return `${baseLabel} · Next hidden concern: ${hiddenConcernSummaries.join("; ")}`;
  }

  const hiddenChangedTitles = prioritizedHiddenSubcards
    .filter((subcard) => subcard.hasRefreshChange)
    .slice(0, 2)
    .map((subcard) => subcard.title);
  const remainingChangedCount =
    options.hiddenSubcards.filter((subcard) => subcard.hasRefreshChange).length -
    hiddenChangedTitles.length;

  if (hiddenChangedTitles.length === 1) {
    return remainingChangedCount > 0
      ? `${baseLabel} · Recent hidden change: ${hiddenChangedTitles[0]} and ${remainingChangedCount} more`
      : `${baseLabel} · Recent hidden change: ${hiddenChangedTitles[0]}`;
  }

  if (hiddenChangedTitles.length > 1) {
    return remainingChangedCount > 0
      ? `${baseLabel} · Recent hidden change: ${hiddenChangedTitles[0]}, ${hiddenChangedTitles[1]}, and ${remainingChangedCount} more`
      : `${baseLabel} · Recent hidden change: ${hiddenChangedTitles[0]} and ${hiddenChangedTitles[1]}`;
  }

  const hiddenSubcardTitles = prioritizedHiddenSubcards
    .slice(0, 2)
    .map((subcard) => subcard.title);
  const remainingCount = options.hiddenSubcards.length - hiddenSubcardTitles.length;

  if (hiddenSubcardTitles.length === 1) {
    return remainingCount > 0
      ? `${baseLabel} · Includes ${hiddenSubcardTitles[0]} and ${remainingCount} more`
      : `${baseLabel} · Includes ${hiddenSubcardTitles[0]}`;
  }

  if (hiddenSubcardTitles.length > 1) {
    return remainingCount > 0
      ? `${baseLabel} · Includes ${hiddenSubcardTitles[0]}, ${hiddenSubcardTitles[1]}, and ${remainingCount} more`
      : `${baseLabel} · Includes ${hiddenSubcardTitles[0]} and ${hiddenSubcardTitles[1]}`;
  }

  return baseLabel;
}

function getWorkflowStatusTone(status: string | null | undefined): StatusBadgeTone {
  switch (status) {
    case "completed":
    case "succeeded":
      return "success";
    case "failed":
    case "blocked":
    case "quarantined":
      return "danger";
    case "awaiting_review":
    case "queued":
    case "classifying":
    case "matching":
    case "ocr_running":
    case "running":
    case "extracting":
      return "warning";
    case "ready_for_recommendation":
      return "accent";
    default:
      return "neutral";
  }
}

function getPacketStatusTone(status: string | null | undefined): StatusBadgeTone {
  switch (status) {
    case "completed":
      return "success";
    case "failed":
    case "blocked":
    case "quarantined":
      return "danger";
    case "awaiting_review":
      return "warning";
    case "ready_for_recommendation":
      return "accent";
    default:
      return "neutral";
  }
}

const pipelineStageDefinitions: readonly PipelineStageDefinition[] = [
  {
    description: "Run any queued classification work for the selected packet.",
    id: "classification",
  },
  {
    description: "Execute queued OCR work and advance documents into extraction.",
    id: "ocr",
  },
  {
    description: "Execute queued extraction work and downstream matching/review handoff.",
    id: "extraction",
  },
  {
    description: "Execute queued recommendation work for review-complete documents.",
    id: "recommendation",
  },
] as const;

function toLabel(value: string | null | undefined) {
  if (!value) {
    return "Unknown";
  }

  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "Not available";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatConfidence(confidence: number | null | undefined) {
  if (confidence === undefined || confidence === null) {
    return "n/a";
  }

  return `${Math.round(confidence * 100)}%`;
}

function formatCount(count: number, noun: string) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function getPreviewMode(contentType: string | null | undefined): ViewerPreviewMode {
  const normalizedContentType = (contentType || "").toLowerCase();
  if (normalizedContentType.includes("pdf")) {
    return "pdf";
  }

  if (normalizedContentType.startsWith("image/")) {
    return "image";
  }

  return "download";
}

function truncateText(value: string | null | undefined, maxLength: number) {
  if (!value) {
    return null;
  }

  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength).trimEnd()}...`;
}

function buildExtractedFieldKey(field: Pick<ExtractedField, "name" | "value">) {
  return `${field.name}:${field.value}`;
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function countTextMatches(text: string | null | undefined, value: string | null | undefined) {
  const normalizedValue = value?.trim();
  if (!text || !normalizedValue) {
    return 0;
  }

  const matches = text.match(new RegExp(escapeRegExp(normalizedValue), "gi"));
  return matches?.length ?? 0;
}

function buildHighlightedTextPreview(
  text: string | null | undefined,
  highlightedValue: string | null | undefined,
): {
  content: ReactNode;
  matchCount: number;
} {
  if (!text) {
    return {
      content: "No OCR excerpt or document text is stored for this document yet.",
      matchCount: 0,
    };
  }

  const normalizedValue = highlightedValue?.trim();
  if (!normalizedValue) {
    return { content: text, matchCount: 0 };
  }

  const pattern = new RegExp(`(${escapeRegExp(normalizedValue)})`, "gi");
  const segments = text.split(pattern);
  const content: ReactNode[] = [];
  let matchCount = 0;

  for (let index = 0; index < segments.length; index += 1) {
    const segment = segments[index];
    if (!segment) {
      continue;
    }

    if (segment.toLowerCase() === normalizedValue.toLowerCase()) {
      matchCount += 1;
      content.push(
        <mark className="workspace-highlight-mark" key={`highlight-${index}`}>
          {segment}
        </mark>,
      );
      continue;
    }

    content.push(segment);
  }

  return {
    content: matchCount > 0 ? content : text,
    matchCount,
  };
}

function getLatestRecordByDocument<T extends { created_at_utc: string; document_id: string }>(
  records: readonly T[],
) {
  const latestByDocument = new Map<string, T>();

  for (const record of records) {
    const current = latestByDocument.get(record.document_id);
    if (!current) {
      latestByDocument.set(record.document_id, record);
      continue;
    }

    if (Date.parse(record.created_at_utc) >= Date.parse(current.created_at_utc)) {
      latestByDocument.set(record.document_id, record);
    }
  }

  return latestByDocument;
}

function getLatestOptionalDocumentRecord<
  T extends { created_at_utc: string; document_id?: string | null },
>(records: readonly T[]) {
  const latestByDocument = new Map<string, T>();

  for (const record of records) {
    if (!record.document_id) {
      continue;
    }

    const current = latestByDocument.get(record.document_id);
    if (!current) {
      latestByDocument.set(record.document_id, record);
      continue;
    }

    if (Date.parse(record.created_at_utc) >= Date.parse(current.created_at_utc)) {
      latestByDocument.set(record.document_id, record);
    }
  }

  return latestByDocument;
}

function getLatestReviewDecisionsByTask(reviewDecisions: readonly ReviewDecisionRecord[]) {
  const latestByTask = new Map<string, ReviewDecisionRecord>();

  for (const reviewDecision of reviewDecisions) {
    const current = latestByTask.get(reviewDecision.review_task_id);
    if (
      !current ||
      Date.parse(reviewDecision.decided_at_utc) >= Date.parse(current.decided_at_utc)
    ) {
      latestByTask.set(reviewDecision.review_task_id, reviewDecision);
    }
  }

  return latestByTask;
}

function buildAccountComparisonRows(workspace: PacketWorkspaceSnapshot): AccountComparisonRow[] {
  const latestMatchRuns = getLatestRecordByDocument(workspace.account_match_runs);
  const latestReviewDecisions = getLatestReviewDecisionsByTask(
    workspace.review_decisions,
  );
  const reviewTaskByDocument = new Map(
    workspace.review_tasks.map((reviewTask) => [reviewTask.document_id, reviewTask]),
  );

  return workspace.documents.map((document) => {
    const matchRun = latestMatchRuns.get(document.document_id);
    const reviewTask = reviewTaskByDocument.get(document.document_id);
    const reviewDecision = reviewTask
      ? latestReviewDecisions.get(reviewTask.review_task_id)
      : undefined;
    const suggestedAccountId =
      matchRun?.selected_account_id ||
      matchRun?.candidates[0]?.account_id ||
      document.account_candidates[0] ||
      null;
    const taskAccountId = reviewTask?.selected_account_id || null;
    const finalAccountId =
      reviewDecision?.selected_account_id || taskAccountId || suggestedAccountId;

    return {
      document,
      finalAccountId,
      hasOverride: Boolean(
        finalAccountId && suggestedAccountId && finalAccountId !== suggestedAccountId,
      ),
      matchRun,
      reviewDecision,
      reviewTask,
      suggestedAccountId,
      taskAccountId,
    };
  });
}

function buildAccountLinkageHistory(row: AccountComparisonRow) {
  const entries: {
    actor?: string | null;
    detail: string;
    label: string;
    timestamp: string;
  }[] = [];

  if (row.matchRun) {
    entries.push({
      detail: `Auto-linked ${row.suggestedAccountId || "no account"} from ${formatCount(row.matchRun.candidates.length, "candidate")}.`,
      label: "Match run created",
      timestamp: row.matchRun.created_at_utc,
    });
  }

  if (row.reviewTask) {
    entries.push({
      actor: row.reviewTask.assigned_user_email,
      detail: `${row.reviewTask.assigned_user_email || "Unassigned"} is carrying ${row.taskAccountId || row.suggestedAccountId || "the unresolved linkage"}.`,
      label: row.reviewTask.assigned_user_email ? "Task assigned" : "Task queued",
      timestamp: row.reviewTask.updated_at_utc,
    });
  }

  if (row.reviewDecision) {
    entries.push({
      actor: row.reviewDecision.decided_by_email,
      detail: `Final linkage ${row.reviewDecision.selected_account_id || row.finalAccountId || "not set"}.`,
      label: `Decision ${toLabel(row.reviewDecision.decision_status)}`,
      timestamp: row.reviewDecision.decided_at_utc,
    });
  }

  return entries.sort(
    (left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp),
  );
}

function buildReviewDecisionDetail(reviewDecision: ReviewDecisionRecord) {
  const fragments: string[] = [];

  if (reviewDecision.decision_reason_code) {
    fragments.push(`Reason code ${reviewDecision.decision_reason_code}.`);
  }

  if (reviewDecision.review_notes) {
    fragments.push(reviewDecision.review_notes);
  } else {
    fragments.push(
      `${toLabel(reviewDecision.decision_status)} ${reviewDecision.selected_account_id || "without an account override"}.`,
    );
  }

  return fragments.join(" ");
}

function buildWorkspaceTimeline(workspace: PacketWorkspaceSnapshot): WorkspaceTimelineEntry[] {
  const reviewDecisionEntries: WorkspaceTimelineEntry[] = workspace.review_decisions.map(
    (reviewDecision) => ({
      actor: reviewDecision.decided_by_email || null,
      detail: buildReviewDecisionDetail(reviewDecision),
      id: `review-decision:${reviewDecision.decision_id}`,
      payload: {
        decisionReasonCode: reviewDecision.decision_reason_code,
        decisionStatus: reviewDecision.decision_status,
        reviewTaskId: reviewDecision.review_task_id,
        selectedAccountId: reviewDecision.selected_account_id,
      },
      state:
        reviewDecision.decision_status === "rejected" ? "active" : "complete",
      timestamp: reviewDecision.decided_at_utc,
      title: `Review ${toLabel(reviewDecision.decision_status)}`,
    }),
  );

  const noteEntries: WorkspaceTimelineEntry[] = workspace.operator_notes.map((note) => ({
    actor: note.created_by_email || null,
    detail: note.note_text,
    id: `operator-note:${note.note_id}`,
    payload: note.review_task_id
      ? { reviewTaskId: note.review_task_id, isPrivate: note.is_private }
      : { isPrivate: note.is_private },
    state: "complete",
    timestamp: note.created_at_utc,
    title: "Operator note",
  }));

  const auditEntries: WorkspaceTimelineEntry[] = workspace.audit_events.map(
    (auditEvent) => ({
      actor: auditEvent.actor_email || null,
      detail: summarizeEventPayload(auditEvent.event_payload),
      id: `audit-event:${auditEvent.audit_event_id}`,
      payload: auditEvent.event_payload,
      state:
        auditEvent.event_type.toLowerCase().includes("reject") ||
        auditEvent.event_type.toLowerCase().includes("block")
          ? "active"
          : "complete",
      timestamp: auditEvent.created_at_utc,
      title: auditEvent.event_type,
    }),
  );

  const packetEntries: WorkspaceTimelineEntry[] = workspace.packet_events.map(
    (packetEvent) => ({
      actor: null,
      detail: packetEvent.document_id
        ? `Document ${packetEvent.document_id} · ${summarizeEventPayload(packetEvent.event_payload)}`
        : summarizeEventPayload(packetEvent.event_payload),
      id: `packet-event:${packetEvent.event_id}`,
      payload: packetEvent.event_payload,
      state: getEventMarkerState(packetEvent),
      timestamp: packetEvent.created_at_utc,
      title: packetEvent.event_type,
    }),
  );

  return [
    ...reviewDecisionEntries,
    ...noteEntries,
    ...auditEntries,
    ...packetEntries,
  ].sort((left, right) => toTimestamp(right.timestamp) - toTimestamp(left.timestamp));
}

function buildReviewTaskActivityEntries(
  reviewTask: ReviewTaskRecord,
  options: {
    auditEvents: readonly AuditEventRecord[];
    extractionReviewEditMetadata: ExtractionReviewEditMetadata | null;
    operatorNotes: readonly OperatorNoteRecord[];
    reviewDecision?: ReviewDecisionRecord;
  },
): WorkspaceTimelineEntry[] {
  const entries: WorkspaceTimelineEntry[] = [
    {
      actor: reviewTask.assigned_user_email || null,
      detail: reviewTask.assigned_user_email
        ? `${reviewTask.notes_summary || "Review task opened."} Assigned to ${reviewTask.assigned_user_email}.`
        : reviewTask.notes_summary || "Review task queued without an assignee.",
      id: `review-task:${reviewTask.review_task_id}:opened`,
      state: options.reviewDecision ? "complete" : "active",
      timestamp: reviewTask.created_at_utc,
      title: "Task opened",
    },
  ];

  const hasPersistedExtractionEditEvent = options.auditEvents.some(
    isExtractionEditAuditEvent,
  );
  if (
    options.extractionReviewEditMetadata &&
    options.extractionReviewEditMetadata.editedAtUtc &&
    !hasPersistedExtractionEditEvent &&
    (!options.extractionReviewEditMetadata.reviewTaskId ||
      options.extractionReviewEditMetadata.reviewTaskId === reviewTask.review_task_id)
  ) {
    entries.push({
      actor: null,
      detail: `${formatCount(
        options.extractionReviewEditMetadata.changeCount,
        "field change",
      )} saved for ${
        options.extractionReviewEditMetadata.changedFieldNames.join(", ") ||
        "reviewed fields"
      }.`,
      id: `review-task:${reviewTask.review_task_id}:field-edits`,
      state: "complete",
      timestamp: options.extractionReviewEditMetadata.editedAtUtc,
      title: "Field edits saved",
    });
  }

  const auditEntries: WorkspaceTimelineEntry[] = options.auditEvents.map(
    (auditEvent) => {
      const extractionEditDetails = getExtractionEditAuditEventDetails(auditEvent);

      return {
        actor: auditEvent.actor_email || null,
        detail: extractionEditDetails
          ? `${formatCount(
              extractionEditDetails.changedFields.length,
              "field change",
            )} saved for ${extractionEditDetails.changedFields
              .map((fieldChange) => fieldChange.fieldName)
              .join(", ")}.`
          : summarizeEventPayload(auditEvent.event_payload),
        id: `review-task-audit:${auditEvent.audit_event_id}`,
        state:
          auditEvent.event_type.toLowerCase().includes("reject") ||
          auditEvent.event_type.toLowerCase().includes("block")
            ? ("active" as const)
            : ("complete" as const),
        timestamp: auditEvent.created_at_utc,
        title: extractionEditDetails ? "Field edits saved" : auditEvent.event_type,
      };
    },
  );
  entries.push(...auditEntries);

  const operatorNoteEntries: WorkspaceTimelineEntry[] = options.operatorNotes.map(
    (operatorNote) => ({
      actor: operatorNote.created_by_email || null,
      detail: operatorNote.note_text,
      id: `review-task-note:${operatorNote.note_id}`,
      state: "complete",
      timestamp: operatorNote.created_at_utc,
      title: "Operator note",
    }),
  );
  entries.push(...operatorNoteEntries);

  if (options.reviewDecision) {
    entries.push({
      actor: options.reviewDecision.decided_by_email || null,
      detail: buildReviewDecisionDetail(options.reviewDecision),
      id: `review-task-decision:${options.reviewDecision.decision_id}`,
      state:
        options.reviewDecision.decision_status === "rejected"
          ? "active"
          : "complete",
      timestamp: options.reviewDecision.decided_at_utc,
      title: `Decision ${toLabel(options.reviewDecision.decision_status)}`,
    });
  }

  return entries.sort(
    (left, right) => toTimestamp(right.timestamp) - toTimestamp(left.timestamp),
  );
}

function getLatestJobsByDocument(jobs: readonly ProcessingJobRecord[]) {
  const latestByDocument = new Map<string, ProcessingJobRecord>();

  for (const job of jobs) {
    if (!job.document_id) {
      continue;
    }

    const current = latestByDocument.get(job.document_id);
    if (!current || getMostRecentJobTimestamp(job) >= getMostRecentJobTimestamp(current)) {
      latestByDocument.set(job.document_id, job);
    }
  }

  return latestByDocument;
}

function resolveIntakeReplayState(workspace: PacketWorkspaceSnapshot): IntakeReplayState {
  const latestJobsByDocument = getLatestJobsByDocument(workspace.processing_jobs);
  const staleThreshold = Date.now() - 30 * 60 * 1000;
  const stageOrder: PacketProcessingStageName[] = [
    "classification",
    "ocr",
    "extraction",
    "recommendation",
  ];

  for (const stageName of stageOrder) {
    for (const latestJob of latestJobsByDocument.values()) {
      const isStaleRunningJob =
        latestJob.status === "running" &&
        getMostRecentJobTimestamp(latestJob) <= staleThreshold;
      if (latestJob.stage_name !== stageName) {
        continue;
      }

      if (latestJob.status === "failed" || isStaleRunningJob) {
        return {
          buttonLabel: "Retry failed or stuck work",
          description: `${toLabel(stageName)} has failed or stale work that can be requeued from Intake.`,
          disabledReason: null,
        };
      }
    }
  }

  const documentStatuses = new Set(workspace.documents.map((document) => document.status));
  const packetStatus = workspace.packet.status;

  if (packetStatus === "quarantined") {
    return {
      buttonLabel: "Replay unavailable",
      description: "Quarantined packets must be manually resolved before replay.",
      disabledReason: "Quarantined packets cannot be replayed from Intake.",
    };
  }

  if (packetStatus === "archive_expanding") {
    return {
      buttonLabel: "Archive expansion pending",
      description: "Archive expansion is still in progress, so replay cannot advance the packet yet.",
      disabledReason: "Wait for archive expansion to finish before replaying the packet.",
    };
  }

  if (packetStatus === "awaiting_review" || packetStatus === "blocked") {
    return {
      buttonLabel: "Review action required",
      description: "This packet is paused on operator review rather than pipeline replay.",
      disabledReason: "Review-held packets must be resolved through the Review workspace.",
    };
  }

  if (packetStatus === "completed") {
    return {
      buttonLabel: "Replay unavailable",
      description: "Completed packets do not have queued intake work left to replay.",
      disabledReason: "No replayable intake work remains on this packet.",
    };
  }

  if (packetStatus === "received" || packetStatus === "classifying" || documentStatuses.has("received")) {
    return {
      buttonLabel: "Replay classification",
      description: "Classification is the next actionable intake stage for this packet.",
      disabledReason: null,
    };
  }

  if (packetStatus === "ocr_running" || documentStatuses.has("ocr_running")) {
    return {
      buttonLabel: "Replay OCR",
      description: "OCR is the next actionable stage for the selected packet documents.",
      disabledReason: null,
    };
  }

  if (
    packetStatus === "extracting" ||
    packetStatus === "matching" ||
    documentStatuses.has("extracting") ||
    documentStatuses.has("matching")
  ) {
    return {
      buttonLabel: "Replay extraction",
      description: "Extraction and downstream matching can be replayed from the current packet state.",
      disabledReason: null,
    };
  }

  if (
    packetStatus === "ready_for_recommendation" ||
    documentStatuses.has("ready_for_recommendation")
  ) {
    return {
      buttonLabel: "Replay recommendation",
      description: "Recommendation is the next queued stage for this packet.",
      disabledReason: null,
    };
  }

  return {
    buttonLabel: "Replay unavailable",
    description: "No queued or retryable intake work was found for the selected packet.",
    disabledReason: "The selected packet does not currently expose replayable intake work.",
  };
}

function normalizeLookupKey(value: string | null | undefined) {
  return value?.trim().toLowerCase() || "";
}

function formatManagedContractLabel(
  value: string | null | undefined,
  fallback: string,
) {
  if (!value) {
    return fallback;
  }

  return toLabel(value.replace(/^(cls|doc)_/i, ""));
}

function buildClassificationLookup(
  definitions: readonly ManagedClassificationDefinitionRecord[],
) {
  const lookup = new Map<string, ManagedClassificationDefinitionRecord>();

  for (const definition of definitions) {
    for (const key of [
      definition.classification_id,
      definition.classification_key,
      definition.display_name,
    ]) {
      const normalizedKey = normalizeLookupKey(key);
      if (normalizedKey) {
        lookup.set(normalizedKey, definition);
      }
    }
  }

  return lookup;
}

function buildDocumentTypeLookup(
  definitions: readonly ManagedDocumentTypeDefinitionRecord[],
) {
  const lookup = new Map<string, ManagedDocumentTypeDefinitionRecord>();

  for (const definition of definitions) {
    for (const key of [
      definition.document_type_id,
      definition.document_type_key,
      definition.display_name,
    ]) {
      const normalizedKey = normalizeLookupKey(key);
      if (normalizedKey) {
        lookup.set(normalizedKey, definition);
      }
    }
  }

  return lookup;
}

function getClassificationKey(
  classificationResult: ClassificationResultRecord | undefined,
) {
  const execution = getClassificationExecution(classificationResult);
  const executionClassificationKey = execution?.classificationKey;

  if (typeof executionClassificationKey === "string" && executionClassificationKey.length > 0) {
    return executionClassificationKey;
  }

  return classificationResult?.classification_id || null;
}

function getDocumentTypeKey(
  extractionResult: ExtractionResultRecord | undefined,
  classificationResult: ClassificationResultRecord | undefined,
) {
  const execution = getClassificationExecution(classificationResult);
  const executionDocumentTypeKey = execution?.documentTypeKey;

  if (typeof executionDocumentTypeKey === "string" && executionDocumentTypeKey.length > 0) {
    return executionDocumentTypeKey;
  }

  return extractionResult?.document_type || classificationResult?.document_type_id || null;
}

function getRequiredFieldCoverage(
  definition: ManagedDocumentTypeDefinitionRecord | undefined,
  extractionResult: ExtractionResultRecord | undefined,
) {
  if (!definition) {
    return [];
  }

  const extractedFieldNames = new Set(
    getExtractedFields(extractionResult).map((field) => normalizeLookupKey(field.name)),
  );

  return definition.required_fields.filter(
    (requiredField) => !extractedFieldNames.has(normalizeLookupKey(requiredField)),
  );
}

function buildDocumentContractStatus(
  document: PacketDocumentRecord,
  options: {
    classificationLookup: Map<string, ManagedClassificationDefinitionRecord>;
    documentTypeLookup: Map<string, ManagedDocumentTypeDefinitionRecord>;
    latestClassification?: ClassificationResultRecord;
    latestExtraction?: ExtractionResultRecord;
    promptProfilesById: Map<string, ManagedPromptProfileRecord>;
  },
): DocumentContractStatus {
  const classificationDefinition = options.classificationLookup.get(
    normalizeLookupKey(getClassificationKey(options.latestClassification)),
  );
  const documentTypeDefinition = options.documentTypeLookup.get(
    normalizeLookupKey(
      getDocumentTypeKey(options.latestExtraction, options.latestClassification),
    ),
  );
  const promptProfileId =
    options.latestExtraction?.prompt_profile_id ||
    options.latestClassification?.prompt_profile_id ||
    document.requested_prompt_profile_id ||
    classificationDefinition?.default_prompt_profile_id ||
    documentTypeDefinition?.default_prompt_profile_id ||
    null;
  const promptProfile = promptProfileId
    ? options.promptProfilesById.get(promptProfileId)
    : undefined;
  const missingRequiredFields = getRequiredFieldCoverage(
    documentTypeDefinition,
    options.latestExtraction,
  );

  return {
    classificationLabel:
      classificationDefinition?.display_name ||
      formatManagedContractLabel(
        getClassificationKey(options.latestClassification),
        "Not classified",
      ),
    documentTypeLabel:
      documentTypeDefinition?.display_name ||
      formatManagedContractLabel(
        getDocumentTypeKey(options.latestExtraction, options.latestClassification),
        "Not typed",
      ),
    missingRequiredFields,
    promptProfileLabel:
      promptProfile?.display_name ||
      formatManagedContractLabel(promptProfileId, "Not assigned"),
    requiredFieldCount: documentTypeDefinition?.required_fields.length ?? 0,
  };
}

function getContractCoverageState(contractStatus: DocumentContractStatus | undefined): {
  detail: string;
  status: string;
  tone: StatusBadgeTone;
} {
  if (!contractStatus) {
    return {
      detail: "Classification and managed contract data are not available yet.",
      status: "Contract data unavailable",
      tone: "neutral",
    };
  }

  if (contractStatus.missingRequiredFields.length > 0) {
    return {
      detail: `Prompt ${contractStatus.promptProfileLabel}. Missing required fields: ${contractStatus.missingRequiredFields.join(", ")}.`,
      status: `${formatCount(contractStatus.missingRequiredFields.length, "required field")} missing`,
      tone: "warning",
    };
  }

  if (contractStatus.requiredFieldCount > 0) {
    return {
      detail: `Prompt ${contractStatus.promptProfileLabel}. All managed required fields are present in the current extraction payload.`,
      status: "Managed fields present",
      tone: "success",
    };
  }

  return {
    detail: `Prompt ${contractStatus.promptProfileLabel}. No managed required fields are defined for this document type.`,
    status: "No required fields defined",
    tone: "neutral",
  };
}

function buildProcessingStatusSummary(latestJob: ProcessingJobRecord | undefined) {
  return latestJob
    ? `${toLabel(latestJob.stage_name)} · ${toLabel(latestJob.status)}`
    : "No processing job recorded";
}

function buildExtractionStatusSummary(
  latestExtraction: ExtractionResultRecord | undefined,
) {
  return latestExtraction
    ? `${formatCount(getExtractedFields(latestExtraction).length, "field")} stored`
    : "No extraction stored";
}

function buildOcrStatusSummary(latestOcr: OcrResultRecord | undefined) {
  return latestOcr
    ? `${latestOcr.page_count} pages · ${formatConfidence(latestOcr.ocr_confidence)}`
    : "No OCR stored";
}

function buildRecommendationStatusSummary(
  latestRecommendation: RecommendationResultRecord | undefined,
) {
  return latestRecommendation
    ? `${toLabel(latestRecommendation.disposition)} · ${toLabel(
        latestRecommendation.recommendation_kind,
      )}`
    : "No recommendation stored";
}

function buildContractSummaryStatus(contractStatus: DocumentContractStatus | undefined) {
  return contractStatus
    ? `${contractStatus.documentTypeLabel} · ${contractStatus.classificationLabel}`
    : "No contract status stored";
}

function buildContractRefreshSummary(contractStatus: DocumentContractStatus | undefined) {
  const contractCoverageState = getContractCoverageState(contractStatus);

  return `${buildContractSummaryStatus(contractStatus)} · ${contractCoverageState.status}`;
}

function buildAccountStatusSummary(accountComparison: AccountComparisonRow | undefined) {
  return accountComparison?.finalAccountId
    ? accountComparison.hasOverride
      ? `Override ${accountComparison.finalAccountId}`
      : `Linked ${accountComparison.finalAccountId}`
    : accountComparison?.suggestedAccountId
      ? `Suggested ${accountComparison.suggestedAccountId}`
      : "No account linked";
}

function buildReviewStatusSummary(options: {
  reviewDecision?: ReviewDecisionRecord;
  reviewTask?: ReviewTaskRecord;
}) {
  return options.reviewDecision
    ? `Decision ${toLabel(options.reviewDecision.decision_status)}`
    : options.reviewTask
      ? `Task ${toLabel(options.reviewTask.status)}`
      : "No review task";
}

function buildReviewRefreshSummary(options: {
  reviewDecision?: ReviewDecisionRecord;
  reviewTask?: ReviewTaskRecord;
}) {
  if (options.reviewDecision) {
    return [
      `${toLabel(options.reviewDecision.decision_status)} by ${
        options.reviewDecision.decided_by_email || "an operator"
      }`,
      options.reviewDecision.selected_account_id || "No selected account",
    ].join(" · ");
  }

  if (options.reviewTask) {
    return [
      toLabel(options.reviewTask.status),
      options.reviewTask.assigned_user_email || "Unassigned",
      options.reviewTask.selected_account_id || "No selected account",
    ].join(" · ");
  }

  return "No review task";
}

function getReviewDecisionTone(status: string | null | undefined): StatusBadgeTone {
  switch (status) {
    case "accepted":
    case "approved":
      return "success";
    case "rejected":
      return "danger";
    default:
      return "accent";
  }
}

function buildDocumentAttentionState(options: {
  accountComparison?: AccountComparisonRow;
  contractStatus?: DocumentContractStatus;
  document: PacketDocumentRecord;
  latestExtraction?: ExtractionResultRecord;
  latestJob?: ProcessingJobRecord;
  latestOcr?: OcrResultRecord;
  latestRecommendation?: RecommendationResultRecord;
  reviewDecision?: ReviewDecisionRecord;
  reviewTask?: ReviewTaskRecord;
}): DocumentAttentionState {
  const suggestedAccountId =
    options.accountComparison?.suggestedAccountId ||
    options.document.account_candidates[0] ||
    "";
  const finalAccountId = options.accountComparison?.finalAccountId || "";
  const missingRequiredCount =
    options.contractStatus?.missingRequiredFields.length ?? 0;

  if (options.reviewDecision) {
    const decisionLabel = toLabel(options.reviewDecision.decision_status);
    const selectedAccountId = options.reviewDecision.selected_account_id || "No account";

    return {
      detail: `${decisionLabel} was recorded by ${
        options.reviewDecision.decided_by_email || "an operator"
      }${options.reviewDecision.selected_account_id ? ` for ${selectedAccountId}` : ""}.`,
      summary: `No action pending · ${decisionLabel} · ${selectedAccountId}`,
      tone: getReviewDecisionTone(options.reviewDecision.decision_status),
    };
  }

  if (options.reviewTask) {
    const assignedReviewer = options.reviewTask.assigned_user_email || "an operator";

    if (!finalAccountId && suggestedAccountId) {
      return {
        detail: `Suggested account ${suggestedAccountId} is waiting for ${assignedReviewer} to confirm before the review decision is finalized.`,
        summary: `Confirm account · ${suggestedAccountId}`,
        tone: "warning",
      };
    }

    if (missingRequiredCount > 0) {
      return {
        detail: `${formatCount(missingRequiredCount, "required field")} still missing before ${assignedReviewer} can close the review task.`,
        summary: `Backfill fields · ${formatCount(missingRequiredCount, "missing field")}`,
        tone: "warning",
      };
    }

    return {
      detail: `${toLabel(options.reviewTask.status)} is assigned to ${assignedReviewer}${
        options.reviewTask.selected_account_id
          ? ` with ${options.reviewTask.selected_account_id} selected.`
          : "."
      }`,
      summary: `Complete review · ${assignedReviewer}`,
      tone:
        options.reviewTask.status === "awaiting_review" ? "warning" : "accent",
    };
  }

  if (options.latestRecommendation) {
    return {
      detail: `${toLabel(options.latestRecommendation.disposition)} ${toLabel(
        options.latestRecommendation.recommendation_kind,
      )} guidance is stored and ready for an operator review task.`,
      summary: `Start review · ${toLabel(options.latestRecommendation.disposition)}`,
      tone: options.latestRecommendation.reviewed_at_utc ? "accent" : "warning",
    };
  }

  if (missingRequiredCount > 0) {
    return {
      detail: `${formatCount(missingRequiredCount, "required field")} still missing from the managed extraction contract before the document is review-ready.`,
      summary: `Backfill fields · ${formatCount(missingRequiredCount, "missing field")}`,
      tone: "warning",
    };
  }

  if (options.latestExtraction) {
    if (!finalAccountId && suggestedAccountId) {
      return {
        detail: `Extraction is stored, but suggested account ${suggestedAccountId} still needs operator confirmation.`,
        summary: `Confirm account · ${suggestedAccountId}`,
        tone: "warning",
      };
    }

    if (!finalAccountId) {
      return {
        detail: "Extraction is stored, but no linked account is recorded yet.",
        summary: "Resolve account link",
        tone: "warning",
      };
    }

    return {
      detail: `Extraction and account linkage are ready to produce recommendation guidance for ${finalAccountId}.`,
      summary: `Generate recommendation · ${finalAccountId}`,
      tone: "accent",
    };
  }

  if (options.latestOcr) {
    return {
      detail: "OCR output is stored and the document is waiting for extraction.",
      summary: "Run extraction",
      tone: "accent",
    };
  }

  if (options.latestJob) {
    const stageLabel = toLabel(options.latestJob.stage_name);
    const statusLabel = toLabel(options.latestJob.status);

    if (options.latestJob.status === "failed" || options.latestJob.status === "blocked") {
      return {
        detail:
          options.latestJob.error_message ||
          `${stageLabel} finished in a ${statusLabel.toLowerCase()} state and needs investigation.`,
        summary: `Investigate ${stageLabel}`,
        tone: getWorkflowStatusTone(options.latestJob.status),
      };
    }

    return {
      detail: `${stageLabel} is ${statusLabel.toLowerCase()} in the latest processing job.`,
      summary: `Pipeline running · ${stageLabel}`,
      tone: getWorkflowStatusTone(options.latestJob.status),
    };
  }

  return {
    detail: "The packet workspace has not stored a processing job for this document yet.",
    summary: "Await pipeline start",
    tone: "neutral",
  };
}

function buildDocumentProgressStages(options: {
  accountComparison?: AccountComparisonRow;
  refreshDelta?: DocumentRefreshDelta;
  latestExtraction?: ExtractionResultRecord;
  latestJob?: ProcessingJobRecord;
  latestOcr?: OcrResultRecord;
  latestRecommendation?: RecommendationResultRecord;
  reviewDecision?: ReviewDecisionRecord;
  reviewTask?: ReviewTaskRecord;
}): readonly DocumentProgressStage[] {
  const latestJobStage = options.latestJob?.stage_name;
  const hasFinalAccount = Boolean(options.accountComparison?.finalAccountId);
  const hasSuggestedAccount = Boolean(options.accountComparison?.suggestedAccountId);

  return [
    {
      detail: options.latestOcr
        ? `Stored ${formatDateTime(options.latestOcr.created_at_utc)}`
        : latestJobStage === "ocr" && options.latestJob
          ? `Updated ${formatDateTime(options.latestJob.updated_at_utc)}`
          : undefined,
      hasRefreshChange: options.refreshDelta?.hasOcrChange,
      label: "OCR",
      refreshDetail: formatRefreshDeltaDetail(options.refreshDelta?.ocrDetail),
      status: options.latestOcr
        ? "Ready"
        : latestJobStage === "ocr"
          ? toLabel(options.latestJob?.status)
          : "Waiting",
      tone: options.latestOcr
        ? "success"
        : latestJobStage === "ocr"
          ? getWorkflowStatusTone(options.latestJob?.status)
          : "neutral",
    },
    {
      detail: options.latestExtraction
        ? `Stored ${formatDateTime(options.latestExtraction.created_at_utc)}`
        : latestJobStage === "extraction" && options.latestJob
          ? `Updated ${formatDateTime(options.latestJob.updated_at_utc)}`
          : undefined,
      hasRefreshChange: options.refreshDelta?.hasExtractionChange,
      label: "Extraction",
      refreshDetail: formatRefreshDeltaDetail(
        options.refreshDelta?.extractionDetail,
      ),
      status: options.latestExtraction
        ? "Ready"
        : latestJobStage === "extraction"
          ? toLabel(options.latestJob?.status)
          : options.latestOcr
            ? "Queued"
            : "Waiting",
      tone: options.latestExtraction
        ? "success"
        : latestJobStage === "extraction"
          ? getWorkflowStatusTone(options.latestJob?.status)
          : options.latestOcr
            ? "accent"
            : "neutral",
    },
    {
      detail: options.accountComparison?.reviewDecision
        ? `Reviewed ${formatDateTime(options.accountComparison.reviewDecision.decided_at_utc)}`
        : options.accountComparison?.reviewTask
          ? `Updated ${formatDateTime(options.accountComparison.reviewTask.updated_at_utc)}`
          : options.accountComparison?.matchRun
            ? `Matched ${formatDateTime(options.accountComparison.matchRun.created_at_utc)}`
            : undefined,
      hasRefreshChange: options.refreshDelta?.hasAccountChange,
      label: "Account",
      refreshDetail: formatRefreshDeltaDetail(options.refreshDelta?.accountDetail),
      status: hasFinalAccount
        ? options.accountComparison?.hasOverride
          ? "Override"
          : "Linked"
        : hasSuggestedAccount
          ? "Confirm"
          : options.latestExtraction
            ? "Pending"
            : "Waiting",
      tone: hasFinalAccount
        ? options.accountComparison?.hasOverride
          ? "accent"
          : "success"
        : hasSuggestedAccount || options.latestExtraction
          ? "warning"
          : "neutral",
    },
    {
      detail: options.reviewDecision
        ? `Reviewed ${formatDateTime(options.reviewDecision.decided_at_utc)}`
        : options.reviewTask
          ? `Updated ${formatDateTime(options.reviewTask.updated_at_utc)}`
          : undefined,
      hasRefreshChange: options.refreshDelta?.hasReviewChange,
      label: "Review",
      refreshDetail: formatRefreshDeltaDetail(options.refreshDelta?.reviewDetail),
      status: options.reviewDecision
        ? toLabel(options.reviewDecision.decision_status)
        : options.reviewTask
          ? toLabel(options.reviewTask.status)
          : hasFinalAccount || hasSuggestedAccount || options.latestExtraction
            ? "Queued"
            : "Waiting",
      tone: options.reviewDecision
        ? getReviewDecisionTone(options.reviewDecision.decision_status)
        : options.reviewTask
          ? options.reviewTask.status === "awaiting_review"
            ? "warning"
            : "accent"
          : hasFinalAccount || hasSuggestedAccount || options.latestExtraction
            ? "accent"
            : "neutral",
    },
    {
      detail: options.latestRecommendation?.reviewed_at_utc
        ? `Reviewed ${formatDateTime(options.latestRecommendation.reviewed_at_utc)}`
        : options.latestRecommendation
          ? `Updated ${formatDateTime(options.latestRecommendation.updated_at_utc)}`
          : undefined,
      hasRefreshChange: options.refreshDelta?.hasRecommendationChange,
      label: "Recommendation",
      refreshDetail: formatRefreshDeltaDetail(
        options.refreshDelta?.recommendationDetail,
      ),
      status: options.latestRecommendation
        ? options.latestRecommendation.reviewed_at_utc
          ? toLabel(options.latestRecommendation.disposition)
          : "Pending"
        : options.reviewDecision
          ? "Queued"
          : "Waiting",
      tone: options.latestRecommendation
        ? options.latestRecommendation.reviewed_at_utc
          ? getReviewDecisionTone(options.latestRecommendation.disposition)
          : "warning"
        : options.reviewDecision
          ? "accent"
          : "neutral",
    },
  ];
}

function buildRefreshDeltaDetail(
  previous: string,
  current: string,
): RefreshDeltaDetail | undefined {
  if (previous === current) {
    return undefined;
  }

  return { current, previous };
}

function formatRefreshDeltaDetail(
  detail: RefreshDeltaDetail | undefined,
): string | undefined {
  if (!detail) {
    return undefined;
  }

  return `${detail.previous} -> ${detail.current}.`;
}

function getActivePromptProfileVersion(
  promptProfileId: string,
  promptProfileVersions: readonly PromptProfileVersionRecord[],
) {
  return (
    promptProfileVersions.find(
      (version) => version.prompt_profile_id === promptProfileId && version.is_active,
    ) ||
    promptProfileVersions
      .filter((version) => version.prompt_profile_id === promptProfileId)
      .sort((left, right) => right.version_number - left.version_number)[0] ||
    null
  );
}

function resolveSuggestedAccountId(
  reviewTask: ReviewTaskRecord,
  accountMatchRun: AccountMatchRunRecord | undefined,
  document: PacketDocumentRecord | undefined,
) {
  return (
    reviewTask.selected_account_id ||
    resolveDocumentSuggestedAccountId(accountMatchRun, document)
  );
}

function resolveDocumentSuggestedAccountId(
  accountMatchRun: AccountMatchRunRecord | undefined,
  document: PacketDocumentRecord | undefined,
) {
  return (
    accountMatchRun?.selected_account_id ||
    accountMatchRun?.candidates[0]?.account_id ||
    document?.account_candidates[0] ||
    ""
  );
}

function getClassificationExecution(
  classificationResult: ClassificationResultRecord | undefined,
) {
  const rawExecution = classificationResult?.result_payload.classificationExecution;
  if (!rawExecution || typeof rawExecution !== "object") {
    return null;
  }

  return rawExecution as Record<string, unknown>;
}

function getExtractedFields(
  extractionResult: ExtractionResultRecord | undefined,
): ExtractedField[] {
  const rawFields = extractionResult?.result_payload.extractedFields;
  if (!Array.isArray(rawFields)) {
    return [];
  }

  return rawFields.flatMap((rawField) => {
    if (!rawField || typeof rawField !== "object") {
      return [];
    }

    const candidate = rawField as Record<string, unknown>;
    if (typeof candidate.name !== "string" || typeof candidate.value !== "string") {
      return [];
    }

    return [
      {
        confidence:
          typeof candidate.confidence === "number" ? candidate.confidence : undefined,
        name: candidate.name,
        value: candidate.value,
      },
    ];
  });
}

function getExtractionReviewEditMetadata(
  extractionResult: ExtractionResultRecord | undefined,
): ExtractionReviewEditMetadata | null {
  const rawReviewEdits = extractionResult?.result_payload.reviewEdits;
  if (!rawReviewEdits || typeof rawReviewEdits !== "object") {
    return null;
  }

  const candidate = rawReviewEdits as Record<string, unknown>;
  const changedFieldNames = Array.isArray(candidate.changedFieldNames)
    ? candidate.changedFieldNames.filter(
        (fieldName): fieldName is string => typeof fieldName === "string",
      )
    : [];

  return {
    changeCount:
      typeof candidate.changeCount === "number"
        ? candidate.changeCount
        : changedFieldNames.length,
    changedFieldNames,
    editedAtUtc:
      typeof candidate.editedAtUtc === "string" ? candidate.editedAtUtc : null,
    reviewTaskId:
      typeof candidate.reviewTaskId === "string" ? candidate.reviewTaskId : null,
    sourceExtractionResultId:
      typeof candidate.sourceExtractionResultId === "string"
        ? candidate.sourceExtractionResultId
        : null,
  };
}

function getExtractionEditAuditEventDetails(
  auditEvent: AuditEventRecord,
): {
  changedFields: ReviewFieldChange[];
  newExtractionResultId: string | null;
  sourceExtractionResultId: string | null;
} | null {
  const rawPayload = auditEvent.event_payload;
  if (!rawPayload || typeof rawPayload !== "object") {
    return null;
  }

  const rawChangedFields = (rawPayload as Record<string, unknown>).changedFields;
  if (!Array.isArray(rawChangedFields)) {
    return null;
  }

  const changedFields = rawChangedFields.flatMap((rawChangedField) => {
    if (!rawChangedField || typeof rawChangedField !== "object") {
      return [];
    }

    const candidate = rawChangedField as Record<string, unknown>;
    if (
      typeof candidate.field_name !== "string" ||
      typeof candidate.original_value !== "string" ||
      typeof candidate.current_value !== "string"
    ) {
      return [];
    }

    return [
      {
        confidence:
          typeof candidate.confidence === "number"
            ? candidate.confidence
            : undefined,
        currentValue: candidate.current_value,
        fieldName: candidate.field_name,
        originalValue: candidate.original_value,
      },
    ];
  });

  if (changedFields.length === 0) {
    return null;
  }

  return {
    changedFields,
    newExtractionResultId:
      typeof (rawPayload as Record<string, unknown>).newExtractionResultId === "string"
        ? ((rawPayload as Record<string, unknown>).newExtractionResultId as string)
        : null,
    sourceExtractionResultId:
      typeof (rawPayload as Record<string, unknown>).sourceExtractionResultId ===
      "string"
        ? ((rawPayload as Record<string, unknown>).sourceExtractionResultId as string)
        : null,
  };
}

function isExtractionEditAuditEvent(auditEvent: AuditEventRecord) {
  return getExtractionEditAuditEventDetails(auditEvent) !== null;
}

function getEditedFieldValue(
  field: ExtractedField,
  editedFieldValues: Record<string, string>,
) {
  return editedFieldValues[field.name] ?? field.value;
}

function getReviewFieldChanges(
  fields: readonly ExtractedField[],
  editedFieldValues: Record<string, string>,
): ReviewFieldChange[] {
  return fields.flatMap((field) => {
    const currentValue = getEditedFieldValue(field, editedFieldValues);
    if (currentValue === field.value) {
      return [];
    }

    return [
      {
        confidence: field.confidence,
        currentValue,
        fieldName: field.name,
        originalValue: field.value,
      },
    ];
  });
}

function resolveViewerFieldKey(
  extractionResult: ExtractionResultRecord | undefined,
  preferredFieldName?: string | null,
) {
  const extractedFields = getExtractedFields(extractionResult);
  if (extractedFields.length === 0) {
    return null;
  }

  if (preferredFieldName) {
    const preferredField = extractedFields.find(
      (field) => normalizeLookupKey(field.name) === normalizeLookupKey(preferredFieldName),
    );
    if (preferredField) {
      return buildExtractedFieldKey(preferredField);
    }
  }

  return buildExtractedFieldKey(extractedFields[0]);
}

function getLatestPacketEventsByDocument(
  packetEvents: readonly PacketEventRecord[],
) {
  const latestByDocument = new Map<string, PacketEventRecord>();

  for (const packetEvent of packetEvents) {
    if (!packetEvent.document_id) {
      continue;
    }

    const current = latestByDocument.get(packetEvent.document_id);
    if (!current || toTimestamp(packetEvent.created_at_utc) >= toTimestamp(current.created_at_utc)) {
      latestByDocument.set(packetEvent.document_id, packetEvent);
    }
  }

  return latestByDocument;
}

function buildDocumentRefreshComparisonKey(
  document: PacketDocumentRecord,
  latestJobsByDocument: Map<string, ProcessingJobRecord>,
  latestExtractionsByDocument: Map<string, ExtractionResultRecord>,
  latestOcrByDocument: Map<string, OcrResultRecord>,
  latestRecommendationsByDocument: Map<string, RecommendationResultRecord>,
  contractStatusByDocument: Map<string, DocumentContractStatus>,
  accountComparisonByDocument: Map<string, AccountComparisonRow>,
  reviewTasksByDocument: Map<string, ReviewTaskRecord>,
  latestReviewDecisionsByTask: Map<string, ReviewDecisionRecord>,
): DocumentRefreshComparisonKey {
  const latestJob = latestJobsByDocument.get(document.document_id);
  const latestExtraction = latestExtractionsByDocument.get(document.document_id);
  const latestOcr = latestOcrByDocument.get(document.document_id);
  const latestRecommendation = latestRecommendationsByDocument.get(document.document_id);
  const contractStatus = contractStatusByDocument.get(document.document_id);
  const accountComparison = accountComparisonByDocument.get(document.document_id);
  const reviewTask = reviewTasksByDocument.get(document.document_id);
  const latestReviewDecision = reviewTask
    ? latestReviewDecisionsByTask.get(reviewTask.review_task_id)
    : undefined;
  const extractionReviewEditMetadata = getExtractionReviewEditMetadata(latestExtraction);
  const attentionState = buildDocumentAttentionState({
    accountComparison,
    contractStatus,
    document,
    latestExtraction,
    latestJob,
    latestOcr,
    latestRecommendation,
    reviewDecision: latestReviewDecision,
    reviewTask,
  });

  return {
    accountKey: accountComparison
      ? [
          accountComparison.finalAccountId || "",
          accountComparison.suggestedAccountId || "",
          accountComparison.taskAccountId || "",
          accountComparison.hasOverride ? "override" : "direct",
          accountComparison.matchRun?.match_run_id || "",
          accountComparison.matchRun?.selected_account_id || "",
          accountComparison.reviewDecision?.decision_id || "",
        ].join("|")
      : "",
    accountSummary: buildAccountStatusSummary(accountComparison),
    attentionKey: [attentionState.summary, attentionState.detail, attentionState.tone].join("|"),
    attentionSummary: attentionState.summary,
    contractKey: contractStatus
      ? [
          contractStatus.classificationLabel,
          contractStatus.documentTypeLabel,
          contractStatus.promptProfileLabel,
          contractStatus.requiredFieldCount,
          contractStatus.missingRequiredFields.join(","),
        ].join("|")
      : "",
    contractSummary: buildContractRefreshSummary(contractStatus),
    extractionKey: latestExtraction
      ? [
          latestExtraction.extraction_result_id,
          latestExtraction.created_at_utc,
          extractionReviewEditMetadata?.editedAtUtc || "",
        ].join("|")
      : "",
    extractionSummary: buildExtractionStatusSummary(latestExtraction),
    ocrKey: latestOcr
      ? [
          latestOcr.ocr_result_id,
          latestOcr.created_at_utc,
          latestOcr.provider,
          latestOcr.page_count,
          latestOcr.ocr_confidence,
        ].join("|")
      : "",
    ocrSummary: buildOcrStatusSummary(latestOcr),
    processingKey: latestJob
      ? [
          latestJob.job_id,
          latestJob.stage_name,
          latestJob.status,
          latestJob.updated_at_utc,
          latestJob.completed_at_utc || "",
        ].join("|")
      : "",
    processingSummary: buildProcessingStatusSummary(latestJob),
    recommendationKey: latestRecommendation
      ? [
          latestRecommendation.recommendation_result_id,
          latestRecommendation.disposition,
          latestRecommendation.updated_at_utc,
          latestRecommendation.reviewed_at_utc || "",
          latestRecommendation.reviewed_by_email || "",
        ].join("|")
      : "",
    recommendationSummary: buildRecommendationStatusSummary(latestRecommendation),
    reviewKey: [
      reviewTask
        ? [
            reviewTask.review_task_id,
            reviewTask.status,
            reviewTask.assigned_user_email || "",
            reviewTask.selected_account_id || "",
            reviewTask.updated_at_utc,
          ].join("|")
        : "",
      latestReviewDecision
        ? [
            latestReviewDecision.decision_id,
            latestReviewDecision.decision_status,
            latestReviewDecision.selected_account_id || "",
            latestReviewDecision.decided_at_utc,
          ].join("|")
        : "",
    ].join("||"),
    reviewSummary: buildReviewRefreshSummary({
      reviewDecision: latestReviewDecision,
      reviewTask,
    }),
  };
}

function getPreferredFieldNameForReviewTask(reviewTask: ReviewTaskRecord) {
  const normalizedReasonCodes = reviewTask.reason_codes.map((reasonCode) =>
    normalizeLookupKey(reasonCode),
  );

  if (normalizedReasonCodes.some((reasonCode) => reasonCode.includes("account"))) {
    return "account_number";
  }

  if (
    normalizedReasonCodes.some(
      (reasonCode) => reasonCode.includes("statement") || reasonCode.includes("date"),
    )
  ) {
    return "statement_date";
  }

  return null;
}

function buildReviewDecisionReasonCodeOptions(
  reviewTask: ReviewTaskRecord,
  decisionStatus: PacketWorkspaceReviewDecisionStatus,
) {
  const options = new Set<string>();

  for (const reasonCode of reviewTask.reason_codes) {
    const normalizedReasonCode = reasonCode.trim();
    if (!normalizedReasonCode) {
      continue;
    }

    options.add(normalizedReasonCode);
    options.add(
      decisionStatus === "approved"
        ? `${normalizedReasonCode}_confirmed`
        : `${normalizedReasonCode}_follow_up`,
    );
  }

  if (options.size === 0) {
    options.add(
      decisionStatus === "approved" ? "verified" : "follow_up_required",
    );
  }

  return Array.from(options);
}

function renderListFallback(message: string) {
  return <div className="status-panel workspace-status-panel">{message}</div>;
}

function renderDocumentSummary(
  document: PacketDocumentRecord,
  documentState?: DocumentWorkspaceState,
  options?: {
    isExpanded?: boolean;
    onToggleExpanded?: () => void;
  },
) {
  const accountComparison = documentState?.accountComparison;
  const contractStatus = documentState?.contractStatus;
  const contractCoverageState = getContractCoverageState(contractStatus);
  const refreshDelta = documentState?.refreshDelta;
  const hasRefreshDelta = Boolean(
    refreshDelta?.hasAccountChange ||
      refreshDelta?.hasAttentionChange ||
      refreshDelta?.hasContractChange ||
      refreshDelta?.hasOcrChange ||
      refreshDelta?.hasProcessingChange ||
      refreshDelta?.hasExtractionChange ||
      refreshDelta?.hasRecommendationChange ||
      refreshDelta?.hasReviewChange,
  );
  const latestJobStatus = buildProcessingStatusSummary(documentState?.latestJob);
  const latestExtractionStatus = buildExtractionStatusSummary(
    documentState?.latestExtraction,
  );
  const latestOcrStatus = buildOcrStatusSummary(documentState?.latestOcr);
  const latestRecommendationStatus = buildRecommendationStatusSummary(
    documentState?.latestRecommendation,
  );
  const contractSummaryStatus = buildContractSummaryStatus(contractStatus);
  const accountStatus = buildAccountStatusSummary(accountComparison);
  const attentionState = buildDocumentAttentionState({
    accountComparison,
    contractStatus,
    document,
    latestExtraction: documentState?.latestExtraction,
    latestJob: documentState?.latestJob,
    latestOcr: documentState?.latestOcr,
    latestRecommendation: documentState?.latestRecommendation,
    reviewDecision: documentState?.reviewDecision,
    reviewTask: documentState?.reviewTask,
  });
  const documentProgressStages = buildDocumentProgressStages({
    accountComparison,
    refreshDelta,
    latestExtraction: documentState?.latestExtraction,
    latestJob: documentState?.latestJob,
    latestOcr: documentState?.latestOcr,
    latestRecommendation: documentState?.latestRecommendation,
    reviewDecision: documentState?.reviewDecision,
    reviewTask: documentState?.reviewTask,
  });
  const reviewStatus = buildReviewStatusSummary({
    reviewDecision: documentState?.reviewDecision,
    reviewTask: documentState?.reviewTask,
  });
  const extractionReviewEditMetadata = documentState?.extractionReviewEditMetadata;
  const documentProgressToneByLabel = new Map(
    documentProgressStages.map((stage) => [stage.label, stage.tone]),
  );
  const documentSummarySubcards: readonly DocumentSummarySubcard[] = [
    {
      detail: attentionState.detail,
      hasRefreshChange: refreshDelta?.hasAttentionChange,
      id: "attention",
      refreshCopy: "Attention changed on the last workspace refresh.",
      refreshDetail: formatRefreshDeltaDetail(refreshDelta?.attentionDetail),
      summary: attentionState.summary,
      title: "Attention",
      tone: attentionState.tone,
    },
    {
      detail: documentState?.reviewDecision
        ? `Reviewed by ${documentState.reviewDecision.decided_by_email || "an operator"} at ${formatDateTime(documentState.reviewDecision.decided_at_utc)}${documentState.reviewDecision.selected_account_id ? ` · Selected ${documentState.reviewDecision.selected_account_id}.` : "."}`
        : documentState?.reviewTask
          ? `${documentState.reviewTask.assigned_user_email || "Unassigned"}${documentState.reviewTask.selected_account_id ? ` · Selected ${documentState.reviewTask.selected_account_id}` : ""}. Updated ${formatDateTime(documentState.reviewTask.updated_at_utc)}.`
          : "No review workflow has started for this document yet.",
      hasRefreshChange: refreshDelta?.hasReviewChange,
      id: "review",
      refreshCopy: "Review changed on the last workspace refresh.",
      refreshDetail: formatRefreshDeltaDetail(refreshDelta?.reviewDetail),
      summary: reviewStatus,
      title: "Review",
      tone: documentProgressToneByLabel.get("Review") ?? "neutral",
    },
    {
      detail: contractCoverageState.detail,
      hasRefreshChange: refreshDelta?.hasContractChange,
      id: "contract",
      refreshCopy: "Contract changed on the last workspace refresh.",
      refreshDetail: formatRefreshDeltaDetail(refreshDelta?.contractDetail),
      summary: contractSummaryStatus,
      title: "Contract",
      tone: contractCoverageState.tone,
    },
    {
      detail: accountComparison?.hasOverride
        ? `Suggested ${accountComparison.suggestedAccountId || "no account"} from ${formatCount(accountComparison.matchRun?.candidates.length ?? document.account_candidates.length, "candidate")}. Final ${accountComparison.finalAccountId || "no account"} confirmed by ${accountComparison.reviewDecision?.decided_by_email || "an operator"}${accountComparison.reviewDecision ? ` at ${formatDateTime(accountComparison.reviewDecision.decided_at_utc)}.` : "."}`
        : accountComparison?.finalAccountId
          ? `${accountComparison.matchRun ? `Auto-linked from ${formatCount(accountComparison.matchRun.candidates.length, "candidate")}.` : "Linked from stored account candidates."}${accountComparison.reviewTask?.assigned_user_email ? ` Assigned review owner ${accountComparison.reviewTask.assigned_user_email}.` : ""}`
          : accountComparison?.suggestedAccountId
            ? `Suggested ${accountComparison.suggestedAccountId} is waiting for review confirmation.`
            : "No account match has been recorded for this document yet.",
      hasRefreshChange: refreshDelta?.hasAccountChange,
      id: "account",
      refreshCopy: "Account changed on the last workspace refresh.",
      refreshDetail: formatRefreshDeltaDetail(refreshDelta?.accountDetail),
      summary: accountStatus,
      title: "Account",
      tone: documentProgressToneByLabel.get("Account") ?? "neutral",
    },
    {
      detail: documentState?.latestRecommendation
        ? `${documentState.latestRecommendation.summary} ${documentState.latestRecommendation.reviewed_at_utc ? `Reviewed by ${documentState.latestRecommendation.reviewed_by_email || "an operator"} at ${formatDateTime(documentState.latestRecommendation.reviewed_at_utc)}.` : `Confidence ${formatConfidence(documentState.latestRecommendation.confidence)} · Awaiting operator disposition.`}`
        : "No recommendation guidance is stored for this document yet.",
      hasRefreshChange: refreshDelta?.hasRecommendationChange,
      id: "recommendation",
      refreshCopy: "Recommendation changed on the last workspace refresh.",
      refreshDetail: formatRefreshDeltaDetail(refreshDelta?.recommendationDetail),
      summary: latestRecommendationStatus,
      title: "Recommendation",
      tone: documentProgressToneByLabel.get("Recommendation") ?? "neutral",
    },
    {
      collapsedSummary:
        !documentState?.latestExtraction && documentState?.latestOcr
          ? "Extraction: Queued"
          : !documentState?.latestExtraction
            ? "Extraction: Waiting"
            : undefined,
      detail: extractionReviewEditMetadata
        ? `Manual review edits saved ${formatDateTime(extractionReviewEditMetadata.editedAtUtc)}.`
        : documentState?.latestExtraction
          ? `Stored ${formatDateTime(documentState.latestExtraction.created_at_utc)}.`
          : "No extraction payload is available yet.",
      hasRefreshChange: refreshDelta?.hasExtractionChange,
      id: "extraction",
      refreshCopy: "Extraction changed on the last workspace refresh.",
      refreshDetail: formatRefreshDeltaDetail(refreshDelta?.extractionDetail),
      summary: latestExtractionStatus,
      title: "Extraction",
      tone: documentProgressToneByLabel.get("Extraction") ?? "neutral",
    },
    {
      collapsedSummary:
        documentState?.latestJob &&
        documentState.latestJob.status !== "completed" &&
        documentState.latestJob.status !== "succeeded"
          ? `Processing: ${toLabel(documentState.latestJob.stage_name)} ${toLabel(documentState.latestJob.status).toLowerCase()}`
          : undefined,
      detail: documentState?.latestJob
        ? `Updated ${formatDateTime(documentState.latestJob.updated_at_utc)}`
        : "The packet workspace has not stored a document job yet.",
      hasRefreshChange: refreshDelta?.hasProcessingChange,
      id: "processing",
      refreshCopy: "Processing changed on the last workspace refresh.",
      refreshDetail: formatRefreshDeltaDetail(refreshDelta?.processingDetail),
      summary: latestJobStatus,
      title: "Processing",
      tone: documentState?.latestJob
        ? getWorkflowStatusTone(documentState.latestJob.status)
        : "neutral",
    },
    {
      collapsedSummary: documentState?.latestOcr ? undefined : "OCR: Waiting",
      detail: documentState?.latestOcr
        ? `${toLabel(documentState.latestOcr.provider)} stored ${formatDateTime(documentState.latestOcr.created_at_utc)}.`
        : "No OCR output is stored for this document yet.",
      hasRefreshChange: refreshDelta?.hasOcrChange,
      id: "ocr",
      refreshCopy: "OCR changed on the last workspace refresh.",
      refreshDetail: formatRefreshDeltaDetail(refreshDelta?.ocrDetail),
      summary: latestOcrStatus,
      title: "OCR",
      tone: documentProgressToneByLabel.get("OCR") ?? "neutral",
    },
    {
      detail: documentState?.latestPacketEvent
        ? `${documentState.latestPacketEvent.event_type} at ${formatDateTime(documentState.latestPacketEvent.created_at_utc)}.`
        : "No document packet event has been recorded yet.",
      id: "signals",
      summary: `${documentState?.auditEventCount ?? 0} audit events · ${documentState?.operatorNoteCount ?? 0} notes`,
      title: "Signals",
      tone: "neutral",
    },
  ];
  const visibleDocumentSummarySubcards = getVisibleDocumentSummarySubcards({
    isExpanded: Boolean(options?.isExpanded),
    subcards: documentSummarySubcards,
  });
  const visibleDocumentSummarySubcardIds = new Set(
    visibleDocumentSummarySubcards.map((subcard) => subcard.id),
  );
  const hiddenDocumentSummarySubcards = documentSummarySubcards.filter(
    (subcard) => !visibleDocumentSummarySubcardIds.has(subcard.id),
  );
  const hiddenDocumentSummarySubcardCount =
    documentSummarySubcards.length - visibleDocumentSummarySubcards.length;
  const documentSummarySubcardGridId = `document-status-grid-${document.document_id}`;
  const hiddenDocumentSummaryToggleLabel = formatHiddenDocumentSummaryToggleLabel({
    hiddenSubcards: hiddenDocumentSummarySubcards,
  });

  return (
    <SurfaceCard
      className={
        hasRefreshDelta ? "workspace-document-refresh-card" : undefined
      }
      key={document.document_id}
    >
      <div className="queue-card-header">
        <div className="queue-card-heading">
          <span className="queue-card-label">{toLabel(document.status)}</span>
          <h3>{document.file_name}</h3>
        </div>
        <span className="workspace-inline-chip">{toLabel(document.content_type)}</span>
      </div>

      <div className="workspace-document-signal-row">
        <StatusBadge tone={getWorkflowStatusTone(document.status)}>
          {toLabel(document.status)}
        </StatusBadge>
        <StatusBadge
          tone={documentState?.latestJob ? getWorkflowStatusTone(documentState.latestJob.status) : "neutral"}
        >
          {latestJobStatus}
        </StatusBadge>
        <StatusBadge
          tone={documentState?.reviewDecision ? "success" : documentState?.reviewTask ? "warning" : "neutral"}
        >
          {reviewStatus}
        </StatusBadge>
        <StatusBadge
          tone={
            documentState?.latestRecommendation?.disposition === "accepted"
              ? "success"
              : documentState?.latestRecommendation?.disposition === "rejected"
                ? "danger"
                : documentState?.latestRecommendation
                  ? "accent"
                  : "neutral"
          }
        >
          {latestRecommendationStatus}
        </StatusBadge>
        <StatusBadge
          tone={
            accountComparison?.hasOverride
              ? "accent"
              : accountComparison?.finalAccountId
                ? "success"
                : accountComparison?.suggestedAccountId
                  ? "warning"
                  : "neutral"
          }
        >
          {accountStatus}
        </StatusBadge>
        {extractionReviewEditMetadata ? (
          <StatusBadge tone="accent">
            {formatCount(extractionReviewEditMetadata.changeCount, "manual edit")}
          </StatusBadge>
        ) : null}
        {hasRefreshDelta ? (
          <StatusBadge tone="accent">Updated on refresh</StatusBadge>
        ) : null}
      </div>

      <dl className="detail-list compact-detail-list">
        <div>
          <dt>Source</dt>
          <dd>{toLabel(document.source)}</dd>
        </div>
        <div>
          <dt>Issuer</dt>
          <dd>{document.issuer_name || toLabel(document.issuer_category)}</dd>
        </div>
        <div>
          <dt>Prompt profile</dt>
          <dd>{toLabel(document.requested_prompt_profile_id)}</dd>
        </div>
        <div>
          <dt>Received</dt>
          <dd>{formatDateTime(document.received_at_utc)}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>{formatDateTime(document.updated_at_utc)}</dd>
        </div>
      </dl>

      <div className="workspace-document-status-strip">
        <div className="workspace-document-status-summary">
          <p className="workspace-document-status-label">Current attention</p>
          <strong>{attentionState.summary}</strong>
          <small>{attentionState.detail}</small>
        </div>

        <ol
          aria-label={`Document path for ${document.file_name}`}
          className="workspace-document-path"
        >
          {documentProgressStages.map((stage) => (
            <li className="workspace-document-path-step" key={stage.label}>
              <span className="workspace-document-path-step-label">
                {stage.label}
              </span>
              <div className="workspace-document-path-step-state">
                <StatusBadge tone={stage.tone}>{stage.status}</StatusBadge>
                {stage.hasRefreshChange ? (
                  <StatusBadge tone="accent">Changed</StatusBadge>
                ) : null}
              </div>
              {stage.detail ? (
                <small className="workspace-document-path-step-copy">
                  {stage.detail}
                </small>
              ) : null}
              {stage.refreshDetail ? (
                <small className="workspace-refresh-delta-detail">
                  {stage.refreshDetail}
                </small>
              ) : null}
            </li>
          ))}
        </ol>
      </div>

      <div
        className="workspace-subcard-list workspace-document-live-grid"
        id={documentSummarySubcardGridId}
      >
        {visibleDocumentSummarySubcards.map((subcard) => (
          <div
            className={[
              "workspace-subcard",
              subcard.hasRefreshChange ? "workspace-subcard-refresh-delta" : null,
            ]
              .filter(Boolean)
              .join(" ")}
            key={subcard.id}
          >
            <strong>{subcard.title}</strong>
            {subcard.title === "Attention" ? (
              <StatusBadge tone={attentionState.tone}>{subcard.summary}</StatusBadge>
            ) : (
              <span>{subcard.summary}</span>
            )}
            <small>{subcard.detail}</small>
            {subcard.hasRefreshChange && subcard.refreshCopy ? (
              <small className="workspace-refresh-delta-copy">
                {subcard.refreshCopy}
              </small>
            ) : null}
            {subcard.hasRefreshChange && subcard.refreshDetail ? (
              <small className="workspace-refresh-delta-detail">
                {subcard.refreshDetail}
              </small>
            ) : null}
          </div>
        ))}
      </div>

      {documentSummarySubcards.length > visibleDocumentSummarySubcards.length ||
      options?.isExpanded ? (
        <div className="workspace-document-detail-toggle-row">
          <button
            aria-controls={documentSummarySubcardGridId}
            aria-expanded={Boolean(options?.isExpanded)}
            className="ghost-button"
            onClick={options?.onToggleExpanded}
            type="button"
          >
            {options?.isExpanded
              ? "Show fewer status cards"
              : hiddenDocumentSummaryToggleLabel}
          </button>
        </div>
      ) : null}

      {documentState?.latestOcr ? (
        <p className="workspace-caption">
          OCR ready with {documentState.latestOcr.page_count} pages at {formatConfidence(documentState.latestOcr.ocr_confidence)} confidence.
        </p>
      ) : null}

      {document.lineage?.archive_member_path ? (
        <p className="workspace-copy">
          Archive lineage: {document.lineage.archive_member_path} at depth {document.lineage.archive_depth}.
        </p>
      ) : null}

      {document.source_tags.length > 0 ? (
        <ul className="chip-list stack-chip-list">
          {document.source_tags.map((tag) => (
            <li className="match-pill" key={tag}>
              {tag}
            </li>
          ))}
        </ul>
      ) : null}
    </SurfaceCard>
  );
}

function renderProcessingJob(job: ProcessingJobRecord) {
  return (
    <SurfaceCard key={job.job_id}>
      <div className="queue-card-header">
        <div className="queue-card-heading">
          <span className="queue-card-label">{toLabel(job.status)}</span>
          <h3>{toLabel(job.stage_name)}</h3>
        </div>
        <span className="workspace-inline-chip">Attempt {job.attempt_number}</span>
      </div>

      <dl className="detail-list compact-detail-list">
        <div>
          <dt>Queued</dt>
          <dd>{formatDateTime(job.queued_at_utc)}</dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd>{formatDateTime(job.started_at_utc)}</dd>
        </div>
        <div>
          <dt>Completed</dt>
          <dd>{formatDateTime(job.completed_at_utc)}</dd>
        </div>
      </dl>

      {job.error_message ? <p className="workspace-copy">{job.error_message}</p> : null}
    </SurfaceCard>
  );
}

function toTimestamp(value: string | null | undefined) {
  if (!value) {
    return 0;
  }

  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function getMostRecentJobTimestamp(job: ProcessingJobRecord) {
  return Math.max(
    toTimestamp(job.completed_at_utc),
    toTimestamp(job.started_at_utc),
    toTimestamp(job.updated_at_utc),
    toTimestamp(job.queued_at_utc),
  );
}

function getLatestJobsByStage(jobs: readonly ProcessingJobRecord[]) {
  const latestByStage = new Map<string, ProcessingJobRecord>();

  for (const job of jobs) {
    const current = latestByStage.get(job.stage_name);
    if (!current || getMostRecentJobTimestamp(job) >= getMostRecentJobTimestamp(current)) {
      latestByStage.set(job.stage_name, job);
    }
  }

  return Array.from(latestByStage.values()).sort(
    (left, right) => getMostRecentJobTimestamp(right) - getMostRecentJobTimestamp(left),
  );
}

function getAttentionJobs(jobs: readonly ProcessingJobRecord[]) {
  const attentionJobs = jobs.filter(
    (job) => job.attempt_number > 1 || job.status === "failed" || Boolean(job.error_message),
  );

  return attentionJobs.sort(
    (left, right) => getMostRecentJobTimestamp(right) - getMostRecentJobTimestamp(left),
  );
}

function getEventMarkerState(packetEvent: PacketEventRecord) {
  const normalizedEventType = packetEvent.event_type.toLowerCase();
  if (
    normalizedEventType.includes("fail") ||
    normalizedEventType.includes("error") ||
    normalizedEventType.includes("quarantine") ||
    normalizedEventType.includes("block")
  ) {
    return "active";
  }

  return "complete";
}

function summarizeEventPayload(payload: Record<string, unknown> | null | undefined) {
  if (!payload) {
    return "No event payload stored.";
  }

  const fragments = Object.entries(payload).slice(0, 3).map(([key, value]) => {
    if (Array.isArray(value)) {
      return `${key}: ${value.length} items`;
    }

    if (value && typeof value === "object") {
      return `${key}: object`;
    }

    return `${key}: ${String(value)}`;
  });

  return fragments.length > 0 ? fragments.join(" • ") : "Event payload recorded.";
}

function renderOcrResult(ocrResult: OcrResultRecord) {
  return (
    <SurfaceCard key={ocrResult.ocr_result_id}>
      <div className="queue-card-header">
        <div className="queue-card-heading">
          <span className="queue-card-label">OCR</span>
          <h3>{ocrResult.provider}</h3>
        </div>
        <span className="workspace-inline-chip">{formatConfidence(ocrResult.ocr_confidence)}</span>
      </div>
      <dl className="detail-list compact-detail-list">
        <div>
          <dt>Pages</dt>
          <dd>{ocrResult.page_count}</dd>
        </div>
        <div>
          <dt>Model</dt>
          <dd>{ocrResult.model_name || "Not captured"}</dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{formatDateTime(ocrResult.created_at_utc)}</dd>
        </div>
      </dl>
      <p className="workspace-copy workspace-copy-prewrap">
        {ocrResult.text_excerpt || "No OCR excerpt is stored yet."}
      </p>
    </SurfaceCard>
  );
}

function renderExtractionSummary(
  extractionResult: ExtractionResultRecord,
  classificationResult: ClassificationResultRecord | undefined,
) {
  const extractedFields = getExtractedFields(extractionResult);
  const classificationExecution = getClassificationExecution(classificationResult);

  return (
    <SurfaceCard key={extractionResult.extraction_result_id}>
      <div className="queue-card-header">
        <div className="queue-card-heading">
          <span className="queue-card-label">Extraction</span>
          <h3>{extractionResult.document_type || "No document type"}</h3>
        </div>
        <span className="workspace-inline-chip">{toLabel(extractionResult.provider)}</span>
      </div>

      <p className="workspace-copy">{extractionResult.summary || "No extraction summary stored yet."}</p>

      <dl className="detail-list compact-detail-list">
        <div>
          <dt>Prompt profile</dt>
          <dd>{toLabel(extractionResult.prompt_profile_id)}</dd>
        </div>
        <div>
          <dt>Classification</dt>
          <dd>
            {toLabel(
              typeof classificationExecution?.classificationKey === "string"
                ? classificationExecution.classificationKey
                : classificationResult?.classification_id,
            )}
          </dd>
        </div>
        <div>
          <dt>Doctype key</dt>
          <dd>
            {toLabel(
              typeof classificationExecution?.documentTypeKey === "string"
                ? classificationExecution.documentTypeKey
                : classificationResult?.document_type_id,
            )}
          </dd>
        </div>
        <div>
          <dt>Stored</dt>
          <dd>{formatDateTime(extractionResult.created_at_utc)}</dd>
        </div>
      </dl>

      {extractedFields.length > 0 ? (
        <div className="workspace-field-list">
          {extractedFields.map((field) => (
            <div className="workspace-field-row" key={`${field.name}:${field.value}`}>
              <strong>{field.name}</strong>
              <span>{field.value}</span>
              <small>{formatConfidence(field.confidence)}</small>
            </div>
          ))}
        </div>
      ) : (
        <p className="workspace-copy">No extracted fields are stored in this result payload yet.</p>
      )}
    </SurfaceCard>
  );
}

function renderMatchRun(matchRun: AccountMatchRunRecord) {
  return (
    <SurfaceCard key={matchRun.match_run_id}>
      <div className="queue-card-header">
        <div className="queue-card-heading">
          <span className="queue-card-label">{toLabel(matchRun.status)}</span>
          <h3>{matchRun.selected_account_id || "No account selected"}</h3>
        </div>
        <span className="workspace-inline-chip">{matchRun.candidates.length} candidates</span>
      </div>

      <p className="workspace-copy">{matchRun.rationale || "No match rationale stored."}</p>

      {matchRun.candidates.length > 0 ? (
        <div className="workspace-subcard-list">
          {matchRun.candidates.map((candidate) => (
            <div className="workspace-subcard" key={candidate.account_id}>
              <strong>{candidate.account_id}</strong>
              <span>{candidate.account_number || "No account number"}</span>
              <span>{candidate.debtor_name || "No debtor name"}</span>
              <small>
                Score {Math.round(candidate.score)} · {candidate.matched_on.join(", ")}
              </small>
            </div>
          ))}
        </div>
      ) : null}
    </SurfaceCard>
  );
}

function renderReviewTask(
  reviewTask: ReviewTaskRecord,
  options: {
    assignmentDraft: string;
    assignmentErrorMessage: string | null;
    assignmentSuccessMessage: string | null;
    auditEvents: readonly AuditEventRecord[];
    contractStatus?: DocumentContractStatus;
    decisionReasonCode: string;
    decisionErrorMessage: string | null;
    decisionNote: string;
    document?: PacketDocumentRecord;
    editableFields: ExtractedField[];
    editedFieldValues: Record<string, string>;
    extractionEditErrorMessage: string | null;
    extractionReviewEditMetadata: ExtractionReviewEditMetadata | null;
    extractionEditSuccessMessage: string | null;
    fieldChanges: ReviewFieldChange[];
    hasRecordedDecision: boolean;
    isAssignmentSubmitting: boolean;
    isExtractionEditSubmitting: boolean;
    isDecisionSubmitting: boolean;
    isNoteSubmitting: boolean;
    noteDraft: string;
    noteErrorMessage: string | null;
    noteSuccessMessage: string | null;
    onEditedFieldValueChange: (fieldName: string, value: string) => void;
    onInspectDocument?: (
      documentId: string,
      preferredFieldName?: string | null,
      returnTarget?: ReviewViewerReturnTarget,
    ) => void;
    onDecisionNoteChange: (value: string) => void;
    onDecisionReasonCodeChange: (value: string) => void;
    onDecisionStatusChange: (
      value: PacketWorkspaceReviewDecisionStatus,
    ) => void;
    onAssignmentDraftChange: (value: string) => void;
    onNoteDraftChange: (value: string) => void;
    onResetEditedFieldValue: (fieldName: string) => void;
    onSelectedAccountIdChange: (value: string) => void;
    onSubmitExtractionEdits?: (
      extractionEdit: PacketWorkspaceExtractionEditInput,
    ) => Promise<void> | void;
    onSubmitReviewAssignment?: (
      assignment: PacketWorkspaceReviewAssignmentInput,
    ) => Promise<void> | void;
    onSubmitReviewNote?: (
      note: PacketWorkspaceReviewNoteInput,
    ) => Promise<void> | void;
    onSubmitReviewDecision?: (
      decision: PacketWorkspaceReviewDecisionInput,
    ) => Promise<void> | void;
    operatorNotes: readonly OperatorNoteRecord[];
    reviewerEmail: string | null;
    reviewDecision?: ReviewDecisionRecord;
    selectedDecisionStatus: PacketWorkspaceReviewDecisionStatus;
    selectedAccountId: string;
    suggestedAccountId: string | null;
  },
) {
  const reviewerEmailValue = options.reviewerEmail?.trim() || "";
  const reviewerEmail = reviewerEmailValue.toLowerCase() || null;
  const assignedReviewerEmail = reviewTask.assigned_user_email?.trim().toLowerCase() || null;
  const assignmentDraft = options.assignmentDraft.trim();
  const currentAssignmentValue = reviewTask.assigned_user_email?.trim() || "";
  const isAssignmentChanged = assignmentDraft !== currentAssignmentValue;
  const canUpdateAssignment =
    !options.hasRecordedDecision &&
    reviewTask.status === "awaiting_review" &&
    Boolean(options.onSubmitReviewAssignment);
  const documentLabel = options.document?.file_name || reviewTask.document_id;
  const decisionReasonCode = options.decisionReasonCode.trim();
  const decisionReasonCodeOptions = buildReviewDecisionReasonCodeOptions(
    reviewTask,
    options.selectedDecisionStatus,
  );
  const decisionReasonCodePlaceholder =
    options.selectedDecisionStatus === "approved"
      ? "account_override_confirmed"
      : "account_override_follow_up";
  const decisionActionLabel =
    options.selectedDecisionStatus === "approved" ? "Approve task" : "Reject task";
  const noteDraft = options.noteDraft.trim();
  const decisionWorkflowCopy =
    options.selectedDecisionStatus === "approved"
      ? "Approval clears the task with the current selected account, reviewer note, and structured reason code for downstream operators."
      : "Rejection records the issue, reviewer note, and structured reason code so the next operator sees what evidence is missing or incorrect.";
  const contractCoverageState = getContractCoverageState(options.contractStatus);
  const isWorkflowBusy =
    options.isAssignmentSubmitting ||
    options.isDecisionSubmitting ||
    options.isExtractionEditSubmitting ||
    options.isNoteSubmitting;
  let actionability: ReviewTaskActionability = {
    isActionable:
      !options.hasRecordedDecision &&
      reviewTask.status === "awaiting_review" &&
      Boolean(
        options.onSubmitReviewDecision ||
          options.onSubmitExtractionEdits ||
          options.onSubmitReviewNote,
      ),
    message: null,
  };

  if (actionability.isActionable && !reviewTask.row_version) {
    actionability = {
      isActionable: false,
      message: "Refresh the workspace before recording a decision. This task is missing its concurrency token.",
    };
  }

  if (
    actionability.isActionable &&
    assignedReviewerEmail &&
    reviewerEmail !== assignedReviewerEmail
  ) {
    actionability = {
      isActionable: false,
      message: `Assigned to ${reviewTask.assigned_user_email}. Refresh or reassign the task before recording a decision.`,
    };
  }

  const reviewTaskActivityEntries = buildReviewTaskActivityEntries(reviewTask, {
    auditEvents: options.auditEvents,
    extractionReviewEditMetadata: options.extractionReviewEditMetadata,
    operatorNotes: options.operatorNotes,
    reviewDecision: options.reviewDecision,
  });

  return (
    <SurfaceCard
      data-review-task-id={reviewTask.review_task_id}
      key={reviewTask.review_task_id}
      tabIndex={-1}
    >
      <div className="queue-card-header">
        <div className="queue-card-heading">
          <span className="queue-card-label">{toLabel(reviewTask.status)}</span>
          <h3>{documentLabel}</h3>
        </div>
        <span className="workspace-inline-chip">{reviewTask.assigned_user_email || "Unassigned"}</span>
      </div>

      <p className="workspace-copy">{reviewTask.notes_summary || "No task summary stored."}</p>
      <p className="workspace-caption">
        Priority {toLabel(reviewTask.priority)}
        {reviewTask.due_at_utc ? ` · Due ${formatDateTime(reviewTask.due_at_utc)}` : ""}
      </p>
      {reviewTask.reason_codes.length > 0 ? (
        <ul className="chip-list stack-chip-list">
          {reviewTask.reason_codes.map((reasonCode) => (
            <li className="match-pill" key={reasonCode}>
              {reasonCode}
            </li>
          ))}
        </ul>
      ) : null}

      <dl className="detail-list compact-detail-list">
        <div>
          <dt>Suggested account</dt>
          <dd>{options.suggestedAccountId || "Not suggested"}</dd>
        </div>
        <div>
          <dt>Selected account</dt>
          <dd>{options.selectedAccountId || "Not set"}</dd>
        </div>
        <div>
          <dt>Reviewer</dt>
          <dd>{options.reviewerEmail || reviewTask.assigned_user_email || "Protected admin session"}</dd>
        </div>
        <div>
          <dt>Content type</dt>
          <dd>{options.document ? toLabel(options.document.content_type) : "Not captured"}</dd>
        </div>
      </dl>

      <div className="workspace-review-field-editor">
        <div className="mini-card-header">
          <div>
            <p className="queue-card-label">Review readiness</p>
            <strong>{options.contractStatus?.documentTypeLabel || "Not typed"}</strong>
          </div>
          <StatusBadge tone={contractCoverageState.tone}>
            {contractCoverageState.status}
          </StatusBadge>
        </div>
        <dl className="detail-list compact-detail-list">
          <div>
            <dt>Classification</dt>
            <dd>{options.contractStatus?.classificationLabel || "Not classified"}</dd>
          </div>
          <div>
            <dt>Document type</dt>
            <dd>{options.contractStatus?.documentTypeLabel || "Not typed"}</dd>
          </div>
          <div>
            <dt>Prompt profile</dt>
            <dd>{options.contractStatus?.promptProfileLabel || "Not assigned"}</dd>
          </div>
          <div>
            <dt>Required fields missing</dt>
            <dd>{options.contractStatus?.missingRequiredFields.length ?? 0}</dd>
          </div>
        </dl>
        <p className="workspace-caption">{contractCoverageState.detail}</p>
        {options.contractStatus?.missingRequiredFields.length && options.onInspectDocument ? (
          <div className="workspace-review-support-actions">
            {options.contractStatus.missingRequiredFields.map((fieldName) => (
              <button
                className="ghost-button"
                key={fieldName}
                onClick={() => {
                  options.onInspectDocument?.(reviewTask.document_id, fieldName, {
                    focusFieldName: fieldName,
                    reviewTaskId: reviewTask.review_task_id,
                  });
                }}
                type="button"
              >
                Inspect {toLabel(fieldName)} in viewer
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <div className="workspace-review-field-editor">
        <div className="mini-card-header">
          <div>
            <p className="queue-card-label">Task activity</p>
            <strong>{formatCount(reviewTaskActivityEntries.length, "captured step")}</strong>
          </div>
          <StatusBadge tone={options.reviewDecision ? "success" : "warning"}>
            {options.reviewDecision ? "Decision stored" : "Awaiting decision"}
          </StatusBadge>
        </div>
        <div className="timeline-list">
          {reviewTaskActivityEntries.map((entry) => (
            <SurfaceTimelineItem
              badge={
                <span className="workspace-inline-chip">{entry.actor || "System"}</span>
              }
              description={`${entry.detail} · ${formatDateTime(entry.timestamp)}`}
              eyebrow="Review activity"
              key={entry.id}
              markerState={entry.state}
              title={entry.title}
            />
          ))}
        </div>
      </div>

      <div className="workspace-review-support-actions">
        <button
          className="ghost-button"
          disabled={!options.onInspectDocument}
          onClick={() => {
            options.onInspectDocument?.(
              reviewTask.document_id,
              getPreferredFieldNameForReviewTask(reviewTask),
              {
                focusFieldName: getPreferredFieldNameForReviewTask(reviewTask),
                reviewTaskId: reviewTask.review_task_id,
              },
            );
          }}
          type="button"
        >
          Open viewer evidence
        </button>
        {actionability.isActionable &&
        options.suggestedAccountId &&
        options.selectedAccountId !== options.suggestedAccountId ? (
          <button
            className="ghost-button"
            onClick={() => {
              options.onSelectedAccountIdChange(options.suggestedAccountId || "");
            }}
            type="button"
          >
            Use suggested account
          </button>
        ) : null}
      </div>

      {options.hasRecordedDecision ? (
        <p className="workspace-caption">
          This review task already has a persisted SQL decision.
        </p>
      ) : null}

      {!options.hasRecordedDecision && actionability.message ? (
        <p className="workspace-caption">{actionability.message}</p>
      ) : null}

      {canUpdateAssignment ? (
        <div className="workspace-review-field-editor">
          <div className="mini-card-header">
            <div>
              <p className="queue-card-label">Task assignment</p>
              <strong>{assignmentDraft || "Unassigned"}</strong>
            </div>
            <StatusBadge tone={assignmentDraft ? "accent" : "neutral"}>
              {assignmentDraft ? "Reviewer selected" : "Unassigned"}
            </StatusBadge>
          </div>
          {options.assignmentErrorMessage ? (
            <p className="status-banner status-error workspace-inline-status">
              {options.assignmentErrorMessage}
            </p>
          ) : null}
          {options.assignmentSuccessMessage ? (
            <p className="status-banner status-success workspace-inline-status">
              {options.assignmentSuccessMessage}
            </p>
          ) : null}
          <label className="filter-field">
            <span>Assigned reviewer</span>
            <input
              onChange={(event) => {
                options.onAssignmentDraftChange(event.target.value);
              }}
              placeholder="reviewer@example.com"
              type="email"
              value={options.assignmentDraft}
            />
          </label>
          <p className="workspace-caption">
            Reassign open tasks here before recording the final decision. Leave the field blank to clear the assignment.
          </p>
          <div className="workspace-review-support-actions">
            {reviewerEmailValue && reviewerEmail !== assignmentDraft.toLowerCase() ? (
              <button
                className="ghost-button"
                onClick={() => {
                  options.onAssignmentDraftChange(reviewerEmailValue);
                }}
                type="button"
              >
                Assign to me
              </button>
            ) : null}
            {assignedReviewerEmail ? (
              <button
                className="ghost-button"
                onClick={() => {
                  options.onAssignmentDraftChange("");
                }}
                type="button"
              >
                Clear assignment
              </button>
            ) : null}
          </div>
          <div className="workspace-action-buttons">
            <button
              className="ghost-button"
              disabled={
                isWorkflowBusy ||
                !options.onSubmitReviewAssignment ||
                !reviewTask.row_version ||
                !isAssignmentChanged
              }
              onClick={() => {
                if (!reviewTask.row_version || !isAssignmentChanged) {
                  return;
                }

                options.onSubmitReviewAssignment?.({
                  assigned_user_email: assignmentDraft || null,
                  expected_row_version: reviewTask.row_version,
                  review_task_id: reviewTask.review_task_id,
                });
              }}
              type="button"
            >
              {options.isAssignmentSubmitting ? "Saving assignment..." : "Save assignment"}
            </button>
          </div>
        </div>
      ) : null}

      {actionability.isActionable ? (
        <div className="workspace-action-panel">
          <p className="workspace-caption">
            Inspect the protected evidence, choose the decision path, then record the final disposition through the SQL-backed review-task route.
          </p>
          {options.decisionErrorMessage ? (
            <p className="status-banner status-error workspace-inline-status">
              {options.decisionErrorMessage}
            </p>
          ) : null}
          {options.extractionEditErrorMessage ? (
            <p className="status-banner status-error workspace-inline-status">
              {options.extractionEditErrorMessage}
            </p>
          ) : null}
          {options.extractionEditSuccessMessage ? (
            <p className="status-banner status-success workspace-inline-status">
              {options.extractionEditSuccessMessage}
            </p>
          ) : null}
          {options.noteErrorMessage ? (
            <p className="status-banner status-error workspace-inline-status">
              {options.noteErrorMessage}
            </p>
          ) : null}
          {options.noteSuccessMessage ? (
            <p className="status-banner status-success workspace-inline-status">
              {options.noteSuccessMessage}
            </p>
          ) : null}
          <div className="workspace-review-field-editor">
            <div className="mini-card-header">
              <div>
                <p className="queue-card-label">Task note</p>
                <strong>{noteDraft || "No draft note"}</strong>
              </div>
              <StatusBadge tone={noteDraft ? "accent" : "neutral"}>
                {noteDraft ? "Ready to save" : "Optional"}
              </StatusBadge>
            </div>
            <label className="filter-field workspace-textarea-field">
              <span>Task note</span>
              <textarea
                onChange={(event) => {
                  options.onNoteDraftChange(event.target.value);
                }}
                placeholder="Add a task-scoped note for the next operator or audit trail."
                rows={3}
                value={options.noteDraft}
              />
            </label>
            <p className="workspace-caption">
              Task notes persist immediately and appear in the review activity timeline after the workspace refreshes.
            </p>
            <div className="workspace-action-buttons">
              <button
                className="ghost-button"
                disabled={
                  isWorkflowBusy ||
                  !options.onSubmitReviewNote ||
                  !reviewTask.row_version ||
                  !noteDraft
                }
                onClick={() => {
                  if (!reviewTask.row_version || !noteDraft) {
                    return;
                  }

                  options.onSubmitReviewNote?.({
                    expected_row_version: reviewTask.row_version,
                    is_private: false,
                    note_text: noteDraft,
                    review_task_id: reviewTask.review_task_id,
                  });
                }}
                type="button"
              >
                {options.isNoteSubmitting ? "Saving task note..." : "Save task note"}
              </button>
            </div>
          </div>
          {options.editableFields.length > 0 ? (
            <div className="workspace-review-field-editor">
              <div className="mini-card-header">
                <div>
                  <p className="queue-card-label">Editable extracted values</p>
                  <strong>
                    {formatCount(options.editableFields.length, "captured field")}
                  </strong>
                </div>
                <StatusBadge tone={options.fieldChanges.length > 0 ? "warning" : "neutral"}>
                  {options.fieldChanges.length > 0
                    ? `${options.fieldChanges.length} staged edit${options.fieldChanges.length === 1 ? "" : "s"}`
                    : "No staged edits"}
                </StatusBadge>
              </div>
              <p className="workspace-caption">
                Save extracted-value changes through the dedicated extraction edit route before recording the final review decision.
              </p>
              <div className="workspace-editable-field-list">
                {options.editableFields.map((field) => {
                  const editedValue = getEditedFieldValue(
                    field,
                    options.editedFieldValues,
                  );
                  const isChanged = editedValue !== field.value;

                  return (
                    <div className="workspace-editable-field" key={field.name}>
                      <div className="mini-card-header">
                        <div>
                          <p className="queue-card-label">{field.name}</p>
                          <strong>{editedValue || "[blank]"}</strong>
                        </div>
                        <StatusBadge tone={isChanged ? "warning" : "neutral"}>
                          {isChanged ? "Edited" : "Stored"}
                        </StatusBadge>
                      </div>
                      <label className="filter-field">
                        <span>{field.name} value</span>
                        <input
                          data-review-field-name={field.name}
                          onChange={(event) => {
                            options.onEditedFieldValueChange(
                              field.name,
                              event.target.value,
                            );
                          }}
                          type="text"
                          value={editedValue}
                        />
                      </label>
                      <p className="workspace-caption">
                        Stored value: {field.value || "[blank]"} · {formatConfidence(field.confidence)}
                      </p>
                      {isChanged ? (
                        <div className="workspace-review-support-actions">
                          <button
                            className="ghost-button"
                            onClick={() => {
                              options.onResetEditedFieldValue(field.name);
                            }}
                            type="button"
                          >
                            Reset field
                          </button>
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <p className="workspace-caption">
              No extracted fields are currently available for inline review edits on this document.
            </p>
          )}
          <div className="workspace-action-grid">
            <label className="filter-field">
              <span>Selected account</span>
              <input
                onChange={(event) => {
                  options.onSelectedAccountIdChange(event.target.value);
                }}
                placeholder="acct_123"
                type="text"
                value={options.selectedAccountId}
              />
            </label>
            <label className="filter-field workspace-textarea-field">
              <span>Review notes</span>
              <textarea
                onChange={(event) => {
                  options.onDecisionNoteChange(event.target.value);
                }}
                placeholder="Explain the approval or rejection for downstream operators."
                rows={4}
                value={options.decisionNote}
              />
            </label>
          </div>
          <div className="workspace-review-field-editor">
            <div className="mini-card-header">
              <div>
                <p className="queue-card-label">Decision reason</p>
                <strong>{decisionReasonCode || "No structured reason selected"}</strong>
              </div>
              <StatusBadge tone={decisionReasonCode ? "accent" : "neutral"}>
                {decisionReasonCode ? "Ready for audit" : "Optional"}
              </StatusBadge>
            </div>
            <label className="filter-field">
              <span>Decision reason code</span>
              <input
                onChange={(event) => {
                  options.onDecisionReasonCodeChange(event.target.value);
                }}
                placeholder={decisionReasonCodePlaceholder}
                type="text"
                value={options.decisionReasonCode}
              />
            </label>
            <p className="workspace-caption">
              Structured reason codes stay on the persisted decision so Review and Audit can explain why the task was closed or sent back.
            </p>
            <div className="workspace-review-support-actions">
              {decisionReasonCodeOptions.map((reasonCode) => (
                <button
                  aria-pressed={decisionReasonCode === reasonCode}
                  className="ghost-button"
                  key={reasonCode}
                  onClick={() => {
                    options.onDecisionReasonCodeChange(reasonCode);
                  }}
                  type="button"
                >
                  Use {reasonCode}
                </button>
              ))}
            </div>
          </div>
          <div
            aria-label={`Decision path for ${documentLabel}`}
            className="workspace-review-decision-toggle"
            role="group"
          >
            <button
              aria-pressed={options.selectedDecisionStatus === "approved"}
              className={
                options.selectedDecisionStatus === "approved"
                  ? "workspace-review-decision-button workspace-review-decision-button-active"
                  : "workspace-review-decision-button"
              }
              onClick={() => {
                options.onDecisionStatusChange("approved");
              }}
              type="button"
            >
              Approve and close
            </button>
            <button
              aria-pressed={options.selectedDecisionStatus === "rejected"}
              className={
                options.selectedDecisionStatus === "rejected"
                  ? "workspace-review-decision-button workspace-review-decision-button-active"
                  : "workspace-review-decision-button"
              }
              onClick={() => {
                options.onDecisionStatusChange("rejected");
              }}
              type="button"
            >
              Reject for follow-up
            </button>
          </div>
          <p className="workspace-caption">{decisionWorkflowCopy}</p>
          <div className="workspace-audit-preview">
            <div className="mini-card-header">
              <div>
                <p className="queue-card-label">Audit capture preview</p>
                <strong>
                  {options.fieldChanges.length > 0
                    ? `${options.fieldChanges.length} field edit${options.fieldChanges.length === 1 ? "" : "s"} ready to persist`
                    : "No extracted-value edits queued"}
                </strong>
              </div>
              <StatusBadge tone={options.fieldChanges.length > 0 ? "accent" : "neutral"}>
                {options.fieldChanges.length > 0 ? "Ready to save" : "No extraction edit queued"}
              </StatusBadge>
            </div>
            {options.fieldChanges.length > 0 ? (
              <ul className="workspace-audit-list">
                {options.fieldChanges.map((fieldChange) => (
                  <li key={fieldChange.fieldName}>
                    <strong>{fieldChange.fieldName}</strong>
                    <span>
                      {fieldChange.originalValue || "[blank]"} to {fieldChange.currentValue || "[blank]"}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="workspace-caption">
                Save a field edit to persist an audited extraction override. Review decisions now persist the selected account, reviewer note, structured reason code, and disposition.
              </p>
            )}
          </div>
          <div className="workspace-action-buttons">
            {options.fieldChanges.length > 0 ? (
              <button
                disabled={
                  isWorkflowBusy ||
                  !options.onSubmitExtractionEdits ||
                  !reviewTask.row_version
                }
                onClick={() => {
                  if (!reviewTask.row_version) {
                    return;
                  }

                  options.onSubmitExtractionEdits?.({
                    expected_row_version: reviewTask.row_version,
                    field_edits: options.fieldChanges.map((fieldChange) => ({
                      field_name: fieldChange.fieldName,
                      value: fieldChange.currentValue,
                    })),
                    review_task_id: reviewTask.review_task_id,
                  });
                }}
                type="button"
              >
                {options.isExtractionEditSubmitting
                  ? "Saving extraction edits..."
                  : `Save ${formatCount(options.fieldChanges.length, "field edit")}`}
              </button>
            ) : null}
            <button
              disabled={isWorkflowBusy}
              onClick={() => {
                if (!reviewTask.row_version) {
                  return;
                }

                options.onSubmitReviewDecision?.({
                  decision_reason_code: decisionReasonCode || undefined,
                  decision_status: options.selectedDecisionStatus,
                  expected_row_version: reviewTask.row_version,
                  review_notes: options.decisionNote.trim() || undefined,
                  review_task_id: reviewTask.review_task_id,
                  selected_account_id: options.selectedAccountId || null,
                });
              }}
              type="button"
            >
              {decisionActionLabel}
            </button>
          </div>
        </div>
      ) : null}
    </SurfaceCard>
  );
}

function renderReviewTaskCreateCard(
  document: PacketDocumentRecord,
  options: {
    assignmentDraft: string;
    extractedFields: ExtractedField[];
    extractionSummary: string | null;
    isCreateTaskSubmitting: boolean;
    notesSummaryDraft: string;
    onAssignmentDraftChange: (value: string) => void;
    onInspectDocument?: (
      documentId: string,
      preferredFieldName?: string | null,
      returnTarget?: ReviewViewerReturnTarget,
    ) => void;
    onNotesSummaryChange: (value: string) => void;
    onSelectedAccountIdChange: (value: string) => void;
    onSubmitReviewTaskCreate?: (
      reviewTask: PacketWorkspaceReviewTaskCreateInput,
    ) => Promise<void> | void;
    reviewerEmail: string | null;
    selectedAccountId: string;
    suggestedAccountId: string;
  },
) {
  const assignmentDraft = options.assignmentDraft.trim();
  const notesSummaryDraft = options.notesSummaryDraft.trim();
  const reviewerEmailValue = options.reviewerEmail?.trim() || "";

  return (
    <SurfaceCard key={document.document_id}>
      <div className="queue-card-header">
        <div className="queue-card-heading">
          <span className="queue-card-label">No task yet</span>
          <h3>{document.file_name}</h3>
        </div>
        <span className="workspace-inline-chip">{toLabel(document.status)}</span>
      </div>

      <p className="workspace-copy">
        {options.extractionSummary ||
          document.source_summary ||
          "No extraction or source summary is stored for this document yet."}
      </p>
      <dl className="detail-list compact-detail-list">
        <div>
          <dt>Suggested account</dt>
          <dd>{options.suggestedAccountId || "Not suggested"}</dd>
        </div>
        <div>
          <dt>Selected account</dt>
          <dd>{options.selectedAccountId || "Not set"}</dd>
        </div>
        <div>
          <dt>Extracted fields</dt>
          <dd>{formatCount(options.extractedFields.length, "captured field")}</dd>
        </div>
        <div>
          <dt>Document type</dt>
          <dd>{toLabel(document.content_type)}</dd>
        </div>
      </dl>

      <div className="workspace-review-support-actions">
        <button
          className="ghost-button"
          disabled={!options.onInspectDocument}
          onClick={() => {
            options.onInspectDocument?.(
              document.document_id,
              options.extractedFields[0]?.name || null,
            );
          }}
          type="button"
        >
          Open viewer evidence
        </button>
        {options.suggestedAccountId &&
        options.selectedAccountId !== options.suggestedAccountId ? (
          <button
            className="ghost-button"
            onClick={() => {
              options.onSelectedAccountIdChange(options.suggestedAccountId);
            }}
            type="button"
          >
            Use suggested account
          </button>
        ) : null}
      </div>

      <div className="workspace-review-field-editor">
        <div className="mini-card-header">
          <div>
            <p className="queue-card-label">Task authoring</p>
            <strong>{assignmentDraft || "Unassigned"}</strong>
          </div>
          <StatusBadge tone={assignmentDraft ? "accent" : "neutral"}>
            {assignmentDraft ? "Reviewer seeded" : "Reviewer optional"}
          </StatusBadge>
        </div>
        <label className="filter-field">
          <span>Initial reviewer</span>
          <input
            onChange={(event) => {
              options.onAssignmentDraftChange(event.target.value);
            }}
            placeholder="reviewer@example.com"
            type="email"
            value={options.assignmentDraft}
          />
        </label>
        <label className="filter-field">
          <span>Selected account</span>
          <input
            onChange={(event) => {
              options.onSelectedAccountIdChange(event.target.value);
            }}
            placeholder="acct_123"
            type="text"
            value={options.selectedAccountId}
          />
        </label>
        <label className="filter-field workspace-textarea-field">
          <span>Task summary</span>
          <textarea
            onChange={(event) => {
              options.onNotesSummaryChange(event.target.value);
            }}
            placeholder="Describe the review follow-up needed for this document."
            rows={3}
            value={options.notesSummaryDraft}
          />
        </label>
        <p className="workspace-caption">
          Create a packet-local review task for this document without leaving the protected workspace.
        </p>
        <div className="workspace-review-support-actions">
          {reviewerEmailValue &&
          reviewerEmailValue.toLowerCase() !== assignmentDraft.toLowerCase() ? (
            <button
              className="ghost-button"
              onClick={() => {
                options.onAssignmentDraftChange(reviewerEmailValue);
              }}
              type="button"
            >
              Assign to me
            </button>
          ) : null}
          {assignmentDraft ? (
            <button
              className="ghost-button"
              onClick={() => {
                options.onAssignmentDraftChange("");
              }}
              type="button"
            >
              Clear reviewer
            </button>
          ) : null}
        </div>
        <div className="workspace-action-buttons">
          <button
            className="ghost-button"
            disabled={
              options.isCreateTaskSubmitting || !options.onSubmitReviewTaskCreate
            }
            onClick={() => {
              options.onSubmitReviewTaskCreate?.({
                assigned_user_email: assignmentDraft || null,
                document_id: document.document_id,
                notes_summary: notesSummaryDraft || null,
                selected_account_id: options.selectedAccountId.trim() || null,
              });
            }}
            type="button"
          >
            {options.isCreateTaskSubmitting
              ? "Creating review task..."
              : "Create review task"}
          </button>
        </div>
      </div>
    </SurfaceCard>
  );
}

function renderReviewDecision(reviewDecision: ReviewDecisionRecord) {
  return (
    <SurfaceCard key={reviewDecision.decision_id}>
      <div className="queue-card-header">
        <div className="queue-card-heading">
          <span className="queue-card-label">Decision</span>
          <h3>{toLabel(reviewDecision.decision_status)}</h3>
        </div>
        <span className="workspace-inline-chip">{reviewDecision.decided_by_email || "Unknown reviewer"}</span>
      </div>

      <dl className="detail-list compact-detail-list">
        <div>
          <dt>Task</dt>
          <dd>{reviewDecision.review_task_id}</dd>
        </div>
        <div>
          <dt>Reason code</dt>
          <dd>{reviewDecision.decision_reason_code || "Not captured"}</dd>
        </div>
        <div>
          <dt>Selected account</dt>
          <dd>{reviewDecision.selected_account_id || "Not set"}</dd>
        </div>
        <div>
          <dt>When</dt>
          <dd>{formatDateTime(reviewDecision.decided_at_utc)}</dd>
        </div>
      </dl>
      {reviewDecision.review_notes ? (
        <p className="workspace-copy workspace-copy-prewrap">{reviewDecision.review_notes}</p>
      ) : null}
    </SurfaceCard>
  );
}

function renderOperatorNote(note: OperatorNoteRecord) {
  return (
    <SurfaceCard key={note.note_id}>
      <div className="queue-card-header">
        <div className="queue-card-heading">
          <span className="queue-card-label">Note</span>
          <h3>{note.created_by_email || "Unknown author"}</h3>
        </div>
        <span className="workspace-inline-chip">{formatDateTime(note.created_at_utc)}</span>
      </div>
      <p className="workspace-copy">{note.note_text}</p>
    </SurfaceCard>
  );
}

function renderAuditEvent(auditEvent: AuditEventRecord) {
  const extractionEditDetails = getExtractionEditAuditEventDetails(auditEvent);

  return (
    <SurfaceCard key={auditEvent.audit_event_id}>
      <div className="queue-card-header">
        <div className="queue-card-heading">
          <span className="queue-card-label">
            {extractionEditDetails ? "Field edit audit" : "Audit"}
          </span>
          <h3>{auditEvent.event_type}</h3>
        </div>
        <span className="workspace-inline-chip">{auditEvent.actor_email || "System"}</span>
      </div>
      <p className="workspace-copy">{formatDateTime(auditEvent.created_at_utc)}</p>
      {extractionEditDetails ? (
        <div className="workspace-audit-event-summary">
          <p className="workspace-caption">
            {formatCount(extractionEditDetails.changedFields.length, "field edit")} recorded for {auditEvent.document_id || "the packet"}.
          </p>
          <ul className="workspace-audit-list">
            {extractionEditDetails.changedFields.map((fieldChange) => (
              <li key={`${auditEvent.audit_event_id}:${fieldChange.fieldName}`}>
                <strong>{fieldChange.fieldName}</strong>
                <span>
                  {fieldChange.originalValue || "[blank]"} to {fieldChange.currentValue || "[blank]"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {auditEvent.event_payload ? (
        <pre className="workspace-json-block">
          {JSON.stringify(auditEvent.event_payload, null, 2)}
        </pre>
      ) : null}
    </SurfaceCard>
  );
}

function renderExtractionEditAuditHistoryCard(
  auditEvent: AuditEventRecord,
  options: {
    documentLabel: string;
  },
) {
  const extractionEditDetails = getExtractionEditAuditEventDetails(auditEvent);
  if (!extractionEditDetails) {
    return null;
  }

  return (
    <SurfaceCard key={`field-edit:${auditEvent.audit_event_id}`}>
      <div className="queue-card-header">
        <div className="queue-card-heading">
          <span className="queue-card-label">Field edit</span>
          <h3>{options.documentLabel}</h3>
        </div>
        <span className="workspace-inline-chip">{auditEvent.actor_email || "System"}</span>
      </div>
      <p className="workspace-copy">
        Saved {formatCount(extractionEditDetails.changedFields.length, "field change")} at {formatDateTime(auditEvent.created_at_utc)}.
      </p>
      <div className="workspace-subcard-list">
        {extractionEditDetails.changedFields.map((fieldChange) => (
          <div
            className="workspace-subcard workspace-subcard-refresh-delta"
            key={`${auditEvent.audit_event_id}:${fieldChange.fieldName}`}
          >
            <strong>{fieldChange.fieldName}</strong>
            <span>
              {fieldChange.originalValue || "[blank]"} to {fieldChange.currentValue || "[blank]"}
            </span>
            <small>
              {fieldChange.confidence !== undefined
                ? `Prior confidence ${formatConfidence(fieldChange.confidence)}`
                : "Confidence not captured"}
            </small>
          </div>
        ))}
      </div>
      {(extractionEditDetails.sourceExtractionResultId ||
        extractionEditDetails.newExtractionResultId) ? (
        <p className="workspace-caption">
          Source result {extractionEditDetails.sourceExtractionResultId || "not captured"}{" -> "}
          new result {extractionEditDetails.newExtractionResultId || "not captured"}.
        </p>
      ) : null}
    </SurfaceCard>
  );
}

function renderAssignmentCard(
  reviewTask: ReviewTaskRecord,
  reviewDecision: ReviewDecisionRecord | undefined,
) {
  return (
    <SurfaceCard key={reviewTask.review_task_id}>
      <div className="queue-card-header">
        <div className="queue-card-heading">
          <span className="queue-card-label">Assignment</span>
          <h3>{reviewTask.assigned_user_email || "Unassigned"}</h3>
        </div>
        <span className="workspace-inline-chip">{toLabel(reviewTask.status)}</span>
      </div>
      <p className="workspace-copy">{reviewTask.notes_summary || "No task summary stored."}</p>
      <dl className="detail-list compact-detail-list">
        <div>
          <dt>Priority</dt>
          <dd>{toLabel(reviewTask.priority)}</dd>
        </div>
        <div>
          <dt>Selected account</dt>
          <dd>{reviewDecision?.selected_account_id || reviewTask.selected_account_id || "Not set"}</dd>
        </div>
        <div>
          <dt>Due</dt>
          <dd>{formatDateTime(reviewTask.due_at_utc)}</dd>
        </div>
        <div>
          <dt>Decision</dt>
          <dd>{reviewDecision ? toLabel(reviewDecision.decision_status) : "Pending"}</dd>
        </div>
      </dl>
      {reviewTask.reason_codes.length > 0 ? (
        <ul className="chip-list stack-chip-list">
          {reviewTask.reason_codes.map((reasonCode) => (
            <li className="match-pill" key={reasonCode}>
              {reasonCode}
            </li>
          ))}
        </ul>
      ) : null}
    </SurfaceCard>
  );
}

function renderRecommendationResult(
  recommendationResult: RecommendationResultRecord,
  options: {
    onReviewRecommendation?: (
      recommendationResultId: string,
      disposition: RecommendationReviewDisposition,
    ) => Promise<void> | void;
    processingRecommendationReview: string | null;
    run?: RecommendationRunRecord;
  },
) {
  const acceptActionKey = `${recommendationResult.recommendation_result_id}:accepted`;
  const rejectActionKey = `${recommendationResult.recommendation_result_id}:rejected`;
  const isPending = recommendationResult.disposition === "pending";

  return (
    <SurfaceCard key={recommendationResult.recommendation_result_id}>
      <div className="queue-card-header">
        <div className="queue-card-heading">
          <span className="queue-card-label">{toLabel(recommendationResult.disposition)}</span>
          <h3>{recommendationResult.recommendation_kind}</h3>
        </div>
        <span className="workspace-inline-chip">{formatConfidence(recommendationResult.confidence)}</span>
      </div>
      <p className="workspace-copy">{recommendationResult.summary}</p>
      {recommendationResult.advisory_text ? (
        <p className="workspace-copy">{recommendationResult.advisory_text}</p>
      ) : null}
      <dl className="detail-list compact-detail-list">
        <div>
          <dt>Requested by</dt>
          <dd>{options.run?.requested_by_email || "Not captured"}</dd>
        </div>
        <div>
          <dt>Run status</dt>
          <dd>{toLabel(options.run?.status)}</dd>
        </div>
        <div>
          <dt>Reviewed by</dt>
          <dd>{recommendationResult.reviewed_by_email || "Pending operator decision"}</dd>
        </div>
        <div>
          <dt>Reviewed at</dt>
          <dd>{formatDateTime(recommendationResult.reviewed_at_utc)}</dd>
        </div>
      </dl>
      {recommendationResult.evidence_items.length > 0 ? (
        <div className="workspace-subcard-list">
          {recommendationResult.evidence_items.map((evidenceItem, index) => (
            <div className="workspace-subcard" key={`${recommendationResult.recommendation_result_id}:${index}`}>
              <strong>{toLabel(evidenceItem.evidence_kind)}</strong>
              <span>{evidenceItem.field_name || evidenceItem.source_document_id || "No field name"}</span>
              <small>{evidenceItem.source_excerpt || "No excerpt stored"}</small>
            </div>
          ))}
        </div>
      ) : null}
      {isPending ? (
        <div className="workspace-action-panel">
          <p className="workspace-caption">
            Recommendation guidance is advisory until an operator records an explicit disposition.
          </p>
          <div className="workspace-action-buttons">
            <button
              className="ghost-button"
              disabled={
                Boolean(options.processingRecommendationReview) ||
                !options.onReviewRecommendation
              }
              onClick={() => {
                options.onReviewRecommendation?.(
                  recommendationResult.recommendation_result_id,
                  "rejected",
                );
              }}
              type="button"
            >
              {options.processingRecommendationReview === rejectActionKey
                ? "Rejecting..."
                : "Reject recommendation"}
            </button>
            <button
              disabled={
                Boolean(options.processingRecommendationReview) ||
                !options.onReviewRecommendation
              }
              onClick={() => {
                options.onReviewRecommendation?.(
                  recommendationResult.recommendation_result_id,
                  "accepted",
                );
              }}
              type="button"
            >
              {options.processingRecommendationReview === acceptActionKey
                ? "Approving..."
                : "Approve recommendation"}
            </button>
          </div>
        </div>
      ) : (
        <p className="workspace-caption">
          Reviewed by {recommendationResult.reviewed_by_email || "an operator"} at {formatDateTime(recommendationResult.reviewed_at_utc)}.
        </p>
      )}
    </SurfaceCard>
  );
}

export function PacketWorkspacePanel({
  assignmentErrorMessage,
  assignmentSuccessMessage,
  createTaskErrorMessage,
  createTaskSuccessMessage,
  decisionErrorMessage,
  errorMessage,
  extractionEditErrorMessage,
  extractionEditSuccessMessage,
  intakeActionErrorMessage,
  intakeActionSuccessMessage,
  isAssignmentSubmitting,
  isExtractionEditSubmitting,
  isDecisionSubmitting,
  isNoteSubmitting,
  isReviewTaskCreateSubmitting,
  isLoading,
  isOperatorContractsLoading,
  isReplayingPacket,
  noteErrorMessage,
  noteSuccessMessage,
  onExecuteStage,
  onRefresh,
  onReplayPacket,
  onReviewRecommendation,
  onRetryStage,
  onSubmitExtractionEdits,
  onSubmitReviewAssignment,
  onSubmitReviewNote,
  onSubmitReviewTaskCreate,
  onSubmitReviewDecision,
  operatorContracts,
  operatorContractsErrorMessage,
  panelDescription,
  panelTitle,
  pipelineActionErrorMessage,
  pipelineActionSuccessMessage,
  preferredTab,
  processingRecommendationReview,
  processingPipelineAction,
  recommendationActionErrorMessage,
  recommendationActionSuccessMessage,
  reviewerEmail,
  selectedPacketSummary,
  tabPriorityAnchor,
  workspace,
  workspaceLastLoadedAt,
  onSelectTab,
}: PacketWorkspacePanelProps) {
  const [activeTab, setActiveTab] = useState<WorkspaceTabId>(preferredTab);
  const [showAllWorkspaceTabs, setShowAllWorkspaceTabs] = useState(false);
  const effectiveTabPriorityAnchor = tabPriorityAnchor ?? preferredTab;
  const prioritizedWorkspaceTabs = getPrioritizedWorkspaceTabs(effectiveTabPriorityAnchor);
  const prioritizedWorkspaceTabPreviews: readonly WorkspaceTabPreview[] =
    prioritizedWorkspaceTabs.map((tab) => ({
      ...tab,
      ...getWorkspaceTabUrgency({
        selectedPacketSummary,
        tabId: tab.id,
        workspace,
      }),
    }));
  const visibleWorkspaceTabs = getVisibleWorkspaceTabs({
    activeTab,
    prioritizedTabs: prioritizedWorkspaceTabPreviews,
    showAllTabs: showAllWorkspaceTabs,
  });
  const visibleWorkspaceTabIds = new Set(visibleWorkspaceTabs.map((tab) => tab.id));
  const hiddenWorkspaceTabs = prioritizedWorkspaceTabPreviews.filter(
    (tab) => !visibleWorkspaceTabIds.has(tab.id),
  );
  const hiddenWorkspaceTabCount =
    prioritizedWorkspaceTabs.length - visibleWorkspaceTabs.length;
  const workspaceTabToggleLabel = formatWorkspaceTabToggleLabel(hiddenWorkspaceTabs);
  const workspaceTabCopy =
    hiddenWorkspaceTabCount > 0 && !showAllWorkspaceTabs
      ? `${formatTabPrioritySummary(effectiveTabPriorityAnchor)} More views reveals ${hiddenWorkspaceTabCount} additional tabs when needed.`
      : formatTabPrioritySummary(effectiveTabPriorityAnchor);
  const [reviewTaskAssignmentDraftsByTaskId, setReviewTaskAssignmentDraftsByTaskId] =
    useState<Record<string, string>>({});
  const [reviewTaskCreateAssignmentDraftsByDocumentId,
    setReviewTaskCreateAssignmentDraftsByDocumentId] = useState<
      Record<string, string>
    >({});
  const [reviewTaskCreateNotesByDocumentId, setReviewTaskCreateNotesByDocumentId] =
    useState<Record<string, string>>({});
  const [reviewTaskCreateSelectedAccountsByDocumentId,
    setReviewTaskCreateSelectedAccountsByDocumentId] = useState<
      Record<string, string>
    >({});
  const [reviewTaskNoteDraftsByTaskId, setReviewTaskNoteDraftsByTaskId] = useState<
    Record<string, string>
  >({});
  const [reviewNotesByTaskId, setReviewNotesByTaskId] = useState<
    Record<string, string>
  >({});
  const [reviewDecisionReasonCodesByTaskId, setReviewDecisionReasonCodesByTaskId] =
    useState<Record<string, string>>({});
  const [selectedAccountIdsByTaskId, setSelectedAccountIdsByTaskId] = useState<
    Record<string, string>
  >({});
  const [auditEventFilterMode, setAuditEventFilterMode] =
    useState<AuditEventFilterMode>("all");
  const [selectedAuditDocumentId, setSelectedAuditDocumentId] =
    useState<string>("all");
  const [documentRefreshDeltasByDocumentId, setDocumentRefreshDeltasByDocumentId] =
    useState<Record<string, DocumentRefreshDelta>>({});
  const [editedExtractedValuesByTaskId, setEditedExtractedValuesByTaskId] = useState<
    Record<string, Record<string, string>>
  >({});
  const [reviewDecisionStatusByTaskId, setReviewDecisionStatusByTaskId] = useState<
    Record<string, PacketWorkspaceReviewDecisionStatus>
  >({});
  const [expandedDocumentDetailsByDocumentId,
    setExpandedDocumentDetailsByDocumentId] = useState<Record<string, boolean>>({});
  const [selectedViewerDocumentId, setSelectedViewerDocumentId] = useState<
    string | null
  >(null);
  const [selectedViewerFieldKey, setSelectedViewerFieldKey] = useState<string | null>(
    null,
  );
  const [selectedViewerFieldNameHint, setSelectedViewerFieldNameHint] = useState<
    string | null
  >(null);
  const [viewerReturnTarget, setViewerReturnTarget] = useState<ReviewViewerReturnTarget | null>(
    null,
  );
  const [pendingReviewFocusTarget, setPendingReviewFocusTarget] = useState<
    ReviewViewerReturnTarget | null
  >(null);
  const previousWorkspacePacketIdRef = useRef<string | null>(null);
  const previousDocumentRefreshKeysRef = useRef<
    Record<string, DocumentRefreshComparisonKey>
  >({});

  useEffect(() => {
    setActiveTab(preferredTab);
  }, [preferredTab, workspace?.packet.packet_id]);

  useEffect(() => {
    setShowAllWorkspaceTabs(false);
  }, [effectiveTabPriorityAnchor, workspace?.packet.packet_id]);

  useEffect(() => {
    setExpandedDocumentDetailsByDocumentId({});
  }, [workspace?.packet.packet_id]);

  function toggleDocumentDetails(documentId: string) {
    setExpandedDocumentDetailsByDocumentId((currentValue) => ({
      ...currentValue,
      [documentId]: !currentValue[documentId],
    }));
  }

  useEffect(() => {
    if (!workspace) {
      setAuditEventFilterMode("all");
      setSelectedAuditDocumentId("all");
      setDocumentRefreshDeltasByDocumentId({});
      setSelectedViewerFieldNameHint(null);
      setViewerReturnTarget(null);
      setPendingReviewFocusTarget(null);
      setReviewTaskAssignmentDraftsByTaskId({});
      setReviewTaskCreateAssignmentDraftsByDocumentId({});
      setReviewTaskCreateNotesByDocumentId({});
      setReviewTaskCreateSelectedAccountsByDocumentId({});
      setReviewTaskNoteDraftsByTaskId({});
      setReviewNotesByTaskId({});
      setReviewDecisionReasonCodesByTaskId({});
      setSelectedAccountIdsByTaskId({});
      setEditedExtractedValuesByTaskId({});
      setReviewDecisionStatusByTaskId({});
      setSelectedViewerDocumentId(null);
      setSelectedViewerFieldKey(null);
      previousWorkspacePacketIdRef.current = null;
      previousDocumentRefreshKeysRef.current = {};
      return;
    }

    const latestAccountMatches = getLatestRecordByDocument(
      workspace.account_match_runs,
    );
    const latestExtractionsByDocument = getLatestRecordByDocument(
      workspace.extraction_results,
    );
    const latestReviewDecisionsByTask = getLatestReviewDecisionsByTask(
      workspace.review_decisions,
    );
    const documentsById = new Map(
      workspace.documents.map((document) => [document.document_id, document]),
    );
    const reviewTasksByDocument = new Map(
      workspace.review_tasks.map((reviewTask) => [reviewTask.document_id, reviewTask]),
    );
    const nextDecisionReasonCodes: Record<string, string> = {};
    const nextCreateTaskSelectedAccounts: Record<string, string> = {};
    const nextSelectedAccounts: Record<string, string> = {};
    const nextDecisionStatuses: Record<
      string,
      PacketWorkspaceReviewDecisionStatus
    > = {};
    for (const document of workspace.documents) {
      if (reviewTasksByDocument.has(document.document_id)) {
        continue;
      }

      nextCreateTaskSelectedAccounts[document.document_id] =
        resolveDocumentSuggestedAccountId(
          latestAccountMatches.get(document.document_id),
          document,
        );
    }
    for (const reviewTask of workspace.review_tasks) {
      nextDecisionReasonCodes[reviewTask.review_task_id] =
        latestReviewDecisionsByTask.get(reviewTask.review_task_id)?.decision_reason_code || "";
      nextSelectedAccounts[reviewTask.review_task_id] = resolveSuggestedAccountId(
        reviewTask,
        latestAccountMatches.get(reviewTask.document_id),
        documentsById.get(reviewTask.document_id),
      );
      nextDecisionStatuses[reviewTask.review_task_id] = "approved";
    }

    const initialViewerDocumentId = workspace.documents[0]?.document_id ?? null;

    setReviewTaskAssignmentDraftsByTaskId({});
  setReviewTaskCreateAssignmentDraftsByDocumentId({});
  setReviewTaskCreateNotesByDocumentId({});
  setReviewTaskCreateSelectedAccountsByDocumentId(nextCreateTaskSelectedAccounts);
    setReviewTaskNoteDraftsByTaskId({});
    setReviewNotesByTaskId({});
    setReviewDecisionReasonCodesByTaskId(nextDecisionReasonCodes);
    setAuditEventFilterMode("all");
    setSelectedAuditDocumentId("all");
    setSelectedAccountIdsByTaskId(nextSelectedAccounts);
    setEditedExtractedValuesByTaskId({});
    setReviewDecisionStatusByTaskId(nextDecisionStatuses);
    setSelectedViewerDocumentId(initialViewerDocumentId);
    setSelectedViewerFieldNameHint(null);
    setViewerReturnTarget(null);
    setPendingReviewFocusTarget(null);
    setSelectedViewerFieldKey(
      initialViewerDocumentId
        ? resolveViewerFieldKey(
            latestExtractionsByDocument.get(initialViewerDocumentId),
          )
        : null,
    );
  }, [workspace?.packet.packet_id]);

  useEffect(() => {
    if (!assignmentSuccessMessage) {
      return;
    }

    setReviewTaskAssignmentDraftsByTaskId({});
  }, [assignmentSuccessMessage]);

  useEffect(() => {
    if (!createTaskSuccessMessage) {
      return;
    }

    setReviewTaskCreateAssignmentDraftsByDocumentId({});
    setReviewTaskCreateNotesByDocumentId({});
  }, [createTaskSuccessMessage]);

  useEffect(() => {
    if (!noteSuccessMessage) {
      return;
    }

    setReviewTaskNoteDraftsByTaskId({});
  }, [noteSuccessMessage]);

  useEffect(() => {
    if (!workspace) {
      setDocumentRefreshDeltasByDocumentId({});
      previousWorkspacePacketIdRef.current = null;
      previousDocumentRefreshKeysRef.current = {};
      return;
    }

    const currentRefreshKeys = Object.fromEntries(
      workspace.documents.map((document) => [
        document.document_id,
        buildDocumentRefreshComparisonKey(
          document,
          latestJobsByDocument,
          latestExtractions,
          latestOcrResults,
          latestRecommendations,
          contractStatusByDocument,
          accountComparisonByDocument,
          reviewTasksByDocument,
          latestReviewDecisions,
        ),
      ]),
    ) as Record<string, DocumentRefreshComparisonKey>;

    if (previousWorkspacePacketIdRef.current !== workspace.packet.packet_id) {
      previousWorkspacePacketIdRef.current = workspace.packet.packet_id;
      previousDocumentRefreshKeysRef.current = currentRefreshKeys;
      setDocumentRefreshDeltasByDocumentId({});
      return;
    }

    const nextRefreshDeltas = Object.fromEntries(
      workspace.documents.flatMap((document) => {
        const previousKeys = previousDocumentRefreshKeysRef.current[document.document_id];
        const currentKeys = currentRefreshKeys[document.document_id];
        const refreshDelta: DocumentRefreshDelta = {
          hasAccountChange:
            Boolean(previousKeys) && previousKeys.accountKey !== currentKeys.accountKey,
          accountDetail:
            previousKeys && previousKeys.accountKey !== currentKeys.accountKey
              ? buildRefreshDeltaDetail(
                  previousKeys.accountSummary,
                  currentKeys.accountSummary,
                )
              : undefined,
          hasAttentionChange:
            Boolean(previousKeys) && previousKeys.attentionKey !== currentKeys.attentionKey,
          attentionDetail:
            previousKeys && previousKeys.attentionKey !== currentKeys.attentionKey
              ? buildRefreshDeltaDetail(
                  previousKeys.attentionSummary,
                  currentKeys.attentionSummary,
                )
              : undefined,
          hasContractChange:
            Boolean(previousKeys) && previousKeys.contractKey !== currentKeys.contractKey,
          contractDetail:
            previousKeys && previousKeys.contractKey !== currentKeys.contractKey
              ? buildRefreshDeltaDetail(
                  previousKeys.contractSummary,
                  currentKeys.contractSummary,
                )
              : undefined,
          hasExtractionChange:
            Boolean(previousKeys) && previousKeys.extractionKey !== currentKeys.extractionKey,
          extractionDetail:
            previousKeys && previousKeys.extractionKey !== currentKeys.extractionKey
              ? buildRefreshDeltaDetail(
                  previousKeys.extractionSummary,
                  currentKeys.extractionSummary,
                )
              : undefined,
          hasOcrChange:
            Boolean(previousKeys) && previousKeys.ocrKey !== currentKeys.ocrKey,
          ocrDetail:
            previousKeys && previousKeys.ocrKey !== currentKeys.ocrKey
              ? buildRefreshDeltaDetail(
                  previousKeys.ocrSummary,
                  currentKeys.ocrSummary,
                )
              : undefined,
          hasProcessingChange:
            Boolean(previousKeys) && previousKeys.processingKey !== currentKeys.processingKey,
          processingDetail:
            previousKeys && previousKeys.processingKey !== currentKeys.processingKey
              ? buildRefreshDeltaDetail(
                  previousKeys.processingSummary,
                  currentKeys.processingSummary,
                )
              : undefined,
          hasRecommendationChange:
            Boolean(previousKeys) &&
            previousKeys.recommendationKey !== currentKeys.recommendationKey,
          recommendationDetail:
            previousKeys &&
            previousKeys.recommendationKey !== currentKeys.recommendationKey
              ? buildRefreshDeltaDetail(
                  previousKeys.recommendationSummary,
                  currentKeys.recommendationSummary,
                )
              : undefined,
          hasReviewChange:
            Boolean(previousKeys) && previousKeys.reviewKey !== currentKeys.reviewKey,
          reviewDetail:
            previousKeys && previousKeys.reviewKey !== currentKeys.reviewKey
              ? buildRefreshDeltaDetail(
                  previousKeys.reviewSummary,
                  currentKeys.reviewSummary,
                )
              : undefined,
        };

        if (
          !refreshDelta.hasAccountChange &&
          !refreshDelta.hasAttentionChange &&
          !refreshDelta.hasContractChange &&
          !refreshDelta.hasExtractionChange &&
          !refreshDelta.hasOcrChange &&
          !refreshDelta.hasProcessingChange &&
          !refreshDelta.hasRecommendationChange &&
          !refreshDelta.hasReviewChange
        ) {
          return [];
        }

        return [[document.document_id, refreshDelta]];
      }),
    ) as Record<string, DocumentRefreshDelta>;

    previousDocumentRefreshKeysRef.current = currentRefreshKeys;
    setDocumentRefreshDeltasByDocumentId(nextRefreshDeltas);
  }, [workspace]);

  const latestClassifications = getLatestRecordByDocument(
    workspace?.classification_results ?? [],
  );
  const latestAccountMatches = getLatestRecordByDocument(
    workspace?.account_match_runs ?? [],
  );
  const latestExtractions = getLatestRecordByDocument(
    workspace?.extraction_results ?? [],
  );
  const latestOcrResults = getLatestRecordByDocument(workspace?.ocr_results ?? []);
  const latestRecommendations = getLatestOptionalDocumentRecord(
    workspace?.recommendation_results ?? [],
  );
  const latestReviewDecisions = getLatestReviewDecisionsByTask(
    workspace?.review_decisions ?? [],
  );
  const latestPacketEventsByDocument = getLatestPacketEventsByDocument(
    workspace?.packet_events ?? [],
  );
  const latestJobsByDocument = getLatestJobsByDocument(
    workspace?.processing_jobs ?? [],
  );
  const classificationLookup = buildClassificationLookup(
    operatorContracts?.classification_definitions ?? [],
  );
  const documentTypeLookup = buildDocumentTypeLookup(
    operatorContracts?.document_type_definitions ?? [],
  );
  const promptProfilesById = new Map(
    (operatorContracts?.prompt_profiles ?? []).map((promptProfile) => [
      promptProfile.prompt_profile_id,
      promptProfile,
    ]),
  );
  const contractStatusByDocument = new Map(
    (workspace?.documents ?? []).map((document) => [
      document.document_id,
      buildDocumentContractStatus(document, {
        classificationLookup,
        documentTypeLookup,
        latestClassification: latestClassifications.get(document.document_id),
        latestExtraction: latestExtractions.get(document.document_id),
        promptProfilesById,
      }),
    ]),
  );
  const accountComparisonByDocument = new Map(
    (workspace ? buildAccountComparisonRows(workspace) : []).map((row) => [
      row.document.document_id,
      row,
    ]),
  );
  const documentsById = new Map(
    (workspace?.documents ?? []).map((document) => [document.document_id, document]),
  );
  const reviewTasksById = new Map(
    (workspace?.review_tasks ?? []).map((reviewTask) => [reviewTask.review_task_id, reviewTask]),
  );
  const reviewTasksByDocument = new Map(
    (workspace?.review_tasks ?? []).map((reviewTask) => [reviewTask.document_id, reviewTask]),
  );
  const documentsWithoutReviewTasks = (workspace?.documents ?? []).filter(
    (document) => !reviewTasksByDocument.has(document.document_id),
  );
  const auditEventCountByDocument = new Map<string, number>();
  for (const auditEvent of workspace?.audit_events ?? []) {
    if (!auditEvent.document_id) {
      continue;
    }

    auditEventCountByDocument.set(
      auditEvent.document_id,
      (auditEventCountByDocument.get(auditEvent.document_id) ?? 0) + 1,
    );
  }
  const operatorNoteCountByDocument = new Map<string, number>();
  for (const operatorNote of workspace?.operator_notes ?? []) {
    if (!operatorNote.document_id) {
      continue;
    }

    operatorNoteCountByDocument.set(
      operatorNote.document_id,
      (operatorNoteCountByDocument.get(operatorNote.document_id) ?? 0) + 1,
    );
  }
  const auditEventsByReviewTaskId = new Map<string, AuditEventRecord[]>();
  for (const auditEvent of workspace?.audit_events ?? []) {
    if (!auditEvent.review_task_id) {
      continue;
    }

    const currentEvents = auditEventsByReviewTaskId.get(auditEvent.review_task_id) ?? [];
    currentEvents.push(auditEvent);
    auditEventsByReviewTaskId.set(auditEvent.review_task_id, currentEvents);
  }
  const operatorNotesByReviewTaskId = new Map<string, OperatorNoteRecord[]>();
  for (const operatorNote of workspace?.operator_notes ?? []) {
    if (!operatorNote.review_task_id) {
      continue;
    }

    const currentNotes =
      operatorNotesByReviewTaskId.get(operatorNote.review_task_id) ?? [];
    currentNotes.push(operatorNote);
    operatorNotesByReviewTaskId.set(operatorNote.review_task_id, currentNotes);
  }

  const buildDocumentState = (
    documentId: string,
  ): DocumentWorkspaceState | undefined => {
    const latestExtraction = latestExtractions.get(documentId);
    const reviewTask = reviewTasksByDocument.get(documentId);

    return {
      accountComparison: accountComparisonByDocument.get(documentId),
      auditEventCount: auditEventCountByDocument.get(documentId) ?? 0,
      contractStatus: contractStatusByDocument.get(documentId),
      extractionReviewEditMetadata: getExtractionReviewEditMetadata(latestExtraction),
      latestExtraction,
      latestJob: latestJobsByDocument.get(documentId),
      latestOcr: latestOcrResults.get(documentId),
      latestPacketEvent: latestPacketEventsByDocument.get(documentId),
      latestRecommendation: latestRecommendations.get(documentId),
      operatorNoteCount: operatorNoteCountByDocument.get(documentId) ?? 0,
      refreshDelta: documentRefreshDeltasByDocumentId[documentId],
      reviewDecision: reviewTask
        ? latestReviewDecisions.get(reviewTask.review_task_id)
        : undefined,
      reviewTask,
    };
  };
  const selectedViewerDocument =
    workspace?.documents.find(
      (document) => document.document_id === selectedViewerDocumentId,
    ) || workspace?.documents[0];

  const selectViewerDocument = (
    documentId: string,
    options?: {
      preferredFieldName?: string | null;
      returnTarget?: ReviewViewerReturnTarget | null;
      switchToViewer?: boolean;
    },
  ) => {
    const preferredFieldName = options?.preferredFieldName || null;
    const extractedFields = getExtractedFields(latestExtractions.get(documentId));
    const resolvedFieldKey = resolveViewerFieldKey(
      latestExtractions.get(documentId),
      preferredFieldName,
    );

    setSelectedViewerDocumentId(documentId);
    setSelectedViewerFieldKey(resolvedFieldKey);
    setViewerReturnTarget(options?.returnTarget ?? null);
    setSelectedViewerFieldNameHint(
      preferredFieldName &&
        !extractedFields.some(
          (field) => normalizeLookupKey(field.name) === normalizeLookupKey(preferredFieldName),
        )
        ? preferredFieldName
        : null,
    );

    if (options?.switchToViewer) {
      selectWorkspaceTab("viewer");
    }
  };

  const selectWorkspaceTab = (tabId: WorkspaceTabId) => {
    setActiveTab(tabId);
    onSelectTab?.(tabId);
  };

  useEffect(() => {
    if (activeTab !== "review" || !pendingReviewFocusTarget) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      const taskElement = document.querySelector<HTMLElement>(
        `[data-review-task-id="${pendingReviewFocusTarget.reviewTaskId}"]`,
      );
      const fieldElement =
        pendingReviewFocusTarget.focusFieldName && taskElement
          ? Array.from(
              taskElement.querySelectorAll<HTMLInputElement>(
                "[data-review-field-name]",
              ),
            ).find(
              (element) =>
                normalizeLookupKey(element.dataset.reviewFieldName) ===
                normalizeLookupKey(pendingReviewFocusTarget.focusFieldName),
            ) || null
          : null;
      const focusTarget = fieldElement || taskElement;

      if (typeof focusTarget?.scrollIntoView === "function") {
        focusTarget.scrollIntoView({ block: "center" });
      }
      focusTarget?.focus();
      setPendingReviewFocusTarget(null);
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [activeTab, pendingReviewFocusTarget]);

  const returnToViewerOrigin = () => {
    if (!viewerReturnTarget) {
      return;
    }

    setPendingReviewFocusTarget(viewerReturnTarget);
    selectWorkspaceTab("review");
  };

  const renderActiveTab = () => {
    if (!workspace) {
      return renderListFallback(
        selectedPacketSummary
          ? `Select refresh to load the packet workspace for ${selectedPacketSummary.packet_name}.`
          : "Select a packet row to open the workspace inspector.",
      );
    }

    if (activeTab === "overview") {
      const selectedDocumentLabel =
        selectedPacketSummary?.primary_file_name ||
        workspace.documents[0]?.file_name ||
        "No primary document";
      const issuerLabel =
        selectedPacketSummary?.primary_issuer_name ||
        selectedPacketSummary?.primary_issuer_category ||
        workspace.documents[0]?.issuer_name ||
        "No issuer captured";

      return (
        <div className="workspace-stack-grid">
          <SurfacePanel>
            <SectionHeading
              description="Packet posture, workload volume, and the current primary selection at a glance."
              title="Overview summary"
            />
            <div className="workspace-card-grid">
              <SurfaceCard>
                <StatusBadge tone="accent">Packet</StatusBadge>
                <h3>{workspace.packet.packet_name}</h3>
                <p className="workspace-copy">
                  {toLabel(workspace.packet.source)} · {toLabel(workspace.packet.status)}
                </p>
                <dl className="detail-list compact-detail-list">
                  <div>
                    <dt>Submitted by</dt>
                    <dd>{workspace.packet.submitted_by || "Unknown"}</dd>
                  </div>
                  <div>
                    <dt>Received</dt>
                    <dd>{formatDateTime(workspace.packet.received_at_utc)}</dd>
                  </div>
                </dl>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone="neutral">Counts</StatusBadge>
                <h3>{workspace.documents.length} documents</h3>
                <p className="workspace-copy">
                  {workspace.review_tasks.length} review tasks · {workspace.processing_jobs.length} processing jobs
                </p>
                <p className="workspace-copy">
                  {workspace.operator_notes.length} notes · {workspace.audit_events.length} audit events
                </p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone="accent">Recommendation</StatusBadge>
                <h3>{workspace.recommendation_results.length} results</h3>
                <p className="workspace-copy">
                  {workspace.recommendation_runs.length} runs are stored on this packet.
                </p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone="success">Selection</StatusBadge>
                <h3>{selectedDocumentLabel}</h3>
                <p className="workspace-copy">{issuerLabel}</p>
              </SurfaceCard>
            </div>
          </SurfacePanel>

          <SurfacePanel>
            <SectionHeading
              description="Document-level summaries currently attached to the selected packet workspace."
              title="Document summaries"
            />
            <div className="workspace-card-grid">
              {workspace.documents.map((document) =>
                renderDocumentSummary(document, buildDocumentState(document.document_id), {
                  isExpanded: Boolean(
                    expandedDocumentDetailsByDocumentId[document.document_id],
                  ),
                  onToggleExpanded: () => {
                    toggleDocumentDetails(document.document_id);
                  },
                }),
              )}
            </div>
          </SurfacePanel>
        </div>
      );
    }

    if (activeTab === "intake") {
      const archiveParentDocuments = workspace.documents.filter(
        (document) => document.archive_preflight.is_archive,
      );
      const archiveVisibleDocuments = workspace.documents.filter(
        (document) =>
          document.archive_preflight.is_archive ||
          Boolean(document.lineage?.archive_member_path),
      );
      const archivedChildDocuments = workspace.documents.filter((document) =>
        Boolean(document.lineage?.parent_document_id),
      );
      const deepestArchiveDepth = archivedChildDocuments.reduce(
        (maxDepth, document) =>
          Math.max(maxDepth, document.lineage?.archive_depth ?? 0),
        0,
      );
      const totalArchiveEntries = archiveParentDocuments.reduce(
        (entryCount, document) =>
          entryCount + document.archive_preflight.entry_count,
        0,
      );
      const deadLetterDocuments = workspace.documents.filter((document) =>
        ["failed", "quarantined", "blocked"].includes(document.status),
      );
      const attentionJobs = getAttentionJobs(workspace.processing_jobs).slice(0, 6);
      const latestJobsByDocument = getLatestJobsByDocument(workspace.processing_jobs);
      const replayState = resolveIntakeReplayState(workspace);
      const intakeEvents = [...workspace.packet_events]
        .sort(
          (left, right) =>
            toTimestamp(right.created_at_utc) - toTimestamp(left.created_at_utc),
        )
        .slice(0, 8);

      return (
        <div className="workspace-stack-grid">
          {intakeActionSuccessMessage ? (
            <p className="status-banner status-success">{intakeActionSuccessMessage}</p>
          ) : null}

          {intakeActionErrorMessage ? (
            <p className="status-banner status-error">{intakeActionErrorMessage}</p>
          ) : null}

          <SurfacePanel>
            <SectionHeading
              description="Archive posture, replay readiness, and blocked-work visibility for the current packet."
              title="Intake summary"
            />
            <div className="workspace-card-grid">
              <SurfaceCard>
                <StatusBadge tone="accent">Packet source</StatusBadge>
                <h3>{toLabel(workspace.packet.source)}</h3>
                <p className="workspace-copy">
                  {workspace.packet.source_uri || workspace.packet.packet_name}
                </p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone="neutral">Archive parents</StatusBadge>
                <h3>{archiveParentDocuments.length}</h3>
                <p className="workspace-copy">
                  {formatCount(totalArchiveEntries, "archive entry")} discovered across packet-level archives.
                </p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone="accent">Archive descendants</StatusBadge>
                <h3>{archivedChildDocuments.length}</h3>
                <p className="workspace-copy">
                  Deepest expanded lineage depth is {deepestArchiveDepth}.
                </p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone={deadLetterDocuments.length > 0 ? "warning" : "success"}>
                  Dead-letter visibility
                </StatusBadge>
                <h3>{deadLetterDocuments.length}</h3>
                <p className="workspace-copy">
                  {formatCount(attentionJobs.length, "attention job")} currently need intake intervention.
                </p>
              </SurfaceCard>
            </div>
          </SurfacePanel>

          <SurfacePanel>
            <SectionHeading
              description="Replay decisions and packet lineage stay in one place so intake triage remains packet-first."
              title="Replay and ingress controls"
            />
            <div className="workspace-card-grid">
              <SurfaceCard>
                <div className="queue-card-header">
                  <div className="queue-card-heading">
                    <StatusBadge tone={getPacketStatusTone(workspace.packet.status)}>
                      Replay
                    </StatusBadge>
                    <h3>{toLabel(workspace.packet.status)}</h3>
                  </div>
                  <StatusBadge tone={replayState.disabledReason ? "warning" : "accent"}>
                    {replayState.buttonLabel}
                  </StatusBadge>
                </div>
                <p className="workspace-copy">{replayState.description}</p>
                <dl className="detail-list compact-detail-list">
                  <div>
                    <dt>Submitted by</dt>
                    <dd>{workspace.packet.submitted_by || "Protected admin session"}</dd>
                  </div>
                  <div>
                    <dt>Received</dt>
                    <dd>{formatDateTime(workspace.packet.received_at_utc)}</dd>
                  </div>
                  <div>
                    <dt>Fingerprint</dt>
                    <dd>{workspace.packet.packet_fingerprint || "Not captured"}</dd>
                  </div>
                  <div>
                    <dt>Duplicate signals</dt>
                    <dd>{summarizeEventPayload(workspace.packet.duplicate_detection)}</dd>
                  </div>
                </dl>
                {workspace.packet.packet_tags.length > 0 ? (
                  <ul className="chip-list stack-chip-list">
                    {workspace.packet.packet_tags.map((tag) => (
                      <li className="match-pill" key={tag}>
                        {tag}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {replayState.disabledReason ? (
                  <p className="workspace-caption">{replayState.disabledReason}</p>
                ) : null}
                <div className="workspace-action-buttons">
                  <button
                    disabled={
                      isReplayingPacket ||
                      Boolean(replayState.disabledReason) ||
                      !onReplayPacket
                    }
                    onClick={() => {
                      onReplayPacket?.();
                    }}
                    type="button"
                  >
                    {isReplayingPacket ? "Replaying..." : replayState.buttonLabel}
                  </button>
                </div>
              </SurfaceCard>

              <SurfaceCard>
                <StatusBadge tone="neutral">Source lineage</StatusBadge>
                <h3>{workspace.packet.source_uri || "Source URI not captured"}</h3>
                <p className="workspace-copy">
                  Intake lineage, archive ancestry, and packet-level source tags are exposed here so operators can triage replay without leaving the workspace.
                </p>
                {workspace.documents[0]?.source_tags.length ? (
                  <ul className="chip-list stack-chip-list">
                    {workspace.documents[0].source_tags.map((tag) => (
                      <li className="match-pill" key={tag}>
                        {tag}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </SurfaceCard>
            </div>
          </SurfacePanel>

          {archiveVisibleDocuments.length > 0 ? (
            <SurfacePanel>
              <SectionHeading
                description="Archive parents and expanded children stay visible here so intake lineage can be inspected without leaving the packet workspace."
                title="Archive visibility"
              />
              <div className="workspace-card-grid">
                {archiveVisibleDocuments.map((document) => (
                  <SurfaceCard key={document.document_id}>
                    <div className="queue-card-header">
                      <div className="queue-card-heading">
                        <span className="queue-card-label">
                          {document.archive_preflight.is_archive
                            ? "Archive parent"
                            : "Archive child"}
                        </span>
                        <h3>{document.file_name}</h3>
                      </div>
                      <span className="workspace-inline-chip">{toLabel(document.status)}</span>
                    </div>
                    <dl className="detail-list compact-detail-list">
                      <div>
                        <dt>Archive format</dt>
                        <dd>{document.archive_preflight.archive_format || "Not an archive"}</dd>
                      </div>
                      <div>
                        <dt>Disposition</dt>
                        <dd>{toLabel(document.archive_preflight.disposition)}</dd>
                      </div>
                      <div>
                        <dt>Member path</dt>
                        <dd>{document.lineage?.archive_member_path || "Packet root"}</dd>
                      </div>
                      <div>
                        <dt>Parent document</dt>
                        <dd>{document.lineage?.parent_document_id || "Packet root"}</dd>
                      </div>
                    </dl>
                    <p className="workspace-copy">
                      {document.archive_preflight.is_archive
                        ? `${formatCount(document.archive_preflight.entry_count, "entry")} inspected with ${formatCount(document.archive_preflight.nested_archive_count, "nested archive")}.`
                        : `Expanded from ${document.lineage?.archive_member_path || "the source archive"} at depth ${document.lineage?.archive_depth ?? 0}.`}
                    </p>
                  </SurfaceCard>
                ))}
              </div>
            </SurfacePanel>
          ) : null}

          {deadLetterDocuments.length > 0 || attentionJobs.length > 0 ? (
            <SurfacePanel>
              <SectionHeading
                description="Blocked documents and attention jobs stay grouped here so operators can triage intake failures alongside the latest processing context."
                title="Dead-letter and blocked work"
              />
              <div className="workspace-card-grid">
                {deadLetterDocuments.map((document) => {
                  const latestJob = latestJobsByDocument.get(document.document_id);

                  return (
                    <SurfaceCard key={document.document_id}>
                      <div className="queue-card-header">
                        <div className="queue-card-heading">
                          <span className="queue-card-label">Attention</span>
                          <h3>{document.file_name}</h3>
                        </div>
                        <span className="workspace-inline-chip">{toLabel(document.status)}</span>
                      </div>
                      <p className="workspace-copy">
                        {latestJob?.error_message || document.source_summary || "No intake summary is stored for this blocked document yet."}
                      </p>
                      <dl className="detail-list compact-detail-list">
                        <div>
                          <dt>Latest stage</dt>
                          <dd>{latestJob ? toLabel(latestJob.stage_name) : "Not captured"}</dd>
                        </div>
                        <div>
                          <dt>Latest job state</dt>
                          <dd>{latestJob ? toLabel(latestJob.status) : "Not captured"}</dd>
                        </div>
                        <div>
                          <dt>Updated</dt>
                          <dd>{formatDateTime(latestJob?.updated_at_utc || document.updated_at_utc)}</dd>
                        </div>
                      </dl>
                    </SurfaceCard>
                  );
                })}
                {attentionJobs.map((job) => renderProcessingJob(job))}
              </div>
            </SurfacePanel>
          ) : null}

          {intakeEvents.length > 0 ? (
            <SurfacePanel>
              <SectionHeading
                description="Ingest and archive activity remains visible as a packet-first timeline instead of a detached event list."
                title="Ingest and archive events"
              />
              <div className="timeline-list">
                {intakeEvents.map((packetEvent) => (
                  <SurfaceTimelineItem
                    badge={
                      <span className="workspace-inline-chip">
                        {formatDateTime(packetEvent.created_at_utc)}
                      </span>
                    }
                    description={
                      packetEvent.document_id
                        ? `Document ${packetEvent.document_id} · ${summarizeEventPayload(packetEvent.event_payload)}`
                        : summarizeEventPayload(packetEvent.event_payload)
                    }
                    eyebrow="Packet event"
                    key={packetEvent.event_id}
                    markerState={getEventMarkerState(packetEvent)}
                    title={packetEvent.event_type}
                  />
                ))}
              </div>
            </SurfacePanel>
          ) : null}
        </div>
      );
    }

    if (activeTab === "documents") {
      return workspace.documents.length > 0 ? (
        <div className="workspace-card-grid">
          {workspace.documents.map((document) =>
            renderDocumentSummary(document, buildDocumentState(document.document_id), {
              isExpanded: Boolean(
                expandedDocumentDetailsByDocumentId[document.document_id],
              ),
              onToggleExpanded: () => {
                toggleDocumentDetails(document.document_id);
              },
            }),
          )}
        </div>
      ) : (
        renderListFallback("No packet documents are stored yet.")
      );
    }

    if (activeTab === "viewer") {
      if (!selectedViewerDocument) {
        return renderListFallback(
          "No packet documents are available for protected preview yet.",
        );
      }

      const documentAssets = workspace.document_assets.filter(
        (asset) => asset.document_id === selectedViewerDocument.document_id,
      );
      const latestClassification = latestClassifications.get(
        selectedViewerDocument.document_id,
      );
      const latestExtraction = latestExtractions.get(
        selectedViewerDocument.document_id,
      );
      const latestOcr = latestOcrResults.get(selectedViewerDocument.document_id);
      const previewUrl = buildPacketDocumentContentUrl(
        workspace.packet.packet_id,
        selectedViewerDocument.document_id,
        selectedViewerDocument.updated_at_utc,
      );
      const previewMode = getPreviewMode(selectedViewerDocument.content_type);
      const textPreview = truncateText(
        latestOcr?.text_excerpt || selectedViewerDocument.document_text,
        1800,
      );
      const extractedFields = getExtractedFields(latestExtraction);
      const requestedMissingFieldName = selectedViewerFieldNameHint
        ? toLabel(selectedViewerFieldNameHint)
        : null;
      const viewerOriginTask = viewerReturnTarget
        ? reviewTasksById.get(viewerReturnTarget.reviewTaskId) ?? null
        : null;
      const viewerOriginTaskLabel = viewerOriginTask
        ? documentsById.get(viewerOriginTask.document_id)?.file_name ||
          viewerOriginTask.document_id
        : selectedViewerDocument.file_name;
      const viewerOriginFieldLabel = requestedMissingFieldName
        ? requestedMissingFieldName
        : viewerReturnTarget?.focusFieldName
          ? toLabel(viewerReturnTarget.focusFieldName)
          : null;
      const highlightedField = requestedMissingFieldName
        ? null
        : extractedFields.find(
            (field) => buildExtractedFieldKey(field) === selectedViewerFieldKey,
          ) || extractedFields[0] || null;
      const highlightedTextPreview = buildHighlightedTextPreview(
        textPreview,
        highlightedField?.value,
      );
      const highlightedFieldStatus = requestedMissingFieldName
        ? `${requestedMissingFieldName} is required by the managed contract but missing from the extracted fields. Inspect the OCR evidence here, then return to Review to save the missing value.`
        : highlightedField
          ? highlightedTextPreview.matchCount > 0
            ? `Highlighting ${highlightedField.name} in the OCR excerpt.`
            : `${highlightedField.name} is selected, but its value is not visible in the stored OCR excerpt.`
          : "Select an extracted field to highlight its value in the OCR evidence below.";

      return (
        <div className="workspace-viewer-layout">
          <SurfacePanel as="section" className="workspace-viewer-rail">
            <SectionHeading
              description="Choose a document to load the protected preview and evidence panel."
              title="Packet documents"
            />
            <div className="workspace-viewer-document-list">
              {workspace.documents.map((document) => {
                const isSelected = document.document_id === selectedViewerDocument.document_id;
                const assetCount = workspace.document_assets.filter(
                  (asset) => asset.document_id === document.document_id,
                ).length;

                return (
                  <button
                    className={
                      isSelected
                        ? "workspace-viewer-document-button workspace-viewer-document-button-active"
                        : "workspace-viewer-document-button"
                    }
                    key={document.document_id}
                    onClick={() => {
                      selectViewerDocument(document.document_id);
                    }}
                    type="button"
                  >
                    <span className="queue-card-label">{toLabel(document.status)}</span>
                    <strong>{document.file_name}</strong>
                    <span>{toLabel(document.content_type)}</span>
                    <small>
                      {formatCount(assetCount, "asset")} · {toLabel(document.source)}
                    </small>
                  </button>
                );
              })}
            </div>
          </SurfacePanel>

          <section className="workspace-viewer-preview-column">
            <SurfaceCard className="workspace-viewer-preview-card">
              <div className="section-heading section-heading-row compact-section-heading">
                <div>
                  <span className="queue-card-label">Protected preview</span>
                  <h3>{selectedViewerDocument.file_name}</h3>
                  <p>
                    {toLabel(selectedViewerDocument.content_type)} · received {formatDateTime(selectedViewerDocument.received_at_utc)}
                  </p>
                  {viewerReturnTarget ? (
                    <p className="workspace-caption">
                      Opened from review task for {viewerOriginTaskLabel}
                      {viewerOriginFieldLabel
                        ? ` › Missing field: ${viewerOriginFieldLabel}`
                        : ""}
                    </p>
                  ) : null}
                </div>
                <a
                  className="ghost-button workspace-viewer-open-link"
                  href={previewUrl}
                  rel="noreferrer"
                  target="_blank"
                >
                  Open file
                </a>
              </div>

              {viewerReturnTarget ? (
                <div className="workspace-review-support-actions">
                  <button
                    className="ghost-button"
                    onClick={returnToViewerOrigin}
                    type="button"
                  >
                    Return to {selectedViewerDocument.file_name} review task
                  </button>
                </div>
              ) : null}

              {previewMode === "pdf" ? (
                <iframe
                  className="workspace-viewer-frame"
                  src={previewUrl}
                  title={`Protected preview for ${selectedViewerDocument.file_name}`}
                />
              ) : null}

              {previewMode === "image" ? (
                <img
                  alt={selectedViewerDocument.file_name}
                  className="workspace-viewer-image"
                  src={previewUrl}
                />
              ) : null}

              {previewMode === "download" ? (
                <div className="status-panel workspace-status-panel">
                  Inline preview is currently supported for PDFs and images. Use Open file to inspect this document in a protected browser tab.
                </div>
              ) : null}
            </SurfaceCard>
          </section>

          <div className="workspace-stack-grid">
            <SurfaceCard>
              <span className="queue-card-label">Document details</span>
              <h3>{selectedViewerDocument.issuer_name || "Issuer not captured"}</h3>
              <dl className="detail-list compact-detail-list">
                <div>
                  <dt>Status</dt>
                  <dd>{toLabel(selectedViewerDocument.status)}</dd>
                </div>
                <div>
                  <dt>Prompt profile</dt>
                  <dd>{toLabel(selectedViewerDocument.requested_prompt_profile_id)}</dd>
                </div>
                <div>
                  <dt>Classification</dt>
                  <dd>
                    {toLabel(
                      latestClassification?.document_type_id ||
                        latestClassification?.classification_id,
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Assets</dt>
                  <dd>{formatCount(documentAssets.length, "stored asset")}</dd>
                </div>
              </dl>
              {selectedViewerDocument.lineage?.archive_member_path ? (
                <p className="workspace-copy">
                  Archive lineage: {selectedViewerDocument.lineage.archive_member_path} at depth {selectedViewerDocument.lineage.archive_depth}.
                </p>
              ) : null}
              {selectedViewerDocument.source_tags.length > 0 ? (
                <ul className="chip-list stack-chip-list">
                  {selectedViewerDocument.source_tags.map((tag) => (
                    <li className="match-pill" key={tag}>
                      {tag}
                    </li>
                  ))}
                </ul>
              ) : null}
              {documentAssets.length > 0 ? (
                <div className="workspace-subcard-list">
                  {documentAssets.map((asset: DocumentAssetRecord) => (
                    <div className="workspace-subcard" key={asset.asset_id}>
                      <strong>{toLabel(asset.asset_role)}</strong>
                      <span>{asset.container_name}</span>
                      <small>{asset.blob_name}</small>
                    </div>
                  ))}
                </div>
              ) : null}
            </SurfaceCard>

            <SurfaceCard>
              <div className="mini-card-header">
                <div>
                  <span className="queue-card-label">OCR evidence</span>
                  <h3>{latestOcr ? latestOcr.provider : "No OCR result stored"}</h3>
                </div>
                {requestedMissingFieldName ? (
                  <StatusBadge tone="warning">Missing extracted field</StatusBadge>
                ) : highlightedField ? (
                  <StatusBadge
                    tone={highlightedTextPreview.matchCount > 0 ? "accent" : "neutral"}
                  >
                    {highlightedTextPreview.matchCount > 0
                      ? `${highlightedTextPreview.matchCount} highlight match${highlightedTextPreview.matchCount === 1 ? "" : "es"}`
                      : "No visible highlight"}
                  </StatusBadge>
                ) : null}
              </div>
              <p className="workspace-caption">{highlightedFieldStatus}</p>
              <p className="workspace-copy workspace-copy-prewrap">
                {highlightedTextPreview.content}
              </p>
              {latestOcr ? (
                <dl className="detail-list compact-detail-list">
                  <div>
                    <dt>Confidence</dt>
                    <dd>{formatConfidence(latestOcr.ocr_confidence)}</dd>
                  </div>
                  <div>
                    <dt>Pages</dt>
                    <dd>{latestOcr.page_count}</dd>
                  </div>
                </dl>
              ) : null}
              </SurfaceCard>

              <SurfaceCard>
              <span className="queue-card-label">Extraction evidence</span>
              <h3>{latestExtraction?.document_type || "No extracted type stored"}</h3>
              <p className="workspace-copy">
                {latestExtraction?.summary ||
                  selectedViewerDocument.source_summary ||
                  "No extraction summary or source summary is stored for this document yet."}
              </p>
              <dl className="detail-list compact-detail-list">
                <div>
                  <dt>Provider</dt>
                  <dd>{toLabel(latestExtraction?.provider)}</dd>
                </div>
                <div>
                  <dt>Stored</dt>
                  <dd>{formatDateTime(latestExtraction?.created_at_utc)}</dd>
                </div>
              </dl>
              {extractedFields.length > 0 ? (
                <>
                  <p className="workspace-caption">
                    Select a field to keep the OCR evidence and decision entry focused on the same stored value.
                  </p>
                  <div className="workspace-field-list">
                    {extractedFields.map((field) => {
                      const fieldKey = buildExtractedFieldKey(field);
                      const fieldMatchCount = countTextMatches(textPreview, field.value);
                      const isSelected = highlightedField
                        ? fieldKey === buildExtractedFieldKey(highlightedField)
                        : false;

                      return (
                        <button
                          className={
                            isSelected
                              ? "workspace-field-button workspace-field-button-active"
                              : "workspace-field-button"
                          }
                          key={fieldKey}
                          onClick={() => {
                            setSelectedViewerFieldNameHint(null);
                            setSelectedViewerFieldKey(fieldKey);
                          }}
                          type="button"
                        >
                          <small>{formatConfidence(field.confidence)}</small>
                          <strong>{field.name}</strong>
                          <span>{field.value}</span>
                          <span className="workspace-field-emphasis">
                            {fieldMatchCount > 0
                              ? `Visible in OCR excerpt (${fieldMatchCount} match${fieldMatchCount === 1 ? "" : "es"})`
                              : "Not visible in current OCR excerpt"}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </>
              ) : (
                <p className="workspace-copy">
                  No extracted fields are stored for this document yet.
                </p>
              )}
            </SurfaceCard>
          </div>
        </div>
      );
    }

    if (activeTab === "ocr") {
      return workspace.ocr_results.length > 0 ? (
        <div className="workspace-card-grid">
          {workspace.ocr_results.map((ocrResult) => renderOcrResult(ocrResult))}
        </div>
      ) : (
        renderListFallback("No OCR results are stored for the selected packet yet.")
      );
    }

    if (activeTab === "extraction") {
      return workspace.extraction_results.length > 0 ? (
        <div className="workspace-card-grid">
          {workspace.extraction_results.map((extractionResult) =>
            renderExtractionSummary(
              extractionResult,
              latestClassifications.get(extractionResult.document_id),
            ),
          )}
        </div>
      ) : (
        renderListFallback("No extraction results are stored for the selected packet yet.")
      );
    }

    if (activeTab === "rules_doctypes") {
      if (isOperatorContractsLoading && !operatorContracts) {
        return renderListFallback(
          "Loading managed classifications, doctypes, and prompt profiles...",
        );
      }

      if (!operatorContracts) {
        return renderListFallback(
          operatorContractsErrorMessage ||
            "Managed operator contracts have not been loaded yet.",
        );
      }

      const classificationLookup = buildClassificationLookup(
        operatorContracts.classification_definitions,
      );
      const documentTypeLookup = buildDocumentTypeLookup(
        operatorContracts.document_type_definitions,
      );
      const promptProfilesById = new Map(
        operatorContracts.prompt_profiles.map((promptProfile) => [
          promptProfile.prompt_profile_id,
          promptProfile,
        ]),
      );

      return (
        <div className="workspace-stack-grid">
          {operatorContractsErrorMessage ? (
            <p className="status-banner status-error">
              {operatorContractsErrorMessage}
            </p>
          ) : null}

          <SurfacePanel>
            <SectionHeading title="Managed contract summary" />
            <div className="workspace-card-grid">
              <SurfaceCard>
                <span className="queue-card-label">Classifications</span>
                <h3>{operatorContracts.classification_definitions.length}</h3>
                <p className="workspace-copy">Managed classification definitions loaded from SQL.</p>
              </SurfaceCard>
              <SurfaceCard>
                <span className="queue-card-label">Document types</span>
                <h3>{operatorContracts.document_type_definitions.length}</h3>
                <p className="workspace-copy">Document-type contracts with required field expectations.</p>
              </SurfaceCard>
              <SurfaceCard>
                <span className="queue-card-label">Prompt profiles</span>
                <h3>
                  {
                    operatorContracts.prompt_profiles.filter(
                      (promptProfile) => promptProfile.is_enabled,
                    ).length
                  }
                </h3>
                <p className="workspace-copy">Enabled prompt profiles currently available to taxonomy rules.</p>
              </SurfaceCard>
              <SurfaceCard>
                <span className="queue-card-label">Recommendation contract</span>
                <h3>{toLabel(operatorContracts.recommendation_contract.required_packet_status)}</h3>
                <p className="workspace-copy">
                  Required evidence: {operatorContracts.recommendation_contract.required_evidence_kinds.join(", ")}
                </p>
              </SurfaceCard>
            </div>
          </SurfacePanel>

          <SurfacePanel>
            <SectionHeading title="Managed classifications" />
            <div className="workspace-card-grid">
              {operatorContracts.classification_definitions.map((definition) => (
                <SurfaceCard key={definition.classification_id}>
                  <div className="queue-card-header">
                    <div className="queue-card-heading">
                      <span className="queue-card-label">Classification</span>
                      <h3>{definition.display_name}</h3>
                    </div>
                    <span className="workspace-inline-chip">
                      {definition.is_enabled ? "Enabled" : "Disabled"}
                    </span>
                  </div>
                  <p className="workspace-copy">
                    {definition.description || "No classification description is stored."}
                  </p>
                  <dl className="detail-list compact-detail-list">
                    <div>
                      <dt>Key</dt>
                      <dd>{definition.classification_key}</dd>
                    </div>
                    <div>
                      <dt>Issuer category</dt>
                      <dd>{toLabel(definition.issuer_category)}</dd>
                    </div>
                    <div>
                      <dt>Prompt profile</dt>
                      <dd>{definition.default_prompt_profile_id || "Not assigned"}</dd>
                    </div>
                    <div>
                      <dt>Document types</dt>
                      <dd>
                        {
                          operatorContracts.document_type_definitions.filter(
                            (documentType) =>
                              documentType.classification_id === definition.classification_id,
                          ).length
                        }
                      </dd>
                    </div>
                  </dl>
                </SurfaceCard>
              ))}
            </div>
          </SurfacePanel>

          <SurfacePanel>
            <SectionHeading title="Document types and required fields" />
            <div className="workspace-card-grid">
              {operatorContracts.document_type_definitions.map((definition) => (
                <SurfaceCard key={definition.document_type_id}>
                  <div className="queue-card-header">
                    <div className="queue-card-heading">
                      <span className="queue-card-label">Doctype</span>
                      <h3>{definition.display_name}</h3>
                    </div>
                    <span className="workspace-inline-chip">
                      {definition.is_enabled ? "Enabled" : "Disabled"}
                    </span>
                  </div>
                  <p className="workspace-copy">
                    {definition.description || "No doctype description is stored."}
                  </p>
                  <dl className="detail-list compact-detail-list">
                    <div>
                      <dt>Key</dt>
                      <dd>{definition.document_type_key}</dd>
                    </div>
                    <div>
                      <dt>Classification</dt>
                      <dd>
                        {definition.classification_id
                          ? classificationLookup.get(
                              normalizeLookupKey(definition.classification_id),
                            )?.display_name || definition.classification_id
                          : "Not scoped"}
                      </dd>
                    </div>
                    <div>
                      <dt>Prompt profile</dt>
                      <dd>{definition.default_prompt_profile_id || "Not assigned"}</dd>
                    </div>
                    <div>
                      <dt>Required fields</dt>
                      <dd>{definition.required_fields.length}</dd>
                    </div>
                  </dl>
                  {definition.required_fields.length > 0 ? (
                    <ul className="chip-list stack-chip-list">
                      {definition.required_fields.map((fieldName) => (
                        <li className="match-pill" key={fieldName}>
                          {fieldName}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </SurfaceCard>
              ))}
            </div>
          </SurfacePanel>

          <SurfacePanel>
            <SectionHeading title="Prompt profiles" />
            <div className="workspace-card-grid">
              {operatorContracts.prompt_profiles.map((promptProfile) => {
                const activeVersion = getActivePromptProfileVersion(
                  promptProfile.prompt_profile_id,
                  operatorContracts.prompt_profile_versions,
                );

                return (
                  <SurfaceCard key={promptProfile.prompt_profile_id}>
                    <div className="queue-card-header">
                      <div className="queue-card-heading">
                        <span className="queue-card-label">Prompt profile</span>
                        <h3>{promptProfile.display_name}</h3>
                      </div>
                      <span className="workspace-inline-chip">
                        {promptProfile.is_enabled ? "Enabled" : "Disabled"}
                      </span>
                    </div>
                    <p className="workspace-copy">
                      {promptProfile.description || "No prompt profile description is stored."}
                    </p>
                    <dl className="detail-list compact-detail-list">
                      <div>
                        <dt>Issuer category</dt>
                        <dd>{toLabel(promptProfile.issuer_category)}</dd>
                      </div>
                      <div>
                        <dt>Active version</dt>
                        <dd>
                          {activeVersion
                            ? `v${activeVersion.version_number}`
                            : "No version recorded"}
                        </dd>
                      </div>
                      <div>
                        <dt>Version count</dt>
                        <dd>
                          {
                            operatorContracts.prompt_profile_versions.filter(
                              (version) =>
                                version.prompt_profile_id === promptProfile.prompt_profile_id,
                            ).length
                          }
                        </dd>
                      </div>
                    </dl>
                    {activeVersion?.definition_payload ? (
                      <p className="workspace-caption">
                        {summarizeEventPayload(activeVersion.definition_payload)}
                      </p>
                    ) : null}
                  </SurfaceCard>
                );
              })}
            </div>
          </SurfacePanel>

          <SurfacePanel>
            <SectionHeading title="Packet evidence against contracts" />
            <div className="workspace-card-grid">
              {workspace.documents.map((document) => {
                const latestClassification = latestClassifications.get(document.document_id);
                const latestExtraction = latestExtractions.get(document.document_id);
                const classificationDefinition = classificationLookup.get(
                  normalizeLookupKey(getClassificationKey(latestClassification)),
                );
                const documentTypeDefinition = documentTypeLookup.get(
                  normalizeLookupKey(
                    getDocumentTypeKey(latestExtraction, latestClassification),
                  ),
                );
                const promptProfileId =
                  latestExtraction?.prompt_profile_id ||
                  latestClassification?.prompt_profile_id ||
                  document.requested_prompt_profile_id ||
                  classificationDefinition?.default_prompt_profile_id ||
                  documentTypeDefinition?.default_prompt_profile_id ||
                  null;
                const promptProfile = promptProfileId
                  ? promptProfilesById.get(promptProfileId)
                  : undefined;
                const missingRequiredFields = getRequiredFieldCoverage(
                  documentTypeDefinition,
                  latestExtraction,
                );

                return (
                  <SurfaceCard key={document.document_id}>
                    <div className="queue-card-header">
                      <div className="queue-card-heading">
                        <span className="queue-card-label">Packet evidence</span>
                        <h3>{document.file_name}</h3>
                      </div>
                      <span className="workspace-inline-chip">{toLabel(document.status)}</span>
                    </div>
                    <p className="workspace-copy">
                      {latestExtraction?.summary ||
                        document.source_summary ||
                        "No extraction summary is stored for this document yet."}
                    </p>
                    <dl className="detail-list compact-detail-list">
                      <div>
                        <dt>Classification</dt>
                        <dd>
                          {classificationDefinition?.display_name ||
                            getClassificationKey(latestClassification) ||
                            "Not classified"}
                        </dd>
                      </div>
                      <div>
                        <dt>Document type</dt>
                        <dd>
                          {documentTypeDefinition?.display_name ||
                            getDocumentTypeKey(latestExtraction, latestClassification) ||
                            "Not typed"}
                        </dd>
                      </div>
                      <div>
                        <dt>Prompt profile</dt>
                        <dd>{promptProfile?.display_name || promptProfileId || "Not assigned"}</dd>
                      </div>
                      <div>
                        <dt>Required fields missing</dt>
                        <dd>{missingRequiredFields.length}</dd>
                      </div>
                    </dl>
                    {missingRequiredFields.length > 0 ? (
                      <p className="workspace-caption">
                        Missing required fields: {missingRequiredFields.join(", ")}
                      </p>
                    ) : documentTypeDefinition?.required_fields.length ? (
                      <p className="workspace-caption">
                        All managed required fields are present in the current extraction payload.
                      </p>
                    ) : null}
                  </SurfaceCard>
                );
              })}
            </div>
          </SurfacePanel>

          <SurfacePanel>
            <SectionHeading title="Processing taxonomy" />
            <div className="workspace-card-grid">
              {operatorContracts.processing_taxonomy.stages.map((stage) => (
                <SurfaceCard key={stage.stage_name}>
                  <span className="queue-card-label">Stage</span>
                  <h3>{stage.display_name}</h3>
                  <p className="workspace-copy">{stage.description}</p>
                  <p className="workspace-caption">
                    Statuses: {stage.statuses.map((status) => toLabel(status)).join(", ")}
                  </p>
                </SurfaceCard>
              ))}
            </div>
          </SurfacePanel>
        </div>
      );
    }

    if (activeTab === "matching") {
      const accountRows = buildAccountComparisonRows(workspace);
      const overrideCount = accountRows.filter((row) => row.hasOverride).length;
      const resolvedCount = accountRows.filter((row) => row.finalAccountId).length;
      const awaitingCount = accountRows.filter(
        (row) => row.reviewTask?.status === "awaiting_review",
      ).length;
      const linkedAccountCount = new Set(
        accountRows
          .map((row) => row.finalAccountId || row.suggestedAccountId)
          .filter((accountId): accountId is string => Boolean(accountId)),
      ).size;

      return accountRows.length > 0 ? (
        <div className="workspace-stack-grid">
          <SurfacePanel>
            <SectionHeading title="Account resolution summary" />
            <div className="workspace-card-grid">
              <SurfaceCard>
                <span className="queue-card-label">Overrides</span>
                <h3>{overrideCount}</h3>
                <p className="workspace-copy">Documents where operator linkage diverged from the auto-selected account.</p>
              </SurfaceCard>
              <SurfaceCard>
                <span className="queue-card-label">Resolved linkages</span>
                <h3>{resolvedCount}</h3>
                <p className="workspace-copy">Documents with a packet-local selected account.</p>
              </SurfaceCard>
              <SurfaceCard>
                <span className="queue-card-label">Awaiting review</span>
                <h3>{awaitingCount}</h3>
                <p className="workspace-copy">Tasks still waiting on operator account confirmation.</p>
              </SurfaceCard>
              <SurfaceCard>
                <span className="queue-card-label">Linked accounts</span>
                <h3>{linkedAccountCount}</h3>
                <p className="workspace-copy">Distinct account ids referenced across this packet workspace.</p>
              </SurfaceCard>
            </div>
          </SurfacePanel>

          <SurfacePanel>
            <SectionHeading title="Override comparison and linkage history" />
            <div className="workspace-card-grid">
              {accountRows.map((row) => {
                const linkageHistory = buildAccountLinkageHistory(row);

                return (
                  <SurfaceCard key={row.document.document_id}>
                    <div className="queue-card-header">
                      <div className="queue-card-heading">
                        <span className="queue-card-label">
                          {row.hasOverride ? "Override" : "Auto linkage"}
                        </span>
                        <h3>{row.document.file_name}</h3>
                      </div>
                      <span className="workspace-inline-chip">
                        {row.finalAccountId || "Unresolved"}
                      </span>
                    </div>
                    <p className="workspace-copy">
                      {row.matchRun?.rationale ||
                        row.document.source_summary ||
                        "No account rationale is stored for this document yet."}
                    </p>
                    <dl className="detail-list compact-detail-list">
                      <div>
                        <dt>Suggested</dt>
                        <dd>{row.suggestedAccountId || "No auto-link stored"}</dd>
                      </div>
                      <div>
                        <dt>Task linkage</dt>
                        <dd>{row.taskAccountId || "No operator selection yet"}</dd>
                      </div>
                      <div>
                        <dt>Final linkage</dt>
                        <dd>{row.finalAccountId || "Pending"}</dd>
                      </div>
                      <div>
                        <dt>Owner</dt>
                        <dd>{row.reviewTask?.assigned_user_email || "Unassigned"}</dd>
                      </div>
                    </dl>
                    {row.matchRun?.candidates.length ? (
                      <div className="workspace-subcard-list">
                        {row.matchRun.candidates.map((candidate) => {
                          const candidateTags = [
                            candidate.account_id === row.suggestedAccountId
                              ? "Suggested"
                              : null,
                            candidate.account_id === row.taskAccountId
                              ? "Task"
                              : null,
                            candidate.account_id === row.finalAccountId
                              ? "Final"
                              : null,
                          ].filter((tag): tag is string => Boolean(tag));

                          return (
                            <div className="workspace-subcard" key={candidate.account_id}>
                              <strong>{candidate.account_id}</strong>
                              <span>
                                {candidate.account_number || candidate.debtor_name || "No account metadata"}
                              </span>
                              <small>
                                Score {Math.round(candidate.score)}
                                {candidateTags.length > 0 ? ` · ${candidateTags.join(" / ")}` : ""}
                              </small>
                            </div>
                          );
                        })}
                      </div>
                    ) : null}
                    {linkageHistory.length > 0 ? (
                      <div className="workspace-subcard-list">
                        {linkageHistory.map((entry) => (
                          <div className="workspace-subcard" key={`${row.document.document_id}:${entry.label}:${entry.timestamp}`}>
                            <strong>{entry.label}</strong>
                            <span>{entry.detail}</span>
                            <small>
                              {entry.actor ? `${entry.actor} · ` : ""}
                              {formatDateTime(entry.timestamp)}
                            </small>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </SurfaceCard>
                );
              })}
            </div>
          </SurfacePanel>

          <SurfacePanel>
            <SectionHeading title="Raw match runs" />
            <div className="workspace-card-grid">
              {workspace.account_match_runs.map((matchRun) => renderMatchRun(matchRun))}
            </div>
          </SurfacePanel>
        </div>
      ) : (
        renderListFallback("No account matching runs are stored for this packet yet.")
      );
    }

    if (activeTab === "review") {
      const decidedReviewTaskIds = new Set(
        workspace.review_decisions.map((reviewDecision) => reviewDecision.review_task_id),
      );
      const pendingReviewTaskCount = workspace.review_tasks.filter(
        (reviewTask) =>
          reviewTask.status === "awaiting_review" &&
          !decidedReviewTaskIds.has(reviewTask.review_task_id),
      ).length;
      const assignedReviewerCount = new Set(
        workspace.review_tasks
          .map((reviewTask) => reviewTask.assigned_user_email?.trim().toLowerCase())
          .filter((reviewerEmail): reviewerEmail is string => Boolean(reviewerEmail)),
      ).size;
      const documentsWithoutTaskCount = documentsWithoutReviewTasks.length;
      const stagedFieldEditCount = workspace.review_tasks.reduce(
        (totalCount, reviewTask) =>
          totalCount +
          getReviewFieldChanges(
            getExtractedFields(latestExtractions.get(reviewTask.document_id)),
            editedExtractedValuesByTaskId[reviewTask.review_task_id] || {},
          ).length,
        0,
      );

      return workspace.review_tasks.length > 0 ||
        workspace.review_decisions.length > 0 ||
        workspace.operator_notes.length > 0 ||
        documentsWithoutTaskCount > 0 ? (
        <div className="workspace-stack-grid">
          <SurfacePanel>
            <SectionHeading
              description="Current reviewer workload, recorded decisions, and operator-note activity for the packet workspace."
              title="Review summary"
            />
            <div className="workspace-card-grid">
              <SurfaceCard>
                <StatusBadge tone="warning">Pending tasks</StatusBadge>
                <h3>{pendingReviewTaskCount}</h3>
                <p className="workspace-copy">
                  Review tasks still waiting on an explicit operator decision.
                </p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone="accent">Decisions</StatusBadge>
                <h3>{workspace.review_decisions.length}</h3>
                <p className="workspace-copy">
                  Recorded approve or reject actions already stored for this packet.
                </p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone="neutral">Operator notes</StatusBadge>
                <h3>{workspace.operator_notes.length}</h3>
                <p className="workspace-copy">
                  Notes available to explain packet review context and follow-up actions.
                </p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone={assignedReviewerCount > 0 ? "success" : "warning"}>
                  Assigned reviewers
                </StatusBadge>
                <h3>{assignedReviewerCount}</h3>
                <p className="workspace-copy">
                  Distinct reviewers currently attached to the packet review workload.
                </p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone={stagedFieldEditCount > 0 ? "warning" : "neutral"}>
                  Staged field edits
                </StatusBadge>
                <h3>{stagedFieldEditCount}</h3>
                <p className="workspace-copy">
                  Inline extracted-value edits waiting to be saved through the dedicated extraction edit route.
                </p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone={documentsWithoutTaskCount > 0 ? "warning" : "neutral"}>
                  Missing tasks
                </StatusBadge>
                <h3>{documentsWithoutTaskCount}</h3>
                <p className="workspace-copy">
                  Packet documents that still need a manually authored review task.
                </p>
              </SurfaceCard>
            </div>
          </SurfacePanel>

          {documentsWithoutReviewTasks.length > 0 ? (
            <SurfacePanel>
              <SectionHeading
                description="Create packet-local review tasks for documents that do not yet have one."
                title="Create review tasks"
              />
              {createTaskErrorMessage ? (
                <p className="status-banner status-error workspace-inline-status">
                  {createTaskErrorMessage}
                </p>
              ) : null}
              {createTaskSuccessMessage ? (
                <p className="status-banner status-success workspace-inline-status">
                  {createTaskSuccessMessage}
                </p>
              ) : null}
              <div className="workspace-card-grid">
                {documentsWithoutReviewTasks.map((document) => {
                  const extractionResult = latestExtractions.get(document.document_id);
                  const extractedFields = getExtractedFields(extractionResult);
                  const suggestedAccountId = resolveDocumentSuggestedAccountId(
                    latestAccountMatches.get(document.document_id),
                    document,
                  );

                  return renderReviewTaskCreateCard(document, {
                    assignmentDraft:
                      reviewTaskCreateAssignmentDraftsByDocumentId[
                        document.document_id
                      ] || "",
                    extractedFields,
                    extractionSummary: extractionResult?.summary || null,
                    isCreateTaskSubmitting: isReviewTaskCreateSubmitting,
                    notesSummaryDraft:
                      reviewTaskCreateNotesByDocumentId[document.document_id] || "",
                    onAssignmentDraftChange: (value) => {
                      setReviewTaskCreateAssignmentDraftsByDocumentId(
                        (currentDrafts) => ({
                          ...currentDrafts,
                          [document.document_id]: value,
                        }),
                      );
                    },
                    onInspectDocument: (documentId, preferredFieldName) => {
                      selectViewerDocument(documentId, {
                        preferredFieldName,
                        switchToViewer: true,
                      });
                    },
                    onNotesSummaryChange: (value) => {
                      setReviewTaskCreateNotesByDocumentId((currentDrafts) => ({
                        ...currentDrafts,
                        [document.document_id]: value,
                      }));
                    },
                    onSelectedAccountIdChange: (value) => {
                      setReviewTaskCreateSelectedAccountsByDocumentId(
                        (currentAccounts) => ({
                          ...currentAccounts,
                          [document.document_id]: value,
                        }),
                      );
                    },
                    onSubmitReviewTaskCreate,
                    reviewerEmail,
                    selectedAccountId:
                      document.document_id in
                      reviewTaskCreateSelectedAccountsByDocumentId
                        ? reviewTaskCreateSelectedAccountsByDocumentId[
                            document.document_id
                          ]
                        : suggestedAccountId,
                    suggestedAccountId,
                  });
                })}
              </div>
            </SurfacePanel>
          ) : null}

          {workspace.review_tasks.length > 0 ? (
            <SurfacePanel>
              <SectionHeading
                description="Active review tasks, selected account overrides, and decision entry for packet documents."
                title="Review tasks"
              />
              <div className="workspace-card-grid">
                {workspace.review_tasks.map((reviewTask) => {
                  const editableFields = getExtractedFields(
                    latestExtractions.get(reviewTask.document_id),
                  );

                  return renderReviewTask(reviewTask, {
                    assignmentDraft:
                      reviewTaskAssignmentDraftsByTaskId[reviewTask.review_task_id] ??
                      reviewTask.assigned_user_email ??
                      "",
                    assignmentErrorMessage,
                    assignmentSuccessMessage,
                    auditEvents:
                      auditEventsByReviewTaskId.get(reviewTask.review_task_id) || [],
                    contractStatus: contractStatusByDocument.get(reviewTask.document_id),
                    decisionReasonCode:
                      reviewDecisionReasonCodesByTaskId[reviewTask.review_task_id] || "",
                    decisionErrorMessage,
                    decisionNote:
                      reviewNotesByTaskId[reviewTask.review_task_id] || "",
                    document: workspace.documents.find(
                      (document) => document.document_id === reviewTask.document_id,
                    ),
                    editableFields,
                    editedFieldValues:
                      editedExtractedValuesByTaskId[reviewTask.review_task_id] || {},
                    extractionEditErrorMessage,
                    extractionReviewEditMetadata: getExtractionReviewEditMetadata(
                      latestExtractions.get(reviewTask.document_id),
                    ),
                    extractionEditSuccessMessage,
                    fieldChanges: getReviewFieldChanges(
                      editableFields,
                      editedExtractedValuesByTaskId[reviewTask.review_task_id] || {},
                    ),
                    hasRecordedDecision: decidedReviewTaskIds.has(
                      reviewTask.review_task_id,
                    ),
                    isAssignmentSubmitting,
                    isExtractionEditSubmitting,
                    isDecisionSubmitting,
                    isNoteSubmitting,
                    noteDraft:
                      reviewTaskNoteDraftsByTaskId[reviewTask.review_task_id] || "",
                    noteErrorMessage,
                    noteSuccessMessage,
                    onEditedFieldValueChange: (fieldName, value) => {
                      const matchingField = editableFields.find(
                        (field) => field.name === fieldName,
                      );

                      setEditedExtractedValuesByTaskId((currentFieldValues) => {
                        const nextTaskFieldValues = {
                          ...(currentFieldValues[reviewTask.review_task_id] || {}),
                        };

                        if (matchingField && value === matchingField.value) {
                          delete nextTaskFieldValues[fieldName];
                        } else {
                          nextTaskFieldValues[fieldName] = value;
                        }

                        return {
                          ...currentFieldValues,
                          [reviewTask.review_task_id]: nextTaskFieldValues,
                        };
                      });
                    },
                    onInspectDocument: (documentId, preferredFieldName, returnTarget) => {
                      selectViewerDocument(documentId, {
                        preferredFieldName,
                        returnTarget,
                        switchToViewer: true,
                      });
                    },
                    onDecisionNoteChange: (value) => {
                      setReviewNotesByTaskId((currentNotes) => ({
                        ...currentNotes,
                        [reviewTask.review_task_id]: value,
                      }));
                    },
                    onDecisionReasonCodeChange: (value) => {
                      setReviewDecisionReasonCodesByTaskId((currentReasonCodes) => ({
                        ...currentReasonCodes,
                        [reviewTask.review_task_id]: value,
                      }));
                    },
                    onDecisionStatusChange: (value) => {
                      setReviewDecisionStatusByTaskId((currentStatuses) => ({
                        ...currentStatuses,
                        [reviewTask.review_task_id]: value,
                      }));
                    },
                    onAssignmentDraftChange: (value) => {
                      setReviewTaskAssignmentDraftsByTaskId((currentDrafts) => ({
                        ...currentDrafts,
                        [reviewTask.review_task_id]: value,
                      }));
                    },
                    onNoteDraftChange: (value) => {
                      setReviewTaskNoteDraftsByTaskId((currentDrafts) => ({
                        ...currentDrafts,
                        [reviewTask.review_task_id]: value,
                      }));
                    },
                    onResetEditedFieldValue: (fieldName) => {
                      setEditedExtractedValuesByTaskId((currentFieldValues) => {
                        const nextTaskFieldValues = {
                          ...(currentFieldValues[reviewTask.review_task_id] || {}),
                        };

                        delete nextTaskFieldValues[fieldName];

                        return {
                          ...currentFieldValues,
                          [reviewTask.review_task_id]: nextTaskFieldValues,
                        };
                      });
                    },
                    onSelectedAccountIdChange: (value) => {
                      setSelectedAccountIdsByTaskId((currentAccounts) => ({
                        ...currentAccounts,
                        [reviewTask.review_task_id]: value,
                      }));
                    },
                    onSubmitExtractionEdits,
                    onSubmitReviewAssignment,
                    onSubmitReviewNote,
                    onSubmitReviewDecision,
                    operatorNotes:
                      operatorNotesByReviewTaskId.get(reviewTask.review_task_id) || [],
                    reviewerEmail,
                    reviewDecision: latestReviewDecisions.get(reviewTask.review_task_id),
                    selectedDecisionStatus:
                      reviewDecisionStatusByTaskId[reviewTask.review_task_id] ||
                      "approved",
                    selectedAccountId:
                      selectedAccountIdsByTaskId[reviewTask.review_task_id] ||
                      resolveSuggestedAccountId(
                        reviewTask,
                        latestAccountMatches.get(reviewTask.document_id),
                        workspace.documents.find(
                          (document) => document.document_id === reviewTask.document_id,
                        ),
                      ),
                    suggestedAccountId: resolveSuggestedAccountId(
                      reviewTask,
                      latestAccountMatches.get(reviewTask.document_id),
                      workspace.documents.find(
                        (document) => document.document_id === reviewTask.document_id,
                      ),
                    ) || null,
                  });
                })}
              </div>
              </SurfacePanel>
          ) : null}
          {workspace.review_decisions.length > 0 ? (
              <SurfacePanel>
                <SectionHeading
                  description="Persisted review decisions already recorded against packet tasks."
                  title="Decisions"
                />
              <div className="workspace-card-grid">
                {workspace.review_decisions.map((reviewDecision) => renderReviewDecision(reviewDecision))}
              </div>
              </SurfacePanel>
          ) : null}
          {workspace.operator_notes.length > 0 ? (
              <SurfacePanel>
                <SectionHeading
                  description="Packet-level reviewer notes and private operator context captured during adjudication."
                  title="Operator notes"
                />
              <div className="workspace-card-grid">
                {workspace.operator_notes.map((note) => renderOperatorNote(note))}
              </div>
              </SurfacePanel>
          ) : null}
        </div>
      ) : (
        renderListFallback("No review tasks, decisions, or notes are stored for this packet yet.")
      );
    }

    if (activeTab === "pipeline") {
      if (workspace.processing_jobs.length === 0 && workspace.packet_events.length === 0) {
        return renderListFallback(
          "No processing jobs or packet events are stored for this packet yet.",
        );
      }

      const latestJobsByStage = getLatestJobsByStage(workspace.processing_jobs);
      const latestJobByStage = new Map(
        latestJobsByStage.map((job) => [job.stage_name, job]),
      );
      const attentionJobs = getAttentionJobs(workspace.processing_jobs);
      const activeJobCount = workspace.processing_jobs.filter(
        (job) => !job.completed_at_utc && job.status !== "failed",
      ).length;
      const failedJobCount = workspace.processing_jobs.filter(
        (job) => job.status === "failed" || Boolean(job.error_message),
      ).length;
      const latestPipelineJob = latestJobsByStage[0];
      const latestPacketEvent = [...workspace.packet_events].sort(
        (left, right) => toTimestamp(right.created_at_utc) - toTimestamp(left.created_at_utc),
      )[0];

      return (
        <div className="workspace-stack-grid">
          {pipelineActionSuccessMessage ? (
            <p className="status-banner status-success">{pipelineActionSuccessMessage}</p>
          ) : null}

          {pipelineActionErrorMessage ? (
            <p className="status-banner status-error">{pipelineActionErrorMessage}</p>
          ) : null}

          <SurfacePanel>
            <SectionHeading
              description="Latest stage posture, active workload, and recent packet activity for this workspace."
              title="Pipeline summary"
            />
            <div className="workspace-card-grid">
              <SurfaceCard>
                <StatusBadge tone={getPacketStatusTone(workspace.packet.status)}>
                  Packet status
                </StatusBadge>
                <h3>{toLabel(workspace.packet.status)}</h3>
                <p className="workspace-copy">Source {toLabel(workspace.packet.source)}</p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone={getWorkflowStatusTone(latestPipelineJob?.status)}>
                  Latest stage
                </StatusBadge>
                <h3>{latestPipelineJob ? toLabel(latestPipelineJob.stage_name) : "Not started"}</h3>
                <p className="workspace-copy">
                  {latestPipelineJob
                    ? `${toLabel(latestPipelineJob.status)} at ${formatDateTime(latestPipelineJob.updated_at_utc)}`
                    : "No stage execution has been persisted yet."}
                </p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge
                  tone={failedJobCount > 0 ? "warning" : activeJobCount > 0 ? "accent" : "success"}
                >
                  Jobs in flight
                </StatusBadge>
                <h3>{activeJobCount}</h3>
                <p className="workspace-copy">
                  {failedJobCount} job{failedJobCount === 1 ? "" : "s"} currently need attention.
                </p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone="neutral">Latest event</StatusBadge>
                <h3>{latestPacketEvent ? latestPacketEvent.event_type : "No events"}</h3>
                <p className="workspace-copy">
                  {latestPacketEvent
                    ? formatDateTime(latestPacketEvent.created_at_utc)
                    : "No packet events recorded yet."}
                </p>
              </SurfaceCard>
            </div>
          </SurfacePanel>

          <SurfacePanel>
            <SectionHeading
              description="Run queued work or retry stuck stages directly from the protected operator workspace."
              title="Stage controls"
            />
            <div className="workspace-card-grid">
              {pipelineStageDefinitions.map((stage) => {
                const latestStageJob = latestJobByStage.get(stage.id);
                const executeActionKey = `execute:${stage.id}`;
                const retryActionKey = `retry:${stage.id}`;

                return (
                  <SurfaceCard key={stage.id}>
                    <div className="queue-card-header">
                      <div className="queue-card-heading">
                        <StatusBadge tone="accent">Stage action</StatusBadge>
                        <h3>{toLabel(stage.id)}</h3>
                      </div>
                      <StatusBadge tone={getWorkflowStatusTone(latestStageJob?.status)}>
                        {latestStageJob ? toLabel(latestStageJob.status) : "Not started"}
                      </StatusBadge>
                    </div>
                    <p className="workspace-copy">{stage.description}</p>
                    <dl className="detail-list compact-detail-list">
                      <div>
                        <dt>Latest update</dt>
                        <dd>
                          {latestStageJob
                            ? formatDateTime(latestStageJob.updated_at_utc)
                            : "Not available"}
                        </dd>
                      </div>
                      <div>
                        <dt>Attempts</dt>
                        <dd>
                          {formatCount(
                            workspace.processing_jobs.filter(
                              (job) => job.stage_name === stage.id,
                            ).length,
                            "job",
                          )}
                        </dd>
                      </div>
                    </dl>
                    <div className="workspace-action-buttons">
                      <button
                        className="ghost-button"
                        disabled={
                          Boolean(processingPipelineAction) || !onExecuteStage
                        }
                        onClick={() => {
                          onExecuteStage?.(stage.id);
                        }}
                        type="button"
                      >
                        {processingPipelineAction === executeActionKey
                          ? "Running..."
                          : "Run queued"}
                      </button>
                      <button
                        disabled={
                          Boolean(processingPipelineAction) ||
                          !latestStageJob ||
                          !onRetryStage
                        }
                        onClick={() => {
                          onRetryStage?.(stage.id);
                        }}
                        type="button"
                      >
                        {processingPipelineAction === retryActionKey
                          ? "Retrying..."
                          : "Retry failed/stuck"}
                      </button>
                    </div>
                  </SurfaceCard>
                );
              })}
            </div>
          </SurfacePanel>

          {latestJobsByStage.length > 0 ? (
            <SurfacePanel>
              <SectionHeading title="Latest stage checkpoints" />
              <div className="workspace-card-grid">
                {latestJobsByStage.map((job) => renderProcessingJob(job))}
              </div>
            </SurfacePanel>
          ) : null}

          {attentionJobs.length > 0 ? (
            <SurfacePanel>
              <SectionHeading title="Retries and failures" />
              <div className="workspace-card-grid">
                {attentionJobs.map((job) => renderProcessingJob(job))}
              </div>
            </SurfacePanel>
          ) : null}

          {workspace.packet_events.length > 0 ? (
            <SurfacePanel>
              <SectionHeading
                description="Packet events remain visible as a chronological operator timeline beside the stage controls and checkpoints."
                title="Packet event timeline"
              />
              <div className="timeline-list">
                {[...workspace.packet_events]
                  .sort(
                    (left, right) =>
                      toTimestamp(right.created_at_utc) - toTimestamp(left.created_at_utc),
                  )
                  .map((packetEvent) => (
                    <SurfaceTimelineItem
                      badge={
                        <span className="workspace-inline-chip">
                          {formatDateTime(packetEvent.created_at_utc)}
                        </span>
                      }
                      description={
                        packetEvent.document_id
                          ? `Document ${packetEvent.document_id} · ${summarizeEventPayload(packetEvent.event_payload)}`
                          : summarizeEventPayload(packetEvent.event_payload)
                      }
                      eyebrow="Packet event"
                      key={packetEvent.event_id}
                      markerState={getEventMarkerState(packetEvent)}
                      title={packetEvent.event_type}
                    >
                      {packetEvent.event_payload ? (
                        <pre className="workspace-json-block">
                          {JSON.stringify(packetEvent.event_payload, null, 2)}
                        </pre>
                      ) : null}
                    </SurfaceTimelineItem>
                  ))}
              </div>
            </SurfacePanel>
          ) : null}
        </div>
      );
    }

    if (activeTab === "recommendations") {
      const recommendationRunById = new Map(
        workspace.recommendation_runs.map((recommendationRun) => [
          recommendationRun.recommendation_run_id,
          recommendationRun,
        ]),
      );
      const acceptedCount = workspace.recommendation_results.filter(
        (recommendationResult) => recommendationResult.disposition === "accepted",
      ).length;
      const rejectedCount = workspace.recommendation_results.filter(
        (recommendationResult) => recommendationResult.disposition === "rejected",
      ).length;
      const pendingCount = workspace.recommendation_results.filter(
        (recommendationResult) => recommendationResult.disposition === "pending",
      ).length;

      return workspace.recommendation_results.length > 0 ? (
        <div className="workspace-stack-grid">
          {recommendationActionSuccessMessage ? (
            <p className="status-banner status-success">{recommendationActionSuccessMessage}</p>
          ) : null}

          {recommendationActionErrorMessage ? (
            <p className="status-banner status-error">{recommendationActionErrorMessage}</p>
          ) : null}

          <SurfacePanel>
            <SectionHeading
              description="Recommendation posture across pending operator approvals, accepted outcomes, and rejected guidance for the selected packet."
              title="Recommendation summary"
            />
            <div className="workspace-card-grid">
              <SurfaceCard>
                <StatusBadge tone="warning">Pending</StatusBadge>
                <h3>{pendingCount}</h3>
                <p className="workspace-copy">Recommendations still waiting on explicit operator approval or rejection.</p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone="success">Accepted</StatusBadge>
                <h3>{acceptedCount}</h3>
                <p className="workspace-copy">Operator-approved recommendation results.</p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone="danger">Rejected</StatusBadge>
                <h3>{rejectedCount}</h3>
                <p className="workspace-copy">Recommendation results rejected by an operator.</p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone="accent">Runs</StatusBadge>
                <h3>{workspace.recommendation_runs.length}</h3>
                <p className="workspace-copy">Stored recommendation runs captured for this packet.</p>
              </SurfaceCard>
            </div>
          </SurfacePanel>

          <SurfacePanel>
            <SectionHeading
              description="Advisory outputs remain visible here until an operator records an explicit approval or rejection."
              title="Recommendation decisions"
            />
            <div className="workspace-card-grid">
              {workspace.recommendation_results.map((recommendationResult) =>
                renderRecommendationResult(recommendationResult, {
                  onReviewRecommendation,
                  processingRecommendationReview,
                  run: recommendationRunById.get(
                    recommendationResult.recommendation_run_id,
                  ),
                }),
              )}
            </div>
          </SurfacePanel>
        </div>
      ) : (
        renderListFallback("No recommendation results are stored for this packet yet.")
      );
    }

    if (activeTab === "audit") {
      const latestReviewDecisions = getLatestReviewDecisionsByTask(
        workspace.review_decisions,
      );
      const timelineEntries = buildWorkspaceTimeline(workspace);
      const extractionEditAuditEvents = workspace.audit_events.filter(
        (auditEvent) => isExtractionEditAuditEvent(auditEvent),
      );
      const filteredAuditEvents = workspace.audit_events.filter((auditEvent) => {
        if (
          auditEventFilterMode === "field-edits" &&
          !isExtractionEditAuditEvent(auditEvent)
        ) {
          return false;
        }

        if (
          selectedAuditDocumentId !== "all" &&
          auditEvent.document_id !== selectedAuditDocumentId
        ) {
          return false;
        }

        return true;
      });
      const filteredExtractionEditAuditEvents = extractionEditAuditEvents.filter(
        (auditEvent) =>
          selectedAuditDocumentId === "all" ||
          auditEvent.document_id === selectedAuditDocumentId,
      );
      const assignedOwners = Array.from(
        new Set(
          workspace.review_tasks
            .map((reviewTask) => reviewTask.assigned_user_email?.trim().toLowerCase())
            .filter((owner): owner is string => Boolean(owner)),
        ),
      );
      const ownershipLabel =
        assignedOwners.length === 0
          ? "Unassigned"
          : assignedOwners.length === 1
            ? assignedOwners[0]
            : "Mixed owners";

      return workspace.audit_events.length > 0 ||
        workspace.operator_notes.length > 0 ||
        workspace.review_tasks.length > 0 ||
        workspace.review_decisions.length > 0 ||
        workspace.packet_events.length > 0 ? (
        <div className="workspace-stack-grid">
          <SurfacePanel>
            <SectionHeading
              description="Assignment ownership, review-state volume, and unified packet history for the selected workspace."
              title="Ownership summary"
            />
            <div className="workspace-card-grid">
              <SurfaceCard>
                <StatusBadge tone="neutral">Ownership</StatusBadge>
                <h3>{ownershipLabel}</h3>
                <p className="workspace-copy">Current review-task ownership across the selected packet.</p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone="accent">Review tasks</StatusBadge>
                <h3>{workspace.review_tasks.length}</h3>
                <p className="workspace-copy">Tasks persisted for this packet workspace.</p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone="success">Decisions</StatusBadge>
                <h3>{workspace.review_decisions.length}</h3>
                <p className="workspace-copy">Review decisions recorded against packet tasks.</p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone="warning">Timeline entries</StatusBadge>
                <h3>{timelineEntries.length}</h3>
                <p className="workspace-copy">Combined packet, audit, note, and decision history.</p>
              </SurfaceCard>
              <SurfaceCard>
                <StatusBadge tone={extractionEditAuditEvents.length > 0 ? "accent" : "neutral"}>
                  Field edit audits
                </StatusBadge>
                <h3>{extractionEditAuditEvents.length}</h3>
                <p className="workspace-copy">
                  Dedicated extraction edit events available for filtered audit review.
                </p>
              </SurfaceCard>
            </div>
          </SurfacePanel>

          {workspace.audit_events.length > 0 ? (
            <SurfacePanel>
              <SectionHeading
                description="Filter the audit stream down to dedicated extraction field edit events and, when needed, one document at a time."
                title="Audit filters"
              />
              <div className="workspace-audit-filter-bar">
                <div
                  aria-label="Audit event filters"
                  className="workspace-review-support-actions"
                  role="group"
                >
                  <button
                    aria-pressed={auditEventFilterMode === "all"}
                    className={
                      auditEventFilterMode === "all"
                        ? "workspace-field-button workspace-field-button-active"
                        : "workspace-field-button"
                    }
                    onClick={() => {
                      setAuditEventFilterMode("all");
                    }}
                    type="button"
                  >
                    <strong>All audit events</strong>
                    <span>{formatCount(workspace.audit_events.length, "event")}</span>
                  </button>
                  <button
                    aria-pressed={auditEventFilterMode === "field-edits"}
                    className={
                      auditEventFilterMode === "field-edits"
                        ? "workspace-field-button workspace-field-button-active"
                        : "workspace-field-button"
                    }
                    onClick={() => {
                      setAuditEventFilterMode("field-edits");
                    }}
                    type="button"
                  >
                    <strong>Field edit events</strong>
                    <span>{formatCount(extractionEditAuditEvents.length, "event")}</span>
                  </button>
                </div>
                <label className="filter-field workspace-audit-document-filter">
                  <span>Document focus</span>
                  <select
                    onChange={(event) => {
                      setSelectedAuditDocumentId(event.target.value);
                    }}
                    value={selectedAuditDocumentId}
                  >
                    <option value="all">All documents</option>
                    {workspace.documents.map((document) => (
                      <option key={document.document_id} value={document.document_id}>
                        {document.file_name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <p className="workspace-caption">
                Showing {formatCount(filteredAuditEvents.length, "audit event")}
                {selectedAuditDocumentId !== "all"
                  ? ` for ${documentsById.get(selectedAuditDocumentId)?.file_name || selectedAuditDocumentId}`
                  : " across the packet workspace"}
                .
              </p>
            </SurfacePanel>
          ) : null}

          {workspace.review_tasks.length > 0 ? (
            <SurfacePanel>
              <SectionHeading
                description="Current task ownership, due dates, and recorded review outcomes by assignment."
                title="Assignments"
              />
              <div className="workspace-card-grid">
                {workspace.review_tasks.map((reviewTask) =>
                  renderAssignmentCard(
                    reviewTask,
                    latestReviewDecisions.get(reviewTask.review_task_id),
                  ),
                )}
              </div>
            </SurfacePanel>
          ) : null}

          {extractionEditAuditEvents.length > 0 ? (
            <SurfacePanel>
              <SectionHeading
                description="Dedicated extraction edit events are expanded here so operators can inspect field changes without reading raw payload JSON."
                title="Field edit history"
              />
              {filteredExtractionEditAuditEvents.length > 0 ? (
                <div className="workspace-card-grid">
                  {filteredExtractionEditAuditEvents.map((auditEvent) =>
                    renderExtractionEditAuditHistoryCard(auditEvent, {
                      documentLabel:
                        documentsById.get(auditEvent.document_id || "")?.file_name ||
                        auditEvent.document_id ||
                        "Packet workspace",
                    }),
                  )}
                </div>
              ) : (
                <div className="status-panel workspace-status-panel">
                  No field edit history matches the current audit filter.
                </div>
              )}
            </SurfacePanel>
          ) : null}

          {timelineEntries.length > 0 ? (
            <SurfacePanel>
              <SectionHeading
                description="Unified packet, audit, note, and decision events remain visible as one chronological operator trail."
                title="Change timeline"
              />
              <div className="timeline-list">
                {timelineEntries.map((entry) => (
                  <SurfaceTimelineItem
                    badge={
                      <span className="workspace-inline-chip">
                        {entry.actor || "System"}
                      </span>
                    }
                    description={`${entry.detail} · ${formatDateTime(entry.timestamp)}`}
                    eyebrow="Workspace change"
                    key={entry.id}
                    markerState={entry.state}
                    title={entry.title}
                  >
                    {entry.payload ? (
                      <pre className="workspace-json-block">
                        {JSON.stringify(entry.payload, null, 2)}
                      </pre>
                    ) : null}
                  </SurfaceTimelineItem>
                ))}
              </div>
            </SurfacePanel>
          ) : null}

          {workspace.audit_events.length > 0 ? (
            <SurfacePanel>
              <SectionHeading
                description="Raw audit events remain available separately from the synthesized change timeline and honor the current audit filter."
                title="Audit events"
              />
              {filteredAuditEvents.length > 0 ? (
                <div className="workspace-card-grid">
                  {filteredAuditEvents.map((auditEvent) => renderAuditEvent(auditEvent))}
                </div>
              ) : (
                <div className="status-panel workspace-status-panel">
                  No audit events match the current filter.
                </div>
              )}
            </SurfacePanel>
          ) : null}
        </div>
      ) : (
        renderListFallback("No audit events or operator notes are stored for this packet yet.")
      );
    }

    return renderListFallback("Select a packet workspace view.");
  };

  return (
      <SurfacePanel className="workspace-panel-surface">
        <SectionHeading
          actions={
            <button
              className="ghost-button"
              disabled={isLoading || !selectedPacketSummary}
              onClick={onRefresh}
              type="button"
            >
              Refresh workspace
            </button>
          }
          description={panelDescription}
          title={panelTitle}
        />

      <p className="workspace-refresh-indicator" aria-live="polite">
        {workspaceLastLoadedAt
          ? `Workspace last refreshed ${formatDateTime(workspaceLastLoadedAt)}`
          : "Workspace awaiting first refresh"}
        {reviewerEmail ? ` · Operator ${reviewerEmail}` : ""}
      </p>

      {selectedPacketSummary ? (
        <div className="workspace-packet-banner">
            <SurfaceCard className="workspace-packet-banner-card">
              <StatusBadge tone="accent">Selected packet</StatusBadge>
            <strong>{selectedPacketSummary.packet_name}</strong>
              <small>
                {selectedPacketSummary.primary_file_name || "No primary document"}
                {selectedPacketSummary.primary_issuer_name
                  ? ` · ${selectedPacketSummary.primary_issuer_name}`
                  : ""}
              </small>
            </SurfaceCard>
            <SurfaceCard className="workspace-packet-banner-card">
              <StatusBadge tone="neutral">Stage</StatusBadge>
            <strong>{toLabel(selectedPacketSummary.stage_name)}</strong>
              <small>
                {selectedPacketSummary.latest_job_stage_name
                  ? `Latest ${toLabel(selectedPacketSummary.latest_job_stage_name)} · ${toLabel(selectedPacketSummary.latest_job_status)}`
                  : "No job history yet"}
              </small>
            </SurfaceCard>
            <SurfaceCard className="workspace-packet-banner-card">
              <StatusBadge tone={getPacketStatusTone(selectedPacketSummary.status)}>
                Status
              </StatusBadge>
            <strong>{toLabel(selectedPacketSummary.status)}</strong>
              <small>
                {formatCount(
                  selectedPacketSummary.awaiting_review_document_count,
                  "document",
                )} awaiting review.
              </small>
            </SurfaceCard>
        </div>
      ) : null}

      {errorMessage ? <p className="status-banner status-error">{errorMessage}</p> : null}

      {isLoading ? (
        <div className="status-panel workspace-status-panel">Loading packet workspace from the SQL-backed Functions API...</div>
      ) : null}

      {!isLoading && workspace ? (
        <>
          <SurfaceCard className="workspace-tab-shell">
            <div className="workspace-tab-shell-heading">
              <div>
                <p className="workspace-tab-shell-label">Workspace views</p>
                <strong>{getWorkspaceTabLabel(activeTab)}</strong>
                <p className="workspace-tab-shell-copy">
                  {workspaceTabCopy}
                </p>
              </div>
              <StatusBadge className="workspace-tab-shell-badge" tone="accent">
                Current view
              </StatusBadge>
            </div>

            <div
              aria-label="Packet workspace views"
              className="workspace-tab-strip"
              role="tablist"
            >
              {visibleWorkspaceTabs.map((tab) => (
                <button
                  aria-selected={activeTab === tab.id}
                  className={
                    activeTab === tab.id
                      ? "workspace-tab-button workspace-tab-button-active"
                      : "workspace-tab-button"
                  }
                  key={tab.id}
                  onClick={() => {
                    selectWorkspaceTab(tab.id);
                  }}
                  role="tab"
                  type="button"
                >
                  {tab.label}
                </button>
              ))}
            </div>
            {prioritizedWorkspaceTabs.length > visibleWorkspaceTabs.length ||
            showAllWorkspaceTabs ? (
              <div className="workspace-tab-toggle-row">
                <button
                  className="ghost-button"
                  onClick={() => {
                    setShowAllWorkspaceTabs((currentValue) => !currentValue);
                  }}
                  type="button"
                >
                  {showAllWorkspaceTabs
                    ? "Show fewer views"
                    : workspaceTabToggleLabel}
                </button>
              </div>
            ) : null}
          </SurfaceCard>
          {renderActiveTab()}
        </>
      ) : null}

      {!isLoading && !workspace && !errorMessage ? renderActiveTab() : null}
    </SurfacePanel>
  );
}
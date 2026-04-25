import { useEffect, useRef, useState } from "react";

import { getLiveSession, type LiveSession } from "../api/liveSessionApi";
import {
  type AdminQueueFilterUrlState,
  navigateToAdminSection,
  replaceAdminSection,
  resolveAdminPacketIdFromSearch,
  resolveAdminQueueFiltersFromSearch,
  resolveAdminSectionFromPath,
  resolveAdminWorkspaceTabFromSearch,
} from "../appRoutes";
import {
  getOperatorContracts,
  type OperatorContractsResponse,
} from "../api/operatorContractsApi";
import {
  createIntakeSource,
  deleteIntakeSource,
  executeIntakeSource,
  listIntakeSources,
  setIntakeSourceEnablement,
  updateIntakeSource,
  type IntakeSourceCreateRequest,
  type IntakeSourceExecutionResponse,
  type IntakeSourceRecord,
  type IntakeSourceUpdateRequest,
} from "../api/intakeSourcesApi";
import {
  submitPacketReviewAssignment,
  submitPacketReviewExtractionEdits,
  submitPacketReviewDecision,
  submitPacketReviewNote,
  submitPacketReviewTaskCreate,
} from "../api/packetReviewApi";
import {
  listPacketQueue,
  type PacketQueueFilters,
  type PacketQueueItem,
  type PacketQueueListResponse,
} from "../api/packetQueueApi";
import {
  executePacketStage,
  getPacketWorkspace,
  replayPacket,
  reviewPacketRecommendation,
  retryPacketStage,
  type PacketProcessingStageName,
  type RecommendationReviewDisposition,
  type PacketWorkspaceSnapshot,
} from "../api/packetWorkspaceApi";
import {
  AdminNavigation,
  adminWorkflowLandmarks,
  isWorkflowLandmarkActive,
  type AdminSectionId,
  type AdminWorkflowLandmark,
  type AdminWorkflowLandmarkQueuePreset,
} from "./AdminNavigation";
import { IntakeSourcesPanel } from "./IntakeSourcesPanel";
import { ManualUploadPanel } from "./ManualUploadPanel";
import {
  PacketQueueTable,
  type PacketQueueRefreshDelta,
} from "./PacketQueueTable";
import {
  buildVisibleQueueActionSummary,
  formatVisibleQueueActionSummary,
} from "./packetQueueUrgency";
import {
  PacketWorkspacePanel,
  type PacketWorkspaceExtractionEditInput,
  type PacketWorkspaceReviewAssignmentInput,
  type PacketWorkspaceReviewDecisionInput,
  type PacketWorkspaceReviewNoteInput,
  type PacketWorkspaceReviewTaskCreateInput,
  type WorkspaceTabId,
} from "./PacketWorkspacePanel";
import { ProtectedSiteLayout } from "./ProtectedSiteLayout";
import {
  SectionHeading,
  StatusBadge,
  SurfaceCard,
  SurfaceDrawer,
  SurfaceMetricCard,
  SurfacePanel,
  type StatusBadgeTone,
} from "./SurfacePrimitives";
const defaultPacketQueueFilters: PacketQueueFilters = {
  page: 1,
  page_size: 10,
  stage_name: "review",
};

const sectionConfig: Record<
  AdminSectionId,
  {
    panelDescription: string;
    panelTitle: string;
    preferredWorkspaceTab: WorkspaceTabId;
    queueDescription: string;
    showManualUploadPanel: boolean;
    showSourcesPanel: boolean;
  }
> = {
  review: {
    panelDescription:
      "Review tasks, task authoring, decisions, and operator notes now sit beside the selected packet workspace, with viewer-linked evidence jumps, extracted-field highlighting, and SQL-backed review-task decisions.",
    panelTitle: "Review workspace",
    preferredWorkspaceTab: "review",
    queueDescription:
      "Select a packet row to load the full SQL-backed workspace on the right, create missing review tasks, and approve or reject them without dropping back to the legacy document queue.",
    showManualUploadPanel: true,
    showSourcesPanel: false,
  },
  intake: {
    panelDescription:
      "Replay, dead-letter visibility, archive lineage, and ingest provenance now live beside the selected packet so intake triage stays packet-first.",
    panelTitle: "Intake workspace",
    preferredWorkspaceTab: "intake",
    queueDescription:
      "Use the queue to select a packet, then inspect archive expansion, blocked documents, and replay readiness in the workspace panel.",
    showManualUploadPanel: true,
    showSourcesPanel: false,
  },
  pipeline: {
    panelDescription:
      "Processing jobs and packet events for the selected packet are exposed from the SQL workspace snapshot.",
    panelTitle: "Pipeline workspace",
    preferredWorkspaceTab: "pipeline",
    queueDescription:
      "The queue remains the packet picker while the right-hand workspace shifts to job history and stage events.",
    showManualUploadPanel: false,
    showSourcesPanel: false,
  },
  viewer: {
    panelDescription:
      "The selected packet workspace now exposes protected PDF and image preview alongside OCR, extraction, lineage, and extracted-field highlighting for the chosen document.",
    panelTitle: "Viewer workspace",
    preferredWorkspaceTab: "viewer",
    queueDescription:
      "Choose a packet to inspect document previews, stored OCR output, and packet evidence without leaving the protected admin shell.",
    showManualUploadPanel: false,
    showSourcesPanel: false,
  },
  accounts: {
    panelDescription:
      "Account matching evidence, operator overrides, and packet-local linkage history now read directly from the selected packet workspace.",
    panelTitle: "Accounts workspace",
    preferredWorkspaceTab: "matching",
    queueDescription:
      "Select a packet to compare auto-linked accounts against operator-selected linkage and review history.",
    showManualUploadPanel: false,
    showSourcesPanel: false,
  },
  rules_doctypes: {
    panelDescription:
      "Managed classifications, doctypes, prompt profiles, and the packet's live taxonomy evidence now share the same workspace.",
    panelTitle: "Rules and doctypes workspace",
    preferredWorkspaceTab: "rules_doctypes",
    queueDescription:
      "Use the queue to inspect live packet classification evidence against the managed SQL taxonomy and prompt-profile contracts.",
    showManualUploadPanel: false,
    showSourcesPanel: false,
  },
  sources: {
    panelDescription:
      "The Sources tab now lists managed intake definitions, execution health, and the packet lineage that each source produces.",
    panelTitle: "Sources workspace",
    preferredWorkspaceTab: "documents",
    queueDescription:
      "Run a source to stage new packets, then select a packet row to inspect source URIs, archive lineage, and the resulting document set.",
    showManualUploadPanel: false,
    showSourcesPanel: true,
  },
  recommendations: {
    panelDescription:
      "Recommendation runs now support explicit operator acceptance or rejection directly from the selected packet workspace.",
    panelTitle: "Recommendations workspace",
    preferredWorkspaceTab: "recommendations",
    queueDescription:
      "Choose a packet row to inspect recommendation summaries, evidence, confidence, and record the final operator disposition.",
    showManualUploadPanel: false,
    showSourcesPanel: false,
  },
  audit: {
    panelDescription:
      "Packet ownership, notes, decisions, and audit history now sit together in one workspace timeline.",
    panelTitle: "Audit workspace",
    preferredWorkspaceTab: "audit",
    queueDescription:
      "Select a packet row to inspect task ownership, operator notes, review decisions, and the packet change timeline.",
    showManualUploadPanel: false,
    showSourcesPanel: false,
  },
};

type PacketQueueRefreshComparisonKey = {
  activityKey: string;
  activitySummary: string;
  assignmentKey: string;
  assignmentSummary: string;
  contractKey: string;
  contractSummary: string;
  stageKey: string;
  stageSummary: string;
  statusKey: string;
  statusSummary: string;
};

type PacketQueueRefreshDeltaCounts = {
  activityChangeCount: number;
  assignmentChangeCount: number;
  contractChangeCount: number;
  newPacketCount: number;
  stageChangeCount: number;
  statusChangeCount: number;
};

type QueueLensPill = {
  isAccent?: boolean;
  key: string;
  label: string;
};

type RefreshDeltaDetail = {
  current: string;
  previous: string;
};

function formatQueueAge(hours: number) {
  if (hours < 1) {
    return `${Math.max(1, Math.round(hours * 60))}m`;
  }

  if (hours < 24) {
    return `${hours.toFixed(hours < 10 ? 1 : 0)}h`;
  }

  return `${(hours / 24).toFixed(1)}d`;
}

function toSentenceLabel(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatCount(count: number, noun: string) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function formatAssignmentSummary(item: PacketQueueItem) {
  if (item.assignment_state === "assigned" && item.assigned_user_email) {
    return `Assigned · ${item.assigned_user_email}`;
  }

  if (item.assignment_state === "mixed") {
    return "Mixed · Multiple owners";
  }

  return "Unassigned";
}

function formatContractSummary(values: string[]) {
  if (values.length === 0) {
    return "Not set";
  }

  return values.map((value) => toSentenceLabel(value)).join(", ");
}

function formatActivitySummary(item: PacketQueueItem) {
  return [
    formatCount(item.audit_event_count, "audit event"),
    formatCount(item.operator_note_count, "note"),
    formatCount(item.review_task_count, "review task"),
  ].join(" · ");
}

function formatStageSummary(item: PacketQueueItem) {
  const latestJobSummary = item.latest_job_stage_name
    ? `${toSentenceLabel(item.latest_job_stage_name)} · ${toSentenceLabel(
        item.latest_job_status || "unknown",
      )}`
    : "No job history";

  return `${toSentenceLabel(item.stage_name)} queue · ${latestJobSummary}`;
}

function formatStatusSummary(item: PacketQueueItem) {
  return [
    toSentenceLabel(item.status),
    formatCount(item.awaiting_review_document_count, "awaiting review doc"),
    formatCount(item.completed_document_count, "completed doc"),
  ].join(" · ");
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

function formatRefreshSnapshot(value: string | null) {
  if (!value) {
    return "Awaiting first successful refresh";
  }

  return `Last refreshed ${formatDateTime(value)}`;
}

function formatWorkflowLanePreset(
  queuePreset: AdminWorkflowLandmarkQueuePreset,
) {
  const segments: string[] = [];

  if (queuePreset.stage_name) {
    segments.push(`${toSentenceLabel(queuePreset.stage_name)} stage`);
  }

  if (queuePreset.status) {
    segments.push(`${toSentenceLabel(queuePreset.status)} status`);
  }

  return segments.length > 0
    ? segments.join(" · ")
    : "All packets in the current queue view";
}

function formatMinimumQueueAgeFilter(hours: number | undefined) {
  if (hours === undefined || !Number.isFinite(hours)) {
    return null;
  }

  return `Minimum age: ${Number.isInteger(hours) ? hours.toFixed(0) : hours.toFixed(1)}h`;
}

function buildQueueLensPills(
  filters: PacketQueueFilters,
  activeWorkflowLandmark: AdminWorkflowLandmark | null,
  visiblePacketCount: number,
): QueueLensPill[] {
  const pills: QueueLensPill[] = [];

  pills.push({
    isAccent: visiblePacketCount > 0,
    key: `visible:${visiblePacketCount}`,
    label: `Visible: ${formatCount(visiblePacketCount, "packet")}`,
  });

  if (activeWorkflowLandmark) {
    pills.push({
      isAccent: true,
      key: `sections:${activeWorkflowLandmark.id}`,
      label: `Sections: ${activeWorkflowLandmark.mappedSectionsLabel}`,
    });
  }

  if (filters.stage_name) {
    pills.push({
      isAccent: true,
      key: `stage:${filters.stage_name}`,
      label: `Stage: ${toSentenceLabel(filters.stage_name)}`,
    });
  }

  if (filters.status) {
    pills.push({
      isAccent: true,
      key: `status:${filters.status}`,
      label: `Status: ${toSentenceLabel(filters.status)}`,
    });
  }

  if (filters.source) {
    pills.push({
      key: `source:${filters.source}`,
      label: `Source: ${toSentenceLabel(filters.source)}`,
    });
  }

  if (filters.assigned_user_email) {
    pills.push({
      key: `assignment:${filters.assigned_user_email}`,
      label: `Assignment: ${filters.assigned_user_email}`,
    });
  }

  if (filters.classification_key) {
    pills.push({
      key: `classification:${filters.classification_key}`,
      label: `Classification: ${toSentenceLabel(filters.classification_key)}`,
    });
  }

  if (filters.document_type_key) {
    pills.push({
      key: `document-type:${filters.document_type_key}`,
      label: `Document type: ${toSentenceLabel(filters.document_type_key)}`,
    });
  }

  const minimumQueueAgeLabel = formatMinimumQueueAgeFilter(
    filters.min_queue_age_hours,
  );

  if (minimumQueueAgeLabel) {
    pills.push({
      key: `min-age:${filters.min_queue_age_hours}`,
      label: minimumQueueAgeLabel,
    });
  }

  return pills;
}

function summarizePacketQueueRefreshDeltas(
  refreshDeltas: Record<string, PacketQueueRefreshDelta>,
): PacketQueueRefreshDeltaCounts {
  const deltaCounts: PacketQueueRefreshDeltaCounts = {
    activityChangeCount: 0,
    assignmentChangeCount: 0,
    contractChangeCount: 0,
    newPacketCount: 0,
    stageChangeCount: 0,
    statusChangeCount: 0,
  };

  for (const refreshDelta of Object.values(refreshDeltas)) {
    if (refreshDelta.hasActivityChange) {
      deltaCounts.activityChangeCount += 1;
    }

    if (refreshDelta.hasAssignmentChange) {
      deltaCounts.assignmentChangeCount += 1;
    }

    if (refreshDelta.hasContractChange) {
      deltaCounts.contractChangeCount += 1;
    }

    if (refreshDelta.isNewPacket) {
      deltaCounts.newPacketCount += 1;
    }

    if (refreshDelta.hasStageChange) {
      deltaCounts.stageChangeCount += 1;
    }

    if (refreshDelta.hasStatusChange) {
      deltaCounts.statusChangeCount += 1;
    }
  }

  return deltaCounts;
}

function formatQueueRefreshDeltaSummary(
  deltaCounts: PacketQueueRefreshDeltaCounts,
) {
  const parts = [
    deltaCounts.newPacketCount > 0
      ? formatCount(deltaCounts.newPacketCount, "new packet")
      : null,
    deltaCounts.stageChangeCount > 0
      ? formatCount(deltaCounts.stageChangeCount, "stage move")
      : null,
    deltaCounts.statusChangeCount > 0
      ? formatCount(deltaCounts.statusChangeCount, "status update")
      : null,
    deltaCounts.assignmentChangeCount > 0
      ? formatCount(deltaCounts.assignmentChangeCount, "assignment change")
      : null,
    deltaCounts.activityChangeCount > 0
      ? formatCount(deltaCounts.activityChangeCount, "activity change")
      : null,
    deltaCounts.contractChangeCount > 0
      ? formatCount(deltaCounts.contractChangeCount, "contract summary change")
      : null,
  ].filter((part): part is string => Boolean(part));

  return parts.length > 0
    ? parts.join(" · ")
    : "No queue-row changes since last snapshot.";
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
    case "queued":
      return "warning";
    case "ready_for_recommendation":
      return "accent";
    default:
      return "neutral";
  }
}

function getRefreshTone(
  isLoading: boolean,
  errorMessage: string | null,
  lastLoadedAt: string | null,
): StatusBadgeTone {
  if (isLoading) {
    return "accent";
  }

  if (errorMessage) {
    return "danger";
  }

  return lastLoadedAt ? "success" : "neutral";
}

function sortIntakeSources(sources: IntakeSourceRecord[]) {
  return [...sources].sort((left, right) => {
    const nameComparison = left.source_name.localeCompare(right.source_name);
    if (nameComparison !== 0) {
      return nameComparison;
    }

    return left.source_id.localeCompare(right.source_id);
  });
}

function buildRouteBackedPacketQueueFilters(search: string): PacketQueueFilters {
  return {
    ...defaultPacketQueueFilters,
    ...resolveAdminQueueFiltersFromSearch(search),
  };
}

function buildPacketQueueInputState(filters: PacketQueueFilters) {
  return {
    assignmentFilter: filters.assigned_user_email ?? "",
    classificationFilter: filters.classification_key ?? "",
    documentTypeFilter: filters.document_type_key ?? "",
    minQueueAgeHoursFilter:
      filters.min_queue_age_hours !== undefined
        ? String(filters.min_queue_age_hours)
        : "",
    sourceFilter: filters.source ?? "",
    stageFilter: filters.stage_name ?? defaultPacketQueueFilters.stage_name ?? "",
    statusFilter: filters.status ?? "",
  };
}

function buildQueueFilterRouteState(
  filters: PacketQueueFilters,
): AdminQueueFilterUrlState {
  return {
    assigned_user_email: filters.assigned_user_email || undefined,
    classification_key: filters.classification_key || undefined,
    document_type_key: filters.document_type_key || undefined,
    min_queue_age_hours: filters.min_queue_age_hours,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
    source: filters.source || undefined,
    stage_name:
      filters.stage_name && filters.stage_name !== defaultPacketQueueFilters.stage_name
        ? filters.stage_name
        : undefined,
    status: filters.status || undefined,
  };
}

function buildQueueFilterRouteSignature(filters: PacketQueueFilters) {
  return JSON.stringify(buildQueueFilterRouteState(filters));
}

function buildPacketQueueRefreshComparisonKey(
  item: PacketQueueItem,
): PacketQueueRefreshComparisonKey {
  return {
    activityKey: [
      item.updated_at_utc,
      item.audit_event_count,
      item.operator_note_count,
      item.review_task_count,
      item.awaiting_review_document_count,
      item.completed_document_count,
    ].join("|"),
    activitySummary: formatActivitySummary(item),
    assignmentKey: `${item.assignment_state}|${item.assigned_user_email ?? ""}`,
    assignmentSummary: formatAssignmentSummary(item),
    contractKey: [
      [...item.classification_keys].sort().join(","),
      [...item.document_type_keys].sort().join(","),
    ].join("|"),
    contractSummary: [
      `Classifications ${formatContractSummary(item.classification_keys)}`,
      `Types ${formatContractSummary(item.document_type_keys)}`,
    ].join(" · "),
    stageKey: `${item.stage_name}|${item.latest_job_stage_name ?? ""}|${item.latest_job_status ?? ""}`,
    stageSummary: formatStageSummary(item),
    statusKey: `${item.status}|${item.awaiting_review_document_count}|${item.completed_document_count}`,
    statusSummary: formatStatusSummary(item),
  };
}

function buildWorkflowLandmarkQueueFilters(
  queuePreset: AdminWorkflowLandmarkQueuePreset,
): PacketQueueFilters {
  return {
    ...defaultPacketQueueFilters,
    ...queuePreset,
    page: 1,
    page_size: defaultPacketQueueFilters.page_size,
  };
}

export function LiveReviewWorkbench() {
  const initialAppliedPacketQueueFilters = buildRouteBackedPacketQueueFilters(
    window.location.search,
  );
  const initialPacketQueueInputState = buildPacketQueueInputState(
    initialAppliedPacketQueueFilters,
  );
  const [activeSection, setActiveSection] = useState<AdminSectionId>(() =>
    resolveAdminSectionFromPath(window.location.pathname),
  );
  const [activeWorkspaceTabOverride, setActiveWorkspaceTabOverride] = useState<
    WorkspaceTabId | null
  >(() => resolveAdminWorkspaceTabFromSearch(window.location.search));
  const [activePacketWorkspace, setActivePacketWorkspace] =
    useState<PacketWorkspaceSnapshot | null>(null);
  const [activePacketWorkspaceErrorMessage, setActivePacketWorkspaceErrorMessage] =
    useState<string | null>(null);
  const [isPacketWorkspaceLoading, setIsPacketWorkspaceLoading] = useState(false);
  const [isOperatorContractsLoading, setIsOperatorContractsLoading] = useState(false);
  const [isReplayingPacket, setIsReplayingPacket] = useState(false);
  const [packetQueue, setPacketQueue] = useState<PacketQueueListResponse | null>(
    null,
  );
  const [intakeSources, setIntakeSources] = useState<IntakeSourceRecord[]>([]);
  const [intakeSourcesErrorMessage, setIntakeSourcesErrorMessage] = useState<
    string | null
  >(null);
  const [intakeSourcesSuccessMessage, setIntakeSourcesSuccessMessage] = useState<
    string | null
  >(null);
  const [isCreatingSource, setIsCreatingSource] = useState(false);
  const [isIntakeSourcesLoading, setIsIntakeSourcesLoading] = useState(false);
  const [isQueueLoading, setIsQueueLoading] = useState(true);
  const [packetQueueRefreshDeltas, setPacketQueueRefreshDeltas] = useState<
    Record<string, PacketQueueRefreshDelta>
  >({});
  const [isReviewAssignmentSubmitting, setIsReviewAssignmentSubmitting] =
    useState(false);
  const [isExtractionEditSubmitting, setIsExtractionEditSubmitting] =
    useState(false);
  const [isReviewDecisionSubmitting, setIsReviewDecisionSubmitting] =
    useState(false);
  const [isReviewNoteSubmitting, setIsReviewNoteSubmitting] = useState(false);
  const [isReviewTaskCreateSubmitting, setIsReviewTaskCreateSubmitting] =
    useState(false);
  const [latestIntakeSourceExecution, setLatestIntakeSourceExecution] =
    useState<IntakeSourceExecutionResponse | null>(null);
  const [deletingSourceId, setDeletingSourceId] = useState<string | null>(null);
  const [runningSourceId, setRunningSourceId] = useState<string | null>(null);
  const [savingSourceId, setSavingSourceId] = useState<string | null>(null);
  const [togglingSourceId, setTogglingSourceId] = useState<string | null>(null);
  const [queueErrorMessage, setQueueErrorMessage] = useState<string | null>(null);
  const [queueLastLoadedAt, setQueueLastLoadedAt] = useState<string | null>(null);
  const [pipelineActionErrorMessage, setPipelineActionErrorMessage] = useState<
    string | null
  >(null);
  const [pipelineActionSuccessMessage, setPipelineActionSuccessMessage] = useState<
    string | null
  >(null);
  const [intakeActionErrorMessage, setIntakeActionErrorMessage] = useState<
    string | null
  >(null);
  const [intakeActionSuccessMessage, setIntakeActionSuccessMessage] = useState<
    string | null
  >(null);
  const [operatorContracts, setOperatorContracts] =
    useState<OperatorContractsResponse | null>(null);
  const [operatorContractsErrorMessage, setOperatorContractsErrorMessage] =
    useState<string | null>(null);
  const [processingPipelineAction, setProcessingPipelineAction] = useState<
    string | null
  >(null);
  const [processingRecommendationReview, setProcessingRecommendationReview] =
    useState<string | null>(null);
  const [recommendationActionErrorMessage, setRecommendationActionErrorMessage] =
    useState<string | null>(null);
  const [recommendationActionSuccessMessage, setRecommendationActionSuccessMessage] =
    useState<string | null>(null);
  const [extractionEditErrorMessage, setExtractionEditErrorMessage] = useState<
    string | null
  >(null);
  const [extractionEditSuccessMessage, setExtractionEditSuccessMessage] =
    useState<string | null>(null);
  const [reviewAssignmentErrorMessage, setReviewAssignmentErrorMessage] = useState<
    string | null
  >(null);
  const [reviewAssignmentSuccessMessage, setReviewAssignmentSuccessMessage] =
    useState<string | null>(null);
  const [reviewTaskCreateErrorMessage, setReviewTaskCreateErrorMessage] =
    useState<string | null>(null);
  const [reviewTaskCreateSuccessMessage, setReviewTaskCreateSuccessMessage] =
    useState<string | null>(null);
  const [reviewNoteErrorMessage, setReviewNoteErrorMessage] = useState<
    string | null
  >(null);
  const [reviewNoteSuccessMessage, setReviewNoteSuccessMessage] = useState<
    string | null
  >(null);
  const [reviewErrorMessage, setReviewErrorMessage] = useState<string | null>(null);
  const [workspaceLastLoadedAt, setWorkspaceLastLoadedAt] = useState<string | null>(
    null,
  );
  const [liveSession, setLiveSession] = useState<LiveSession | null>(null);
  const [selectedPacketId, setSelectedPacketId] = useState<string | null>(() =>
    resolveAdminPacketIdFromSearch(window.location.search),
  );
  const [appliedPacketQueueFilters, setAppliedPacketQueueFilters] = useState(
    initialAppliedPacketQueueFilters,
  );
  const appliedPacketQueueFiltersRef = useRef(initialAppliedPacketQueueFilters);
  const [sourceFilter, setSourceFilter] = useState(
    initialPacketQueueInputState.sourceFilter,
  );
  const [stageFilter, setStageFilter] = useState(
    initialPacketQueueInputState.stageFilter,
  );
  const [statusFilter, setStatusFilter] = useState(
    initialPacketQueueInputState.statusFilter,
  );
  const [assignmentFilter, setAssignmentFilter] = useState(
    initialPacketQueueInputState.assignmentFilter,
  );
  const [classificationFilter, setClassificationFilter] = useState(
    initialPacketQueueInputState.classificationFilter,
  );
  const [documentTypeFilter, setDocumentTypeFilter] = useState(
    initialPacketQueueInputState.documentTypeFilter,
  );
  const [minQueueAgeHoursFilter, setMinQueueAgeHoursFilter] = useState(
    initialPacketQueueInputState.minQueueAgeHoursFilter,
  );
  const previousPacketQueueFilterSignatureRef = useRef<string | null>(null);
  const previousPacketQueueRefreshKeysRef = useRef<
    Record<string, PacketQueueRefreshComparisonKey>
  >({});

  const activeSectionConfig = sectionConfig[activeSection];
  const preferredWorkspaceTab =
    activeWorkspaceTabOverride ?? activeSectionConfig.preferredWorkspaceTab;

  useEffect(() => {
    setExtractionEditErrorMessage(null);
    setExtractionEditSuccessMessage(null);
    setReviewTaskCreateErrorMessage(null);
    setReviewTaskCreateSuccessMessage(null);
    setReviewNoteErrorMessage(null);
    setReviewNoteSuccessMessage(null);
  }, [selectedPacketId]);

  const syncPacketQueueFilterInputs = (filters: PacketQueueFilters) => {
    const nextInputState = buildPacketQueueInputState(filters);

    setAssignmentFilter(nextInputState.assignmentFilter);
    setClassificationFilter(nextInputState.classificationFilter);
    setDocumentTypeFilter(nextInputState.documentTypeFilter);
    setMinQueueAgeHoursFilter(nextInputState.minQueueAgeHoursFilter);
    setSourceFilter(nextInputState.sourceFilter);
    setStageFilter(nextInputState.stageFilter);
    setStatusFilter(nextInputState.statusFilter);
  };

  const setAppliedPacketQueueRouteState = (filters: PacketQueueFilters) => {
    appliedPacketQueueFiltersRef.current = filters;
    setAppliedPacketQueueFilters(filters);
  };

  const getAdminRouteOptions = (overrides?: {
    packetId?: string | null;
    queueFilters?: PacketQueueFilters;
    tab?: WorkspaceTabId | null;
  }) => ({
    packetId:
      overrides && "packetId" in overrides
        ? overrides.packetId ?? null
        : selectedPacketId,
    queueFilters: buildQueueFilterRouteState(
      overrides?.queueFilters ?? appliedPacketQueueFiltersRef.current,
    ),
    tab:
      overrides && "tab" in overrides
        ? overrides.tab ?? null
        : activeWorkspaceTabOverride,
  });

  const loadPacketQueue = async (filters: PacketQueueFilters) => {
    setQueueErrorMessage(null);
    setIsQueueLoading(true);
    const queueFilterSignature = buildQueueFilterRouteSignature(filters);

    try {
      const response = await listPacketQueue(filters);
      const currentRefreshKeys = Object.fromEntries(
        response.items.map((item) => [
          item.packet_id,
          buildPacketQueueRefreshComparisonKey(item),
        ]),
      ) as Record<string, PacketQueueRefreshComparisonKey>;

      if (previousPacketQueueFilterSignatureRef.current !== queueFilterSignature) {
        previousPacketQueueFilterSignatureRef.current = queueFilterSignature;
        previousPacketQueueRefreshKeysRef.current = currentRefreshKeys;
        setPacketQueueRefreshDeltas({});
      } else {
        const nextRefreshDeltas = Object.fromEntries(
          response.items.flatMap((item) => {
            const previousKeys =
              previousPacketQueueRefreshKeysRef.current[item.packet_id];
            const currentKeys = currentRefreshKeys[item.packet_id];
            const refreshDelta: PacketQueueRefreshDelta = {
              hasActivityChange:
                Boolean(previousKeys) &&
                previousKeys.activityKey !== currentKeys.activityKey,
              activityDetail:
                previousKeys && previousKeys.activityKey !== currentKeys.activityKey
                  ? buildRefreshDeltaDetail(
                      previousKeys.activitySummary,
                      currentKeys.activitySummary,
                    )
                  : undefined,
              hasAssignmentChange:
                Boolean(previousKeys) &&
                previousKeys.assignmentKey !== currentKeys.assignmentKey,
              assignmentDetail:
                previousKeys &&
                previousKeys.assignmentKey !== currentKeys.assignmentKey
                  ? buildRefreshDeltaDetail(
                      previousKeys.assignmentSummary,
                      currentKeys.assignmentSummary,
                    )
                  : undefined,
              hasContractChange:
                Boolean(previousKeys) &&
                previousKeys.contractKey !== currentKeys.contractKey,
              contractDetail:
                previousKeys && previousKeys.contractKey !== currentKeys.contractKey
                  ? buildRefreshDeltaDetail(
                      previousKeys.contractSummary,
                      currentKeys.contractSummary,
                    )
                  : undefined,
              hasStageChange:
                Boolean(previousKeys) &&
                previousKeys.stageKey !== currentKeys.stageKey,
              stageDetail:
                previousKeys && previousKeys.stageKey !== currentKeys.stageKey
                  ? buildRefreshDeltaDetail(
                      previousKeys.stageSummary,
                      currentKeys.stageSummary,
                    )
                  : undefined,
              hasStatusChange:
                Boolean(previousKeys) &&
                previousKeys.statusKey !== currentKeys.statusKey,
              statusDetail:
                previousKeys && previousKeys.statusKey !== currentKeys.statusKey
                  ? buildRefreshDeltaDetail(
                      previousKeys.statusSummary,
                      currentKeys.statusSummary,
                    )
                  : undefined,
              isNewPacket: !previousKeys,
            };

            if (
              !refreshDelta.isNewPacket &&
              !refreshDelta.hasActivityChange &&
              !refreshDelta.hasAssignmentChange &&
              !refreshDelta.hasContractChange &&
              !refreshDelta.hasStageChange &&
              !refreshDelta.hasStatusChange
            ) {
              return [];
            }

            return [[item.packet_id, refreshDelta]];
          }),
        ) as Record<string, PacketQueueRefreshDelta>;

        previousPacketQueueRefreshKeysRef.current = currentRefreshKeys;
        setPacketQueueRefreshDeltas(nextRefreshDeltas);
      }

      setPacketQueue(response);
      setQueueLastLoadedAt(new Date().toISOString());
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to load the packet queue.";
      setQueueErrorMessage(message);
    } finally {
      setIsQueueLoading(false);
    }
  };

  const loadPacketWorkspace = async (packetId: string) => {
    setActivePacketWorkspaceErrorMessage(null);
    setIsPacketWorkspaceLoading(true);

    try {
      const response = await getPacketWorkspace(packetId);
      setActivePacketWorkspace(response);
      setWorkspaceLastLoadedAt(new Date().toISOString());
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unable to load the packet workspace.";
      setActivePacketWorkspaceErrorMessage(message);
      setActivePacketWorkspace(null);
    } finally {
      setIsPacketWorkspaceLoading(false);
    }
  };

  const loadIntakeSources = async () => {
    setIntakeSourcesErrorMessage(null);
    setIsIntakeSourcesLoading(true);

    try {
      const response = await listIntakeSources();
      setIntakeSources(sortIntakeSources(response));
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to load intake sources.";
      setIntakeSourcesErrorMessage(message);
    } finally {
      setIsIntakeSourcesLoading(false);
    }
  };

  const loadOperatorContracts = async () => {
    setOperatorContractsErrorMessage(null);
    setIsOperatorContractsLoading(true);

    try {
      const response = await getOperatorContracts();
      setOperatorContracts(response);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unable to load the operator contracts.";
      setOperatorContractsErrorMessage(message);
      setOperatorContracts(null);
    } finally {
      setIsOperatorContractsLoading(false);
    }
  };

  useEffect(() => {
    void loadPacketQueue(appliedPacketQueueFilters);
    void getLiveSession()
      .then(setLiveSession)
      .catch(() => {
        setLiveSession(null);
      });
  }, []);

  useEffect(() => {
    const handleLocationChange = () => {
      const nextPacketQueueFilters = buildRouteBackedPacketQueueFilters(
        window.location.search,
      );

      setActiveSection(resolveAdminSectionFromPath(window.location.pathname));
      setSelectedPacketId(resolveAdminPacketIdFromSearch(window.location.search));
      setActiveWorkspaceTabOverride(
        resolveAdminWorkspaceTabFromSearch(window.location.search),
      );

      if (
        buildQueueFilterRouteSignature(nextPacketQueueFilters) !==
        buildQueueFilterRouteSignature(appliedPacketQueueFiltersRef.current)
      ) {
        setAppliedPacketQueueRouteState(nextPacketQueueFilters);
        syncPacketQueueFilterInputs(nextPacketQueueFilters);
        void loadPacketQueue(nextPacketQueueFilters);
      }
    };

    window.addEventListener("popstate", handleLocationChange);
    return () => {
      window.removeEventListener("popstate", handleLocationChange);
    };
  }, []);

  useEffect(() => {
    if (activeSection === "sources") {
      void loadIntakeSources();
    }

    if (activeSection === "rules_doctypes") {
      void loadOperatorContracts();
    }
  }, [activeSection]);

  useEffect(() => {
    if (!packetQueue) {
      return;
    }

    if (packetQueue.items.length === 0) {
      setSelectedPacketId(null);
      setActivePacketWorkspace(null);
      replaceAdminSection(activeSection, getAdminRouteOptions({ packetId: null }));
      return;
    }

    const selectedPacketStillVisible =
      selectedPacketId !== null &&
      packetQueue.items.some((item) => item.packet_id === selectedPacketId);
    if (!selectedPacketStillVisible) {
      const nextSelectedPacketId = packetQueue.items[0].packet_id;
      setSelectedPacketId(nextSelectedPacketId);
      replaceAdminSection(
        activeSection,
        getAdminRouteOptions({ packetId: nextSelectedPacketId }),
      );
    }
  }, [activeSection, activeWorkspaceTabOverride, packetQueue, selectedPacketId]);

  useEffect(() => {
    if (!selectedPacketId) {
      return;
    }

    void loadPacketWorkspace(selectedPacketId);
  }, [selectedPacketId]);

  useEffect(() => {
    setPipelineActionErrorMessage(null);
    setPipelineActionSuccessMessage(null);
    setIntakeActionErrorMessage(null);
    setIntakeActionSuccessMessage(null);
    setReviewAssignmentErrorMessage(null);
    setReviewAssignmentSuccessMessage(null);
    setReviewTaskCreateErrorMessage(null);
    setReviewTaskCreateSuccessMessage(null);
  }, [activeSection, selectedPacketId]);

  const queuedPacketCount = packetQueue?.total_count ?? 0;
  const visibleReviewTaskCount =
    packetQueue?.items.reduce((total, item) => total + item.review_task_count, 0) ?? 0;
  const unassignedPacketCount =
    packetQueue?.items.filter((item) => item.assignment_state === "unassigned")
      .length ?? 0;
  const oldestQueueAgeHours =
    packetQueue?.items.reduce(
      (oldestAge, item) => Math.max(oldestAge, item.queue_age_hours),
      0,
    ) ?? 0;
  const visibleAuditEventCount =
    packetQueue?.items.reduce((total, item) => total + item.audit_event_count, 0) ?? 0;
  const visibleOperatorNoteCount =
    packetQueue?.items.reduce((total, item) => total + item.operator_note_count, 0) ?? 0;
  const selectedPacketSummary: PacketQueueItem | null =
    packetQueue?.items.find((item) => item.packet_id === selectedPacketId) || null;
  const selectedPacketAuditEventCount = activePacketWorkspace
    ? activePacketWorkspace.audit_events.length
    : selectedPacketSummary?.audit_event_count ?? 0;
  const selectedPacketOperatorNoteCount = activePacketWorkspace
    ? activePacketWorkspace.operator_notes.length
    : selectedPacketSummary?.operator_note_count ?? 0;
  const selectedPacketReviewTaskCount = activePacketWorkspace
    ? activePacketWorkspace.review_tasks.length
    : selectedPacketSummary?.review_task_count ?? 0;
  const selectedPacketAwaitingReviewCount = selectedPacketSummary?.awaiting_review_document_count ?? 0;
  const currentWorkflowLanePreset: AdminWorkflowLandmarkQueuePreset = {
    stage_name: appliedPacketQueueFilters.stage_name,
    status: appliedPacketQueueFilters.status,
  };
  const activeWorkflowLandmark =
    adminWorkflowLandmarks.find((landmark) =>
      isWorkflowLandmarkActive(
        landmark,
        activeSection,
        currentWorkflowLanePreset,
      ),
    ) ?? null;
  const queueRefreshDeltaCount = Object.keys(packetQueueRefreshDeltas).length;
  const queueRefreshDeltaCounts = summarizePacketQueueRefreshDeltas(
    packetQueueRefreshDeltas,
  );
  const queueContractChangeDeltaCount = queueRefreshDeltaCounts.contractChangeCount;
  const workflowLaneDetail = activeWorkflowLandmark
    ? `Maps to ${activeWorkflowLandmark.mappedSectionsLabel}. Queue lens: ${formatWorkflowLanePreset(activeWorkflowLandmark.queuePreset)}.`
    : `No named lane matches the current queue filters. Queue lens: ${formatWorkflowLanePreset(currentWorkflowLanePreset)}.`;
  const queueRefreshStatusLabel = isQueueLoading ? "Refreshing queue" : "Queue live snapshot";
  const queueRefreshDetail = formatRefreshSnapshot(queueLastLoadedAt);
  const workspaceRefreshDetail = formatRefreshSnapshot(workspaceLastLoadedAt);
  const queueRefreshMovementSummary = formatQueueRefreshDeltaSummary(
    queueRefreshDeltaCounts,
  );
  const visibleQueueActionSummary = buildVisibleQueueActionSummary(
    packetQueue?.items ?? [],
  );
  const queueLensPills = buildQueueLensPills(
    appliedPacketQueueFilters,
    activeWorkflowLandmark,
    visibleQueueActionSummary.visiblePacketCount,
  );

  const applyPacketQueueFilters = () => {
    const filters: PacketQueueFilters = {
      page: 1,
      page_size: defaultPacketQueueFilters.page_size,
      assigned_user_email: assignmentFilter || undefined,
      classification_key: classificationFilter || undefined,
      document_type_key: documentTypeFilter || undefined,
      min_queue_age_hours: minQueueAgeHoursFilter
        ? Number(minQueueAgeHoursFilter)
        : undefined,
      source: sourceFilter || undefined,
      stage_name: stageFilter || undefined,
      status: statusFilter || undefined,
    };
    setAppliedPacketQueueRouteState(filters);
    navigateToAdminSection(activeSection, getAdminRouteOptions({ queueFilters: filters }));
    void loadPacketQueue(filters);
  };

  const resetPacketQueueFilters = () => {
    syncPacketQueueFilterInputs(defaultPacketQueueFilters);
    setAppliedPacketQueueRouteState(defaultPacketQueueFilters);
    navigateToAdminSection(
      activeSection,
      getAdminRouteOptions({ queueFilters: defaultPacketQueueFilters }),
    );
    void loadPacketQueue(defaultPacketQueueFilters);
  };

  const changePacketQueuePage = (nextPage: number) => {
    const filters = {
      ...appliedPacketQueueFilters,
      page: nextPage,
    };
    setAppliedPacketQueueRouteState(filters);
    navigateToAdminSection(activeSection, getAdminRouteOptions({ queueFilters: filters }));
    void loadPacketQueue(filters);
  };

  const refreshSelectedPacketWorkspace = () => {
    if (activeSection === "rules_doctypes") {
      void loadOperatorContracts();
    }

    if (!selectedPacketId) {
      return;
    }

    void loadPacketWorkspace(selectedPacketId);
  };

  const selectAdminSection = (sectionId: AdminSectionId) => {
    setActiveSection(sectionId);
    setActiveWorkspaceTabOverride(null);
    navigateToAdminSection(sectionId, getAdminRouteOptions({ tab: null }));
  };

  const selectWorkflowLandmark = (landmark: AdminWorkflowLandmark) => {
    const nextFilters = buildWorkflowLandmarkQueueFilters(landmark.queuePreset);

    syncPacketQueueFilterInputs(nextFilters);
    setAppliedPacketQueueRouteState(nextFilters);
    setActiveSection(landmark.defaultSectionId);
    setActiveWorkspaceTabOverride(null);
    navigateToAdminSection(
      landmark.defaultSectionId,
      getAdminRouteOptions({ queueFilters: nextFilters, tab: null }),
    );
    void loadPacketQueue(nextFilters);
  };

  const selectWorkspaceTab = (tabId: WorkspaceTabId) => {
    setActiveWorkspaceTabOverride(tabId);
    navigateToAdminSection(activeSection, getAdminRouteOptions({ tab: tabId }));
  };

  const selectPacket = (packetId: string) => {
    setSelectedPacketId(packetId);
    navigateToAdminSection(activeSection, getAdminRouteOptions({ packetId }));
  };

  const replaySelectedPacket = async () => {
    if (!selectedPacketId) {
      return;
    }

    setIntakeActionErrorMessage(null);
    setIntakeActionSuccessMessage(null);
    setIsReplayingPacket(true);

    try {
      const response = await replayPacket(selectedPacketId);
      setIntakeActionSuccessMessage(
        `${response.message} Packet status is ${toSentenceLabel(response.status)}.`,
      );
      await loadPacketQueue(appliedPacketQueueFilters);
      await loadPacketWorkspace(selectedPacketId);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to replay the packet.";
      setIntakeActionErrorMessage(message);
    } finally {
      setIsReplayingPacket(false);
    }
  };

  const runPipelineStage = async (stageName: PacketProcessingStageName) => {
    if (!selectedPacketId) {
      return;
    }

    setPipelineActionErrorMessage(null);
    setPipelineActionSuccessMessage(null);
    setProcessingPipelineAction(`execute:${stageName}`);

    try {
      const response = await executePacketStage(selectedPacketId, stageName);
      setPipelineActionSuccessMessage(
        `${toSentenceLabel(stageName)} executed ${formatCount(response.executed_document_count, "document")}. Packet status is ${toSentenceLabel(response.status)}.`,
      );
      await loadPacketQueue(appliedPacketQueueFilters);
      await loadPacketWorkspace(selectedPacketId);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to execute the packet stage.";
      setPipelineActionErrorMessage(message);
    } finally {
      setProcessingPipelineAction(null);
    }
  };

  const retryPipelineStageWork = async (stageName: PacketProcessingStageName) => {
    if (!selectedPacketId) {
      return;
    }

    setPipelineActionErrorMessage(null);
    setPipelineActionSuccessMessage(null);
    setProcessingPipelineAction(`retry:${stageName}`);

    try {
      const response = await retryPacketStage(selectedPacketId, stageName);
      setPipelineActionSuccessMessage(
        `${toSentenceLabel(stageName)} retried ${formatCount(response.requeued_document_count, "document")}. ${formatCount(response.failed_job_count, "failed job")} and ${formatCount(response.stale_running_job_count, "stale running job")} qualified for intervention.`,
      );
      await loadPacketQueue(appliedPacketQueueFilters);
      await loadPacketWorkspace(selectedPacketId);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to retry the packet stage.";
      setPipelineActionErrorMessage(message);
    } finally {
      setProcessingPipelineAction(null);
    }
  };

  const applyDecision = async (
    decision: PacketWorkspaceReviewDecisionInput,
  ) => {
    setReviewErrorMessage(null);
    setIsReviewDecisionSubmitting(true);

    try {
      await submitPacketReviewDecision(decision.review_task_id, {
        decided_by_email: liveSession?.email || undefined,
        decision_reason_code: decision.decision_reason_code,
        decision_status: decision.decision_status,
        expected_row_version: decision.expected_row_version,
        review_notes: decision.review_notes,
        selected_account_id: decision.selected_account_id,
      });
      await loadPacketQueue(appliedPacketQueueFilters);
      if (selectedPacketId) {
        await loadPacketWorkspace(selectedPacketId);
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unable to update the packet review task.";
      setReviewErrorMessage(message);
      if (
        selectedPacketId &&
        /assigned to|changed while|changed after|already has a recorded decision/i.test(message)
      ) {
        await loadPacketQueue(appliedPacketQueueFilters);
        await loadPacketWorkspace(selectedPacketId);
      }
    } finally {
      setIsReviewDecisionSubmitting(false);
    }
  };

  const applyReviewAssignment = async (
    assignment: PacketWorkspaceReviewAssignmentInput,
  ) => {
    setReviewAssignmentErrorMessage(null);
    setReviewAssignmentSuccessMessage(null);
    setIsReviewAssignmentSubmitting(true);

    try {
      await submitPacketReviewAssignment(assignment.review_task_id, {
        assigned_by_email: liveSession?.email || undefined,
        assigned_user_email: assignment.assigned_user_email ?? null,
        assigned_user_id: assignment.assigned_user_id ?? null,
        expected_row_version: assignment.expected_row_version,
      });
      setReviewAssignmentSuccessMessage(
        assignment.assigned_user_email?.trim()
          ? "Updated assignee for the selected review task."
          : "Cleared assignee for the selected review task.",
      );
      await loadPacketQueue(appliedPacketQueueFilters);
      if (selectedPacketId) {
        await loadPacketWorkspace(selectedPacketId);
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unable to update the review-task assignment.";
      setReviewAssignmentErrorMessage(message);
      if (
        selectedPacketId &&
        /assigned to|changed while|changed after|already has a recorded decision/i.test(message)
      ) {
        await loadPacketQueue(appliedPacketQueueFilters);
        await loadPacketWorkspace(selectedPacketId);
      }
    } finally {
      setIsReviewAssignmentSubmitting(false);
    }
  };

  const createReviewTask = async (
    reviewTask: PacketWorkspaceReviewTaskCreateInput,
  ) => {
    if (!selectedPacketId) {
      return;
    }

    const documentLabel =
      activePacketWorkspace?.documents.find(
        (document) => document.document_id === reviewTask.document_id,
      )?.file_name || "the selected document";

    setReviewTaskCreateErrorMessage(null);
    setReviewTaskCreateSuccessMessage(null);
    setIsReviewTaskCreateSubmitting(true);

    try {
      await submitPacketReviewTaskCreate(selectedPacketId, reviewTask.document_id, {
        assigned_user_email: reviewTask.assigned_user_email ?? null,
        assigned_user_id: reviewTask.assigned_user_id ?? null,
        created_by_email: liveSession?.email || undefined,
        notes_summary: reviewTask.notes_summary ?? null,
        selected_account_id: reviewTask.selected_account_id ?? null,
      });
      setReviewTaskCreateSuccessMessage(
        `Created a review task for ${documentLabel}.`,
      );
      await loadPacketQueue(appliedPacketQueueFilters);
      await loadPacketWorkspace(selectedPacketId);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to create the review task.";
      setReviewTaskCreateErrorMessage(message);
      if (
        /already has a persisted review task|could not be loaded|does not belong to packet/i.test(
          message,
        )
      ) {
        await loadPacketQueue(appliedPacketQueueFilters);
        await loadPacketWorkspace(selectedPacketId);
      }
    } finally {
      setIsReviewTaskCreateSubmitting(false);
    }
  };

  const applyExtractionEdits = async (
    extractionEdit: PacketWorkspaceExtractionEditInput,
  ) => {
    setExtractionEditErrorMessage(null);
    setExtractionEditSuccessMessage(null);
    setIsExtractionEditSubmitting(true);

    try {
      const response = await submitPacketReviewExtractionEdits(
        extractionEdit.review_task_id,
        {
          edited_by_email: liveSession?.email || undefined,
          expected_row_version: extractionEdit.expected_row_version,
          field_edits: extractionEdit.field_edits,
        },
      );
      setExtractionEditSuccessMessage(
        `Saved ${formatCount(response.changed_fields.length, "field edit")} for the selected review task.`,
      );
      await loadPacketQueue(appliedPacketQueueFilters);
      if (selectedPacketId) {
        await loadPacketWorkspace(selectedPacketId);
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unable to persist the extracted field edits.";
      setExtractionEditErrorMessage(message);
      if (
        selectedPacketId &&
        /assigned to|changed while|changed after|already has a recorded decision/i.test(message)
      ) {
        await loadPacketQueue(appliedPacketQueueFilters);
        await loadPacketWorkspace(selectedPacketId);
      }
    } finally {
      setIsExtractionEditSubmitting(false);
    }
  };

  const applyReviewNote = async (reviewNote: PacketWorkspaceReviewNoteInput) => {
    setReviewNoteErrorMessage(null);
    setReviewNoteSuccessMessage(null);
    setIsReviewNoteSubmitting(true);

    try {
      await submitPacketReviewNote(reviewNote.review_task_id, {
        created_by_email: liveSession?.email || undefined,
        expected_row_version: reviewNote.expected_row_version,
        is_private: reviewNote.is_private,
        note_text: reviewNote.note_text,
      });
      setReviewNoteSuccessMessage("Saved note for the selected review task.");
      await loadPacketQueue(appliedPacketQueueFilters);
      if (selectedPacketId) {
        await loadPacketWorkspace(selectedPacketId);
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unable to persist the review-task note.";
      setReviewNoteErrorMessage(message);
      if (
        selectedPacketId &&
        /assigned to|changed while|changed after|already has a recorded decision/i.test(message)
      ) {
        await loadPacketQueue(appliedPacketQueueFilters);
        await loadPacketWorkspace(selectedPacketId);
      }
    } finally {
      setIsReviewNoteSubmitting(false);
    }
  };

  const reviewRecommendation = async (
    recommendationResultId: string,
    disposition: RecommendationReviewDisposition,
  ) => {
    if (!selectedPacketId) {
      return;
    }

    setRecommendationActionErrorMessage(null);
    setRecommendationActionSuccessMessage(null);
    setProcessingRecommendationReview(
      `${recommendationResultId}:${disposition}`,
    );

    try {
      const response = await reviewPacketRecommendation(
        selectedPacketId,
        recommendationResultId,
        {
          disposition,
          reviewed_by_email: liveSession?.email || undefined,
        },
      );
      setRecommendationActionSuccessMessage(
        `${toSentenceLabel(disposition)} ${response.recommendation_result.recommendation_kind} for ${response.recommendation_result.document_id || "packet-level guidance"}.`,
      );
      await loadPacketQueue(appliedPacketQueueFilters);
      await loadPacketWorkspace(selectedPacketId);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unable to review the recommendation result.";
      setRecommendationActionErrorMessage(message);
    } finally {
      setProcessingRecommendationReview(null);
    }
  };

  const runSource = async (sourceId: string) => {
    setIntakeSourcesErrorMessage(null);
    setIntakeSourcesSuccessMessage(null);
    setRunningSourceId(sourceId);

    try {
      const response = await executeIntakeSource(sourceId);
      setLatestIntakeSourceExecution(response);
      await loadIntakeSources();
      await loadPacketQueue(appliedPacketQueueFilters);
      const latestPacketId = response.packet_results[0]?.packet_id;
      if (latestPacketId) {
        selectPacket(latestPacketId);
        await loadPacketWorkspace(latestPacketId);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to execute intake source.";
      setIntakeSourcesErrorMessage(message);
    } finally {
      setRunningSourceId(null);
    }
  };

  const createSourceDefinition = async (request: IntakeSourceCreateRequest) => {
    setIntakeSourcesErrorMessage(null);
    setIntakeSourcesSuccessMessage(null);
    setIsCreatingSource(true);

    try {
      const response = await createIntakeSource(request);
      setIntakeSources((currentSources) =>
        sortIntakeSources([
          ...currentSources.filter((source) => source.source_id !== response.source_id),
          response,
        ]),
      );
      setLatestIntakeSourceExecution(null);
      setIntakeSourcesSuccessMessage(`Created source ${response.source_name}.`);
      return true;
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to create intake source.";
      setIntakeSourcesErrorMessage(message);
      return false;
    } finally {
      setIsCreatingSource(false);
    }
  };

  const updateSourceDefinition = async (
    sourceId: string,
    request: IntakeSourceUpdateRequest,
  ) => {
    setIntakeSourcesErrorMessage(null);
    setIntakeSourcesSuccessMessage(null);
    setSavingSourceId(sourceId);

    try {
      const response = await updateIntakeSource(sourceId, request);
      setIntakeSources((currentSources) =>
        sortIntakeSources(
          currentSources.map((source) =>
            source.source_id === response.source_id ? response : source,
          ),
        ),
      );
      setLatestIntakeSourceExecution((currentExecution) => {
        if (!currentExecution || currentExecution.source_id !== response.source_id) {
          return currentExecution;
        }

        return {
          ...currentExecution,
          source_kind: response.configuration.source_kind,
          source_name: response.source_name,
        };
      });
      setIntakeSourcesSuccessMessage(`Saved source ${response.source_name}.`);
      return true;
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to update intake source.";
      setIntakeSourcesErrorMessage(message);
      return false;
    } finally {
      setSavingSourceId(null);
    }
  };

  const toggleSourceDefinitionEnablement = async (
    sourceId: string,
    isEnabled: boolean,
  ) => {
    setIntakeSourcesErrorMessage(null);
    setIntakeSourcesSuccessMessage(null);
    setTogglingSourceId(sourceId);

    try {
      const response = await setIntakeSourceEnablement(sourceId, isEnabled);
      setIntakeSources((currentSources) =>
        sortIntakeSources(
          currentSources.map((source) =>
            source.source_id === response.source_id ? response : source,
          ),
        ),
      );
      setIntakeSourcesSuccessMessage(
        response.is_enabled
          ? `Resumed source ${response.source_name}.`
          : `Paused source ${response.source_name}.`,
      );
      return true;
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unable to update source enablement.";
      setIntakeSourcesErrorMessage(message);
      return false;
    } finally {
      setTogglingSourceId(null);
    }
  };

  const deleteSourceDefinition = async (sourceId: string) => {
    setIntakeSourcesErrorMessage(null);
    setIntakeSourcesSuccessMessage(null);
    setDeletingSourceId(sourceId);

    try {
      const response = await deleteIntakeSource(sourceId);
      setIntakeSources((currentSources) =>
        currentSources.filter((source) => source.source_id !== sourceId),
      );
      setLatestIntakeSourceExecution((currentExecution) =>
        currentExecution?.source_id === sourceId ? null : currentExecution,
      );
      setIntakeSourcesSuccessMessage(`Deleted source ${response.source_name}.`);
      return true;
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to delete intake source.";
      setIntakeSourcesErrorMessage(message);
      return false;
    } finally {
      setDeletingSourceId(null);
    }
  };

  return (
    <ProtectedSiteLayout
      navigation={
        <AdminNavigation
          activeSection={activeSection}
          activeQueueFilters={appliedPacketQueueFilters}
          onSelectSection={selectAdminSection}
          onSelectWorkflowLandmark={selectWorkflowLandmark}
          queueCount={queuedPacketCount}
          selectedPacketName={selectedPacketSummary?.packet_name || null}
          unassignedPacketCount={unassignedPacketCount}
          visibleQueueItems={packetQueue?.items ?? []}
        />
      }
      operatorEmail={liveSession?.email}
    >
          <header className="hero hero-wide">
            <div>
              <p className="eyebrow">Live operator shell</p>
              <h1>Debt-relief paperwork without the spreadsheet graveyard.</h1>
              <p className="hero-copy">
                The operator flow now runs through a packet-first admin shell
                backed by the SQL queue, workspace, and review-task APIs so
                reviewer decisions no longer need the legacy Cosmos review cards.
              </p>
            </div>
            <div className="hero-panel">
              <span>Access posture</span>
              <strong>
                {liveSession?.email
                  ? `Signed in as ${liveSession.email}`
                  : "Microsoft-auth protected admin site"}
              </strong>
              <p>
                The protected admin host now fronts both the packet queue and the
                packet workspace so the React shell can review, decide, and refresh
                packet state without bouncing through the legacy document queue.
              </p>
            </div>
          </header>

          <section className="metrics-grid" aria-label="queue metrics">
            <article className="metric-card">
              <span>Queued packets</span>
              <strong>{queuedPacketCount}</strong>
            </article>
            <article className="metric-card">
              <span>Visible review tasks</span>
              <strong>{visibleReviewTaskCount}</strong>
            </article>
            <article className="metric-card">
              <span>Oldest queue age</span>
              <strong>{formatQueueAge(oldestQueueAgeHours)}</strong>
              <p className="metric-detail">
                {unassignedPacketCount} packet rows are unassigned.
              </p>
            </article>
            <article className="metric-card">
              <span>Visible audit signals</span>
              <strong>{visibleAuditEventCount}</strong>
              <p className="metric-detail">
                {visibleOperatorNoteCount} operator note{visibleOperatorNoteCount === 1 ? "" : "s"} across the current queue slice.
              </p>
            </article>
          </section>

          <section className="workbench-layout workspace-layout-wide">
            <div className="queue-column">
              {activeSectionConfig.showManualUploadPanel ? (
                <ManualUploadPanel reviewerEmail={liveSession?.email} />
              ) : null}

              {activeSectionConfig.showSourcesPanel ? (
                <IntakeSourcesPanel
                  deletingSourceId={deletingSourceId}
                  errorMessage={intakeSourcesErrorMessage}
                  executionSummary={latestIntakeSourceExecution}
                  executingSourceId={runningSourceId}
                  isCreatingSource={isCreatingSource}
                  isLoading={isIntakeSourcesLoading}
                  onCreateSource={createSourceDefinition}
                  onDeleteSource={deleteSourceDefinition}
                  onExecuteSource={(sourceId) => {
                    void runSource(sourceId);
                  }}
                  onRefresh={() => {
                    void loadIntakeSources();
                  }}
                  onSetSourceEnablement={toggleSourceDefinitionEnablement}
                  onUpdateSource={updateSourceDefinition}
                  savingSourceId={savingSourceId}
                  sources={intakeSources}
                  successMessage={intakeSourcesSuccessMessage}
                  togglingSourceId={togglingSourceId}
                />
              ) : null}

              <section className="surface-card queue-surface">
                <div className="section-heading section-heading-row">
                  <div>
                    <h2>Packet queue</h2>
                    <p>{activeSectionConfig.queueDescription}</p>
                  </div>
                  <div className="queue-surface-actions">
                    <div className="queue-refresh-copy">
                      <StatusBadge tone={getRefreshTone(isQueueLoading, queueErrorMessage, queueLastLoadedAt)}>
                        {queueRefreshStatusLabel}
                      </StatusBadge>
                      <p>
                        {queueRefreshDetail}
                        {!isQueueLoading && queueRefreshDeltaCount > 0
                          ? ` · ${formatCount(queueRefreshDeltaCount, "packet row")} changed since last snapshot`
                          : ""}
                        {selectedPacketSummary
                          ? ` · selected packet updated ${formatDateTime(selectedPacketSummary.updated_at_utc)}`
                          : ""}
                      </p>
                    </div>
                    <button
                      className="ghost-button"
                      disabled={isQueueLoading}
                      onClick={() => {
                        void loadPacketQueue(appliedPacketQueueFilters);
                      }}
                      type="button"
                    >
                      {isQueueLoading ? "Refreshing packets..." : "Refresh packets"}
                    </button>
                  </div>
                </div>

                <SurfaceCard
                  aria-label="Current queue lens"
                  as="section"
                  className="queue-lens-summary"
                >
                  <div className="queue-lens-heading">
                    <div className="queue-lens-copy-block">
                      <p className="queue-lens-label">Current queue lens</p>
                      <strong className="queue-lens-title">
                        {activeWorkflowLandmark?.label || "Custom queue lens"}
                      </strong>
                      <p className="queue-lens-copy">{workflowLaneDetail}</p>
                      <div className="queue-lens-urgency">
                        <StatusBadge tone={visibleQueueActionSummary.dominantActionTone}>
                          Best next
                        </StatusBadge>
                        <p className="queue-lens-urgency-copy">
                          {formatVisibleQueueActionSummary(visibleQueueActionSummary)}
                        </p>
                      </div>
                    </div>
                    <StatusBadge tone={activeWorkflowLandmark ? "accent" : "neutral"}>
                      {activeWorkflowLandmark ? "Named lane" : "Custom lens"}
                    </StatusBadge>
                  </div>

                  <div className="queue-lens-pill-list">
                    {queueLensPills.map((pill) => (
                      <span
                        className={
                          pill.isAccent
                            ? "queue-inline-pill queue-inline-pill-accent"
                            : "queue-inline-pill"
                        }
                        key={pill.key}
                      >
                        {pill.label}
                      </span>
                    ))}
                  </div>
                </SurfaceCard>

                <form
                  className="queue-filter-panel"
                  onSubmit={(event) => {
                    event.preventDefault();
                    applyPacketQueueFilters();
                  }}
                >
                  <div className="queue-filter-grid">
                    <label className="filter-field">
                      <span>Stage</span>
                      <select
                        onChange={(event) => {
                          setStageFilter(event.target.value);
                        }}
                        value={stageFilter}
                      >
                        <option value="">All stages</option>
                        <option value="intake">Intake</option>
                        <option value="archive_expansion">Archive expansion</option>
                        <option value="classification">Classification</option>
                        <option value="ocr">OCR</option>
                        <option value="extraction">Extraction</option>
                        <option value="matching">Matching</option>
                        <option value="review">Review</option>
                        <option value="recommendation">Recommendation</option>
                        <option value="quarantine">Quarantine</option>
                      </select>
                    </label>

                    <label className="filter-field">
                      <span>Source</span>
                      <select
                        onChange={(event) => {
                          setSourceFilter(event.target.value);
                        }}
                        value={sourceFilter}
                      >
                        <option value="">All sources</option>
                        <option value="scanned_upload">Manual upload</option>
                        <option value="azure_blob">Watched Blob</option>
                        <option value="configured_folder">Configured folder</option>
                        <option value="azure_sftp">Watched SFTP</option>
                        <option value="email_connector">Email connector</option>
                        <option value="partner_api_feed">Partner API</option>
                      </select>
                    </label>

                    <label className="filter-field">
                      <span>Status</span>
                      <select
                        onChange={(event) => {
                          setStatusFilter(event.target.value);
                        }}
                        value={statusFilter}
                      >
                        <option value="">All statuses</option>
                        <option value="received">Received</option>
                        <option value="archive_expanding">Archive expanding</option>
                        <option value="classifying">Classifying</option>
                        <option value="ocr_running">OCR running</option>
                        <option value="extracting">Extracting</option>
                        <option value="matching">Matching</option>
                        <option value="awaiting_review">Awaiting review</option>
                        <option value="ready_for_recommendation">
                          Ready for recommendation
                        </option>
                        <option value="completed">Completed</option>
                        <option value="blocked">Blocked</option>
                        <option value="failed">Failed</option>
                        <option value="quarantined">Quarantined</option>
                      </select>
                    </label>

                    <label className="filter-field">
                      <span>Assignment</span>
                      <input
                        onChange={(event) => {
                          setAssignmentFilter(event.target.value);
                        }}
                        placeholder="ops@example.com or unassigned"
                        type="text"
                        value={assignmentFilter}
                      />
                    </label>

                    <label className="filter-field">
                      <span>Classification</span>
                      <input
                        onChange={(event) => {
                          setClassificationFilter(event.target.value);
                        }}
                        placeholder="bank_correspondence"
                        type="text"
                        value={classificationFilter}
                      />
                    </label>

                    <label className="filter-field">
                      <span>Document type</span>
                      <input
                        onChange={(event) => {
                          setDocumentTypeFilter(event.target.value);
                        }}
                        placeholder="bank_statement"
                        type="text"
                        value={documentTypeFilter}
                      />
                    </label>

                    <label className="filter-field">
                      <span>Minimum age hours</span>
                      <input
                        min="0"
                        onChange={(event) => {
                          setMinQueueAgeHoursFilter(event.target.value);
                        }}
                        placeholder="4"
                        step="0.5"
                        type="number"
                        value={minQueueAgeHoursFilter}
                      />
                    </label>
                  </div>

                  <div className="queue-filter-actions">
                    <button
                      className="ghost-button"
                      onClick={resetPacketQueueFilters}
                      type="button"
                    >
                      Reset filters
                    </button>
                    <button disabled={isQueueLoading} type="submit">
                      Apply filters
                    </button>
                  </div>
                </form>

                {queueErrorMessage ? (
                  <p className="status-banner status-error">{queueErrorMessage}</p>
                ) : null}

                {isQueueLoading ? (
                  <div className="status-panel">
                    Loading packet queue from Functions...
                  </div>
                ) : !packetQueue || packetQueue.items.length === 0 ? (
                  <div className="status-panel">
                    No packets match the current queue filters.
                  </div>
                ) : (
                  <>
                    <PacketQueueTable
                      items={packetQueue.items}
                      onSelectPacket={(item) => {
                        selectPacket(item.packet_id);
                      }}
                      refreshDeltasByPacketId={packetQueueRefreshDeltas}
                      selectedPacketId={selectedPacketId}
                    />
                    <div className="queue-pagination">
                      <p>
                        Page {packetQueue.page} · showing {packetQueue.items.length} of {packetQueue.total_count}
                      </p>
                      <div className="queue-pagination-actions">
                        <button
                          className="ghost-button"
                          disabled={isQueueLoading || packetQueue.page <= 1}
                          onClick={() => {
                            changePacketQueuePage(packetQueue.page - 1);
                          }}
                          type="button"
                        >
                          Previous
                        </button>
                        <button
                          disabled={isQueueLoading || !packetQueue.has_more}
                          onClick={() => {
                            changePacketQueuePage(packetQueue.page + 1);
                          }}
                          type="button"
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </section>

              <SurfacePanel className="workspace-status-panel">
                <SectionHeading
                  description="The selected packet workspace on the right is the primary operator surface for this section. Review and recommendation actions now post through the SQL-backed packet routes, so the legacy Cosmos document cards are no longer required here."
                  title="Workspace focus"
                />

                <div className="workspace-summary-grid">
                  <SurfaceMetricCard
                    badge={<StatusBadge tone="accent">Active section</StatusBadge>}
                    className="workspace-summary-card"
                    detail={`${toSentenceLabel(activeSectionConfig.preferredWorkspaceTab)} tab opens first for this workspace.`}
                    title="Live section focus"
                    value={activeSectionConfig.panelTitle}
                  />

                  <SurfaceMetricCard
                    badge={
                      <StatusBadge tone={activeWorkflowLandmark ? "accent" : "neutral"}>
                        {activeWorkflowLandmark ? "Named lane" : "Custom lens"}
                      </StatusBadge>
                    }
                    className="workspace-summary-card"
                    detail={workflowLaneDetail}
                    title="Workflow lane"
                    value={activeWorkflowLandmark?.label || "Custom queue lens"}
                  />

                  <SurfaceMetricCard
                    badge={
                      <StatusBadge tone={selectedPacketSummary ? "success" : "neutral"}>
                        Packet focus
                      </StatusBadge>
                    }
                    className="workspace-summary-card"
                    detail={
                      selectedPacketSummary
                        ? `${toSentenceLabel(selectedPacketSummary.status)} from ${selectedPacketSummary.source.replace(/_/g, " ")} · updated ${formatDateTime(selectedPacketSummary.updated_at_utc)}.`
                        : "Select a packet row from the queue to load the SQL-backed workspace."
                    }
                    title="Pinned packet"
                    value={selectedPacketSummary?.packet_name || "No packet selected"}
                  />

                  <SurfaceMetricCard
                    badge={
                      <StatusBadge
                        tone={selectedPacketSummary ? getPacketStatusTone(selectedPacketSummary.status) : "neutral"}
                      >
                        Packet operational state
                      </StatusBadge>
                    }
                    className="workspace-summary-card"
                    detail={
                      selectedPacketSummary
                        ? `${selectedPacketReviewTaskCount} review task${selectedPacketReviewTaskCount === 1 ? "" : "s"} · ${selectedPacketAwaitingReviewCount} awaiting review.`
                        : "Choose a packet to inspect its current queue posture and workflow state."
                    }
                    title="Stage and status"
                    value={
                      selectedPacketSummary
                        ? `${toSentenceLabel(selectedPacketSummary.status)} · ${toSentenceLabel(selectedPacketSummary.stage_name)}`
                        : "No packet selected"
                    }
                  />

                  <SurfaceMetricCard
                    badge={
                      <StatusBadge
                        tone={
                          selectedPacketAuditEventCount > 0 || selectedPacketOperatorNoteCount > 0
                            ? "accent"
                            : "neutral"
                        }
                      >
                        Packet signals
                      </StatusBadge>
                    }
                    className="workspace-summary-card"
                    detail={
                      selectedPacketSummary
                        ? `${selectedPacketReviewTaskCount} review task${selectedPacketReviewTaskCount === 1 ? "" : "s"} currently attached to the packet.`
                        : "Queue and workspace counts will appear after you pin a packet row."
                    }
                    title="Audit trail and notes"
                    value={
                      selectedPacketSummary
                        ? `${formatCount(selectedPacketAuditEventCount, "audit event")} · ${formatCount(selectedPacketOperatorNoteCount, "note")}`
                        : "Awaiting packet focus"
                    }
                  />

                  <SurfaceMetricCard
                    badge={
                      <StatusBadge
                        tone={unassignedPacketCount > 0 ? "warning" : "success"}
                      >
                        Queue posture
                      </StatusBadge>
                    }
                    className="workspace-summary-card"
                    detail={`${unassignedPacketCount} unassigned with ${formatQueueAge(oldestQueueAgeHours)} oldest packet age in the current view.`}
                    title="Current queue slice"
                    value={`${queuedPacketCount} queued`}
                  />

                  <SurfaceMetricCard
                    badge={
                      <StatusBadge
                        tone={getRefreshTone(
                          isQueueLoading || isPacketWorkspaceLoading,
                          queueErrorMessage || activePacketWorkspaceErrorMessage,
                          queueLastLoadedAt || workspaceLastLoadedAt,
                        )}
                      >
                        Live refresh
                      </StatusBadge>
                    }
                    className="workspace-summary-card"
                    detail={`Queue: ${queueRefreshDetail} · Workspace: ${workspaceRefreshDetail}${!isQueueLoading && queueContractChangeDeltaCount > 0 ? ` · ${formatCount(queueContractChangeDeltaCount, "contract summary")} changed since last snapshot` : ""}`}
                    title="Operator snapshot"
                    value={
                      isQueueLoading || isPacketWorkspaceLoading
                        ? "Refreshing..."
                        : queueContractChangeDeltaCount > 0
                          ? `${formatCount(queueContractChangeDeltaCount, "contract summary")} changed`
                          : "Ready"
                    }
                  />

                  <SurfaceMetricCard
                    badge={
                      <StatusBadge tone={queueRefreshDeltaCount > 0 ? "accent" : "neutral"}>
                        Queue movement
                      </StatusBadge>
                    }
                    className="workspace-summary-card"
                    detail={queueRefreshMovementSummary}
                    title="Refresh deltas"
                    value={
                      queueRefreshDeltaCount > 0
                        ? `${formatCount(queueRefreshDeltaCount, "packet row")} changed`
                        : "No queue-row changes"
                    }
                  />
                </div>
              </SurfacePanel>
            </div>

            <SurfaceDrawer as="aside" className="operations-panel workspace-aside-panel">
              <PacketWorkspacePanel
                assignmentErrorMessage={reviewAssignmentErrorMessage}
                assignmentSuccessMessage={reviewAssignmentSuccessMessage}
                createTaskErrorMessage={reviewTaskCreateErrorMessage}
                createTaskSuccessMessage={reviewTaskCreateSuccessMessage}
                decisionErrorMessage={reviewErrorMessage}
                errorMessage={activePacketWorkspaceErrorMessage}
                extractionEditErrorMessage={extractionEditErrorMessage}
                extractionEditSuccessMessage={extractionEditSuccessMessage}
                intakeActionErrorMessage={intakeActionErrorMessage}
                intakeActionSuccessMessage={intakeActionSuccessMessage}
                isAssignmentSubmitting={isReviewAssignmentSubmitting}
                isExtractionEditSubmitting={isExtractionEditSubmitting}
                isDecisionSubmitting={isReviewDecisionSubmitting}
                isNoteSubmitting={isReviewNoteSubmitting}
                isReviewTaskCreateSubmitting={isReviewTaskCreateSubmitting}
                isLoading={isPacketWorkspaceLoading}
                isOperatorContractsLoading={isOperatorContractsLoading}
                isReplayingPacket={isReplayingPacket}
                noteErrorMessage={reviewNoteErrorMessage}
                noteSuccessMessage={reviewNoteSuccessMessage}
                onReviewRecommendation={(recommendationResultId, disposition) => {
                  void reviewRecommendation(recommendationResultId, disposition);
                }}
                onExecuteStage={(stageName) => {
                  void runPipelineStage(stageName);
                }}
                onRefresh={refreshSelectedPacketWorkspace}
                onReplayPacket={() => {
                  void replaySelectedPacket();
                }}
                onSubmitExtractionEdits={(extractionEdit) => {
                  void applyExtractionEdits(extractionEdit);
                }}
                onSubmitReviewAssignment={(assignment) => {
                  void applyReviewAssignment(assignment);
                }}
                onSubmitReviewNote={(reviewNote) => {
                  void applyReviewNote(reviewNote);
                }}
                onSubmitReviewTaskCreate={(reviewTask) => {
                  void createReviewTask(reviewTask);
                }}
                onRetryStage={(stageName) => {
                  void retryPipelineStageWork(stageName);
                }}
                onSubmitReviewDecision={(decision) => {
                  void applyDecision(decision);
                }}
                operatorContracts={operatorContracts}
                operatorContractsErrorMessage={operatorContractsErrorMessage}
                panelDescription={activeSectionConfig.panelDescription}
                panelTitle={activeSectionConfig.panelTitle}
                pipelineActionErrorMessage={pipelineActionErrorMessage}
                pipelineActionSuccessMessage={pipelineActionSuccessMessage}
                preferredTab={preferredWorkspaceTab}
                processingRecommendationReview={processingRecommendationReview}
                processingPipelineAction={processingPipelineAction}
                recommendationActionErrorMessage={recommendationActionErrorMessage}
                recommendationActionSuccessMessage={recommendationActionSuccessMessage}
                reviewerEmail={liveSession?.email || null}
                selectedPacketSummary={selectedPacketSummary}
                tabPriorityAnchor={activeSectionConfig.preferredWorkspaceTab}
                workspace={activePacketWorkspace}
                workspaceLastLoadedAt={workspaceLastLoadedAt}
                onSelectTab={selectWorkspaceTab}
              />
            </SurfaceDrawer>
          </section>
    </ProtectedSiteLayout>
  );
}
export type ArchivePreflightResult = {
  archive_format?: string | null;
  disposition: string;
  entry_count: number;
  expected_disk_count?: number | null;
  is_archive: boolean;
  is_multipart_archive: boolean;
  message?: string | null;
  nested_archive_count: number;
  total_uncompressed_bytes: number;
  uses_zip64: boolean;
};

export type ArchiveDocumentLineage = {
  archive_depth: number;
  archive_member_path?: string | null;
  parent_document_id?: string | null;
  source_asset_id?: string | null;
};

export type PacketRecord = {
  created_at_utc: string;
  duplicate_detection?: Record<string, unknown> | null;
  packet_fingerprint?: string | null;
  packet_id: string;
  packet_name: string;
  packet_tags: string[];
  received_at_utc: string;
  source: string;
  source_fingerprint?: string | null;
  source_uri?: string | null;
  status: string;
  submitted_by?: string | null;
  updated_at_utc: string;
};

export type PacketDocumentRecord = {
  account_candidates: string[];
  archive_preflight: ArchivePreflightResult;
  content_type: string;
  created_at_utc: string;
  document_id: string;
  document_text?: string | null;
  file_hash_sha256?: string | null;
  file_name: string;
  issuer_category: string;
  issuer_name?: string | null;
  lineage?: ArchiveDocumentLineage | null;
  packet_id: string;
  received_at_utc: string;
  requested_prompt_profile_id?: string | null;
  source: string;
  source_summary?: string | null;
  source_tags: string[];
  source_uri?: string | null;
  status: string;
  updated_at_utc: string;
};

export type DocumentAssetRecord = {
  asset_id: string;
  asset_role: string;
  blob_name: string;
  container_name: string;
  content_length_bytes: number;
  content_type: string;
  created_at_utc: string;
  document_id: string;
  packet_id: string;
  storage_uri: string;
};

export type PacketEventRecord = {
  created_at_utc: string;
  document_id?: string | null;
  event_id: number;
  event_payload?: Record<string, unknown> | null;
  event_type: string;
  packet_id: string;
};

export type ProcessingJobRecord = {
  attempt_number: number;
  completed_at_utc?: string | null;
  created_at_utc: string;
  document_id?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  job_id: string;
  packet_id: string;
  queued_at_utc: string;
  stage_name: string;
  started_at_utc?: string | null;
  status: string;
  updated_at_utc: string;
};

export type OcrResultRecord = {
  created_at_utc: string;
  document_id: string;
  model_name?: string | null;
  ocr_confidence: number;
  ocr_result_id: string;
  packet_id: string;
  page_count: number;
  provider: string;
  text_excerpt?: string | null;
  text_storage_uri?: string | null;
};

export type ExtractionResultRecord = {
  created_at_utc: string;
  document_id: string;
  document_type?: string | null;
  extraction_result_id: string;
  model_name?: string | null;
  packet_id: string;
  prompt_profile_id?: string | null;
  provider: string;
  result_payload: Record<string, unknown>;
  summary?: string | null;
};

export type ClassificationResultRecord = {
  classification_id?: string | null;
  classification_result_id: string;
  confidence: number;
  created_at_utc: string;
  document_id: string;
  document_type_id?: string | null;
  packet_id: string;
  prompt_profile_id?: string | null;
  result_payload: Record<string, unknown>;
  result_source: string;
};

export type AccountMatchCandidate = {
  account_id: string;
  account_number?: string | null;
  debtor_name?: string | null;
  issuer_name?: string | null;
  matched_on: string[];
  score: number;
};

export type AccountMatchRunRecord = {
  candidates: AccountMatchCandidate[];
  created_at_utc: string;
  document_id: string;
  match_run_id: string;
  packet_id: string;
  rationale?: string | null;
  selected_account_id?: string | null;
  status: string;
};

export type ReviewTaskRecord = {
  assigned_user_email?: string | null;
  assigned_user_id?: string | null;
  created_at_utc: string;
  document_id: string;
  due_at_utc?: string | null;
  notes_summary?: string | null;
  packet_id: string;
  priority: string;
  reason_codes: string[];
  review_task_id: string;
  row_version?: string | null;
  selected_account_id?: string | null;
  status: string;
  updated_at_utc: string;
};

export type ReviewDecisionRecord = {
  decided_at_utc: string;
  decided_by_email?: string | null;
  decided_by_user_id?: string | null;
  decision_id: string;
  decision_reason_code?: string | null;
  decision_status: string;
  document_id: string;
  packet_id: string;
  review_notes?: string | null;
  review_task_id: string;
  selected_account_id?: string | null;
};

export type OperatorNoteRecord = {
  created_at_utc: string;
  created_by_email?: string | null;
  created_by_user_id?: string | null;
  document_id?: string | null;
  is_private: boolean;
  note_id: string;
  note_text: string;
  packet_id?: string | null;
  review_task_id?: string | null;
};

export type AuditEventRecord = {
  actor_email?: string | null;
  actor_user_id?: string | null;
  audit_event_id: number;
  created_at_utc: string;
  document_id?: string | null;
  event_payload?: Record<string, unknown> | null;
  event_type: string;
  packet_id?: string | null;
  review_task_id?: string | null;
};

export type RecommendationRunRecord = {
  completed_at_utc?: string | null;
  created_at_utc: string;
  document_id?: string | null;
  input_payload: Record<string, unknown>;
  packet_id: string;
  prompt_profile_id?: string | null;
  recommendation_run_id: string;
  requested_by_email?: string | null;
  requested_by_user_id?: string | null;
  review_task_id?: string | null;
  status: string;
  updated_at_utc: string;
};

export type RecommendationEvidenceItem = {
  evidence_kind: string;
  field_name?: string | null;
  source_document_id?: string | null;
  source_excerpt?: string | null;
  storage_uri?: string | null;
};

export type RecommendationResultRecord = {
  advisory_text?: string | null;
  confidence: number;
  created_at_utc: string;
  disposition: string;
  document_id?: string | null;
  evidence_items: RecommendationEvidenceItem[];
  packet_id: string;
  rationale_payload: Record<string, unknown>;
  recommendation_kind: string;
  recommendation_result_id: string;
  recommendation_run_id: string;
  reviewed_at_utc?: string | null;
  reviewed_by_email?: string | null;
  reviewed_by_user_id?: string | null;
  summary: string;
  updated_at_utc: string;
};

export type PacketWorkspaceSnapshot = {
  account_match_runs: AccountMatchRunRecord[];
  audit_events: AuditEventRecord[];
  classification_results: ClassificationResultRecord[];
  document_assets: DocumentAssetRecord[];
  documents: PacketDocumentRecord[];
  extraction_results: ExtractionResultRecord[];
  ocr_results: OcrResultRecord[];
  operator_notes: OperatorNoteRecord[];
  packet: PacketRecord;
  packet_events: PacketEventRecord[];
  processing_jobs: ProcessingJobRecord[];
  recommendation_results: RecommendationResultRecord[];
  recommendation_runs: RecommendationRunRecord[];
  review_decisions: ReviewDecisionRecord[];
  review_tasks: ReviewTaskRecord[];
};

export type PacketProcessingStageName =
  | "classification"
  | "ocr"
  | "extraction"
  | "recommendation";

export type PacketStageExecutionResponse = {
  executed_document_count: number;
  next_stage: string;
  packet_id: string;
  skipped_document_ids: string[];
  status: string;
};

export type PacketStageRetryResponse = {
  executed_document_count: number;
  failed_job_count: number;
  next_stage?: string | null;
  packet_id: string;
  requeued_document_count: number;
  skipped_document_ids: string[];
  stage_name: string;
  stale_running_job_count: number;
  status: string;
};

export type PacketReplayAction = "execute" | "retry";

export type PacketReplayResponse = {
  action: PacketReplayAction;
  executed_document_count: number;
  failed_job_count: number;
  message: string;
  next_stage?: string | null;
  packet_id: string;
  requeued_document_count: number;
  skipped_document_ids: string[];
  stage_name: string;
  stale_running_job_count: number;
  status: string;
};

export type RecommendationReviewDisposition = "accepted" | "rejected";

export type PacketRecommendationReviewRequest = {
  disposition: RecommendationReviewDisposition;
  reviewed_by_email?: string;
  reviewed_by_user_id?: string;
};

export type PacketRecommendationReviewResponse = {
  packet_id: string;
  recommendation_result: RecommendationResultRecord;
};

type ApiErrorPayload = {
  details?: unknown;
  message?: string;
};

const defaultApiBaseUrl = import.meta.env.DEV ? "http://localhost:7071/api" : "/api";

const apiBaseUrl =
  import.meta.env.VITE_REVIEW_API_BASE_URL?.replace(/\/$/, "") ||
  defaultApiBaseUrl;

function buildApiUrl(path: string): URL {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const target = `${apiBaseUrl}${normalizedPath}`;

  if (/^https?:\/\//i.test(target)) {
    return new URL(target);
  }

  return new URL(target, window.location.origin);
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T;
  }

  let errorMessage = `Request failed with status ${response.status}`;

  try {
    const payload = (await response.json()) as ApiErrorPayload;
    if (typeof payload.message === "string" && payload.message.length > 0) {
      errorMessage = payload.message;
    } else if (
      typeof payload.details === "string" &&
      payload.details.length > 0
    ) {
      errorMessage = payload.details;
    }
  } catch {
    // Keep the fallback error message.
  }

  throw new Error(errorMessage);
}

async function postPacketAction<T>(path: string): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    headers: { Accept: "application/json" },
    method: "POST",
  });

  return parseJsonResponse<T>(response);
}

export async function getPacketWorkspace(
  packetId: string,
): Promise<PacketWorkspaceSnapshot> {
  const response = await fetch(buildApiUrl(`/packets/${packetId}/workspace`), {
    headers: { Accept: "application/json" },
  });

  return parseJsonResponse<PacketWorkspaceSnapshot>(response);
}

export function buildPacketDocumentContentUrl(
  packetId: string,
  documentId: string,
  cacheBustToken?: string,
): string {
  const url = buildApiUrl(`/packets/${packetId}/documents/${documentId}/content`);

  if (cacheBustToken) {
    url.searchParams.set("v", cacheBustToken);
  }

  return url.toString();
}

export async function executePacketStage(
  packetId: string,
  stageName: PacketProcessingStageName,
): Promise<PacketStageExecutionResponse> {
  return postPacketAction<PacketStageExecutionResponse>(
    `/packets/${packetId}/${stageName}/execute`,
  );
}

export async function retryPacketStage(
  packetId: string,
  stageName: PacketProcessingStageName,
): Promise<PacketStageRetryResponse> {
  return postPacketAction<PacketStageRetryResponse>(
    `/packets/${packetId}/stages/${stageName}/retry`,
  );
}

export async function replayPacket(
  packetId: string,
): Promise<PacketReplayResponse> {
  return postPacketAction<PacketReplayResponse>(`/packets/${packetId}/replay`);
}

export async function reviewPacketRecommendation(
  packetId: string,
  recommendationResultId: string,
  request: PacketRecommendationReviewRequest,
): Promise<PacketRecommendationReviewResponse> {
  const response = await fetch(
    buildApiUrl(
      `/packets/${packetId}/recommendation-results/${recommendationResultId}/review`,
    ),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(request),
    },
  );

  return parseJsonResponse<PacketRecommendationReviewResponse>(response);
}
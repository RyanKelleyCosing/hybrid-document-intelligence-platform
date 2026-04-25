import type {
  AuditEventRecord,
  ExtractionResultRecord,
  OperatorNoteRecord,
  ReviewDecisionRecord,
} from "./packetWorkspaceApi";

export type PacketReviewDecisionStatus = "approved" | "rejected";

export type PacketReviewAssignmentRequest = {
  assigned_by_email?: string;
  assigned_by_user_id?: string;
  assigned_user_email?: string | null;
  assigned_user_id?: string | null;
  expected_row_version: string;
};

export type PacketReviewAssignmentResponse = {
  assigned_user_email?: string | null;
  assigned_user_id?: string | null;
  packet_id: string;
  review_task_id: string;
};

export type PacketReviewTaskCreateRequest = {
  assigned_user_email?: string | null;
  assigned_user_id?: string | null;
  created_by_email?: string;
  created_by_user_id?: string;
  notes_summary?: string | null;
  priority?: "low" | "normal" | "high";
  selected_account_id?: string | null;
};

export type PacketReviewTaskCreateResponse = {
  document_id: string;
  packet_id: string;
  review_task_id: string;
};

export type PacketReviewDecisionRequest = {
  decided_by_email?: string;
  decided_by_user_id?: string;
  decision_reason_code?: string;
  decision_status: PacketReviewDecisionStatus;
  expected_row_version: string;
  review_notes?: string;
  selected_account_id?: string | null;
};

export type PacketReviewDecisionResponse = {
  decision: ReviewDecisionRecord;
  document_status: string;
  operator_note?: OperatorNoteRecord | null;
  packet_id: string;
  packet_status: string;
  queued_recommendation_job_id?: string | null;
  review_task_id: string;
  review_task_status: string;
};

export type PacketReviewNoteRequest = {
  created_by_email?: string;
  created_by_user_id?: string;
  expected_row_version: string;
  is_private?: boolean;
  note_text: string;
};

export type PacketReviewNoteResponse = {
  operator_note: OperatorNoteRecord;
  packet_id: string;
  review_task_id: string;
};

export type PacketReviewExtractionFieldEdit = {
  field_name: string;
  value: string;
};

export type PacketReviewExtractionFieldChangeRecord = {
  confidence?: number | null;
  current_value: string;
  field_name: string;
  original_value: string;
};

export type PacketReviewExtractionEditRequest = {
  edited_by_email?: string;
  edited_by_user_id?: string;
  expected_row_version: string;
  field_edits: PacketReviewExtractionFieldEdit[];
};

export type PacketReviewExtractionEditResponse = {
  audit_event: AuditEventRecord;
  changed_fields: PacketReviewExtractionFieldChangeRecord[];
  document_id: string;
  extraction_result: ExtractionResultRecord;
  packet_id: string;
  review_task_id: string;
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

export async function submitPacketReviewAssignment(
  reviewTaskId: string,
  request: PacketReviewAssignmentRequest,
): Promise<PacketReviewAssignmentResponse> {
  const response = await fetch(buildApiUrl(`/review-tasks/${reviewTaskId}/assignment`), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(request),
  });

  return parseJsonResponse<PacketReviewAssignmentResponse>(response);
}

export async function submitPacketReviewTaskCreate(
  packetId: string,
  documentId: string,
  request: PacketReviewTaskCreateRequest,
): Promise<PacketReviewTaskCreateResponse> {
  const response = await fetch(
    buildApiUrl(`/packets/${packetId}/documents/${documentId}/review-tasks`),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(request),
    },
  );

  return parseJsonResponse<PacketReviewTaskCreateResponse>(response);
}

export async function submitPacketReviewDecision(
  reviewTaskId: string,
  request: PacketReviewDecisionRequest,
): Promise<PacketReviewDecisionResponse> {
  const response = await fetch(buildApiUrl(`/review-tasks/${reviewTaskId}/decision`), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(request),
  });

  return parseJsonResponse<PacketReviewDecisionResponse>(response);
}

export async function submitPacketReviewNote(
  reviewTaskId: string,
  request: PacketReviewNoteRequest,
): Promise<PacketReviewNoteResponse> {
  const response = await fetch(buildApiUrl(`/review-tasks/${reviewTaskId}/notes`), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(request),
  });

  return parseJsonResponse<PacketReviewNoteResponse>(response);
}

export async function submitPacketReviewExtractionEdits(
  reviewTaskId: string,
  request: PacketReviewExtractionEditRequest,
): Promise<PacketReviewExtractionEditResponse> {
  const response = await fetch(
    buildApiUrl(`/review-tasks/${reviewTaskId}/extraction-edits`),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(request),
    },
  );

  return parseJsonResponse<PacketReviewExtractionEditResponse>(response);
}
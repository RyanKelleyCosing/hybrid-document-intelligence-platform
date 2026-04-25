export type PacketAssignmentState = "assigned" | "mixed" | "unassigned";

export type PacketQueueFilters = {
  assigned_user_email?: string;
  classification_key?: string;
  document_type_key?: string;
  min_queue_age_hours?: number;
  page?: number;
  page_size?: number;
  source?: string;
  stage_name?: string;
  status?: string;
};

export type PacketQueueItem = {
  assigned_user_email: string | null;
  assignment_state: PacketAssignmentState;
  audit_event_count: number;
  awaiting_review_document_count: number;
  classification_keys: string[];
  completed_document_count: number;
  document_count: number;
  document_type_keys: string[];
  latest_job_stage_name: string | null;
  latest_job_status: string | null;
  oldest_review_task_created_at_utc: string | null;
  operator_note_count: number;
  packet_id: string;
  packet_name: string;
  primary_document_id: string | null;
  primary_file_name: string | null;
  primary_issuer_category: string;
  primary_issuer_name: string | null;
  queue_age_hours: number;
  received_at_utc: string;
  review_task_count: number;
  source: string;
  source_uri: string | null;
  stage_name: string;
  status: string;
  submitted_by: string | null;
  updated_at_utc: string;
};

export type PacketQueueListResponse = {
  has_more: boolean;
  items: PacketQueueItem[];
  page: number;
  page_size: number;
  total_count: number;
};

type ApiErrorPayload = {
  details?: unknown;
  message?: string;
  status?: string;
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

export async function listPacketQueue(
  filters: PacketQueueFilters = {},
): Promise<PacketQueueListResponse> {
  const url = buildApiUrl("/packets");

  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === "") {
      continue;
    }

    url.searchParams.set(key, String(value));
  }

  const response = await fetch(url, {
    headers: { Accept: "application/json" },
  });

  return parseJsonResponse<PacketQueueListResponse>(response);
}
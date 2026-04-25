export type IntakeSourceKind =
  | "manual_upload"
  | "watched_blob_prefix"
  | "watched_sftp_path"
  | "email_connector"
  | "partner_api_feed"
  | "configured_folder";

export type ManualUploadSourceConfiguration = {
  entry_point_name: string;
  max_documents_per_packet: number;
  source_kind: "manual_upload";
};

export type WatchedBlobPrefixSourceConfiguration = {
  blob_prefix: string;
  container_name: string;
  include_subdirectories: boolean;
  source_kind: "watched_blob_prefix";
  storage_account_name: string;
};

export type WatchedSftpPathSourceConfiguration = {
  local_user_name: string;
  sftp_path: string;
  source_kind: "watched_sftp_path";
  storage_account_name: string;
};

export type EmailConnectorSourceConfiguration = {
  attachment_extension_allowlist: string[];
  folder_path: string;
  mailbox_address: string;
  source_kind: "email_connector";
};

export type PartnerApiFeedSourceConfiguration = {
  auth_scheme: string;
  partner_name: string;
  relative_path: string;
  source_kind: "partner_api_feed";
};

export type ConfiguredFolderSourceConfiguration = {
  file_pattern: string;
  folder_path: string;
  recursive: boolean;
  source_kind: "configured_folder";
};

export type IntakeSourceConfiguration =
  | ConfiguredFolderSourceConfiguration
  | EmailConnectorSourceConfiguration
  | ManualUploadSourceConfiguration
  | PartnerApiFeedSourceConfiguration
  | WatchedBlobPrefixSourceConfiguration
  | WatchedSftpPathSourceConfiguration;

export type IntakeSourceRecord = {
  configuration: IntakeSourceConfiguration;
  created_at_utc: string;
  credentials_reference?: string | null;
  description?: string | null;
  is_enabled: boolean;
  last_error_at_utc?: string | null;
  last_error_message?: string | null;
  last_seen_at_utc?: string | null;
  last_success_at_utc?: string | null;
  owner_email?: string | null;
  polling_interval_minutes?: number | null;
  source_id: string;
  source_name: string;
  updated_at_utc: string;
};

export type IntakeSourceCreateRequest = {
  configuration: IntakeSourceConfiguration;
  credentials_reference?: string | null;
  description?: string | null;
  is_enabled: boolean;
  owner_email?: string | null;
  polling_interval_minutes?: number | null;
  source_id?: string;
  source_name: string;
};

export type IntakeSourceUpdateRequest = {
  configuration: IntakeSourceConfiguration;
  credentials_reference?: string | null;
  description?: string | null;
  is_enabled: boolean;
  owner_email?: string | null;
  polling_interval_minutes?: number | null;
  source_name: string;
};

export type IntakeSourceDeleteResponse = {
  deleted: boolean;
  source_id: string;
  source_name: string;
};

type IntakeSourceListResponse = {
  items: IntakeSourceRecord[];
};

type IntakeSourceEnablementRequest = {
  is_enabled: boolean;
};

export type IntakeSourceExecutionFailure = {
  blob_name: string;
  blob_uri: string;
  message: string;
};

export type IntakeSourceExecutionPacketResult = {
  blob_name: string;
  blob_uri: string;
  content_length_bytes: number;
  content_type: string;
  document_count: number;
  duplicate_detection_status: string;
  idempotency_reused_existing_packet: boolean;
  packet_id: string;
  packet_name: string;
  status: string;
};

export type IntakeSourceExecutionResponse = {
  executed_at_utc: string;
  failed_blob_count: number;
  failures: IntakeSourceExecutionFailure[];
  packet_results: IntakeSourceExecutionPacketResult[];
  processed_blob_count: number;
  reused_packet_count: number;
  seen_blob_count: number;
  source_id: string;
  source_kind: IntakeSourceKind;
  source_name: string;
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

export async function listIntakeSources(): Promise<IntakeSourceRecord[]> {
  const response = await fetch(buildApiUrl("/intake-sources"), {
    headers: { Accept: "application/json" },
  });
  const payload = await parseJsonResponse<IntakeSourceListResponse>(response);
  return payload.items;
}

export async function createIntakeSource(
  request: IntakeSourceCreateRequest,
): Promise<IntakeSourceRecord> {
  const response = await fetch(buildApiUrl("/intake-sources"), {
    body: JSON.stringify(request),
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    method: "POST",
  });

  return parseJsonResponse<IntakeSourceRecord>(response);
}

export async function updateIntakeSource(
  sourceId: string,
  request: IntakeSourceUpdateRequest,
): Promise<IntakeSourceRecord> {
  const response = await fetch(buildApiUrl(`/intake-sources/${sourceId}`), {
    body: JSON.stringify(request),
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    method: "PUT",
  });

  return parseJsonResponse<IntakeSourceRecord>(response);
}

export async function setIntakeSourceEnablement(
  sourceId: string,
  isEnabled: boolean,
): Promise<IntakeSourceRecord> {
  const request: IntakeSourceEnablementRequest = {
    is_enabled: isEnabled,
  };
  const response = await fetch(buildApiUrl(`/intake-sources/${sourceId}/enablement`), {
    body: JSON.stringify(request),
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    method: "POST",
  });

  return parseJsonResponse<IntakeSourceRecord>(response);
}

export async function deleteIntakeSource(
  sourceId: string,
): Promise<IntakeSourceDeleteResponse> {
  const response = await fetch(buildApiUrl(`/intake-sources/${sourceId}`), {
    headers: { Accept: "application/json" },
    method: "DELETE",
  });

  return parseJsonResponse<IntakeSourceDeleteResponse>(response);
}

export async function executeIntakeSource(
  sourceId: string,
): Promise<IntakeSourceExecutionResponse> {
  const response = await fetch(buildApiUrl(`/intake-sources/${sourceId}/execute`), {
    method: "POST",
    headers: { Accept: "application/json" },
  });

  return parseJsonResponse<IntakeSourceExecutionResponse>(response);
}
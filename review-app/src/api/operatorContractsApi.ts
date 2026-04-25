export type PacketStatusDefinition = {
  category: string;
  description: string;
  display_name: string;
  operator_attention_required: boolean;
  stage_name: string;
  status: string;
  terminal: boolean;
};

export type ProcessingStageDefinition = {
  description: string;
  display_name: string;
  stage_name: string;
  statuses: string[];
};

export type ProcessingTaxonomyResponse = {
  stages: ProcessingStageDefinition[];
  statuses: PacketStatusDefinition[];
};

export type ManagedClassificationDefinitionRecord = {
  classification_id: string;
  classification_key: string;
  created_at_utc: string;
  default_prompt_profile_id?: string | null;
  description?: string | null;
  display_name: string;
  is_enabled: boolean;
  issuer_category: string;
  updated_at_utc: string;
};

export type ManagedDocumentTypeDefinitionRecord = {
  classification_id?: string | null;
  created_at_utc: string;
  default_prompt_profile_id?: string | null;
  description?: string | null;
  display_name: string;
  document_type_id: string;
  document_type_key: string;
  is_enabled: boolean;
  required_fields: string[];
  updated_at_utc: string;
};

export type ManagedPromptProfileRecord = {
  created_at_utc: string;
  description?: string | null;
  display_name: string;
  is_enabled: boolean;
  issuer_category: string;
  prompt_profile_id: string;
  updated_at_utc: string;
};

export type PromptProfileVersionRecord = {
  created_at_utc: string;
  definition_payload: Record<string, unknown>;
  is_active: boolean;
  prompt_profile_id: string;
  prompt_profile_version_id: string;
  version_number: number;
};

export type RecommendationContractDefinition = {
  advisory_only: boolean;
  default_status: string;
  disposition_values: string[];
  required_evidence_kinds: string[];
  required_packet_status: string;
};

export type OperatorContractsResponse = {
  classification_definitions: ManagedClassificationDefinitionRecord[];
  document_type_definitions: ManagedDocumentTypeDefinitionRecord[];
  processing_taxonomy: ProcessingTaxonomyResponse;
  prompt_profile_versions: PromptProfileVersionRecord[];
  prompt_profiles: ManagedPromptProfileRecord[];
  recommendation_contract: RecommendationContractDefinition;
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

export async function getOperatorContracts(): Promise<OperatorContractsResponse> {
  const response = await fetch(buildApiUrl("/operator-contracts"), {
    headers: { Accept: "application/json" },
  });

  return parseJsonResponse<OperatorContractsResponse>(response);
}
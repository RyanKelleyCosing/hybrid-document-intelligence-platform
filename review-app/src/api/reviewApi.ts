export type ReviewStatus =
  | "approved"
  | "pending_review"
  | "ready_for_enrichment"
  | "rejected"
  | "reprocess_requested";

export type ReviewDecisionStatus =
  | "approved"
  | "rejected"
  | "reprocess_requested";

export type ExtractedField = {
  confidence: number;
  name: string;
  value: string;
};

export type PromptProfileCandidate = {
  issuer_category: string;
  profile_id: string;
  rationale: string[];
  score: number;
};

export type PromptProfileSelection = {
  candidates: PromptProfileCandidate[];
  document_type_hints: string[];
  issuer_category: string;
  keyword_hints: string[];
  primary_profile_id: string;
  prompt_focus: string[];
  rationale: string[];
  selection_mode: string;
  system_prompt: string;
};

export type AccountMatchCandidate = {
  account_id: string;
  account_number: string | null;
  debtor_name: string | null;
  issuer_name: string | null;
  matched_on: string[];
  score: number;
};

export type AccountMatchResult = {
  candidates: AccountMatchCandidate[];
  rationale: string | null;
  selected_account_id: string | null;
  status: string;
};

export type ReviewQueueItem = {
  account_candidates: string[];
  account_match: AccountMatchResult | null;
  average_confidence: number;
  created_at_utc: string;
  document_id: string;
  document_type: string | null;
  extracted_fields: ExtractedField[];
  file_name: string;
  issuer_category: string;
  issuer_name: string | null;
  minimum_confidence: number;
  ocr_text_excerpt: string | null;
  prompt_profile: PromptProfileSelection;
  reasons: string[];
  received_at_utc: string;
  reviewed_at_utc: string | null;
  reviewer_name: string | null;
  review_notes: string | null;
  selected_account_id: string | null;
  source: string;
  source_uri: string;
  status: ReviewStatus;
  updated_at_utc: string;
};

type ReviewItemListResponse = {
  items: ReviewQueueItem[];
};

type ApiErrorPayload = {
  details?: unknown;
  message?: string;
  status?: string;
};

export type ReviewDecisionUpdate = {
  review_notes?: string;
  reviewer_name: string;
  selected_account_id?: string | null;
  status: ReviewDecisionStatus;
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

export async function listReviewItems(
  status: ReviewStatus = "pending_review",
  limit = 25,
): Promise<ReviewQueueItem[]> {
  const url = buildApiUrl("/review-items");
  url.searchParams.set("status", status);
  url.searchParams.set("limit", String(limit));

  const response = await fetch(url, {
    headers: { Accept: "application/json" },
  });
  const payload = await parseJsonResponse<ReviewItemListResponse>(response);
  return payload.items;
}

export async function submitReviewDecision(
  documentId: string,
  update: ReviewDecisionUpdate,
): Promise<ReviewQueueItem> {
  const response = await fetch(buildApiUrl(`/review-items/${documentId}/decision`), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(update),
  });

  return parseJsonResponse<ReviewQueueItem>(response);
}
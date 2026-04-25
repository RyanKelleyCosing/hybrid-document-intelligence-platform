import { simulationReviewItems } from "../data/simulationData";

import type {
  ReviewDecisionUpdate,
  ReviewQueueItem,
  ReviewStatus,
} from "./reviewApi";

function cloneReviewItem(item: ReviewQueueItem): ReviewQueueItem {
  return {
    ...item,
    account_candidates: [...item.account_candidates],
    account_match: item.account_match
      ? {
          ...item.account_match,
          candidates: item.account_match.candidates.map((candidate) => ({
            ...candidate,
            matched_on: [...candidate.matched_on],
          })),
        }
      : null,
    extracted_fields: item.extracted_fields.map((field) => ({ ...field })),
    prompt_profile: {
      ...item.prompt_profile,
      candidates: item.prompt_profile.candidates.map((candidate) => ({
        ...candidate,
        rationale: [...candidate.rationale],
      })),
      document_type_hints: [...item.prompt_profile.document_type_hints],
      keyword_hints: [...item.prompt_profile.keyword_hints],
      prompt_focus: [...item.prompt_profile.prompt_focus],
      rationale: [...item.prompt_profile.rationale],
    },
    reasons: [...item.reasons],
  };
}

export async function listSimulationReviewItems(
  status: ReviewStatus = "pending_review",
  limit = 25,
): Promise<ReviewQueueItem[]> {
  return simulationReviewItems
    .filter((item) => item.status === status)
    .slice(0, limit)
    .map(cloneReviewItem);
}

export async function submitSimulationReviewDecision(
  documentId: string,
  update: ReviewDecisionUpdate,
): Promise<ReviewQueueItem> {
  void documentId;
  void update;

  throw new Error(
    "Simulation mode is read-only. Review decisions stay disabled on the public site.",
  );
}
import type { ReviewQueueItem } from "../api/reviewApi";

type QueueCardProps = {
  actionNote?: string;
  isMutating: boolean;
  isReadOnly?: boolean;
  item: ReviewQueueItem;
  onApprove?: (item: ReviewQueueItem) => void;
  onReject?: (item: ReviewQueueItem) => void;
  onReprocess?: (item: ReviewQueueItem) => void;
};

function toLabel(value: string | null | undefined) {
  if (!value) {
    return "Unknown";
  }

  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function QueueCard({
  actionNote,
  isMutating,
  isReadOnly = false,
  item,
  onApprove,
  onReject,
  onReprocess,
}: QueueCardProps) {
  const confidenceLabel = `${Math.round(item.average_confidence * 100)}%`;
  const subtitle = `${item.issuer_name || toLabel(item.issuer_category)} profile: ${toLabel(item.prompt_profile.primary_profile_id)}`;
  const receivedAt = new Date(item.received_at_utc).toLocaleString();
  const topCandidate = item.account_match?.candidates[0];
  const selectedAccountId =
    item.selected_account_id || item.account_match?.selected_account_id;
  const accountCandidateCount = item.account_match?.candidates.length ?? 0;
  const accountStatusLabel = selectedAccountId
    ? "selected"
    : item.account_match?.status || "unmatched";
  const accountSummary = selectedAccountId
    ? `Selected account: ${selectedAccountId}`
    : topCandidate
      ? `Top candidate: ${topCandidate.account_id}${topCandidate.debtor_name ? ` · ${topCandidate.debtor_name}` : ""}`
      : accountCandidateCount > 0
        ? `${accountCandidateCount} candidate${accountCandidateCount === 1 ? "" : "s"} waiting for operator selection.`
        : "Matching did not return a candidate account yet.";
  const areActionsDisabled = isReadOnly || isMutating;

  return (
    <article className="queue-card">
      <header className="queue-card-header">
        <div className="queue-card-heading">
          <p className="queue-card-label">{toLabel(item.source)}</p>
          <h3>{item.file_name}</h3>
          <p className="queue-card-subtitle">{subtitle}</p>
        </div>
        <div className="confidence-pill">{confidenceLabel}</div>
      </header>

      <dl className="field-grid">
        {item.extracted_fields.slice(0, 4).map((field) => (
          <div key={field.name}>
            <dt>{toLabel(field.name)}</dt>
            <dd>{field.value}</dd>
          </div>
        ))}
      </dl>

      <div className="queue-card-section">
        <p className="queue-card-section-label">Review triggers</p>
        <div className="reason-strip">
          {item.reasons.map((reason) => (
            <span className="reason-chip" key={reason}>
              {toLabel(reason)}
            </span>
          ))}
        </div>
      </div>

      <div className="queue-card-section">
        <div className="queue-card-section-header">
          <p className="queue-card-section-label">Account match</p>
          <span className="match-pill">{toLabel(accountStatusLabel)}</span>
        </div>
        <p className="match-summary">{accountSummary}</p>
      </div>

      <footer className="queue-card-footer">
        <div>
          <p>{receivedAt}</p>
          {actionNote ? <p className="queue-card-note">{actionNote}</p> : null}
        </div>
        <div className="queue-card-actions">
          <button
            disabled={areActionsDisabled}
            onClick={() => {
              onApprove?.(item);
            }}
            type="button"
          >
            Approve
          </button>
          <button
            className="secondary-button"
            disabled={areActionsDisabled}
            onClick={() => {
              onReprocess?.(item);
            }}
            type="button"
          >
            Request reprocess
          </button>
          <button
            className="danger-button"
            disabled={areActionsDisabled}
            onClick={() => {
              onReject?.(item);
            }}
            type="button"
          >
            Reject
          </button>
        </div>
      </footer>
    </article>
  );
}
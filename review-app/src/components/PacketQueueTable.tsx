import type { PacketQueueItem } from "../api/packetQueueApi";
import {
  StatusBadge,
  SurfaceTable,
  SurfaceTableFrame,
  type StatusBadgeTone,
} from "./SurfacePrimitives";
import { buildPacketNextOperatorAction } from "./packetQueueUrgency";

type RefreshDeltaDetail = {
  current: string;
  previous: string;
};

export type PacketQueueRefreshDelta = {
  activityDetail?: RefreshDeltaDetail;
  hasActivityChange: boolean;
  assignmentDetail?: RefreshDeltaDetail;
  hasAssignmentChange: boolean;
  contractDetail?: RefreshDeltaDetail;
  hasContractChange: boolean;
  stageDetail?: RefreshDeltaDetail;
  hasStageChange: boolean;
  statusDetail?: RefreshDeltaDetail;
  hasStatusChange: boolean;
  isNewPacket: boolean;
};

type PacketQueueTableProps = {
  items: PacketQueueItem[];
  onSelectPacket: (item: PacketQueueItem) => void;
  refreshDeltasByPacketId?: Record<string, PacketQueueRefreshDelta>;
  selectedPacketId: string | null;
};

function toLabel(value: string | null | undefined) {
  if (!value) {
    return "Unknown";
  }

  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatQueueAge(hours: number) {
  if (hours < 1) {
    return `${Math.max(1, Math.round(hours * 60))}m`;
  }

  if (hours < 24) {
    return `${hours.toFixed(hours < 10 ? 1 : 0)}h`;
  }

  return `${(hours / 24).toFixed(1)}d`;
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

function formatAssignment(item: PacketQueueItem) {
  if (item.assignment_state === "assigned" && item.assigned_user_email) {
    return item.assigned_user_email;
  }

  if (item.assignment_state === "mixed") {
    return "Multiple owners";
  }

  return "Unassigned";
}

function formatContractSummary(values: string[]) {
  if (values.length === 0) {
    return "Not set";
  }

  return values.map((value) => toLabel(value)).join(", ");
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

function getAssignmentTone(item: PacketQueueItem): StatusBadgeTone {
  switch (item.assignment_state) {
    case "assigned":
      return "success";
    case "mixed":
      return "warning";
    case "unassigned":
    default:
      return "neutral";
  }
}

function hasPacketQueueRefreshDelta(
  refreshDelta: PacketQueueRefreshDelta | undefined,
) {
  return Boolean(
    refreshDelta?.isNewPacket ||
      refreshDelta?.hasContractChange ||
      refreshDelta?.hasStageChange ||
      refreshDelta?.hasStatusChange ||
      refreshDelta?.hasAssignmentChange ||
      refreshDelta?.hasActivityChange,
  );
}

function formatRefreshDeltaDetail(
  label: string,
  detail: RefreshDeltaDetail | undefined,
) {
  if (!detail) {
    return null;
  }

  return `${label}: ${detail.previous} -> ${detail.current}`;
}

export function PacketQueueTable({
  items,
  onSelectPacket,
  refreshDeltasByPacketId,
  selectedPacketId,
}: PacketQueueTableProps) {
  return (
    <SurfaceTableFrame className="queue-table-wrap">
      <SurfaceTable className="queue-table">
        <thead>
          <tr>
            <th scope="col">Packet</th>
            <th scope="col">Source</th>
            <th scope="col">Stage</th>
            <th scope="col">Status</th>
            <th scope="col">Contracts</th>
            <th scope="col">Docs</th>
            <th scope="col">Assignment</th>
            <th scope="col">Age</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const refreshDelta = refreshDeltasByPacketId?.[item.packet_id];
            const hasRefreshDelta = hasPacketQueueRefreshDelta(refreshDelta);
            const nextOperatorAction = buildPacketNextOperatorAction(item);
            const rowClassName = [
              selectedPacketId === item.packet_id ? "queue-row-selected" : null,
              hasRefreshDelta ? "queue-row-refresh-change" : null,
            ]
              .filter(Boolean)
              .join(" ");

            return (
              <tr
                aria-selected={selectedPacketId === item.packet_id}
                className={rowClassName || undefined}
                key={item.packet_id}
                onClick={() => {
                  onSelectPacket(item);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectPacket(item);
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <td>
                  <div className="queue-row-title">{item.packet_name}</div>
                  <div className="queue-row-subtitle">
                    {item.primary_file_name || "No primary document"}
                  </div>
                  <div className="queue-row-subtitle">
                    {item.primary_issuer_name || toLabel(item.primary_issuer_category)}
                  </div>
                  <div className="queue-row-subtitle">
                    Updated {formatDateTime(item.updated_at_utc)}
                  </div>
                  <div className="queue-row-next-action">
                    <StatusBadge tone={nextOperatorAction.tone}>Best next</StatusBadge>
                    <span className="queue-row-next-action-copy">
                      {nextOperatorAction.summary}
                    </span>
                  </div>
                  {hasRefreshDelta ? (
                    <div className="queue-row-delta-list">
                      {refreshDelta?.isNewPacket ? (
                        <StatusBadge tone="accent">New in queue</StatusBadge>
                      ) : null}
                      {refreshDelta?.hasContractChange ? (
                        <StatusBadge tone="accent">Contracts changed</StatusBadge>
                      ) : null}
                      {refreshDelta?.hasStageChange ? (
                        <StatusBadge tone="accent">Stage moved</StatusBadge>
                      ) : null}
                      {refreshDelta?.hasStatusChange ? (
                        <StatusBadge tone="warning">Status updated</StatusBadge>
                      ) : null}
                      {refreshDelta?.hasAssignmentChange ? (
                        <StatusBadge tone="success">Assignment changed</StatusBadge>
                      ) : null}
                      {refreshDelta?.hasActivityChange ? (
                        <StatusBadge tone="neutral">Fresh activity</StatusBadge>
                      ) : null}
                    </div>
                  ) : null}
                  {hasRefreshDelta ? (
                    <div className="queue-row-delta-details">
                      {refreshDelta?.isNewPacket ? (
                        <p className="queue-row-delta-detail">
                          Queue row is new on this refresh.
                        </p>
                      ) : null}
                      {refreshDelta?.hasContractChange ? (
                        <p className="queue-row-delta-detail">
                          {formatRefreshDeltaDetail(
                            "Contracts",
                            refreshDelta.contractDetail,
                          )}
                        </p>
                      ) : null}
                      {refreshDelta?.hasStageChange ? (
                        <p className="queue-row-delta-detail">
                          {formatRefreshDeltaDetail("Stage", refreshDelta.stageDetail)}
                        </p>
                      ) : null}
                      {refreshDelta?.hasStatusChange ? (
                        <p className="queue-row-delta-detail">
                          {formatRefreshDeltaDetail("Status", refreshDelta.statusDetail)}
                        </p>
                      ) : null}
                      {refreshDelta?.hasAssignmentChange ? (
                        <p className="queue-row-delta-detail">
                          {formatRefreshDeltaDetail(
                            "Assignment",
                            refreshDelta.assignmentDetail,
                          )}
                        </p>
                      ) : null}
                      {refreshDelta?.hasActivityChange ? (
                        <p className="queue-row-delta-detail">
                          {formatRefreshDeltaDetail(
                            "Activity",
                            refreshDelta.activityDetail,
                          )}
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                </td>
                <td>{toLabel(item.source)}</td>
                <td>
                  <div className="queue-tag-stack">
                    <StatusBadge>
                      {toLabel(item.stage_name)}
                    </StatusBadge>
                    <span className="queue-row-subtitle">
                      {item.latest_job_stage_name
                        ? `Latest ${toLabel(item.latest_job_stage_name)} · ${toLabel(item.latest_job_status)}`
                        : "No job history yet"}
                    </span>
                  </div>
                </td>
                <td>
                  <div className="queue-tag-stack">
                    <StatusBadge tone={getPacketStatusTone(item.status)}>
                      {toLabel(item.status)}
                    </StatusBadge>
                    <StatusBadge tone={nextOperatorAction.tone}>
                      {nextOperatorAction.chipLabel}
                    </StatusBadge>
                    <span className="queue-row-subtitle">
                      {item.awaiting_review_document_count} awaiting review
                    </span>
                    <span className="queue-row-subtitle">
                      {item.audit_event_count} audit event{item.audit_event_count === 1 ? "" : "s"} · {item.operator_note_count} note{item.operator_note_count === 1 ? "" : "s"}
                    </span>
                  </div>
                </td>
                <td>
                  <div className="queue-tag-stack">
                    <span>{formatContractSummary(item.classification_keys)}</span>
                    <span className="queue-row-subtitle">
                      {formatContractSummary(item.document_type_keys)}
                    </span>
                  </div>
                </td>
                <td>
                  <div className="queue-tag-stack">
                    <span>{item.document_count} total</span>
                    <span className="queue-row-subtitle">
                      {item.review_task_count} review task
                      {item.review_task_count === 1 ? "" : "s"}
                    </span>
                    <span className="queue-row-subtitle">
                      {item.completed_document_count} completed
                    </span>
                  </div>
                </td>
                <td>
                  <div className="queue-tag-stack">
                    <StatusBadge tone={getAssignmentTone(item)}>
                      {toLabel(item.assignment_state)}
                    </StatusBadge>
                    <span className="queue-row-subtitle">{formatAssignment(item)}</span>
                  </div>
                </td>
                <td>{formatQueueAge(item.queue_age_hours)}</td>
              </tr>
            );
          })}
        </tbody>
      </SurfaceTable>
    </SurfaceTableFrame>
  );
}
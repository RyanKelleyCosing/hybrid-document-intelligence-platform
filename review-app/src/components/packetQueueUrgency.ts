import type { PacketQueueItem } from "../api/packetQueueApi";
import type { StatusBadgeTone } from "./SurfacePrimitives";

export type PacketNextOperatorAction = {
  chipLabel: string;
  summary: string;
  tone: StatusBadgeTone;
};

export type VisibleQueueActionSummary = {
  dominantActionCount: number;
  dominantActionLabel: string;
  dominantActionTone: StatusBadgeTone;
  visiblePacketCount: number;
};

const statusBadgeTonePriority: Record<StatusBadgeTone, number> = {
  accent: 2,
  danger: 0,
  neutral: 4,
  success: 3,
  warning: 1,
};

function toLabel(value: string | null | undefined) {
  if (!value) {
    return "Unknown";
  }

  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatCount(count: number, noun: string) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

export function getStatusBadgeTonePriority(tone: StatusBadgeTone) {
  return statusBadgeTonePriority[tone];
}

export function buildPacketNextOperatorAction(
  item: PacketQueueItem,
): PacketNextOperatorAction {
  const latestJobStageLabel = toLabel(item.latest_job_stage_name || item.stage_name);
  const latestJobStatus = item.latest_job_status;

  if (
    item.status === "failed" ||
    item.status === "blocked" ||
    latestJobStatus === "failed" ||
    latestJobStatus === "blocked"
  ) {
    return {
      chipLabel: "Investigate",
      summary: `Investigate ${latestJobStageLabel} failure`,
      tone: "danger",
    };
  }

  if (item.awaiting_review_document_count > 0) {
    if (item.assignment_state === "unassigned") {
      return {
        chipLabel: "Assign reviewer",
        summary: `Assign reviewer · ${formatCount(item.awaiting_review_document_count, "doc")} waiting`,
        tone: "warning",
      };
    }

    if (item.assignment_state === "mixed") {
      return {
        chipLabel: "Stabilize ownership",
        summary: `Stabilize ownership · ${formatCount(item.awaiting_review_document_count, "doc")} waiting`,
        tone: "warning",
      };
    }

    return {
      chipLabel: "Continue review",
      summary: item.assigned_user_email
        ? `Continue review · ${item.assigned_user_email}`
        : `Continue review · ${formatCount(item.awaiting_review_document_count, "doc")} waiting`,
      tone: "accent",
    };
  }

  if (item.status === "ready_for_recommendation") {
    if (latestJobStatus === "queued" || latestJobStatus === "running") {
      return {
        chipLabel: "Watch run",
        summary: `Watch ${latestJobStageLabel} run`,
        tone: "accent",
      };
    }

    return {
      chipLabel: "Review recommendation",
      summary: "Review recommendation",
      tone: "accent",
    };
  }

  if (latestJobStatus === "queued" || latestJobStatus === "running") {
    return {
      chipLabel: "Monitor run",
      summary: `Monitor ${latestJobStageLabel} run`,
      tone: "warning",
    };
  }

  if (
    item.status === "completed" ||
    (item.document_count > 0 && item.completed_document_count >= item.document_count)
  ) {
    return {
      chipLabel: "No action",
      summary: "No action pending",
      tone: "success",
    };
  }

  return {
    chipLabel: "Inspect queue",
    summary: `Inspect ${toLabel(item.stage_name)} queue`,
    tone: "neutral",
  };
}

export function buildVisibleQueueActionSummary(
  visibleQueueItems: readonly PacketQueueItem[],
): VisibleQueueActionSummary {
  if (visibleQueueItems.length === 0) {
    return {
      dominantActionCount: 0,
      dominantActionLabel: "No visible packets",
      dominantActionTone: "neutral",
      visiblePacketCount: 0,
    };
  }

  const groupedActions = new Map<
    string,
    {
      count: number;
      firstIndex: number;
      label: string;
      tone: StatusBadgeTone;
    }
  >();

  visibleQueueItems.forEach((item, index) => {
    const action = buildPacketNextOperatorAction(item);
    const key = `${action.chipLabel}|${action.tone}`;
    const existing = groupedActions.get(key);

    if (existing) {
      existing.count += 1;
      return;
    }

    groupedActions.set(key, {
      count: 1,
      firstIndex: index,
      label: action.chipLabel,
      tone: action.tone,
    });
  });

  const dominantAction = [...groupedActions.values()].sort((left, right) => {
    const toneComparison =
      getStatusBadgeTonePriority(left.tone) - getStatusBadgeTonePriority(right.tone);
    if (toneComparison !== 0) {
      return toneComparison;
    }

    if (right.count !== left.count) {
      return right.count - left.count;
    }

    return left.firstIndex - right.firstIndex;
  })[0];

  return {
    dominantActionCount: dominantAction.count,
    dominantActionLabel: dominantAction.label,
    dominantActionTone: dominantAction.tone,
    visiblePacketCount: visibleQueueItems.length,
  };
}

export function formatVisibleQueueActionSummary(
  summary: VisibleQueueActionSummary,
) {
  return summary.visiblePacketCount > 0
    ? `Dominant visible next action: ${summary.dominantActionLabel} across ${formatCount(summary.dominantActionCount, "packet")}.`
    : "No visible packets from the current queue page match this slice yet.";
}
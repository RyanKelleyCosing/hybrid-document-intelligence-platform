export type AdminSectionId =
  | "review"
  | "intake"
  | "pipeline"
  | "viewer"
  | "accounts"
  | "rules_doctypes"
  | "sources"
  | "recommendations"
  | "audit";

import type { PacketQueueItem } from "../api/packetQueueApi";
import {
  SectionHeading,
  StatusBadge,
  SurfaceCard,
  SurfaceMetricCard,
  SurfacePanel,
  type StatusBadgeTone,
} from "./SurfacePrimitives";
import {
  buildVisibleQueueActionSummary,
  formatVisibleQueueActionSummary,
} from "./packetQueueUrgency";

type AdminNavigationProps = {
  activeSection: AdminSectionId;
  activeQueueFilters?: AdminWorkflowLandmarkQueuePreset;
  onSelectSection: (sectionId: AdminSectionId) => void;
  onSelectWorkflowLandmark?: (landmark: AdminWorkflowLandmark) => void;
  queueCount: number;
  selectedPacketName: string | null;
  unassignedPacketCount: number;
  visibleQueueItems?: readonly PacketQueueItem[];
};

type AdminSectionDefinition = {
  detail: string;
  id: AdminSectionId;
  label: string;
};

type AdminSectionGroup = {
  detail: string;
  id: "controls" | "evidence" | "triage";
  label: string;
  sectionIds: readonly AdminSectionId[];
};

export type AdminWorkflowLandmarkQueuePreset = {
  stage_name?: string;
  status?: string;
};

export type AdminWorkflowLandmark = {
  defaultSectionId: AdminSectionId;
  detail: string;
  id: "inReview" | "inbox" | "liveStream" | "operations" | "processed";
  label: string;
  mappedSectionsLabel: string;
  primarySectionLabel: string;
  queuePreset: AdminWorkflowLandmarkQueuePreset;
  sectionIds: readonly AdminSectionId[];
};

const adminSections: readonly AdminSectionDefinition[] = [
  {
    id: "review",
    label: "Review",
    detail: "Packet queue, inspector, and reviewer actions.",
  },
  {
    id: "intake",
    label: "Intake",
    detail: "Replay readiness, archive expansion, and dead-letter visibility.",
  },
  {
    id: "pipeline",
    label: "Pipeline",
    detail: "Processing jobs, stage history, and packet events.",
  },
  {
    id: "viewer",
    label: "Viewer",
    detail: "OCR text and document-level preview metadata.",
  },
  {
    id: "accounts",
    label: "Accounts",
    detail: "Account matching candidates and linkage state.",
  },
  {
    id: "rules_doctypes",
    label: "Rules + Doctypes",
    detail: "Managed taxonomy, prompt profiles, and packet evidence mapping.",
  },
  {
    id: "sources",
    label: "Sources",
    detail: "Managed intake sources, execution health, and packet lineage.",
  },
  {
    id: "recommendations",
    label: "Recommendations",
    detail: "Recommendation runs, evidence, and advisory outputs.",
  },
  {
    id: "audit",
    label: "Audit",
    detail: "Notes, decisions, and cross-cutting audit history.",
  },
] as const;

const adminSectionGroups: readonly AdminSectionGroup[] = [
  {
    id: "triage",
    label: "Queue triage",
    detail: "Review, intake, and packet-stage interventions.",
    sectionIds: ["review", "intake", "pipeline"],
  },
  {
    id: "evidence",
    label: "Evidence inspection",
    detail: "Document, account, and audit context for the selected packet.",
    sectionIds: ["viewer", "accounts", "audit"],
  },
  {
    id: "controls",
    label: "Controls + governance",
    detail: "Taxonomy, intake source, and recommendation oversight.",
    sectionIds: ["rules_doctypes", "sources", "recommendations"],
  },
] as const;

export const adminWorkflowLandmarks: readonly AdminWorkflowLandmark[] = [
  {
    defaultSectionId: "review",
    id: "inbox",
    label: "Inbox",
    detail:
      "Review and Intake keep new packets, replay readiness, and assignment gaps visible.",
    mappedSectionsLabel: "Review + Intake",
    primarySectionLabel: "Review",
    queuePreset: {
      stage_name: "review",
    },
    sectionIds: ["review", "intake"],
  },
  {
    defaultSectionId: "viewer",
    id: "inReview",
    label: "In Review",
    detail:
      "Viewer and Accounts keep packet evidence, OCR, and match state together while decisions are forming.",
    mappedSectionsLabel: "Viewer + Accounts",
    primarySectionLabel: "Viewer",
    queuePreset: {
      stage_name: "review",
      status: "awaiting_review",
    },
    sectionIds: ["viewer", "accounts"],
  },
  {
    defaultSectionId: "audit",
    id: "processed",
    label: "Processed",
    detail:
      "Recommendations and Audit carry completed outcomes, advisory results, and operator history.",
    mappedSectionsLabel: "Recommendations + Audit",
    primarySectionLabel: "Audit",
    queuePreset: {
      stage_name: "recommendation",
      status: "completed",
    },
    sectionIds: ["recommendations", "audit"],
  },
  {
    defaultSectionId: "pipeline",
    id: "liveStream",
    label: "Live Stream",
    detail:
      "Pipeline and Sources surface packet movement, stage activity, and new source executions.",
    mappedSectionsLabel: "Pipeline + Sources",
    primarySectionLabel: "Pipeline",
    queuePreset: {
      stage_name: "ocr",
      status: "ocr_running",
    },
    sectionIds: ["pipeline", "sources"],
  },
  {
    defaultSectionId: "rules_doctypes",
    id: "operations",
    label: "Operational tabs",
    detail:
      "Rules + Doctypes remains the governance surface for taxonomy, prompt profiles, and managed evidence rules.",
    mappedSectionsLabel: "Rules + Doctypes",
    primarySectionLabel: "Rules + Doctypes",
    queuePreset: {
      stage_name: "review",
    },
    sectionIds: ["rules_doctypes"],
  },
] as const;

const primaryWorkflowLandmarks = adminWorkflowLandmarks.filter(
  (landmark) => landmark.id !== "operations",
);

function getAdminSectionDefinition(
  sectionId: AdminSectionId,
): AdminSectionDefinition {
  return (
    adminSections.find((section) => section.id === sectionId) ?? {
      detail: "",
      id: sectionId,
      label: sectionId.replace(/_/g, " "),
    }
  );
}

function getAdminSectionGroupTone(
  sectionIds: readonly AdminSectionId[],
  activeSection: AdminSectionId,
): StatusBadgeTone {
  return sectionIds.includes(activeSection) ? "accent" : "neutral";
}

function toSentenceLabel(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatCount(count: number, noun: string) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function formatWorkflowLanePreset(
  queuePreset: AdminWorkflowLandmarkQueuePreset,
) {
  const segments: string[] = [];

  if (queuePreset.stage_name) {
    segments.push(`${toSentenceLabel(queuePreset.stage_name)} stage`);
  }

  if (queuePreset.status) {
    segments.push(`${toSentenceLabel(queuePreset.status)} status`);
  }

  return segments.length > 0
    ? segments.join(" · ")
    : "All packets in the current queue view";
}

function isQueueItemInWorkflowLane(
  item: PacketQueueItem,
  queuePreset: AdminWorkflowLandmarkQueuePreset,
) {
  return Object.entries(queuePreset).every(([key, value]) => {
    if (value === undefined) {
      return true;
    }

    return item[key as keyof AdminWorkflowLandmarkQueuePreset] === value;
  });
}

function buildWorkflowLaneVisibleSummary(
  landmark: AdminWorkflowLandmark,
  visibleQueueItems: readonly PacketQueueItem[],
) {
  const matchingItems = visibleQueueItems.filter((item) =>
    isQueueItemInWorkflowLane(item, landmark.queuePreset),
  );

  return buildVisibleQueueActionSummary(matchingItems);
}

export function isWorkflowLandmarkActive(
  landmark: AdminWorkflowLandmark,
  activeSection: AdminSectionId,
  activeQueueFilters?: AdminWorkflowLandmarkQueuePreset,
) {
  if (!landmark.sectionIds.includes(activeSection)) {
    return false;
  }

  if (!activeQueueFilters) {
    return true;
  }

  return Object.entries(landmark.queuePreset).every(([key, value]) => {
    if (value === undefined) {
      return true;
    }

    return (
      activeQueueFilters[key as keyof AdminWorkflowLandmarkQueuePreset] === value
    );
  });
}

export function AdminNavigation({
  activeSection,
  activeQueueFilters,
  onSelectSection,
  onSelectWorkflowLandmark,
  queueCount,
  selectedPacketName,
  unassignedPacketCount,
  visibleQueueItems = [],
}: AdminNavigationProps) {
  const activeSectionDefinition = getAdminSectionDefinition(activeSection);
  const activeWorkflowLandmark =
    adminWorkflowLandmarks.find((landmark) =>
      isWorkflowLandmarkActive(landmark, activeSection, activeQueueFilters),
    ) ?? null;
  const workflowLaneDetail = activeWorkflowLandmark
    ? `Current lane maps to ${activeWorkflowLandmark.mappedSectionsLabel}. Queue lens: ${formatWorkflowLanePreset(activeWorkflowLandmark.queuePreset)}.`
    : `Current filters no longer match a named lane. Queue lens: ${formatWorkflowLanePreset(activeQueueFilters ?? {})}.`;

  return (
    <SurfacePanel as="aside" className="admin-nav-panel">
      <SectionHeading
        description="Persistent admin navigation is now anchored to the SQL packet model instead of the legacy queue alone."
        title="Operator shell"
      />
      <div className="admin-nav-stats">
        <SurfaceMetricCard
          badge={<StatusBadge tone="accent">Queued packets</StatusBadge>}
          className="admin-nav-stat-card"
          detail="SQL-backed packet rows ready for operator attention."
          title="Operator inbox"
          value={queueCount}
        />
        <SurfaceMetricCard
          badge={
            <StatusBadge tone={unassignedPacketCount > 0 ? "warning" : "success"}>
              {unassignedPacketCount > 0 ? "Needs assignment" : "Assigned"}
            </StatusBadge>
          }
          className="admin-nav-stat-card"
          detail="Unassigned packets still visible in the current queue view."
          title="Current queue health"
          value={unassignedPacketCount}
        />
      </div>

      <SurfaceMetricCard
        badge={<StatusBadge tone="accent">Current section</StatusBadge>}
        className="admin-nav-active-card"
        detail={activeSectionDefinition.detail}
        title="Live workspace focus"
        value={activeSectionDefinition.label}
      />

      <SurfaceMetricCard
        badge={
          <StatusBadge tone={activeWorkflowLandmark ? "accent" : "neutral"}>
            {activeWorkflowLandmark ? "Named lane" : "Custom lens"}
          </StatusBadge>
        }
        className="admin-nav-active-card"
        detail={workflowLaneDetail}
        title="Workflow lane"
        value={activeWorkflowLandmark?.label || "Custom queue lens"}
      />

      <SurfaceCard
        aria-label="Primary lanes"
        as="section"
        className="admin-nav-group"
      >
        <div className="admin-nav-group-heading">
          <div>
            <p className="admin-nav-group-label">Primary lanes</p>
            <p className="admin-nav-group-copy">
              Inbox, In Review, Processed, and Live Stream are now the primary
              queue lanes. The detailed admin tabs stay grouped below when you
              need deeper controls.
            </p>
          </div>
          <StatusBadge tone="accent">Lane nav</StatusBadge>
        </div>

        <div aria-label="Primary lanes" className="admin-nav-group-list">
          {primaryWorkflowLandmarks.map((landmark) => {
            const isActive = isWorkflowLandmarkActive(
              landmark,
              activeSection,
              activeQueueFilters,
            );
            const laneVisibleSummary = buildWorkflowLaneVisibleSummary(
              landmark,
              visibleQueueItems,
            );

            return (
              <button
                aria-pressed={isActive}
                className={
                  isActive
                    ? "admin-nav-button admin-nav-button-active"
                    : "admin-nav-button"
                }
                key={landmark.id}
                onClick={() => {
                  if (onSelectWorkflowLandmark) {
                    onSelectWorkflowLandmark(landmark);
                    return;
                  }

                  onSelectSection(landmark.defaultSectionId);
                }}
                type="button"
              >
                <span className="admin-nav-button-heading">
                  <span>{landmark.label}</span>
                  <StatusBadge className="admin-nav-button-status" tone={isActive ? "accent" : "neutral"}>
                    {isActive
                      ? "Current lane"
                      : `Opens ${landmark.primarySectionLabel}`}
                  </StatusBadge>
                </span>
                <span className="workflow-lane-map">
                  {landmark.mappedSectionsLabel}
                </span>
                <span className="admin-nav-button-metrics">
                  <span
                    className={
                      laneVisibleSummary.visiblePacketCount > 0
                        ? "queue-inline-pill queue-inline-pill-accent"
                        : "queue-inline-pill"
                    }
                  >
                    {formatCount(laneVisibleSummary.visiblePacketCount, "visible packet")}
                  </span>
                  <StatusBadge tone={laneVisibleSummary.dominantActionTone}>
                    {laneVisibleSummary.dominantActionLabel}
                  </StatusBadge>
                </span>
                <small className="admin-nav-button-metric-copy">
                  {laneVisibleSummary.visiblePacketCount > 0
                    ? formatVisibleQueueActionSummary(laneVisibleSummary)
                    : "No visible packets from the current queue page match this lane yet."}
                </small>
                <small>{landmark.detail}</small>
              </button>
            );
          })}
        </div>

        <small className="admin-nav-group-copy">
          Operational tabs remain under Controls + governance.
        </small>
      </SurfaceCard>

      <nav aria-label="Admin navigation" className="admin-nav-list">
        {adminSectionGroups.map((group) => (
          <SurfaceCard as="section" className="admin-nav-group" key={group.id}>
            <div className="admin-nav-group-heading">
              <div>
                <p className="admin-nav-group-label">{group.label}</p>
                <p className="admin-nav-group-copy">{group.detail}</p>
              </div>
              <StatusBadge
                tone={getAdminSectionGroupTone(group.sectionIds, activeSection)}
              >
                {group.sectionIds.includes(activeSection)
                  ? "Current focus"
                  : "Workflow"}
              </StatusBadge>
            </div>

            <div className="admin-nav-group-list">
              {group.sectionIds.map((sectionId) => {
                const section = getAdminSectionDefinition(sectionId);
                const isActive = activeSection === section.id;

                return (
                  <button
                    aria-current={isActive ? "page" : undefined}
                    className={
                      isActive
                        ? "admin-nav-button admin-nav-button-active"
                        : "admin-nav-button"
                    }
                    key={section.id}
                    onClick={() => {
                      onSelectSection(section.id);
                    }}
                    type="button"
                  >
                    <span className="admin-nav-button-heading">
                      <span>{section.label}</span>
                      {isActive ? (
                        <StatusBadge
                          className="admin-nav-button-status"
                          tone="accent"
                        >
                          Active
                        </StatusBadge>
                      ) : null}
                    </span>
                    <small>{section.detail}</small>
                  </button>
                );
              })}
            </div>
          </SurfaceCard>
        ))}
      </nav>

      <SurfaceMetricCard
        badge={
          <StatusBadge tone={selectedPacketName ? "success" : "neutral"}>
            Selected packet
          </StatusBadge>
        }
        className="admin-nav-footer"
        detail="Packet selection stays pinned while the workspace switches between review, viewer, intake, and governance surfaces."
        title="Pinned workspace packet"
        value={selectedPacketName || "Choose a packet row"}
      />

      <SurfaceCard className="admin-nav-api-spec-card">
        <div className="admin-nav-group-heading">
          <div>
            <p className="admin-nav-group-label">Operator API spec</p>
            <p className="admin-nav-group-copy">
              The protected admin OpenAPI document and Swagger-style HTML
              renderer used to live in the page footer. They now live one
              click away on the rail so reviewers find them without
              scrolling.
            </p>
          </div>
          <StatusBadge tone="accent">OpenAPI</StatusBadge>
        </div>
        <div className="admin-nav-api-spec-links">
          <a
            className="admin-nav-api-spec-link"
            href="/docs/operator-api"
            rel="noreferrer"
            target="_blank"
          >
            Open API reference
          </a>
          <a
            className="admin-nav-api-spec-link admin-nav-api-spec-link-secondary"
            href="/docs/operator-openapi.json"
            rel="noreferrer"
            target="_blank"
          >
            Raw OpenAPI JSON
          </a>
        </div>
      </SurfaceCard>
    </SurfacePanel>
  );
}
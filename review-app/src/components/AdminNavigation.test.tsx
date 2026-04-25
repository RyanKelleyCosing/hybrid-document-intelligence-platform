import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { PacketQueueItem } from "../api/packetQueueApi";
import { AdminNavigation } from "./AdminNavigation";

function buildVisibleQueueItem(
  overrides: Partial<PacketQueueItem> = {},
): PacketQueueItem {
  return {
    assigned_user_email: null,
    assignment_state: "unassigned",
    audit_event_count: 0,
    awaiting_review_document_count: 1,
    classification_keys: ["bank_correspondence"],
    completed_document_count: 0,
    document_count: 1,
    document_type_keys: ["bank_statement"],
    latest_job_stage_name: "review",
    latest_job_status: "queued",
    oldest_review_task_created_at_utc: "2026-04-15T16:00:00Z",
    operator_note_count: 0,
    packet_id: "packet-admin-nav-001",
    packet_name: "Northwind review packet",
    primary_document_id: "doc-admin-nav-001",
    primary_file_name: "statement.pdf",
    primary_issuer_category: "bank",
    primary_issuer_name: "Northwind Bank",
    queue_age_hours: 2,
    received_at_utc: "2026-04-15T16:00:00Z",
    review_task_count: 1,
    source: "scanned_upload",
    source_uri: "upload://admin-nav/manual",
    stage_name: "review",
    status: "awaiting_review",
    submitted_by: "reviewer@example.com",
    updated_at_utc: "2026-04-15T16:05:00Z",
    ...overrides,
  };
}

describe("AdminNavigation", () => {
  it("groups admin sections by workflow and routes selection changes", async () => {
    const user = userEvent.setup();
    const onSelectSection = vi.fn();
    const onSelectWorkflowLandmark = vi.fn();

    render(
      <AdminNavigation
        activeSection="pipeline"
        activeQueueFilters={{
          stage_name: "ocr",
          status: "ocr_running",
        }}
        onSelectSection={onSelectSection}
        onSelectWorkflowLandmark={onSelectWorkflowLandmark}
        queueCount={7}
        selectedPacketName="Northwind review packet"
        unassignedPacketCount={2}
        visibleQueueItems={[
          buildVisibleQueueItem({
            assignment_state: "assigned",
            assigned_user_email: "ops@example.com",
            awaiting_review_document_count: 0,
            completed_document_count: 1,
            latest_job_stage_name: "ocr",
            latest_job_status: "running",
            packet_id: "packet-admin-nav-002",
            review_task_count: 0,
            stage_name: "ocr",
            status: "ocr_running",
          }),
        ]}
      />,
    );

    expect(screen.getByText("Queue triage")).toBeInTheDocument();
    expect(screen.getByText("Evidence inspection")).toBeInTheDocument();
    expect(screen.getByText("Controls + governance")).toBeInTheDocument();
    expect(screen.getByText("Primary lanes")).toBeInTheDocument();
    expect(
      screen.getByText("Operational tabs remain under Controls + governance."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^Live Stream\b/i }),
    ).toBeInTheDocument();
    const liveStreamLane = screen.getByRole("button", { name: /^Live Stream\b/i });
    expect(within(liveStreamLane).getByText("1 visible packet")).toBeInTheDocument();
    expect(within(liveStreamLane).getByText("Monitor run")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^Operational tabs\b/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Pipeline + Sources")).toBeInTheDocument();
    expect(screen.getByText("Current lane")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Current lane maps to Pipeline \+ Sources\. Queue lens: Ocr stage · Ocr Running status\./i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^Pipeline\b/i }),
    ).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Northwind review packet")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Live Stream\b/i }));

    expect(onSelectWorkflowLandmark).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "liveStream",
      }),
    );

    await user.click(screen.getByRole("button", { name: /^Sources\b/i }));

    expect(onSelectSection).toHaveBeenCalledWith("sources");
  });

  it("shows the empty packet fallback when no packet is selected", () => {
    render(
      <AdminNavigation
        activeSection="review"
        onSelectSection={() => undefined}
        queueCount={0}
        selectedPacketName={null}
        unassignedPacketCount={0}
        visibleQueueItems={[]}
      />,
    );

    expect(screen.getByText("Choose a packet row")).toBeInTheDocument();
    expect(screen.getByText("Assigned")).toBeInTheDocument();
    const inboxLane = screen.getByRole("button", { name: /^Inbox\b/i });
    expect(within(inboxLane).getByText("0 visible packets")).toBeInTheDocument();
    expect(within(inboxLane).getByText("No visible packets")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Current lane maps to Review \+ Intake\. Queue lens: Review stage\./i,
      ),
    ).toBeInTheDocument();
  });

  it("exposes operator OpenAPI links on the navigation rail", () => {
    render(
      <AdminNavigation
        activeSection="review"
        onSelectSection={() => undefined}
        queueCount={0}
        selectedPacketName={null}
        unassignedPacketCount={0}
        visibleQueueItems={[]}
      />,
    );

    const reference = screen.getByRole("link", { name: /Open API reference/i });
    expect(reference).toHaveAttribute("href", "/docs/operator-api");
    const raw = screen.getByRole("link", { name: /Raw OpenAPI JSON/i });
    expect(raw).toHaveAttribute("href", "/docs/operator-openapi.json");
  });
});
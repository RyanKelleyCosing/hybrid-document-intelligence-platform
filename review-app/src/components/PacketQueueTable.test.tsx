import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PacketQueueItem } from "../api/packetQueueApi";
import { PacketQueueTable, type PacketQueueRefreshDelta } from "./PacketQueueTable";

function buildPacketQueueItem(
  overrides: Partial<PacketQueueItem> = {},
): PacketQueueItem {
  return {
    assigned_user_email: "operator@example.com",
    assignment_state: "assigned",
    audit_event_count: 4,
    awaiting_review_document_count: 2,
    classification_keys: ["hardship_packet"],
    completed_document_count: 1,
    document_count: 3,
    document_type_keys: ["borrower_letter"],
    latest_job_stage_name: "ocr",
    latest_job_status: "completed",
    oldest_review_task_created_at_utc: "2026-04-20T09:00:00Z",
    operator_note_count: 2,
    packet_id: "packet-001",
    packet_name: "Northwind Packet",
    primary_document_id: "doc-001",
    primary_file_name: "northwind.pdf",
    primary_issuer_category: "servicer",
    primary_issuer_name: "Northwind",
    queue_age_hours: 5,
    received_at_utc: "2026-04-20T08:00:00Z",
    review_task_count: 2,
    source: "email_connector",
    source_uri: "mailbox://northwind",
    stage_name: "review",
    status: "awaiting_review",
    submitted_by: "operator@example.com",
    updated_at_utc: "2026-04-20T10:00:00Z",
    ...overrides,
  };
}

describe("PacketQueueTable", () => {
  it("keeps the selectable queue row behavior after moving onto the shared table shell", () => {
    const onSelectPacket = vi.fn();
    const item = buildPacketQueueItem();

    render(
      <PacketQueueTable
        items={[item]}
        onSelectPacket={onSelectPacket}
        selectedPacketId={item.packet_id}
      />,
    );

    expect(
      screen.getByRole("columnheader", { name: "Packet" }),
    ).toBeInTheDocument();

    const row = screen.getByText("Northwind Packet").closest("tr");
    expect(row).toHaveAttribute("aria-selected", "true");

    fireEvent.click(row!);

    expect(onSelectPacket).toHaveBeenCalledWith(item);
    expect(screen.getByText("Assigned")).toBeInTheDocument();
    expect(screen.getByText(/4 audit events · 2 notes/i)).toBeInTheDocument();
    expect(screen.getByText(/Updated /i)).toBeInTheDocument();
    expect(screen.getByText("Best next")).toBeInTheDocument();
    expect(screen.getByText("Continue review")).toBeInTheDocument();
    expect(
      screen.getByText("Continue review · operator@example.com"),
    ).toBeInTheDocument();
  });

  it("prioritizes pipeline investigation when the latest job failed", () => {
    const item = buildPacketQueueItem({
      assigned_user_email: null,
      assignment_state: "unassigned",
      latest_job_stage_name: "ocr",
      latest_job_status: "failed",
      status: "failed",
    });

    render(
      <PacketQueueTable
        items={[item]}
        onSelectPacket={() => undefined}
        selectedPacketId={null}
      />,
    );

    expect(screen.getByText("Best next")).toBeInTheDocument();
    expect(screen.getByText("Investigate")).toBeInTheDocument();
    expect(screen.getByText("Investigate Ocr failure")).toBeInTheDocument();
  });

  it("renders live update badges when a queue row changes after refresh", () => {
    const item = buildPacketQueueItem();
    const refreshDelta: PacketQueueRefreshDelta = {
      activityDetail: {
        current: "3 audit events · 1 note · 2 review tasks",
        previous: "1 audit event · 0 notes · 2 review tasks",
      },
      hasActivityChange: true,
      assignmentDetail: {
        current: "Assigned · operator@example.com",
        previous: "Unassigned",
      },
      hasAssignmentChange: true,
      contractDetail: {
        current:
          "Classifications Hardship Packet, Borrower Letter · Types Borrower Letter, Bank Statement",
        previous: "Classifications Hardship Packet · Types Borrower Letter",
      },
      hasContractChange: true,
      stageDetail: {
        current: "Review queue · Ocr · Running",
        previous: "Review queue · Review · Queued",
      },
      hasStageChange: true,
      statusDetail: {
        current: "Awaiting Review · 1 awaiting review doc · 2 completed docs",
        previous: "Awaiting Review · 2 awaiting review docs · 1 completed doc",
      },
      hasStatusChange: true,
      isNewPacket: true,
    };

    render(
      <PacketQueueTable
        items={[item]}
        onSelectPacket={() => undefined}
        refreshDeltasByPacketId={{
          [item.packet_id]: refreshDelta,
        }}
        selectedPacketId={null}
      />,
    );

    const row = screen.getByText("Northwind Packet").closest("tr");

    expect(row).toHaveClass("queue-row-refresh-change");
    expect(screen.getByText("New in queue")).toBeInTheDocument();
    expect(screen.getByText("Contracts changed")).toBeInTheDocument();
    expect(screen.getByText("Stage moved")).toBeInTheDocument();
    expect(screen.getByText("Status updated")).toBeInTheDocument();
    expect(screen.getByText("Assignment changed")).toBeInTheDocument();
    expect(screen.getByText("Fresh activity")).toBeInTheDocument();
    expect(
      screen.getByText("Queue row is new on this refresh."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Assignment: Unassigned -> Assigned · operator@example.com",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Activity: 1 audit event · 0 notes · 2 review tasks -> 3 audit events · 1 note · 2 review tasks/i,
      ),
    ).toBeInTheDocument();
  });
});
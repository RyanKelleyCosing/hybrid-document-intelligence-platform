import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getLiveSession } from "../api/liveSessionApi";
import {
  listPacketQueue,
  type PacketQueueItem,
  type PacketQueueListResponse,
} from "../api/packetQueueApi";
import {
  executePacketStage,
  getPacketWorkspace,
  replayPacket,
  reviewPacketRecommendation,
  retryPacketStage,
  type PacketReplayResponse,
  type PacketStageExecutionResponse,
  type PacketStageRetryResponse,
  type PacketWorkspaceSnapshot,
} from "../api/packetWorkspaceApi";
import {
  submitPacketReviewAssignment,
  submitPacketReviewExtractionEdits,
  submitPacketReviewDecision,
  submitPacketReviewNote,
  submitPacketReviewTaskCreate,
} from "../api/packetReviewApi";
import { LiveReviewWorkbench } from "./LiveReviewWorkbench";

vi.mock("../api/liveSessionApi", () => ({
  getLiveSession: vi.fn(),
}));

vi.mock("../api/operatorContractsApi", () => ({
  getOperatorContracts: vi.fn(),
}));

vi.mock("../api/intakeSourcesApi", () => ({
  createIntakeSource: vi.fn(),
  deleteIntakeSource: vi.fn(),
  executeIntakeSource: vi.fn(),
  listIntakeSources: vi.fn(),
  setIntakeSourceEnablement: vi.fn(),
  updateIntakeSource: vi.fn(),
}));

vi.mock("../api/packetReviewApi", () => ({
  submitPacketReviewAssignment: vi.fn(),
  submitPacketReviewExtractionEdits: vi.fn(),
  submitPacketReviewDecision: vi.fn(),
  submitPacketReviewNote: vi.fn(),
  submitPacketReviewTaskCreate: vi.fn(),
}));

vi.mock("../api/packetQueueApi", async () => {
  const actual = await vi.importActual<typeof import("../api/packetQueueApi")>(
    "../api/packetQueueApi",
  );

  return {
    ...actual,
    listPacketQueue: vi.fn(),
  };
});

vi.mock("../api/packetWorkspaceApi", async () => {
  const actual = await vi.importActual<
    typeof import("../api/packetWorkspaceApi")
  >("../api/packetWorkspaceApi");

  return {
    ...actual,
    executePacketStage: vi.fn(),
    getPacketWorkspace: vi.fn(),
    replayPacket: vi.fn(),
    reviewPacketRecommendation: vi.fn(),
    retryPacketStage: vi.fn(),
  };
});

vi.mock("./ManualUploadPanel", () => ({
  ManualUploadPanel: () => <div data-testid="manual-upload-panel" />,
}));

vi.mock("./IntakeSourcesPanel", () => ({
  IntakeSourcesPanel: () => <div data-testid="intake-sources-panel" />,
}));

vi.mock("./PacketWorkspacePanel", () => ({
  PacketWorkspacePanel: (props: {
    onExecuteStage?: (stageName: "ocr") => void;
    onSubmitReviewAssignment?: (assignment: {
      assigned_user_email?: string | null;
      assigned_user_id?: string | null;
      expected_row_version: string;
      review_task_id: string;
    }) => void;
    onSubmitReviewDecision?: (decision: {
      decision_reason_code?: string;
      decision_status: "approved" | "rejected";
      expected_row_version: string;
      review_notes?: string;
      review_task_id: string;
      selected_account_id?: string | null;
    }) => void;
    onSubmitReviewNote?: (note: {
      expected_row_version: string;
      is_private?: boolean;
      note_text: string;
      review_task_id: string;
    }) => void;
    onSubmitReviewTaskCreate?: (reviewTask: {
      assigned_user_email?: string | null;
      assigned_user_id?: string | null;
      document_id: string;
      notes_summary?: string | null;
      selected_account_id?: string | null;
    }) => void;
    onSubmitExtractionEdits?: (extractionEdit: {
      expected_row_version: string;
      field_edits: { field_name: string; value: string }[];
      review_task_id: string;
    }) => void;
    onSelectTab?: (tabId: string) => void;
    onRetryStage?: (stageName: "ocr") => void;
    assignmentSuccessMessage: string | null;
    createTaskSuccessMessage: string | null;
    extractionEditSuccessMessage: string | null;
    noteSuccessMessage: string | null;
    pipelineActionSuccessMessage: string | null;
    preferredTab: string;
    selectedPacketSummary: { packet_id: string } | null;
    workspace: { packet: { packet_id: string } } | null;
  }) => (
    <section data-testid="packet-workspace-panel">
      <p data-testid="preferred-tab">{props.preferredTab}</p>
      <p data-testid="selected-packet-id">
        {props.selectedPacketSummary?.packet_id ?? "none"}
      </p>
      <p data-testid="workspace-packet-id">
        {props.workspace?.packet.packet_id ?? "none"}
      </p>
      {props.pipelineActionSuccessMessage ? (
        <p>{props.pipelineActionSuccessMessage}</p>
      ) : null}
      {props.assignmentSuccessMessage ? (
        <p>{props.assignmentSuccessMessage}</p>
      ) : null}
      {props.createTaskSuccessMessage ? <p>{props.createTaskSuccessMessage}</p> : null}
      {props.extractionEditSuccessMessage ? (
        <p>{props.extractionEditSuccessMessage}</p>
      ) : null}
      {props.noteSuccessMessage ? <p>{props.noteSuccessMessage}</p> : null}
      <button
        onClick={() => {
          props.onExecuteStage?.("ocr");
        }}
        type="button"
      >
        Execute OCR
      </button>
      <button
        onClick={() => {
          props.onRetryStage?.("ocr");
        }}
        type="button"
      >
        Retry OCR
      </button>
      <button
        onClick={() => {
          props.onSelectTab?.("ocr");
        }}
        type="button"
      >
        Select OCR tab
      </button>
      <button
        onClick={() => {
          props.onSubmitReviewAssignment?.({
            assigned_user_email: "qa.reviewer@example.com",
            expected_row_version: "0000000000000001",
            review_task_id: "task_workbench_001",
          });
        }}
        type="button"
      >
        Save review assignment
      </button>
      <button
        onClick={() => {
          props.onSubmitExtractionEdits?.({
            expected_row_version: "0000000000000001",
            field_edits: [
              {
                field_name: "account_number",
                value: "5678",
              },
            ],
            review_task_id: "task_workbench_001",
          });
        }}
        type="button"
      >
        Save extraction edit
      </button>
      <button
        onClick={() => {
          props.onSubmitReviewNote?.({
            expected_row_version: "0000000000000001",
            is_private: false,
            note_text: "Need one more statement page before approval.",
            review_task_id: "task_workbench_001",
          });
        }}
        type="button"
      >
        Save review note
      </button>
      <button
        onClick={() => {
          props.onSubmitReviewTaskCreate?.({
            assigned_user_email: "qa.reviewer@example.com",
            document_id: "doc_workbench_001",
            notes_summary: "Manual follow-up requested from the review workspace.",
            selected_account_id: "acct_123",
          });
        }}
        type="button"
      >
        Create review task
      </button>
      <button
        onClick={() => {
          props.onSubmitReviewDecision?.({
            decision_reason_code: "account_override_confirmed",
            decision_status: "approved",
            expected_row_version: "0000000000000001",
            review_notes: "Approved from the packet workspace.",
            review_task_id: "task_workbench_001",
            selected_account_id: "acct_123",
          });
        }}
        type="button"
      >
        Submit review decision
      </button>
    </section>
  ),
}));

const operatorEmail = "reviewer@example.com";
const packetId = "pkt_workbench_001";
const secondaryPacketId = "pkt_workbench_002";

const mockedGetLiveSession = vi.mocked(getLiveSession);
const mockedListPacketQueue = vi.mocked(listPacketQueue);
const mockedGetPacketWorkspace = vi.mocked(getPacketWorkspace);
const mockedExecutePacketStage = vi.mocked(executePacketStage);
const mockedRetryPacketStage = vi.mocked(retryPacketStage);
const mockedReplayPacket = vi.mocked(replayPacket);
const mockedReviewPacketRecommendation = vi.mocked(reviewPacketRecommendation);
const mockedSubmitPacketReviewAssignment = vi.mocked(submitPacketReviewAssignment);
const mockedSubmitPacketReviewExtractionEdits = vi.mocked(
  submitPacketReviewExtractionEdits,
);
const mockedSubmitPacketReviewDecision = vi.mocked(submitPacketReviewDecision);
const mockedSubmitPacketReviewNote = vi.mocked(submitPacketReviewNote);
const mockedSubmitPacketReviewTaskCreate = vi.mocked(submitPacketReviewTaskCreate);

function buildQueueItem(
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
    packet_id: packetId,
    packet_name: "Northwind review packet",
    primary_document_id: "doc_workbench_001",
    primary_file_name: "statement.pdf",
    primary_issuer_category: "bank",
    primary_issuer_name: "Northwind Bank",
    queue_age_hours: 2.5,
    received_at_utc: "2026-04-15T16:00:00Z",
    review_task_count: 1,
    source: "scanned_upload",
    source_uri: "upload://workbench/manual",
    stage_name: "review",
    status: "awaiting_review",
    submitted_by: operatorEmail,
    updated_at_utc: "2026-04-15T16:05:00Z",
    ...overrides,
  };
}

function buildQueueResponse(
  overrides: Partial<PacketQueueListResponse> = {},
): PacketQueueListResponse {
  return {
    has_more: false,
    items: [buildQueueItem()],
    page: 1,
    page_size: 10,
    total_count: 1,
    ...overrides,
  };
}

function buildWorkspace(): PacketWorkspaceSnapshot {
  return {
    account_match_runs: [],
    audit_events: [],
    classification_results: [],
    document_assets: [],
    documents: [
      {
        account_candidates: [],
        archive_preflight: {
          disposition: "not_archive",
          entry_count: 0,
          is_archive: false,
          is_multipart_archive: false,
          nested_archive_count: 0,
          total_uncompressed_bytes: 0,
          uses_zip64: false,
        },
        content_type: "application/pdf",
        created_at_utc: "2026-04-15T16:00:00Z",
        document_id: "doc_workbench_001",
        document_text: null,
        file_hash_sha256: null,
        file_name: "statement.pdf",
        issuer_category: "bank",
        issuer_name: "Northwind Bank",
        lineage: null,
        packet_id: packetId,
        received_at_utc: "2026-04-15T16:00:00Z",
        requested_prompt_profile_id: null,
        source: "scanned_upload",
        source_summary: "Uploaded through the operator shell.",
        source_tags: ["workbench"],
        source_uri: "upload://workbench/manual",
        status: "awaiting_review",
        updated_at_utc: "2026-04-15T16:05:00Z",
      },
    ],
    extraction_results: [],
    ocr_results: [],
    operator_notes: [],
    packet: {
      created_at_utc: "2026-04-15T16:00:00Z",
      duplicate_detection: null,
      packet_fingerprint: "pkt-workbench-fingerprint",
      packet_id: packetId,
      packet_name: "Northwind review packet",
      packet_tags: ["workbench"],
      received_at_utc: "2026-04-15T16:00:00Z",
      source: "scanned_upload",
      source_fingerprint: null,
      source_uri: "upload://workbench/manual",
      status: "awaiting_review",
      submitted_by: operatorEmail,
      updated_at_utc: "2026-04-15T16:05:00Z",
    },
    packet_events: [],
    processing_jobs: [],
    recommendation_results: [],
    recommendation_runs: [],
    review_decisions: [],
    review_tasks: [],
  };
}

function buildStageExecutionResponse(): PacketStageExecutionResponse {
  return {
    executed_document_count: 2,
    next_stage: "extraction",
    packet_id: packetId,
    skipped_document_ids: [],
    status: "extracting",
  };
}

function buildStageRetryResponse(): PacketStageRetryResponse {
  return {
    executed_document_count: 0,
    failed_job_count: 2,
    next_stage: "ocr",
    packet_id: packetId,
    requeued_document_count: 3,
    skipped_document_ids: [],
    stage_name: "ocr",
    stale_running_job_count: 1,
    status: "ocr_running",
  };
}

function buildReplayResponse(): PacketReplayResponse {
  return {
    action: "retry",
    executed_document_count: 0,
    failed_job_count: 1,
    message: "Replay queued the failed OCR work.",
    next_stage: "ocr",
    packet_id: packetId,
    requeued_document_count: 1,
    skipped_document_ids: [],
    stage_name: "ocr",
    stale_running_job_count: 0,
    status: "ocr_running",
  };
}

function renderWorkbench() {
  return render(<LiveReviewWorkbench />);
}

async function waitForWorkbenchToLoad(
  expectedFilters: Parameters<typeof mockedListPacketQueue>[0] = {
    page: 1,
    page_size: 10,
    stage_name: "review",
  },
) {
  await waitFor(() => {
    expect(mockedListPacketQueue).toHaveBeenCalledWith(expectedFilters);
  });

  await waitFor(() => {
    expect(mockedGetPacketWorkspace).toHaveBeenCalledWith(packetId);
  });

  await waitFor(() => {
    expect(screen.getByTestId("selected-packet-id")).toHaveTextContent(packetId);
    expect(screen.getByTestId("workspace-packet-id")).toHaveTextContent(packetId);
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState({}, "", "/admin");

  mockedGetLiveSession.mockResolvedValue({
    authenticated: true,
    authorized: true,
    email: operatorEmail,
    identityProvider: "aad",
  });
  mockedListPacketQueue.mockImplementation(async () => buildQueueResponse());
  mockedGetPacketWorkspace.mockImplementation(async () => buildWorkspace());
  mockedExecutePacketStage.mockResolvedValue(buildStageExecutionResponse());
  mockedRetryPacketStage.mockResolvedValue(buildStageRetryResponse());
  mockedReplayPacket.mockResolvedValue(buildReplayResponse());
  mockedReviewPacketRecommendation.mockResolvedValue({
    packet_id: packetId,
    recommendation_result: {
      advisory_text: null,
      confidence: 0.92,
      created_at_utc: "2026-04-15T16:02:00Z",
      disposition: "accepted",
      document_id: "doc_workbench_001",
      evidence_items: [],
      packet_id: packetId,
      rationale_payload: {},
      recommendation_kind: "route_to_specialist",
      recommendation_result_id: "rec_workbench_001",
      recommendation_run_id: "run_workbench_001",
      reviewed_at_utc: "2026-04-15T16:03:00Z",
      reviewed_by_email: operatorEmail,
      reviewed_by_user_id: null,
      summary: "Route this packet to a specialist.",
      updated_at_utc: "2026-04-15T16:03:00Z",
    },
  });
  mockedSubmitPacketReviewAssignment.mockResolvedValue({
    assigned_user_email: "qa.reviewer@example.com",
    assigned_user_id: null,
    packet_id: packetId,
    review_task_id: "task_workbench_001",
  });
  mockedSubmitPacketReviewExtractionEdits.mockResolvedValue({
    audit_event: {
      actor_email: operatorEmail,
      actor_user_id: null,
      audit_event_id: 301,
      created_at_utc: "2026-04-20T10:03:00Z",
      document_id: "doc_workbench_001",
      event_payload: {
        changedFields: [
          {
            current_value: "5678",
            field_name: "account_number",
            original_value: "1234",
          },
        ],
      },
      event_type: "review.extraction.fields.updated",
      packet_id: packetId,
      review_task_id: "task_workbench_001",
    },
    changed_fields: [
      {
        confidence: 0.94,
        current_value: "5678",
        field_name: "account_number",
        original_value: "1234",
      },
    ],
    document_id: "doc_workbench_001",
    extraction_result: {
      created_at_utc: "2026-04-20T10:03:00Z",
      document_id: "doc_workbench_001",
      document_type: "bank_statement",
      extraction_result_id: "ext_workbench_002",
      model_name: "gpt-5.4",
      packet_id: packetId,
      prompt_profile_id: "bank_statement",
      provider: "azure_openai",
      result_payload: {
        extractedFields: [
          {
            confidence: 0.94,
            name: "account_number",
            value: "5678",
          },
        ],
      },
      summary: "Primary statement extraction summary.",
    },
    packet_id: packetId,
    review_task_id: "task_workbench_001",
  });
  mockedSubmitPacketReviewNote.mockResolvedValue({
    operator_note: {
      created_at_utc: "2026-04-20T10:04:00Z",
      created_by_email: operatorEmail,
      created_by_user_id: null,
      document_id: "doc_workbench_001",
      is_private: false,
      note_id: "note_workbench_001",
      note_text: "Need one more statement page before approval.",
      packet_id: packetId,
      review_task_id: "task_workbench_001",
    },
    packet_id: packetId,
    review_task_id: "task_workbench_001",
  });
  mockedSubmitPacketReviewTaskCreate.mockResolvedValue({
    document_id: "doc_workbench_001",
    packet_id: packetId,
    review_task_id: "task_workbench_002",
  });
  mockedSubmitPacketReviewDecision.mockResolvedValue({
    decision: {
      decided_at_utc: "2026-04-15T16:03:00Z",
      decided_by_email: operatorEmail,
      decided_by_user_id: null,
      decision_id: "decision_workbench_001",
      decision_reason_code: null,
      decision_status: "approved",
      document_id: "doc_workbench_001",
      packet_id: packetId,
      review_notes: null,
      review_task_id: "task_workbench_001",
      selected_account_id: null,
    },
    document_status: "ready_for_recommendation",
    operator_note: null,
    packet_id: packetId,
    packet_status: "ready_for_recommendation",
    queued_recommendation_job_id: "job_workbench_001",
    review_task_id: "task_workbench_001",
    review_task_status: "ready_for_recommendation",
  });
});

describe("LiveReviewWorkbench", () => {
  it("hydrates the active admin section from the URL and updates the path when section changes", async () => {
    const user = userEvent.setup();

    window.history.replaceState({}, "", "/admin/viewer");

    renderWorkbench();
    await waitForWorkbenchToLoad();

    expect(screen.getByTestId("preferred-tab")).toHaveTextContent("viewer");
    expect(screen.getByText("Viewer workspace")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Pipeline\b/i }));

    await waitFor(() => {
      expect(window.location.pathname).toBe("/admin/pipeline");
      expect(screen.getByTestId("preferred-tab")).toHaveTextContent("pipeline");
    });
    expect(screen.getByText("Pipeline workspace")).toBeInTheDocument();
  });

  it("hydrates workspace tab overrides from the URL and updates search when tabs change", async () => {
    const user = userEvent.setup();

    window.history.replaceState({}, "", "/admin/review?tab=audit");

    renderWorkbench();
    await waitForWorkbenchToLoad();

    expect(screen.getByTestId("preferred-tab")).toHaveTextContent("audit");

    await user.click(screen.getByRole("button", { name: "Select OCR tab" }));

    await waitFor(() => {
      expect(window.location.pathname).toBe("/admin/review");
      expect(window.location.search).toBe(`?tab=ocr&packet=${packetId}`);
      expect(screen.getByTestId("preferred-tab")).toHaveTextContent("ocr");
    });
  });

  it("hydrates selected packet focus from the URL and updates search when queue selection changes", async () => {
    const user = userEvent.setup();

    mockedListPacketQueue.mockResolvedValueOnce(
      buildQueueResponse({
        items: [
          buildQueueItem(),
          buildQueueItem({
            packet_id: secondaryPacketId,
            packet_name: "Tailspin escalation packet",
            primary_document_id: "doc_workbench_002",
            primary_file_name: "tailspin.pdf",
            primary_issuer_name: "Tailspin Credit",
            source_uri: "upload://workbench/tailspin",
          }),
        ],
        total_count: 2,
      }),
    );

    window.history.replaceState(
      {},
      "",
      `/admin/review?packet=${secondaryPacketId}`,
    );

    renderWorkbench();

    await waitFor(() => {
      expect(mockedGetPacketWorkspace).toHaveBeenCalledWith(secondaryPacketId);
      expect(screen.getByTestId("selected-packet-id")).toHaveTextContent(
        secondaryPacketId,
      );
    });

    await user.click(screen.getByText("Northwind review packet"));

    await waitFor(() => {
      expect(mockedGetPacketWorkspace).toHaveBeenCalledWith(packetId);
      expect(window.location.pathname).toBe("/admin/review");
      expect(window.location.search).toBe(`?packet=${packetId}`);
      expect(screen.getByTestId("selected-packet-id")).toHaveTextContent(packetId);
    });
  });

  it("hydrates queue filters from the URL and preserves them through apply and reset", async () => {
    const user = userEvent.setup();

    window.history.replaceState(
      {},
      "",
      "/admin/review?stage=ocr&source=azure_blob&status=failed&assignment=ops@example.com",
    );

    renderWorkbench();

    await waitFor(() => {
      expect(mockedListPacketQueue).toHaveBeenCalledWith({
        assigned_user_email: "ops@example.com",
        page: 1,
        page_size: 10,
        source: "azure_blob",
        stage_name: "ocr",
        status: "failed",
      });
    });

    expect(screen.getByLabelText("Stage")).toHaveValue("ocr");
    expect(screen.getByLabelText("Source")).toHaveValue("azure_blob");
    expect(screen.getByLabelText("Status")).toHaveValue("failed");
    expect(screen.getByLabelText("Assignment")).toHaveValue("ops@example.com");

    await user.type(
      screen.getByLabelText("Classification"),
      "bank_correspondence",
    );
    await user.type(screen.getByLabelText("Document type"), "bank_statement");
    await user.type(screen.getByLabelText("Minimum age hours"), "4.5");

    await user.click(screen.getByRole("button", { name: "Apply filters" }));

    await waitFor(() => {
      const searchParams = new URLSearchParams(window.location.search);

      expect(searchParams.get("packet")).toBe(packetId);
      expect(searchParams.get("stage")).toBe("ocr");
      expect(searchParams.get("source")).toBe("azure_blob");
      expect(searchParams.get("status")).toBe("failed");
      expect(searchParams.get("assignment")).toBe("ops@example.com");
      expect(searchParams.get("classification")).toBe("bank_correspondence");
      expect(searchParams.get("documentType")).toBe("bank_statement");
      expect(searchParams.get("minAgeHours")).toBe("4.5");
    });

    await user.click(screen.getByRole("button", { name: "Reset filters" }));

    await waitFor(() => {
      const searchParams = new URLSearchParams(window.location.search);

      expect(searchParams.get("packet")).toBe(packetId);
      expect(searchParams.get("stage")).toBeNull();
      expect(searchParams.get("source")).toBeNull();
      expect(searchParams.get("status")).toBeNull();
      expect(searchParams.get("assignment")).toBeNull();
      expect(searchParams.get("classification")).toBeNull();
      expect(searchParams.get("documentType")).toBeNull();
      expect(searchParams.get("minAgeHours")).toBeNull();
    });
  });

  it("hydrates queue page from the URL and round-trips pagination through route state", async () => {
    const user = userEvent.setup();

    mockedListPacketQueue.mockImplementation(async (filters = {}) => {
      const page = Number(filters.page ?? 1);

      return buildQueueResponse({
        has_more: page < 2,
        page,
        total_count: 2,
      });
    });

    window.history.replaceState({}, "", "/admin/review?page=2");

    renderWorkbench();

    await waitFor(() => {
      expect(mockedListPacketQueue).toHaveBeenCalledWith({
        page: 2,
        page_size: 10,
        stage_name: "review",
      });
      expect(window.location.search).toBe(`?packet=${packetId}&page=2`);
    });

    fireEvent.click(screen.getByRole("button", { name: "Previous" }));

    await waitFor(() => {
      expect(mockedListPacketQueue).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 10,
        stage_name: "review",
      });
      expect(window.location.search).toBe(`?packet=${packetId}`);
    });

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(mockedListPacketQueue).toHaveBeenLastCalledWith({
        page: 2,
        page_size: 10,
        stage_name: "review",
      });
      expect(window.location.search).toBe(`?packet=${packetId}&page=2`);
    });

    window.history.pushState({}, "", `/admin/review?packet=${packetId}`);
    fireEvent.popState(window);

    await waitFor(() => {
      expect(mockedListPacketQueue).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 10,
        stage_name: "review",
      });
      expect(window.location.search).toBe(`?packet=${packetId}`);
    });
  });

  it("restores mixed queue page and filters through popstate transitions", async () => {
    mockedListPacketQueue.mockImplementation(async (filters = {}) => {
      const page = Number(filters.page ?? 1);

      return buildQueueResponse({
        has_more: page < 3,
        page,
        total_count: 3,
      });
    });

    window.history.replaceState(
      {},
      "",
      "/admin/review?page=2&stage=ocr&source=azure_blob&status=failed",
    );

    renderWorkbench();

    await waitFor(() => {
      expect(mockedListPacketQueue).toHaveBeenCalledWith({
        page: 2,
        page_size: 10,
        source: "azure_blob",
        stage_name: "ocr",
        status: "failed",
      });
      expect(screen.getByLabelText("Stage")).toHaveValue("ocr");
      expect(screen.getByLabelText("Source")).toHaveValue("azure_blob");
      expect(screen.getByLabelText("Status")).toHaveValue("failed");
    });

    window.history.pushState(
      {},
      "",
      `/admin/review?packet=${packetId}&stage=ocr&source=azure_blob&status=failed`,
    );
    fireEvent.popState(window);

    await waitFor(() => {
      expect(mockedListPacketQueue).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 10,
        source: "azure_blob",
        stage_name: "ocr",
        status: "failed",
      });
      expect(screen.getByLabelText("Stage")).toHaveValue("ocr");
      expect(screen.getByLabelText("Source")).toHaveValue("azure_blob");
      expect(screen.getByLabelText("Status")).toHaveValue("failed");
    });

    window.history.pushState(
      {},
      "",
      `/admin/review?packet=${packetId}&page=2&stage=ocr&source=azure_blob&status=failed`,
    );
    fireEvent.popState(window);

    await waitFor(() => {
      expect(mockedListPacketQueue).toHaveBeenLastCalledWith({
        page: 2,
        page_size: 10,
        source: "azure_blob",
        stage_name: "ocr",
        status: "failed",
      });
      expect(screen.getByLabelText("Stage")).toHaveValue("ocr");
      expect(screen.getByLabelText("Source")).toHaveValue("azure_blob");
      expect(screen.getByLabelText("Status")).toHaveValue("failed");
    });
  });

  it("applies and resets packet queue filters", async () => {
    const user = userEvent.setup();

    renderWorkbench();
    await waitForWorkbenchToLoad();
    const queueLens = screen.getByRole("region", { name: "Current queue lens" });

    await user.selectOptions(screen.getByLabelText("Stage"), "ocr");
    await user.selectOptions(screen.getByLabelText("Source"), "azure_blob");
    await user.selectOptions(screen.getByLabelText("Status"), "failed");
    await user.type(screen.getByLabelText("Assignment"), "ops@example.com");
    await user.type(
      screen.getByLabelText("Classification"),
      "bank_correspondence",
    );
    await user.type(screen.getByLabelText("Document type"), "bank_statement");
    await user.type(screen.getByLabelText("Minimum age hours"), "4.5");

    await user.click(screen.getByRole("button", { name: "Apply filters" }));

    await waitFor(() => {
      expect(mockedListPacketQueue).toHaveBeenLastCalledWith({
        assigned_user_email: "ops@example.com",
        classification_key: "bank_correspondence",
        document_type_key: "bank_statement",
        min_queue_age_hours: 4.5,
        page: 1,
        page_size: 10,
        source: "azure_blob",
        stage_name: "ocr",
        status: "failed",
      });
    });
    expect(within(queueLens).getByText("Custom queue lens")).toBeInTheDocument();
    expect(within(queueLens).getByText("Stage: Ocr")).toBeInTheDocument();
    expect(within(queueLens).getByText("Status: Failed")).toBeInTheDocument();
    expect(within(queueLens).getByText("Source: Azure Blob")).toBeInTheDocument();
    expect(
      within(queueLens).getByText("Assignment: ops@example.com"),
    ).toBeInTheDocument();
    expect(
      within(queueLens).getByText("Classification: Bank Correspondence"),
    ).toBeInTheDocument();
    expect(
      within(queueLens).getByText("Document type: Bank Statement"),
    ).toBeInTheDocument();
    expect(
      within(queueLens).getByText("Minimum age: 4.5h"),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reset filters" }));

    await waitFor(() => {
      expect(mockedListPacketQueue).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 10,
        stage_name: "review",
      });
    });
    expect(within(queueLens).getByText("Inbox")).toBeInTheDocument();
    expect(
      within(queueLens).getByText("Sections: Review + Intake"),
    ).toBeInTheDocument();
    expect(within(queueLens).getByText("Stage: Review")).toBeInTheDocument();
    expect(
      within(queueLens).queryByText("Status: Failed"),
    ).not.toBeInTheDocument();
    expect(
      within(queueLens).queryByText("Source: Azure Blob"),
    ).not.toBeInTheDocument();
  });

  it("switches the preferred workspace tab when the active section changes", async () => {
    const user = userEvent.setup();

    renderWorkbench();
    await waitForWorkbenchToLoad();

    expect(screen.getByTestId("preferred-tab")).toHaveTextContent("review");
    expect(screen.getByText("Review workspace")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Viewer\b/i }));
    await waitFor(() => {
      expect(screen.getByTestId("preferred-tab")).toHaveTextContent("viewer");
    });
    expect(screen.getByText("Viewer workspace")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Pipeline\b/i }));
    await waitFor(() => {
      expect(screen.getByTestId("preferred-tab")).toHaveTextContent("pipeline");
    });
    expect(screen.getByText("Pipeline workspace")).toBeInTheDocument();
  });

  it("maps primary lanes onto the real admin sections and resets stale queue filters", async () => {
    const user = userEvent.setup();

    window.history.replaceState(
      {},
      "",
      "/admin/review?tab=ocr&page=2&stage=classification&status=failed",
    );

    renderWorkbench();
    await waitForWorkbenchToLoad({
      page: 2,
      page_size: 10,
      stage_name: "classification",
      status: "failed",
    });

    expect(screen.getByText("Primary lanes")).toBeInTheDocument();
    expect(screen.getByText("Review + Intake")).toBeInTheDocument();
    expect(
      screen.getAllByText(
        /No named lane matches the current queue filters\. Queue lens: Classification stage · Failed status\./i,
      ).length,
    ).toBeGreaterThan(0);
    expect(screen.getByTestId("preferred-tab")).toHaveTextContent("ocr");

    mockedListPacketQueue.mockClear();

    await user.click(screen.getByRole("button", { name: /^Processed\b/i }));

    await waitFor(() => {
      expect(mockedListPacketQueue).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 10,
        stage_name: "recommendation",
        status: "completed",
      });
      expect(screen.getByTestId("preferred-tab")).toHaveTextContent("audit");
      expect(
        screen.getAllByText(
          /Maps to Recommendations \+ Audit\. Queue lens: Recommendation stage · Completed status\./i,
        ).length,
      ).toBeGreaterThan(0);
    });
    expect(screen.getByText("Audit workspace")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/admin/audit");
    await waitFor(() => {
      const searchParams = new URLSearchParams(window.location.search);
      expect(searchParams.get("tab")).toBeNull();
      expect(searchParams.get("page")).toBeNull();
      expect(searchParams.get("stage")).toBe("recommendation");
      expect(searchParams.get("status")).toBe("completed");
    });

    await user.click(screen.getByRole("button", { name: /^Inbox\b/i }));

    await waitFor(() => {
      expect(mockedListPacketQueue).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 10,
        stage_name: "review",
      });
      expect(screen.getByTestId("preferred-tab")).toHaveTextContent("review");
      expect(
        screen.getAllByText(/Maps to Review \+ Intake\. Queue lens: Review stage\./i)
          .length,
      ).toBeGreaterThan(0);
    });
    expect(screen.getByText("Review workspace")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/admin/review");
    await waitFor(() => {
      const searchParams = new URLSearchParams(window.location.search);
      expect(searchParams.get("tab")).toBeNull();
      expect(searchParams.get("page")).toBeNull();
      expect(searchParams.get("stage")).toBeNull();
      expect(searchParams.get("status")).toBeNull();
    });
  });

  it("shows queue refresh cues and packet audit signals in the protected shell", async () => {
    mockedListPacketQueue.mockResolvedValueOnce(
      buildQueueResponse({
        items: [
          buildQueueItem({
            audit_event_count: 4,
            operator_note_count: 2,
            review_task_count: 3,
            updated_at_utc: "2026-04-20T10:00:00Z",
          }),
        ],
      }),
    );
    mockedGetPacketWorkspace.mockResolvedValueOnce({
      ...buildWorkspace(),
      audit_events: [
        {
          actor_email: "auditor@example.com",
          actor_user_id: "auditor_001",
          audit_event_id: 1,
          created_at_utc: "2026-04-20T10:01:00Z",
          document_id: "doc_workbench_001",
          event_payload: { field: "account_number" },
          event_type: "field_override_recorded",
          packet_id: packetId,
          review_task_id: "task_workbench_001",
        },
      ],
      operator_notes: [
        {
          created_at_utc: "2026-04-20T10:02:00Z",
          created_by_email: operatorEmail,
          created_by_user_id: "ops_001",
          document_id: "doc_workbench_001",
          is_private: false,
          note_id: "note_workbench_001",
          note_text: "Packet is ready for renewed review.",
          packet_id: packetId,
          review_task_id: "task_workbench_001",
        },
      ],
      review_tasks: [
        {
          assigned_user_email: operatorEmail,
          assigned_user_id: "ops_001",
          created_at_utc: "2026-04-20T10:00:00Z",
          document_id: "doc_workbench_001",
          due_at_utc: null,
          notes_summary: "Review the updated packet.",
          packet_id: packetId,
          priority: "high",
          reason_codes: ["account_override"],
          review_task_id: "task_workbench_001",
          row_version: "0000000000000001",
          selected_account_id: null,
          status: "awaiting_review",
          updated_at_utc: "2026-04-20T10:02:00Z",
        },
      ],
    });

    renderWorkbench();
    await waitForWorkbenchToLoad();

    expect(screen.getByText("Visible audit signals")).toBeInTheDocument();
    expect(screen.getByText("Live refresh")).toBeInTheDocument();
    expect(screen.getByText("Packet signals")).toBeInTheDocument();
    expect(
      screen.getAllByText(/Maps to Review \+ Intake\. Queue lens: Review stage\./i)
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(/No queue-row changes since last snapshot\./i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Queue live snapshot/i)).toBeInTheDocument();
    expect(screen.getByText(/4 audit events · 2 notes/i)).toBeInTheDocument();
    expect(screen.getByText(/1 audit event · 1 note/i)).toBeInTheDocument();
  });

  it("surfaces visible lane urgency cues before the operator enters the queue table", async () => {
    renderWorkbench();
    await waitForWorkbenchToLoad();

    const inboxLane = screen.getByRole("button", { name: /^Inbox\b/i });
    expect(within(inboxLane).getByText("1 visible packet")).toBeInTheDocument();
    expect(within(inboxLane).getByText("Assign reviewer")).toBeInTheDocument();

    const inReviewLane = screen.getByRole("button", { name: /^In Review\b/i });
    expect(within(inReviewLane).getByText("1 visible packet")).toBeInTheDocument();
    expect(within(inReviewLane).getByText("Assign reviewer")).toBeInTheDocument();

    const queueLens = screen.getByRole("region", { name: "Current queue lens" });
    expect(within(queueLens).getByText("Visible: 1 packet")).toBeInTheDocument();
    expect(within(queueLens).getByText("Best next")).toBeInTheDocument();
    expect(
      within(queueLens).getByText(
        "Dominant visible next action: Assign reviewer across 1 packet.",
      ),
    ).toBeInTheDocument();
  });

  it("highlights queue rows that change after a manual refresh", async () => {
    const user = userEvent.setup();
    let queueLoadCount = 0;

    mockedListPacketQueue.mockImplementation(async () => {
      queueLoadCount += 1;

      return buildQueueResponse({
        items: [
          buildQueueItem(
            queueLoadCount === 1
              ? {
                  assigned_user_email: null,
                  assignment_state: "unassigned",
                  audit_event_count: 1,
                  classification_keys: ["bank_correspondence"],
                  document_type_keys: ["bank_statement"],
                  latest_job_stage_name: "review",
                  latest_job_status: "queued",
                  operator_note_count: 0,
                  updated_at_utc: "2026-04-20T10:00:00Z",
                }
              : {
                  assigned_user_email: operatorEmail,
                  assignment_state: "assigned",
                  audit_event_count: 3,
                  classification_keys: ["bank_correspondence", "hardship_packet"],
                  document_type_keys: ["bank_statement", "borrower_letter"],
                  latest_job_stage_name: "ocr",
                  latest_job_status: "running",
                  operator_note_count: 1,
                  updated_at_utc: "2026-04-20T10:05:00Z",
                },
          ),
        ],
      });
    });

    renderWorkbench();
    await waitForWorkbenchToLoad();

    expect(screen.queryByText("Stage moved")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Refresh packets" }));

    await waitFor(() => {
      expect(screen.getByText("Contracts changed")).toBeInTheDocument();
      expect(screen.getByText("Stage moved")).toBeInTheDocument();
      expect(screen.getByText("Assignment changed")).toBeInTheDocument();
      expect(screen.getByText("Fresh activity")).toBeInTheDocument();
      expect(
        screen.getByText(
          `Assignment: Unassigned -> Assigned · ${operatorEmail}`,
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          /Stage: Review queue · Review · Queued -> Review queue · Ocr · Running/i,
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/1 contract summary changed since last snapshot/i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          /1 stage move · 1 assignment change · 1 activity change · 1 contract summary change/i,
        ),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByText(/1 packet row changed since last snapshot/i),
    ).toBeInTheDocument();
  });

  it("persists extraction edits through the dedicated review API and refreshes the workspace", async () => {
    const user = userEvent.setup();

    renderWorkbench();
    await waitForWorkbenchToLoad();

    const initialQueueCallCount = mockedListPacketQueue.mock.calls.length;
    const initialWorkspaceCallCount = mockedGetPacketWorkspace.mock.calls.length;

    await user.click(screen.getByRole("button", { name: "Save extraction edit" }));

    await waitFor(() => {
      expect(mockedSubmitPacketReviewExtractionEdits).toHaveBeenCalledWith(
        "task_workbench_001",
        {
          edited_by_email: operatorEmail,
          expected_row_version: "0000000000000001",
          field_edits: [
            {
              field_name: "account_number",
              value: "5678",
            },
          ],
        },
      );
    });
    await waitFor(() => {
      expect(mockedListPacketQueue.mock.calls.length).toBeGreaterThan(
        initialQueueCallCount,
      );
      expect(mockedGetPacketWorkspace.mock.calls.length).toBeGreaterThan(
        initialWorkspaceCallCount,
      );
    });
    expect(
      screen.getByText("Saved 1 field edit for the selected review task."),
    ).toBeInTheDocument();
  });

  it("persists review-task assignments through the dedicated review API and refreshes the workspace", async () => {
    const user = userEvent.setup();

    renderWorkbench();
    await waitForWorkbenchToLoad();

    const initialQueueCallCount = mockedListPacketQueue.mock.calls.length;
    const initialWorkspaceCallCount = mockedGetPacketWorkspace.mock.calls.length;

    await user.click(screen.getByRole("button", { name: "Save review assignment" }));

    await waitFor(() => {
      expect(mockedSubmitPacketReviewAssignment).toHaveBeenCalledWith(
        "task_workbench_001",
        {
          assigned_by_email: operatorEmail,
          assigned_user_email: "qa.reviewer@example.com",
          assigned_user_id: null,
          expected_row_version: "0000000000000001",
        },
      );
    });
    await waitFor(() => {
      expect(mockedListPacketQueue.mock.calls.length).toBeGreaterThan(
        initialQueueCallCount,
      );
      expect(mockedGetPacketWorkspace.mock.calls.length).toBeGreaterThan(
        initialWorkspaceCallCount,
      );
    });
    expect(
      screen.getByText("Updated assignee for the selected review task."),
    ).toBeInTheDocument();
  });

  it("persists review-task notes through the dedicated review API and refreshes the workspace", async () => {
    const user = userEvent.setup();

    renderWorkbench();
    await waitForWorkbenchToLoad();

    const initialQueueCallCount = mockedListPacketQueue.mock.calls.length;
    const initialWorkspaceCallCount = mockedGetPacketWorkspace.mock.calls.length;

    await user.click(screen.getByRole("button", { name: "Save review note" }));

    await waitFor(() => {
      expect(mockedSubmitPacketReviewNote).toHaveBeenCalledWith(
        "task_workbench_001",
        {
          created_by_email: operatorEmail,
          expected_row_version: "0000000000000001",
          is_private: false,
          note_text: "Need one more statement page before approval.",
        },
      );
    });
    await waitFor(() => {
      expect(mockedListPacketQueue.mock.calls.length).toBeGreaterThan(
        initialQueueCallCount,
      );
      expect(mockedGetPacketWorkspace.mock.calls.length).toBeGreaterThan(
        initialWorkspaceCallCount,
      );
    });
    expect(
      screen.getByText("Saved note for the selected review task."),
    ).toBeInTheDocument();
  });

  it("creates review tasks for packet documents without existing tasks and refreshes the workspace", async () => {
    const user = userEvent.setup();

    renderWorkbench();
    await waitForWorkbenchToLoad();

    const initialQueueCallCount = mockedListPacketQueue.mock.calls.length;
    const initialWorkspaceCallCount = mockedGetPacketWorkspace.mock.calls.length;

    await user.click(screen.getByRole("button", { name: "Create review task" }));

    await waitFor(() => {
      expect(mockedSubmitPacketReviewTaskCreate).toHaveBeenCalledWith(
        packetId,
        "doc_workbench_001",
        {
          assigned_user_email: "qa.reviewer@example.com",
          assigned_user_id: null,
          created_by_email: operatorEmail,
          notes_summary: "Manual follow-up requested from the review workspace.",
          selected_account_id: "acct_123",
        },
      );
    });
    await waitFor(() => {
      expect(mockedListPacketQueue.mock.calls.length).toBeGreaterThan(
        initialQueueCallCount,
      );
      expect(mockedGetPacketWorkspace.mock.calls.length).toBeGreaterThan(
        initialWorkspaceCallCount,
      );
    });
    expect(
      screen.getByText("Created a review task for statement.pdf."),
    ).toBeInTheDocument();
  });

  it("persists structured decision reasons through the review API and refreshes the workspace", async () => {
    const user = userEvent.setup();

    renderWorkbench();
    await waitForWorkbenchToLoad();

    const initialQueueCallCount = mockedListPacketQueue.mock.calls.length;
    const initialWorkspaceCallCount = mockedGetPacketWorkspace.mock.calls.length;

    await user.click(screen.getByRole("button", { name: "Submit review decision" }));

    await waitFor(() => {
      expect(mockedSubmitPacketReviewDecision).toHaveBeenCalledWith(
        "task_workbench_001",
        {
          decided_by_email: operatorEmail,
          decision_reason_code: "account_override_confirmed",
          decision_status: "approved",
          expected_row_version: "0000000000000001",
          review_notes: "Approved from the packet workspace.",
          selected_account_id: "acct_123",
        },
      );
    });
    await waitFor(() => {
      expect(mockedListPacketQueue.mock.calls.length).toBeGreaterThan(
        initialQueueCallCount,
      );
      expect(mockedGetPacketWorkspace.mock.calls.length).toBeGreaterThan(
        initialWorkspaceCallCount,
      );
    });
  });

  it("executes a packet stage and refreshes the selected workspace", async () => {
    const user = userEvent.setup();

    renderWorkbench();
    await waitForWorkbenchToLoad();

    const initialQueueCallCount = mockedListPacketQueue.mock.calls.length;
    const initialWorkspaceCallCount = mockedGetPacketWorkspace.mock.calls.length;

    await user.click(screen.getByRole("button", { name: "Execute OCR" }));

    await waitFor(() => {
      expect(mockedExecutePacketStage).toHaveBeenCalledWith(packetId, "ocr");
    });
    await waitFor(() => {
      expect(mockedListPacketQueue.mock.calls.length).toBeGreaterThan(
        initialQueueCallCount,
      );
      expect(mockedGetPacketWorkspace.mock.calls.length).toBeGreaterThan(
        initialWorkspaceCallCount,
      );
    });
    expect(
      screen.getByText(
        "Ocr executed 2 documents. Packet status is Extracting.",
      ),
    ).toBeInTheDocument();
  });

  it("retries a packet stage and reports the intervention summary", async () => {
    const user = userEvent.setup();

    renderWorkbench();
    await waitForWorkbenchToLoad();

    const initialQueueCallCount = mockedListPacketQueue.mock.calls.length;
    const initialWorkspaceCallCount = mockedGetPacketWorkspace.mock.calls.length;

    await user.click(screen.getByRole("button", { name: "Retry OCR" }));

    await waitFor(() => {
      expect(mockedRetryPacketStage).toHaveBeenCalledWith(packetId, "ocr");
    });
    await waitFor(() => {
      expect(mockedListPacketQueue.mock.calls.length).toBeGreaterThan(
        initialQueueCallCount,
      );
      expect(mockedGetPacketWorkspace.mock.calls.length).toBeGreaterThan(
        initialWorkspaceCallCount,
      );
    });
    expect(
      screen.getByText(
        "Ocr retried 3 documents. 2 failed jobs and 1 stale running job qualified for intervention.",
      ),
    ).toBeInTheDocument();
  });
});
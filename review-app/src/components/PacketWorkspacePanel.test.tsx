import type { ComponentProps } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { OperatorContractsResponse } from "../api/operatorContractsApi";
import type { PacketQueueItem } from "../api/packetQueueApi";
import {
  buildPacketDocumentContentUrl,
  type PacketWorkspaceSnapshot,
} from "../api/packetWorkspaceApi";
import { PacketWorkspacePanel } from "./PacketWorkspacePanel";

function buildWorkspace(): PacketWorkspaceSnapshot {
  return {
    account_match_runs: [
      {
        candidates: [
          {
            account_id: "acct_auto_001",
            account_number: "1234",
            debtor_name: "Alex Carter",
            issuer_name: "Northwind Bank",
            matched_on: ["account_number", "debtor_name"],
            score: 97,
          },
          {
            account_id: "acct_override_002",
            account_number: "9876",
            debtor_name: "Alex Carter",
            issuer_name: "Northwind Bank",
            matched_on: ["debtor_name"],
            score: 88,
          },
        ],
        created_at_utc: "2026-04-16T12:00:00Z",
        document_id: "doc_001",
        match_run_id: "match_001",
        packet_id: "pkt_001",
        rationale: "Auto-linked from account number and debtor name.",
        selected_account_id: "acct_auto_001",
        status: "completed",
      },
    ],
    audit_events: [
      {
        actor_email: "auditor@example.com",
        actor_user_id: "auditor_001",
        audit_event_id: 100,
        created_at_utc: "2026-04-16T12:10:00Z",
        document_id: "doc_001",
        event_payload: { reason: "override reviewed" },
        event_type: "account_override_reviewed",
        packet_id: "pkt_001",
        review_task_id: "task_001",
      },
      {
        actor_email: "reviewer@example.com",
        actor_user_id: "reviewer_001",
        audit_event_id: 101,
        created_at_utc: "2026-04-16T12:11:30Z",
        document_id: "doc_001",
        event_payload: {
          changedFields: [
            {
              confidence: 0.94,
              current_value: "5678",
              field_name: "account_number",
              original_value: "1234",
            },
          ],
          newExtractionResultId: "ext_003",
          sourceExtractionResultId: "ext_001",
        },
        event_type: "review.extraction.fields.updated",
        packet_id: "pkt_001",
        review_task_id: "task_001",
      },
    ],
    classification_results: [
      {
        classification_id: "cls_bank_correspondence",
        classification_result_id: "clsr_001",
        confidence: 0.95,
        created_at_utc: "2026-04-16T12:00:30Z",
        document_id: "doc_001",
        document_type_id: "doc_bank_statement",
        packet_id: "pkt_001",
        prompt_profile_id: "bank_statement",
        result_payload: {},
        result_source: "rule",
      },
      {
        classification_id: "cls_bank_correspondence",
        classification_result_id: "clsr_002",
        confidence: 0.9,
        created_at_utc: "2026-04-16T12:00:45Z",
        document_id: "doc_002",
        document_type_id: "doc_cover_letter",
        packet_id: "pkt_001",
        prompt_profile_id: null,
        result_payload: {},
        result_source: "ai",
      },
    ],
    document_assets: [
      {
        asset_id: "asset_001",
        asset_role: "original_upload",
        blob_name: "raw/statement.pdf",
        container_name: "raw-documents",
        content_length_bytes: 1024,
        content_type: "application/pdf",
        created_at_utc: "2026-04-16T11:55:30Z",
        document_id: "doc_001",
        packet_id: "pkt_001",
        storage_uri: "https://storage.example/raw/statement.pdf",
      },
      {
        asset_id: "asset_002",
        asset_role: "original_upload",
        blob_name: "raw/cover-letter.pdf",
        container_name: "raw-documents",
        content_length_bytes: 512,
        content_type: "application/pdf",
        created_at_utc: "2026-04-16T11:56:30Z",
        document_id: "doc_002",
        packet_id: "pkt_001",
        storage_uri: "https://storage.example/raw/cover-letter.pdf",
      },
    ],
    documents: [
      {
        account_candidates: ["acct_auto_001", "acct_override_002"],
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
        created_at_utc: "2026-04-16T11:55:00Z",
        document_id: "doc_001",
        document_text: null,
        file_hash_sha256: null,
        file_name: "statement.pdf",
        issuer_category: "bank",
        issuer_name: "Northwind Bank",
        lineage: {
          archive_depth: 1,
          archive_member_path: "archive/statement.pdf",
          parent_document_id: "doc_archive_root",
          source_asset_id: "asset_001",
        },
        packet_id: "pkt_001",
        received_at_utc: "2026-04-16T11:55:00Z",
        requested_prompt_profile_id: null,
        source: "scanned_upload",
        source_summary: "Uploaded from the operator batch inbox.",
        source_tags: ["priority"],
        source_uri: null,
        status: "awaiting_review",
        updated_at_utc: "2026-04-16T12:11:00Z",
      },
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
        created_at_utc: "2026-04-16T11:56:00Z",
        document_id: "doc_002",
        document_text: null,
        file_hash_sha256: null,
        file_name: "cover-letter.pdf",
        issuer_category: "bank",
        issuer_name: "Northwind Bank",
        lineage: null,
        packet_id: "pkt_001",
        received_at_utc: "2026-04-16T11:56:00Z",
        requested_prompt_profile_id: null,
        source: "scanned_upload",
        source_summary: "Secondary packet evidence.",
        source_tags: [],
        source_uri: null,
        status: "awaiting_review",
        updated_at_utc: "2026-04-16T12:11:30Z",
      },
    ],
    extraction_results: [
      {
        created_at_utc: "2026-04-16T12:05:00Z",
        document_id: "doc_001",
        document_type: "bank_statement",
        extraction_result_id: "ext_001",
        model_name: "gpt-5.4",
        packet_id: "pkt_001",
        prompt_profile_id: "bank_statement",
        provider: "azure_openai",
        result_payload: {
          extractedFields: [
            {
              confidence: 0.94,
              name: "account_number",
              value: "1234",
            },
          ],
        },
        summary: "Primary statement extraction summary.",
      },
      {
        created_at_utc: "2026-04-16T12:05:10Z",
        document_id: "doc_002",
        document_type: "cover_letter",
        extraction_result_id: "ext_002",
        model_name: "gpt-5.4",
        packet_id: "pkt_001",
        prompt_profile_id: null,
        provider: "azure_openai",
        result_payload: {},
        summary: "Secondary cover letter extraction summary.",
      },
    ],
    ocr_results: [
      {
        created_at_utc: "2026-04-16T12:04:00Z",
        document_id: "doc_001",
        model_name: "prebuilt-layout",
        ocr_confidence: 0.97,
        ocr_result_id: "ocr_001",
        packet_id: "pkt_001",
        page_count: 2,
        provider: "azure_document_intelligence",
        text_excerpt:
          "Statement OCR excerpt for the selected PDF. Account number 1234 is visible.",
        text_storage_uri: "https://storage.example/ocr/doc_001.txt",
      },
      {
        created_at_utc: "2026-04-16T12:04:10Z",
        document_id: "doc_002",
        model_name: "prebuilt-layout",
        ocr_confidence: 0.89,
        ocr_result_id: "ocr_002",
        packet_id: "pkt_001",
        page_count: 1,
        provider: "azure_document_intelligence",
        text_excerpt: "Cover letter OCR excerpt for the secondary document.",
        text_storage_uri: "https://storage.example/ocr/doc_002.txt",
      },
    ],
    operator_notes: [
      {
        created_at_utc: "2026-04-16T12:09:00Z",
        created_by_email: "ops.lead@example.com",
        created_by_user_id: "ops_001",
        document_id: "doc_001",
        is_private: false,
        note_id: "note_001",
        note_text: "Manual override needed before final submission.",
        packet_id: "pkt_001",
        review_task_id: "task_001",
      },
    ],
    packet: {
      created_at_utc: "2026-04-16T11:55:00Z",
      duplicate_detection: null,
      packet_fingerprint: "pkt-fingerprint-001",
      packet_id: "pkt_001",
      packet_name: "Northwind intake packet",
      packet_tags: ["urgent"],
      received_at_utc: "2026-04-16T11:55:00Z",
      source: "scanned_upload",
      source_fingerprint: null,
      source_uri: null,
      status: "awaiting_review",
      submitted_by: "operator@example.com",
      updated_at_utc: "2026-04-16T12:12:00Z",
    },
    packet_events: [
      {
        created_at_utc: "2026-04-16T12:08:00Z",
        document_id: "doc_001",
        event_id: 10,
        event_payload: { stage: "review" },
        event_type: "review_task_created",
        packet_id: "pkt_001",
      },
    ],
    processing_jobs: [
      {
        attempt_number: 1,
        completed_at_utc: "2026-04-16T11:58:00Z",
        created_at_utc: "2026-04-16T11:57:00Z",
        document_id: "doc_001",
        error_code: null,
        error_message: null,
        job_id: "job_classification_001",
        packet_id: "pkt_001",
        queued_at_utc: "2026-04-16T11:57:00Z",
        stage_name: "classification",
        started_at_utc: "2026-04-16T11:57:10Z",
        status: "succeeded",
        updated_at_utc: "2026-04-16T11:58:00Z",
      },
      {
        attempt_number: 2,
        completed_at_utc: null,
        created_at_utc: "2026-04-16T12:02:00Z",
        document_id: "doc_001",
        error_code: "ocr_timeout",
        error_message: "OCR worker timed out on a prior attempt.",
        job_id: "job_ocr_001",
        packet_id: "pkt_001",
        queued_at_utc: "2026-04-16T12:02:00Z",
        stage_name: "ocr",
        started_at_utc: "2026-04-16T12:02:30Z",
        status: "failed",
        updated_at_utc: "2026-04-16T12:03:00Z",
      },
      {
        attempt_number: 1,
        completed_at_utc: null,
        created_at_utc: "2026-04-16T12:04:30Z",
        document_id: "doc_001",
        error_code: null,
        error_message: null,
        job_id: "job_extraction_001",
        packet_id: "pkt_001",
        queued_at_utc: "2026-04-16T12:04:30Z",
        stage_name: "extraction",
        started_at_utc: null,
        status: "queued",
        updated_at_utc: "2026-04-16T12:04:30Z",
      },
    ],
    recommendation_results: [
      {
        advisory_text: "Request additional proof before settlement submission.",
        confidence: 0.91,
        created_at_utc: "2026-04-16T12:06:00Z",
        disposition: "pending",
        document_id: "doc_001",
        evidence_items: [
          {
            evidence_kind: "ocr_excerpt",
            field_name: "account_number",
            source_document_id: "doc_001",
            source_excerpt: "Account number does not match the debtor file.",
            storage_uri: null,
          },
        ],
        packet_id: "pkt_001",
        rationale_payload: { rule: "account_mismatch" },
        recommendation_kind: "request_additional_document",
        recommendation_result_id: "rec_001",
        recommendation_run_id: "run_001",
        reviewed_at_utc: null,
        reviewed_by_email: null,
        reviewed_by_user_id: null,
        summary: "Ask for a new statement with the confirmed account id.",
        updated_at_utc: "2026-04-16T12:06:10Z",
      },
    ],
    recommendation_runs: [
      {
        completed_at_utc: "2026-04-16T12:06:05Z",
        created_at_utc: "2026-04-16T12:05:00Z",
        document_id: "doc_001",
        input_payload: { review_task_id: "task_001" },
        packet_id: "pkt_001",
        prompt_profile_id: null,
        recommendation_run_id: "run_001",
        requested_by_email: "ops.lead@example.com",
        requested_by_user_id: "ops_001",
        review_task_id: "task_001",
        status: "completed",
        updated_at_utc: "2026-04-16T12:06:05Z",
      },
    ],
    review_decisions: [
      {
        decided_at_utc: "2026-04-16T12:07:00Z",
        decided_by_email: "reviewer@example.com",
        decided_by_user_id: "reviewer_001",
        decision_id: "decision_001",
        decision_reason_code: "account_override_confirmed",
        decision_status: "approved",
        document_id: "doc_001",
        packet_id: "pkt_001",
        review_notes: "Override confirmed against the debtor ledger.",
        review_task_id: "task_001",
        selected_account_id: "acct_override_002",
      },
    ],
    review_tasks: [
      {
        assigned_user_email: "reviewer@example.com",
        assigned_user_id: "reviewer_001",
        created_at_utc: "2026-04-16T12:01:00Z",
        document_id: "doc_001",
        due_at_utc: "2026-04-16T14:00:00Z",
        notes_summary: "Confirm the correct account link.",
        packet_id: "pkt_001",
        priority: "high",
        reason_codes: ["account_override"],
        review_task_id: "task_001",
        row_version: "0000000000000001",
        selected_account_id: "acct_override_002",
        status: "awaiting_review",
        updated_at_utc: "2026-04-16T12:02:00Z",
      },
    ],
  };
}

function buildSelectedPacketSummary(): PacketQueueItem {
  return {
    assigned_user_email: "reviewer@example.com",
    assignment_state: "mixed",
    audit_event_count: 1,
    awaiting_review_document_count: 2,
    classification_keys: [],
    completed_document_count: 0,
    document_count: 2,
    document_type_keys: [],
    latest_job_stage_name: "review",
    latest_job_status: "queued",
    oldest_review_task_created_at_utc: "2026-04-16T12:01:00Z",
    operator_note_count: 1,
    packet_id: "pkt_001",
    packet_name: "Northwind intake packet",
    primary_document_id: "doc_001",
    primary_file_name: "statement.pdf",
    primary_issuer_category: "bank",
    primary_issuer_name: "Northwind Bank",
    queue_age_hours: 2,
    received_at_utc: "2026-04-16T11:55:00Z",
    review_task_count: 2,
    source: "scanned_upload",
    source_uri: null,
    stage_name: "review",
    status: "awaiting_review",
    submitted_by: "operator@example.com",
    updated_at_utc: "2026-04-16T12:12:00Z",
  };
}

function buildOperatorContracts(): OperatorContractsResponse {
  return {
    classification_definitions: [
      {
        classification_id: "cls_bank_correspondence",
        classification_key: "bank_correspondence",
        created_at_utc: "2026-04-16T11:56:00Z",
        default_prompt_profile_id: "bank_statement",
        description: "Managed bank correspondence classification.",
        display_name: "Bank correspondence",
        is_enabled: true,
        issuer_category: "bank",
        updated_at_utc: "2026-04-16T11:56:00Z",
      },
    ],
    document_type_definitions: [
      {
        classification_id: "cls_bank_correspondence",
        created_at_utc: "2026-04-16T11:56:10Z",
        default_prompt_profile_id: "bank_statement",
        description: "Managed bank statement contract.",
        display_name: "Bank statement",
        document_type_id: "doc_bank_statement",
        document_type_key: "bank_statement",
        is_enabled: true,
        required_fields: ["account_number", "statement_date"],
        updated_at_utc: "2026-04-16T11:56:10Z",
      },
    ],
    processing_taxonomy: {
      stages: [
        {
          description: "Classify the packet against managed taxonomy.",
          display_name: "Classification",
          stage_name: "classification",
          statuses: ["queued", "succeeded"],
        },
        {
          description: "Run OCR against protected packet documents.",
          display_name: "OCR",
          stage_name: "ocr",
          statuses: ["queued", "failed", "succeeded"],
        },
      ],
      statuses: [],
    },
    prompt_profile_versions: [
      {
        created_at_utc: "2026-04-16T11:56:20Z",
        definition_payload: { model: "gpt-4.1" },
        is_active: true,
        prompt_profile_id: "bank_statement",
        prompt_profile_version_id: "ppv_001",
        version_number: 3,
      },
    ],
    prompt_profiles: [
      {
        created_at_utc: "2026-04-16T11:56:15Z",
        description: "Managed statement extraction profile.",
        display_name: "Bank statement",
        is_enabled: true,
        issuer_category: "bank",
        prompt_profile_id: "bank_statement",
        updated_at_utc: "2026-04-16T11:56:15Z",
      },
    ],
    recommendation_contract: {
      advisory_only: true,
      default_status: "pending",
      disposition_values: ["accepted", "rejected"],
      required_evidence_kinds: ["ocr_excerpt", "classification"],
      required_packet_status: "awaiting_review",
    },
  };
}

function buildPanelProps(
  overrides?: Partial<ComponentProps<typeof PacketWorkspacePanel>>,
): ComponentProps<typeof PacketWorkspacePanel> {
  return {
    assignmentErrorMessage: null,
    assignmentSuccessMessage: null,
    createTaskErrorMessage: null,
    createTaskSuccessMessage: null,
    decisionErrorMessage: null,
    errorMessage: null,
    extractionEditErrorMessage: null,
    extractionEditSuccessMessage: null,
    intakeActionErrorMessage: null,
    intakeActionSuccessMessage: null,
    isAssignmentSubmitting: false,
    isExtractionEditSubmitting: false,
    isDecisionSubmitting: false,
    isNoteSubmitting: false,
    isReviewTaskCreateSubmitting: false,
    isLoading: false,
    isOperatorContractsLoading: false,
    isReplayingPacket: false,
    noteErrorMessage: null,
    noteSuccessMessage: null,
    onExecuteStage: undefined,
    onRefresh: () => undefined,
    onReplayPacket: undefined,
    onRetryStage: undefined,
    onReviewRecommendation: undefined,
    onSubmitExtractionEdits: undefined,
    onSubmitReviewAssignment: undefined,
    onSubmitReviewNote: undefined,
    onSubmitReviewTaskCreate: undefined,
    onSubmitReviewDecision: undefined,
    operatorContracts: null,
    operatorContractsErrorMessage: null,
    panelDescription: "Workspace panel",
    panelTitle: "Workspace",
    pipelineActionErrorMessage: null,
    pipelineActionSuccessMessage: null,
    preferredTab: "overview",
    processingPipelineAction: null,
    processingRecommendationReview: null,
    recommendationActionErrorMessage: null,
    recommendationActionSuccessMessage: null,
    reviewerEmail: "reviewer@example.com",
    selectedPacketSummary: buildSelectedPacketSummary(),
    workspace: buildWorkspace(),
    workspaceLastLoadedAt: "2026-04-24T17:42:00.000Z",
    ...overrides,
  };
}

function renderPanel(overrides?: Partial<ComponentProps<typeof PacketWorkspacePanel>>) {
  return render(<PacketWorkspacePanel {...buildPanelProps(overrides)} />);
}

describe("PacketWorkspacePanel", () => {
  it("renders primitive-backed workspace chrome for the selected packet and active view", () => {
    renderPanel({ preferredTab: "viewer" });

    expect(screen.getByText("Selected packet")).toBeInTheDocument();
    expect(screen.getByText("Northwind intake packet")).toBeInTheDocument();
    expect(screen.getByText("Workspace views")).toBeInTheDocument();
    expect(screen.getByText("Current view")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Viewer" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("renders the workspace last-refreshed indicator with the operator email", () => {
    renderPanel({
      preferredTab: "review",
      reviewerEmail: "operator@contoso.com",
      workspaceLastLoadedAt: "2026-04-24T17:42:00.000Z",
    });

    const indicator = screen.getByText(/Workspace last refreshed/i);
    expect(indicator).toBeInTheDocument();
    expect(indicator.textContent).toMatch(/Operator operator@contoso\.com/);
  });

  it("reorders workspace tabs around the active lane and tightens the tab copy", () => {
    const { rerender } = renderPanel({ preferredTab: "review" });

    expect(
      screen.getByText(
        "Review lane keeps Review, Viewer, Matching, Documents, and Audit first. More views reveals 7 additional tabs when needed.",
      ),
    ).toBeInTheDocument();
    expect(
      screen
        .getAllByRole("tab")
        .slice(0, 5)
        .map((tab) => tab.textContent),
    ).toEqual(["Review", "Viewer", "Matching", "Documents", "Audit"]);
    expect(screen.queryByRole("tab", { name: "OCR" })).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "More views (7) · Best next: Overview · Intake and 5 more",
      }),
    ).toBeInTheDocument();

    rerender(
      <PacketWorkspacePanel
        {...buildPanelProps({ preferredTab: "pipeline" })}
      />,
    );

    expect(
      screen.getByText(
        "Pipeline lane keeps Pipeline, OCR, Extraction, Documents, and Audit first. More views reveals 7 additional tabs when needed.",
      ),
    ).toBeInTheDocument();
    expect(
      screen
        .getAllByRole("tab")
        .slice(0, 5)
        .map((tab) => tab.textContent),
    ).toEqual(["Pipeline", "OCR", "Extraction", "Documents", "Audit"]);
  });

  it("prioritizes urgent hidden workspace views in the collapsed toggle copy", () => {
    const { rerender } = renderPanel({
      preferredTab: "review",
      selectedPacketSummary: {
        ...buildSelectedPacketSummary(),
        latest_job_stage_name: "ocr",
        latest_job_status: "failed",
        status: "failed",
      },
    });

    expect(
      screen.getByRole("button", {
        name: "More views (7) · Best next: Pipeline (Pipeline failure) · Overview and 5 more",
      }),
    ).toBeInTheDocument();

    rerender(
      <PacketWorkspacePanel
        {...buildPanelProps({
          preferredTab: "viewer",
          selectedPacketSummary: {
            ...buildSelectedPacketSummary(),
            audit_event_count: 3,
            latest_job_stage_name: "review",
            latest_job_status: "completed",
          },
        })}
      />,
    );

    expect(
      screen.getByRole("button", {
        name: "More views (7) · Best next: Audit (Fresh audit activity) · Overview and 5 more",
      }),
    ).toBeInTheDocument();
  });

  it("renders overview content through shared surface sections", () => {
    renderPanel({ preferredTab: "overview" });

    expect(
      screen.getByRole("heading", { name: "Overview summary" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Document summaries" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Counts")).toBeInTheDocument();
  });

  it("renders blocker-first document cues before expanding the full status grid", async () => {
    const user = userEvent.setup();

    renderPanel({
      operatorContracts: buildOperatorContracts(),
      preferredTab: "documents",
    });

    const documentCard = screen.getByText("statement.pdf").closest("article");
    expect(documentCard).not.toBeNull();
    expect(
      within(documentCard as HTMLElement).getByText("Current attention"),
    ).toBeInTheDocument();
    const documentPath = within(documentCard as HTMLElement).getByRole("list", {
      name: "Document path for statement.pdf",
    });
    const liveGrid = (documentCard as HTMLElement).querySelector(
      ".workspace-document-live-grid",
    );
    expect(liveGrid).not.toBeNull();
    expect(within(documentPath).getByText("OCR")).toBeInTheDocument();
    expect(within(documentPath).getByText("Extraction")).toBeInTheDocument();
    expect(within(documentPath).getByText("Account")).toBeInTheDocument();
    expect(within(documentPath).getByText("Review")).toBeInTheDocument();
    expect(within(documentPath).getByText("Recommendation")).toBeInTheDocument();
    expect(within(documentPath).getAllByText("Ready")).toHaveLength(2);
    expect(within(documentPath).getByText("Override")).toBeInTheDocument();
    expect(within(documentPath).getByText("Approved")).toBeInTheDocument();
    expect(within(documentPath).getByText("Pending")).toBeInTheDocument();
    expect(within(documentPath).getAllByText(/Stored .*2026/i).length).toBe(2);
    expect(within(documentPath).getAllByText(/Reviewed .*2026/i).length).toBe(2);
    expect(within(liveGrid as HTMLElement).getByText("Attention")).toBeInTheDocument();
    expect(within(liveGrid as HTMLElement).getByText("Review")).toBeInTheDocument();
    expect(within(liveGrid as HTMLElement).getByText("Contract")).toBeInTheDocument();
    expect(within(liveGrid as HTMLElement).getByText("Recommendation")).toBeInTheDocument();
    expect(within(liveGrid as HTMLElement).getByText("Account")).toBeInTheDocument();
    expect(within(liveGrid as HTMLElement).queryByText("Processing")).not.toBeInTheDocument();
    expect(within(liveGrid as HTMLElement).queryByText("Extraction")).not.toBeInTheDocument();
    expect(within(liveGrid as HTMLElement).queryByText("OCR")).not.toBeInTheDocument();
    expect(within(liveGrid as HTMLElement).queryByText("Signals")).not.toBeInTheDocument();
    expect(
      within(documentCard as HTMLElement).getByText(/Reviewed by reviewer@example.com/i),
    ).toBeInTheDocument();
    expect(
      within(documentCard as HTMLElement).getByText(/Ask for a new statement with the confirmed account id/i),
    ).toBeInTheDocument();
    expect(
      within(documentCard as HTMLElement).getByText(/Confidence 91% · Awaiting operator disposition/i),
    ).toBeInTheDocument();
    expect(
      within(documentCard as HTMLElement).getByText(/Bank Statement · Bank Correspondence/i),
    ).toBeInTheDocument();
    expect(
      within(documentCard as HTMLElement).getByText(/Missing required fields: statement_date/i),
    ).toBeInTheDocument();
    expect(
      within(documentCard as HTMLElement).getAllByText(/Override acct_override_002/i).length,
    ).toBeGreaterThan(0);

    const moreStatusCardsButton = within(documentCard as HTMLElement).getByRole("button", {
      name: "More status cards (4) · Next hidden concern: Processing: Extraction queued",
    });
    expect(moreStatusCardsButton).toHaveAttribute("aria-expanded", "false");

    await user.click(moreStatusCardsButton);

    expect(within(liveGrid as HTMLElement).getByText("Processing")).toBeInTheDocument();
    expect(within(liveGrid as HTMLElement).getByText("Extraction")).toBeInTheDocument();
    expect(within(liveGrid as HTMLElement).getByText("OCR")).toBeInTheDocument();
    expect(within(liveGrid as HTMLElement).getByText("Signals")).toBeInTheDocument();
    expect(
      within(documentCard as HTMLElement).getByText(/Azure Document Intelligence stored/i),
    ).toBeInTheDocument();
    expect(
      within(documentCard as HTMLElement).getByText(/Suggested acct_auto_001 from 2 candidates\. Final acct_override_002 confirmed by reviewer@example.com/i),
    ).toBeInTheDocument();
    expect(
      within(documentCard as HTMLElement).getByRole("button", {
        name: "Show fewer status cards",
      }),
    ).toHaveAttribute("aria-expanded", "true");
  });

  it("promotes hidden changed cards when no hidden waiting concern remains", () => {
    const workspace = buildWorkspace();
    const renderResult = renderPanel({
      operatorContracts: buildOperatorContracts(),
      preferredTab: "documents",
      workspace,
    });

    renderResult.rerender(
      <PacketWorkspacePanel
        {...buildPanelProps({
          operatorContracts: buildOperatorContracts(),
          preferredTab: "documents",
          workspace: {
            ...workspace,
            extraction_results: workspace.extraction_results.map((result) =>
              result.document_id === "doc_001"
                ? {
                    ...result,
                    created_at_utc: "2026-04-16T12:15:30Z",
                    extraction_result_id: "ext_010",
                  }
                : result,
            ),
            ocr_results: workspace.ocr_results.map((result) =>
              result.document_id === "doc_001"
                ? {
                    ...result,
                    created_at_utc: "2026-04-16T12:15:10Z",
                    ocr_confidence: 0.99,
                    ocr_result_id: "ocr_010",
                  }
                : result,
            ),
            processing_jobs: workspace.processing_jobs.map((job) =>
              job.job_id === "job_extraction_001"
                ? {
                    ...job,
                    completed_at_utc: "2026-04-16T12:05:30Z",
                    status: "succeeded",
                    updated_at_utc: "2026-04-16T12:05:30Z",
                  }
                : job,
            ),
          },
        })}
      />,
    );

    const documentCard = screen.getByText("statement.pdf").closest("article");
    expect(documentCard).not.toBeNull();
    expect(
      within(documentCard as HTMLElement).getByRole("button", {
        name: "More status cards (4) · Recent hidden change: Extraction, Processing, and 1 more",
      }),
    ).toBeInTheDocument();
  });

  it("prioritizes hidden processing blockers ahead of lower-severity hidden concerns", () => {
    renderPanel({
      operatorContracts: buildOperatorContracts(),
      preferredTab: "documents",
      workspace: {
        ...buildWorkspace(),
        extraction_results: [],
        processing_jobs: buildWorkspace().processing_jobs.map((job) =>
          job.job_id === "job_extraction_001"
            ? {
                ...job,
                stage_name: "ocr",
                status: "blocked",
                updated_at_utc: "2026-04-16T12:09:00Z",
              }
            : job,
        ),
      },
    });

    const documentCard = screen.getByText("statement.pdf").closest("article");
    expect(documentCard).not.toBeNull();
    expect(
      within(documentCard as HTMLElement).getByRole("button", {
        name: "More status cards (4) · Next hidden concern: Processing: Ocr blocked; Extraction: Queued",
      }),
    ).toBeInTheDocument();
  });

  it("shows managed contract readiness on open review task cards", () => {
    renderPanel({
      operatorContracts: buildOperatorContracts(),
      preferredTab: "review",
      workspace: {
        ...buildWorkspace(),
        review_decisions: [],
      },
    });

    const reviewTaskCard = screen.getByText("statement.pdf").closest("article");
    expect(reviewTaskCard).not.toBeNull();
    expect(
      within(reviewTaskCard as HTMLElement).getByText("Review readiness"),
    ).toBeInTheDocument();
    expect(
      within(reviewTaskCard as HTMLElement).getByText(/Bank correspondence/i),
    ).toBeInTheDocument();
    expect(
      within(reviewTaskCard as HTMLElement).getByText(/1 required field missing/i),
    ).toBeInTheDocument();
    expect(
      within(reviewTaskCard as HTMLElement).getByText(/Missing required fields: statement_date/i),
    ).toBeInTheDocument();
  });

  it("jumps from review readiness into viewer evidence for a missing managed field", async () => {
    const user = userEvent.setup();

    renderPanel({
      operatorContracts: buildOperatorContracts(),
      preferredTab: "review",
      workspace: {
        ...buildWorkspace(),
        review_decisions: [],
      },
    });

    const reviewTaskCard = screen.getByText("statement.pdf").closest("article");
    expect(reviewTaskCard).not.toBeNull();

    await user.click(
      within(reviewTaskCard as HTMLElement).getByRole("button", {
        name: /Inspect Statement Date in viewer/i,
      }),
    );

    expect(screen.getByRole("tab", { name: "Viewer" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(
      screen.getByText(
        /Opened from review task for statement\.pdf › Missing field: Statement Date/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Statement Date is required by the managed contract but missing from the extracted fields/i,
      ),
    ).toBeInTheDocument();
  });

  it("returns from viewer evidence to the originating review task after inspecting a missing managed field", async () => {
    const user = userEvent.setup();

    renderPanel({
      operatorContracts: buildOperatorContracts(),
      preferredTab: "review",
      workspace: {
        ...buildWorkspace(),
        review_decisions: [],
      },
    });

    const initialReviewTaskCard = screen.getByText("statement.pdf").closest("article");
    expect(initialReviewTaskCard).not.toBeNull();

    await user.click(
      within(initialReviewTaskCard as HTMLElement).getByRole("button", {
        name: /Inspect Statement Date in viewer/i,
      }),
    );
    await user.click(
      screen.getByRole("button", {
        name: /Return to statement\.pdf review task/i,
      }),
    );

    expect(screen.getByRole("tab", { name: "Review" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    const returnedReviewTaskCard = screen.getByText("statement.pdf").closest("article");
    expect(returnedReviewTaskCard).not.toBeNull();

    await waitFor(() => {
      expect(returnedReviewTaskCard).toContainElement(
        document.activeElement as HTMLElement | null,
      );
    });
  });

  it("renders intake content through shared surface sections", () => {
    renderPanel({ preferredTab: "intake" });

    expect(
      screen.getByRole("heading", { name: "Intake summary" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Replay and ingress controls" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Packet source")).toBeInTheDocument();
    expect(screen.getByText("Replay")).toBeInTheDocument();
  });

  it("renders review content through shared surface sections", () => {
    renderPanel({ preferredTab: "review" });

    expect(
      screen.getByRole("heading", { name: "Review summary" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Create review tasks" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Review tasks" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Pending tasks")).toBeInTheDocument();
  });

  it("submits task authoring for packet documents without review tasks", async () => {
    const user = userEvent.setup();
    const onSubmitReviewTaskCreate = vi.fn();

    renderPanel({
      onSubmitReviewTaskCreate,
      preferredTab: "review",
    });

    const createCard = screen.getByText("cover-letter.pdf").closest("article");

    expect(createCard).not.toBeNull();

    await user.type(
      within(createCard as HTMLElement).getByLabelText("Initial reviewer"),
      "qa.reviewer@example.com",
    );
    await user.type(
      within(createCard as HTMLElement).getByLabelText("Selected account"),
      "acct_manual_001",
    );
    await user.type(
      within(createCard as HTMLElement).getByLabelText("Task summary"),
      "Manual follow-up requested for the cover letter.",
    );
    await user.click(
      within(createCard as HTMLElement).getByRole("button", {
        name: "Create review task",
      }),
    );

    expect(onSubmitReviewTaskCreate).toHaveBeenCalledWith({
      assigned_user_email: "qa.reviewer@example.com",
      document_id: "doc_002",
      notes_summary: "Manual follow-up requested for the cover letter.",
      selected_account_id: "acct_manual_001",
    });
  });

  it("surfaces task-scoped review activity directly in the review cards", () => {
    renderPanel({ preferredTab: "review" });

    const reviewTaskCard = screen.getByText("statement.pdf").closest("article");

    expect(reviewTaskCard).not.toBeNull();
    expect(
      within(reviewTaskCard as HTMLElement).getByText("Task activity"),
    ).toBeInTheDocument();
    expect(
      within(reviewTaskCard as HTMLElement).getByText("Task opened"),
    ).toBeInTheDocument();
    expect(
      within(reviewTaskCard as HTMLElement).getByText("Field edits saved"),
    ).toBeInTheDocument();
    expect(
      within(reviewTaskCard as HTMLElement).getByText("Operator note"),
    ).toBeInTheDocument();
    expect(
      within(reviewTaskCard as HTMLElement).getByText("Decision Approved"),
    ).toBeInTheDocument();
    expect(
      within(reviewTaskCard as HTMLElement).getByText(/account_override_confirmed/i),
    ).toBeInTheDocument();
  });

  it("renders recommendation content through shared surface sections", async () => {
    const user = userEvent.setup();

    renderPanel();

    await user.click(
      screen.getByRole("button", {
        name: /^More views \(7\)/i,
      }),
    );

    await user.click(screen.getByRole("tab", { name: "Recommendations" }));

    const summaryPanel = screen
      .getByRole("heading", { name: "Recommendation summary" })
      .closest(".surface-card");
    const decisionsPanel = screen
      .getByRole("heading", { name: "Recommendation decisions" })
      .closest(".surface-card");

    expect(summaryPanel).not.toBeNull();
    expect(summaryPanel).toHaveClass("surface-panel");
    expect(decisionsPanel).not.toBeNull();
    expect(decisionsPanel).toHaveClass("surface-panel");
    expect(within(summaryPanel as HTMLElement).getByText(/^Pending$/)).toBeInTheDocument();
  });

  it("shows override-focused account comparison after switching to Matching", async () => {
    const user = userEvent.setup();

    renderPanel();

    await user.click(
      screen.getByRole("button", {
        name: /^More views \(7\)/i,
      }),
    );

    await user.click(screen.getByRole("tab", { name: "Matching" }));

    const summaryPanel = screen
      .getByRole("heading", { name: "Account resolution summary" })
      .closest(".surface-card");
    const comparisonPanel = screen
      .getByRole("heading", { name: "Override comparison and linkage history" })
      .closest(".surface-card");

    expect(summaryPanel).not.toBeNull();
    expect(summaryPanel).toHaveClass("surface-panel");
    expect(comparisonPanel).not.toBeNull();
    expect(comparisonPanel).toHaveClass("surface-panel");
    expect(
      screen.getByRole("heading", { name: "Override comparison and linkage history" }),
    ).toBeInTheDocument();
    expect(screen.getByText("statement.pdf")).toBeInTheDocument();
    expect(screen.getAllByText("acct_override_002").length).toBeGreaterThan(0);
    expect(screen.getByText("Match run created")).toBeInTheDocument();
  });

  it("renders rules and doctypes content through shared surface sections", async () => {
    renderPanel({
      operatorContracts: buildOperatorContracts(),
      preferredTab: "rules_doctypes",
    });

    const summaryPanel = screen
      .getByRole("heading", { name: "Managed contract summary" })
      .closest(".surface-card");
    const taxonomyPanel = screen
      .getByRole("heading", { name: "Processing taxonomy" })
      .closest(".surface-card");

    expect(summaryPanel).not.toBeNull();
    expect(summaryPanel).toHaveClass("surface-panel");
    expect(taxonomyPanel).not.toBeNull();
    expect(taxonomyPanel).toHaveClass("surface-panel");
    expect(screen.getByText("Recommendation contract")).toBeInTheDocument();
  });

  it("reports selected workspace tabs for deep-linkable admin URLs", async () => {
    const user = userEvent.setup();
    const onSelectTab = vi.fn();

    renderPanel({ onSelectTab, preferredTab: "review" });

    await user.click(
      screen.getByRole("button", {
        name: /^More views \(7\)/i,
      }),
    );

    await user.click(screen.getByRole("tab", { name: "OCR" }));

    expect(onSelectTab).toHaveBeenCalledWith("ocr");
    expect(screen.getByRole("tab", { name: "OCR" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("calls the recommendation review callback from the Recommendations tab", async () => {
    const user = userEvent.setup();
    const onReviewRecommendation = vi.fn();

    renderPanel({ onReviewRecommendation });

    await user.click(
      screen.getByRole("button", {
        name: /^More views \(7\)/i,
      }),
    );

    await user.click(screen.getByRole("tab", { name: "Recommendations" }));
    await user.click(screen.getByRole("button", { name: "Approve recommendation" }));

    expect(onReviewRecommendation).toHaveBeenCalledWith("rec_001", "accepted");
  });

  it("shows audit content through shared surface sections", async () => {
    const user = userEvent.setup();

    renderPanel();

    await user.click(screen.getByRole("tab", { name: "Audit" }));

    const summaryPanel = screen
      .getByRole("heading", { name: "Ownership summary" })
      .closest(".surface-card");
    const assignmentsPanel = screen
      .getByRole("heading", { name: "Assignments" })
      .closest(".surface-card");
    const timelinePanel = screen
      .getByRole("heading", { name: "Change timeline" })
      .closest(".surface-card");

    expect(summaryPanel).not.toBeNull();
    expect(summaryPanel).toHaveClass("surface-panel");
    expect(assignmentsPanel).not.toBeNull();
    expect(assignmentsPanel).toHaveClass("surface-panel");
    expect(timelinePanel).not.toBeNull();
    expect(timelinePanel).toHaveClass("surface-panel");
    expect(screen.getByRole("heading", { name: "Ownership summary" })).toBeInTheDocument();
    expect(screen.getAllByText("reviewer@example.com").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Assignments" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Change timeline" })).toBeInTheDocument();
    expect(screen.getAllByText("account_override_reviewed").length).toBeGreaterThan(0);
  });

  it("surfaces extraction edit history and filters the audit events down to field edits", async () => {
    const user = userEvent.setup();

    renderPanel();

    await user.click(screen.getByRole("tab", { name: "Audit" }));

    const fieldEditHistoryPanel = screen
      .getByRole("heading", { name: "Field edit history" })
      .closest(".surface-card");
    const auditEventsPanel = screen
      .getByRole("heading", { name: "Audit events" })
      .closest(".surface-card");

    expect(fieldEditHistoryPanel).not.toBeNull();
    expect(auditEventsPanel).not.toBeNull();
    expect(
      within(fieldEditHistoryPanel as HTMLElement).getByText("account_number"),
    ).toBeInTheDocument();
    expect(
      within(fieldEditHistoryPanel as HTMLElement).getByText(
        "Source result ext_001 -> new result ext_003.",
      ),
    ).toBeInTheDocument();
    expect(
      within(auditEventsPanel as HTMLElement).getByText("account_override_reviewed"),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Field edit events/i }));

    expect(screen.getByRole("button", { name: /Field edit events/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      within(auditEventsPanel as HTMLElement).queryByText("account_override_reviewed"),
    ).not.toBeInTheDocument();
    expect(
      within(auditEventsPanel as HTMLElement).getByText(
        "review.extraction.fields.updated",
      ),
    ).toBeInTheDocument();
  });

  it("renders protected viewer state and switches between packet documents", async () => {
    const user = userEvent.setup();

    renderPanel({ preferredTab: "viewer" });

    const primaryPreviewUrl = buildPacketDocumentContentUrl(
      "pkt_001",
      "doc_001",
      "2026-04-16T12:11:00Z",
    );

    expect(
      screen.getByTitle("Protected preview for statement.pdf"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Statement OCR excerpt for the selected PDF/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Primary statement extraction summary.")).toBeInTheDocument();
    expect(screen.getByText(/Highlighting account_number in the OCR excerpt/i)).toBeInTheDocument();
    expect(screen.getByText("1234", { selector: "mark" })).toBeInTheDocument();
    expect(
      screen.getByText("Archive lineage: archive/statement.pdf at depth 1."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open file" })).toHaveAttribute(
      "href",
      primaryPreviewUrl,
    );

    await user.click(screen.getByRole("button", { name: /cover-letter\.pdf/i }));

    const secondaryPreviewUrl = buildPacketDocumentContentUrl(
      "pkt_001",
      "doc_002",
      "2026-04-16T12:11:30Z",
    );

    expect(
      screen.getByTitle("Protected preview for cover-letter.pdf"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Cover letter OCR excerpt for the secondary document."),
    ).toBeInTheDocument();
    expect(screen.getByText("Secondary cover letter extraction summary.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open file" })).toHaveAttribute(
      "href",
      secondaryPreviewUrl,
    );
  });

  it("highlights document status deltas after the same packet workspace reloads", async () => {
    const user = userEvent.setup();

    const initialWorkspace = buildWorkspace();
    const renderResult = render(
      <PacketWorkspacePanel
        {...buildPanelProps({
          operatorContracts: buildOperatorContracts(),
          preferredTab: "documents",
          workspace: initialWorkspace,
        })}
      />,
    );

    const initialDocumentCard = screen.getByText("statement.pdf").closest("article");
    expect(initialDocumentCard).not.toBeNull();
    expect(initialDocumentCard).not.toHaveClass("workspace-document-refresh-card");

    const updatedWorkspace: PacketWorkspaceSnapshot = {
      ...initialWorkspace,
      documents: initialWorkspace.documents.map((document) =>
        document.document_id === "doc_001"
          ? {
              ...document,
              updated_at_utc: "2026-04-16T12:15:00Z",
            }
          : document,
      ),
      extraction_results: [
        ...initialWorkspace.extraction_results,
        {
          created_at_utc: "2026-04-16T12:14:30Z",
          document_id: "doc_001",
          document_type: "bank_statement",
          extraction_result_id: "ext_003",
          model_name: "gpt-5.4",
          packet_id: "pkt_001",
          prompt_profile_id: "bank_statement",
          provider: "azure_openai",
          result_payload: {
            extractedFields: [
              {
                confidence: 0.94,
                name: "account_number",
                value: "5678",
              },
              {
                confidence: 0.91,
                name: "statement_date",
                value: "2026-04-01",
              },
            ],
            reviewEdits: {
              changeCount: 1,
              changedFieldNames: ["account_number", "statement_date"],
              editedAtUtc: "2026-04-16T12:14:30Z",
              reviewTaskId: "task_001",
              sourceExtractionResultId: "ext_001",
            },
          },
          summary: "Operator-adjusted extraction summary.",
        },
      ],
      ocr_results: [
        ...initialWorkspace.ocr_results,
        {
          created_at_utc: "2026-04-16T12:14:10Z",
          document_id: "doc_001",
          model_name: "prebuilt-layout",
          ocr_confidence: 0.99,
          ocr_result_id: "ocr_003",
          packet_id: "pkt_001",
          page_count: 3,
          provider: "azure_document_intelligence",
          text_excerpt:
            "Updated statement OCR excerpt with the corrected account number 5678.",
          text_storage_uri: "https://storage.example/ocr/doc_001_v2.txt",
        },
      ],
      packet: {
        ...initialWorkspace.packet,
        updated_at_utc: "2026-04-16T12:15:00Z",
      },
      processing_jobs: [
        ...initialWorkspace.processing_jobs,
        {
          attempt_number: 1,
          completed_at_utc: null,
          created_at_utc: "2026-04-16T12:14:00Z",
          document_id: "doc_001",
          error_code: null,
          error_message: null,
          job_id: "job_recommendation_001",
          packet_id: "pkt_001",
          queued_at_utc: "2026-04-16T12:14:00Z",
          stage_name: "recommendation",
          started_at_utc: null,
          status: "queued",
          updated_at_utc: "2026-04-16T12:14:00Z",
        },
      ],
      recommendation_results: [
        ...initialWorkspace.recommendation_results,
        {
          ...initialWorkspace.recommendation_results[0],
          disposition: "accepted",
          recommendation_result_id: "rec_002",
          reviewed_at_utc: "2026-04-16T12:14:20Z",
          reviewed_by_email: "reviewer@example.com",
          reviewed_by_user_id: "reviewer_001",
          summary: "Recommendation accepted after the updated account evidence landed.",
          updated_at_utc: "2026-04-16T12:14:20Z",
        },
      ],
      review_decisions: [
        ...initialWorkspace.review_decisions,
        {
          ...initialWorkspace.review_decisions[0],
          decision_id: "decision_002",
          decided_at_utc: "2026-04-16T12:14:15Z",
          review_notes: "Auto-linked account is now verified against the refreshed statement.",
          selected_account_id: "acct_auto_001",
        },
      ],
    };

    renderResult.rerender(
      <PacketWorkspacePanel
        {...buildPanelProps({
          operatorContracts: buildOperatorContracts(),
          preferredTab: "documents",
          workspace: updatedWorkspace,
        })}
      />,
    );

    const refreshedDocumentCard = screen.getByText("statement.pdf").closest("article");
    expect(refreshedDocumentCard).not.toBeNull();
    expect(refreshedDocumentCard).toHaveClass("workspace-document-refresh-card");
    expect(
      within(refreshedDocumentCard as HTMLElement).getByText("Updated on refresh"),
    ).toBeInTheDocument();
    expect(
      within(refreshedDocumentCard as HTMLElement).getByText(
        "Attention changed on the last workspace refresh.",
      ),
    ).toBeInTheDocument();
    expect(
      within(refreshedDocumentCard as HTMLElement).getByText(
        "No action pending · Approved · acct_override_002 -> No action pending · Approved · acct_auto_001.",
      ),
    ).toBeInTheDocument();
    const refreshedDocumentPath = within(
      refreshedDocumentCard as HTMLElement,
    ).getByRole("list", {
      name: "Document path for statement.pdf",
    });
    expect(within(refreshedDocumentPath).getAllByText("Changed").length).toBe(5);
    expect(
      within(refreshedDocumentPath).getByText("1 field stored -> 2 fields stored."),
    ).toBeInTheDocument();
    expect(
      within(refreshedDocumentPath).getByText("2 pages · 97% -> 3 pages · 99%."),
    ).toBeInTheDocument();
    expect(
      within(refreshedDocumentCard as HTMLElement).getByText(
        "Contract changed on the last workspace refresh.",
      ),
    ).toBeInTheDocument();
    expect(
      within(refreshedDocumentCard as HTMLElement).getByText(
        "Bank statement · Bank correspondence · 1 required field missing -> Bank statement · Bank correspondence · Managed fields present.",
      ),
    ).toBeInTheDocument();
    expect(
      within(refreshedDocumentCard as HTMLElement).getByText(
        "Review changed on the last workspace refresh.",
      ),
    ).toBeInTheDocument();
    expect(
      within(refreshedDocumentCard as HTMLElement).getAllByText(
        "Approved by reviewer@example.com · acct_override_002 -> Approved by reviewer@example.com · acct_auto_001.",
      ).length,
    ).toBeGreaterThan(0);
    expect(
      within(refreshedDocumentCard as HTMLElement).getByText(
        "Recommendation changed on the last workspace refresh.",
      ),
    ).toBeInTheDocument();
    expect(
      within(refreshedDocumentCard as HTMLElement).getAllByText(
        "Pending · Request Additional Document -> Accepted · Request Additional Document.",
      ).length,
    ).toBeGreaterThan(0);
    expect(
      within(refreshedDocumentCard as HTMLElement).getByText(
        "Account changed on the last workspace refresh.",
      ),
    ).toBeInTheDocument();
    expect(
      within(refreshedDocumentCard as HTMLElement).getAllByText(
        "Override acct_override_002 -> Linked acct_auto_001.",
      ).length,
    ).toBeGreaterThan(0);

    const moreStatusCardsButton = within(
      refreshedDocumentCard as HTMLElement,
    ).getByRole("button", {
      name: "More status cards (4) · Next hidden concern: Processing: Recommendation queued",
    });
    expect(moreStatusCardsButton).toHaveAttribute("aria-expanded", "false");

    await user.click(moreStatusCardsButton);

    expect(
      within(refreshedDocumentCard as HTMLElement).getByText(
        "Processing changed on the last workspace refresh.",
      ),
    ).toBeInTheDocument();
    expect(
      within(refreshedDocumentCard as HTMLElement).getByText(
        "Extraction changed on the last workspace refresh.",
      ),
    ).toBeInTheDocument();
    expect(
      within(refreshedDocumentCard as HTMLElement).getAllByText(
        "1 field stored -> 2 fields stored.",
      ).length,
    ).toBeGreaterThan(0);
    expect(
      within(refreshedDocumentCard as HTMLElement).getByText(
        "OCR changed on the last workspace refresh.",
      ),
    ).toBeInTheDocument();
    expect(
      within(refreshedDocumentCard as HTMLElement).getAllByText(
        "2 pages · 97% -> 3 pages · 99%.",
      ).length,
    ).toBeGreaterThan(0);
    expect(
      within(refreshedDocumentCard as HTMLElement).getByText(
        "Extraction · Queued -> Recommendation · Queued.",
      ),
    ).toBeInTheDocument();
  });

  it("opens viewer evidence from a review task and keeps the relevant field highlighted", async () => {
    const user = userEvent.setup();

    renderPanel({
      preferredTab: "review",
      workspace: {
        ...buildWorkspace(),
        review_decisions: [],
      },
    });

    const reviewTaskCard = screen.getByText("statement.pdf").closest("article");

    expect(reviewTaskCard).not.toBeNull();

    await user.click(
      within(reviewTaskCard as HTMLElement).getByRole("button", {
        name: "Open viewer evidence",
      }),
    );

    expect(screen.getByRole("tab", { name: "Viewer" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText(/Highlighting account_number in the OCR excerpt/i)).toBeInTheDocument();
    expect(screen.getByText("1234", { selector: "mark" })).toBeInTheDocument();
  });

  it("shows direct pipeline controls and wires execute and retry actions", async () => {
    const user = userEvent.setup();
    const onExecuteStage = vi.fn();
    const onRetryStage = vi.fn();

    renderPanel({
      onExecuteStage,
      onRetryStage,
      preferredTab: "pipeline",
      pipelineActionSuccessMessage:
        "Ocr retried 1 document. 1 failed job and 0 stale running jobs qualified for intervention.",
      processingPipelineAction: null,
    });

    const checkpointPanel = screen
      .getByRole("heading", { name: "Latest stage checkpoints" })
      .closest(".surface-card");
    const failuresPanel = screen
      .getByRole("heading", { name: "Retries and failures" })
      .closest(".surface-card");
    const timelinePanel = screen
      .getByRole("heading", { name: "Packet event timeline" })
      .closest(".surface-card");

    expect(screen.getByRole("heading", { name: "Stage controls" })).toBeInTheDocument();
    expect(screen.getByText("Pipeline summary")).toBeInTheDocument();
    expect(checkpointPanel).not.toBeNull();
    expect(checkpointPanel).toHaveClass("surface-panel");
    expect(failuresPanel).not.toBeNull();
    expect(failuresPanel).toHaveClass("surface-panel");
    expect(timelinePanel).not.toBeNull();
    expect(timelinePanel).toHaveClass("surface-panel");
    expect(
      screen.getByText(
        "Ocr retried 1 document. 1 failed job and 0 stale running jobs qualified for intervention.",
      ),
    ).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Run queued" })[1]);
    expect(onExecuteStage).toHaveBeenCalledWith("ocr");

    await user.click(screen.getAllByRole("button", { name: "Retry failed/stuck" })[1]);
    expect(onRetryStage).toHaveBeenCalledWith("ocr");
  });

  it("submits the review task row version with review decisions", async () => {
    const user = userEvent.setup();
    const onSubmitReviewDecision = vi.fn();

    renderPanel({
      onSubmitReviewDecision,
      preferredTab: "review",
      workspace: {
        ...buildWorkspace(),
        review_decisions: [],
      },
    });

    await user.click(screen.getByRole("button", { name: "Approve task" }));

    expect(onSubmitReviewDecision).toHaveBeenCalledWith(
      expect.objectContaining({
        decision_status: "approved",
        expected_row_version: "0000000000000001",
        review_task_id: "task_001",
      }),
    );
  });

  it("submits structured decision reason codes with review decisions", async () => {
    const user = userEvent.setup();
    const onSubmitReviewDecision = vi.fn();

    renderPanel({
      onSubmitReviewDecision,
      preferredTab: "review",
      workspace: {
        ...buildWorkspace(),
        review_decisions: [],
      },
    });

    const reviewTaskCard = screen.getByText("statement.pdf").closest("article");
    expect(reviewTaskCard).not.toBeNull();

    await user.click(
      within(reviewTaskCard as HTMLElement).getByRole("button", {
        name: "Use account_override_confirmed",
      }),
    );
    await user.click(
      within(reviewTaskCard as HTMLElement).getByRole("button", {
        name: "Approve task",
      }),
    );

    expect(onSubmitReviewDecision).toHaveBeenCalledWith(
      expect.objectContaining({
        decision_reason_code: "account_override_confirmed",
        decision_status: "approved",
        expected_row_version: "0000000000000001",
        review_task_id: "task_001",
      }),
    );
  });

  it("saves edited extracted values through the dedicated extraction edit callback", async () => {
    const user = userEvent.setup();
    const onSubmitExtractionEdits = vi.fn();

    renderPanel({
      onSubmitExtractionEdits,
      preferredTab: "review",
      workspace: {
        ...buildWorkspace(),
        review_decisions: [],
      },
    });

    const reviewTaskCard = screen.getByText("statement.pdf").closest("article");
    expect(reviewTaskCard).not.toBeNull();

    const accountNumberInput = within(reviewTaskCard as HTMLElement).getByLabelText(
      "account_number value",
    );
    await user.clear(accountNumberInput);
    await user.type(accountNumberInput, "5678");

    await user.type(
      within(reviewTaskCard as HTMLElement).getByLabelText("Review notes"),
      "Corrected the extracted value against the visible statement.",
    );

    expect(
      within(reviewTaskCard as HTMLElement).getByText(/Audit capture preview/i),
    ).toBeInTheDocument();
    expect(
      within(reviewTaskCard as HTMLElement).getAllByText(/account_number/i).length,
    ).toBeGreaterThan(0);

    await user.click(
      within(reviewTaskCard as HTMLElement).getByRole("button", {
        name: /Save 1 field edit/i,
      }),
    );

    expect(onSubmitExtractionEdits).toHaveBeenCalledWith(
      expect.objectContaining({
        expected_row_version: "0000000000000001",
        review_task_id: "task_001",
      }),
    );
    expect(onSubmitExtractionEdits).toHaveBeenCalledWith(
      expect.objectContaining({
        field_edits: [
          {
            field_name: "account_number",
            value: "5678",
          },
        ],
      }),
    );
  });

  it("saves task-scoped notes through the dedicated review note callback", async () => {
    const user = userEvent.setup();
    const onSubmitReviewNote = vi.fn();

    renderPanel({
      onSubmitReviewNote,
      preferredTab: "review",
      workspace: {
        ...buildWorkspace(),
        review_decisions: [],
      },
    });

    const reviewTaskCard = screen.getByText("statement.pdf").closest("article");
    expect(reviewTaskCard).not.toBeNull();

    await user.type(
      within(reviewTaskCard as HTMLElement).getByLabelText("Task note"),
      "Need the final statement page before closing the task.",
    );

    await user.click(
      within(reviewTaskCard as HTMLElement).getByRole("button", {
        name: "Save task note",
      }),
    );

    expect(onSubmitReviewNote).toHaveBeenCalledWith({
      expected_row_version: "0000000000000001",
      is_private: false,
      note_text: "Need the final statement page before closing the task.",
      review_task_id: "task_001",
    });
  });

  it("allows reassignment directly from a blocked review task card", async () => {
    const user = userEvent.setup();
    const onSubmitReviewAssignment = vi.fn();
    const onSubmitReviewDecision = vi.fn();

    renderPanel({
      onSubmitReviewAssignment,
      onSubmitReviewDecision,
      preferredTab: "review",
      workspace: {
        ...buildWorkspace(),
        review_decisions: [],
        review_tasks: buildWorkspace().review_tasks.map((reviewTask) =>
          reviewTask.review_task_id === "task_001"
            ? {
                ...reviewTask,
                assigned_user_email: "qa.reviewer@example.com",
              }
            : reviewTask,
        ),
      },
    });

    const reviewTaskCard = screen.getByText("statement.pdf").closest("article");
    expect(reviewTaskCard).not.toBeNull();
    expect(
      within(reviewTaskCard as HTMLElement).getByText(
        /Refresh or reassign the task before recording a decision/i,
      ),
    ).toBeInTheDocument();

    await user.click(
      within(reviewTaskCard as HTMLElement).getByRole("button", {
        name: "Assign to me",
      }),
    );
    await user.click(
      within(reviewTaskCard as HTMLElement).getByRole("button", {
        name: "Save assignment",
      }),
    );

    expect(onSubmitReviewAssignment).toHaveBeenCalledWith({
      assigned_user_email: "reviewer@example.com",
      expected_row_version: "0000000000000001",
      review_task_id: "task_001",
    });
  });


  it("keeps review decision notes free of staged extraction audit text", async () => {
    const user = userEvent.setup();
    const onSubmitReviewDecision = vi.fn();

    renderPanel({
      onSubmitReviewDecision,
      preferredTab: "review",
      workspace: {
        ...buildWorkspace(),
        review_decisions: [],
      },
    });

    const reviewTaskCard = screen.getByText("statement.pdf").closest("article");
    expect(reviewTaskCard).not.toBeNull();

    await user.type(
      within(reviewTaskCard as HTMLElement).getByLabelText("Review notes"),
      "Corrected the extracted value against the visible statement.",
    );

    await user.click(
      within(reviewTaskCard as HTMLElement).getByRole("button", {
        name: "Approve task",
      }),
    );

    expect(onSubmitReviewDecision).toHaveBeenCalledWith(
      expect.objectContaining({
        decision_status: "approved",
        expected_row_version: "0000000000000001",
        review_notes: "Corrected the extracted value against the visible statement.",
      }),
    );
  });
  it("switches the review workflow into reject mode before submitting", async () => {
    const user = userEvent.setup();
    const onSubmitReviewDecision = vi.fn();

    renderPanel({
      onSubmitReviewDecision,
      preferredTab: "review",
      workspace: {
        ...buildWorkspace(),
        review_decisions: [],
      },
    });

    await user.click(screen.getAllByRole("button", { name: "Reject for follow-up" })[0]);
    await user.click(screen.getByRole("button", { name: "Reject task" }));

    expect(onSubmitReviewDecision).toHaveBeenCalledWith(
      expect.objectContaining({
        decision_status: "rejected",
        expected_row_version: "0000000000000001",
        review_task_id: "task_001",
      }),
    );
  });
});
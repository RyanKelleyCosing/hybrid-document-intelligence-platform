"""OpenAPI contract builders for public and protected API documentation."""

from __future__ import annotations

from html import escape
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from document_intelligence.models import (
    IntakeSourceCreateRequest,
    IntakeSourceDeleteResponse,
    IntakeSourceEnablementRequest,
    IntakeSourceExecutionResponse,
    IntakeSourceListResponse,
    IntakeSourceRecord,
    IntakeSourceUpdateRequest,
    ManualPacketIntakeRequest,
    ManualPacketIntakeResponse,
    OperatorContractsResponse,
    PacketClassificationExecutionResponse,
    PacketExtractionExecutionResponse,
    PacketOcrExecutionResponse,
    PacketQueueListResponse,
    PacketRecommendationExecutionResponse,
    PacketRecommendationReviewRequest,
    PacketRecommendationReviewResponse,
    PacketReplayResponse,
    PacketReviewAssignmentRequest,
    PacketReviewAssignmentResponse,
    PacketReviewDecisionRequest,
    PacketReviewDecisionResponse,
    PacketReviewExtractionEditRequest,
    PacketReviewExtractionEditResponse,
    PacketReviewNoteRequest,
    PacketReviewNoteResponse,
    PacketReviewTaskCreateRequest,
    PacketReviewTaskCreateResponse,
    PacketStageRetryResponse,
    PacketWorkspaceSnapshot,
    ProcessingTaxonomyResponse,
)
from document_intelligence.public_cost_metrics import PublicCostMetricsSummary
from document_intelligence.public_request_context import PublicRequestContext
from document_intelligence.public_security_feeds import (
    PublicSecurityCveFeed,
    PublicSecurityMsrcFeed,
)
from document_intelligence.public_traffic_metrics import PublicTrafficMetricsSummary
from document_intelligence.traffic_alerts import PublicTrafficEvent


class ApiErrorResponse(BaseModel):
    """Standard error envelope used by the documented API surfaces."""

    model_config = ConfigDict(str_strip_whitespace=True)

    details: Any | None = None
    message: str | None = Field(default=None, max_length=400)
    status: str = Field(min_length=1, max_length=64)


class PublicHealthResponse(BaseModel):
    """Anonymous readiness payload returned by the health route."""

    model_config = ConfigDict(str_strip_whitespace=True)

    cosmosConfigured: bool
    durableWorkflowsEnabled: bool
    environment: str = Field(min_length=1, max_length=64)
    manualIntakeReady: bool
    requiredFields: tuple[str, ...] = Field(default_factory=tuple)
    reviewQueue: str | None = None
    service: str = Field(min_length=1, max_length=160)
    sqlConfigured: bool
    status: str = Field(min_length=1, max_length=64)
    supportedPromptProfiles: int = Field(ge=0)
    workflowMode: str = Field(min_length=1, max_length=32)


class PublicTrafficAcceptedResponse(BaseModel):
    """Accepted response returned by the public traffic event endpoint."""

    alertSent: bool
    status: str = Field(min_length=1, max_length=64)


class LiveSiteSessionResponse(BaseModel):
    """Authenticated session payload returned by the private live site."""

    model_config = ConfigDict(str_strip_whitespace=True)

    authenticated: bool
    authorized: bool
    email: str | None = Field(default=None, max_length=320)
    identityProvider: str | None = Field(default=None, max_length=80)


_PUBLIC_HEALTH_EXAMPLE = {
    "status": "healthy",
    "service": "hybrid-document-intelligence-platform",
    "environment": "dev",
    "reviewQueue": "review-items",
    "requiredFields": ["account_number", "statement_date"],
    "supportedPromptProfiles": 12,
    "cosmosConfigured": False,
    "sqlConfigured": True,
    "manualIntakeReady": True,
    "durableWorkflowsEnabled": False,
    "workflowMode": "synchronous",
}

_PUBLIC_TRAFFIC_EVENT_EXAMPLE = {
    "event_type": "page_view",
    "route": "security",
    "session_id": "public-session-001",
    "site_mode": "security",
    "page_title": "Security posture route",
    "referrer": "https://www.ryancodes.online/",
}

_PUBLIC_TRAFFIC_ACCEPTED_EXAMPLE = {
    "alertSent": False,
    "status": "accepted",
}

_PUBLIC_METRICS_SUMMARY_EXAMPLE = {
    "availability_percentage": 100.0,
    "availability_source": "External verification history",
    "availability_window": "Last 7d monitored checks",
    "collection_mode": "Durable sanitized aggregate history",
    "collection_window": "Rolling 30d durable aggregate history with hashed session dedupe and sanitized geography buckets.",
    "current_status": "Healthy",
    "current_uptime_seconds": 86400,
    "environment_name": "dev",
    "generated_at_utc": "2026-04-22T14:30:00Z",
    "geography_counts": [
        {"label": "US / WA", "count": 4},
        {"label": "US / CA", "count": 2},
    ],
    "last_event_at_utc": "2026-04-22T14:25:00Z",
    "latest_alert_configuration_ready": True,
    "latest_monitor_name": "azure-functions-public-site-monitor",
    "last_successful_health_check_at_utc": "2026-04-22T14:00:00Z",
    "process_started_at_utc": "2026-04-22T08:00:00Z",
    "recent_health_checks": [
        {
            "checked_at_utc": "2026-04-22T14:00:00Z",
            "note": "Public site and public traffic probe both succeeded.",
            "overall_ok": True,
        }
    ],
    "route_counts": [
        {"label": "security", "count": 5},
        {"label": "cost", "count": 2},
    ],
    "site_mode_counts": [{"label": "security", "count": 7}],
    "total_events": 7,
    "unique_sessions": 5,
}

_PUBLIC_REQUEST_CONTEXT_EXAMPLE = {
    "approximate_location": "US / WA",
    "client_ip": "203.0.113.10",
    "edge_region": "Host region: Central US",
    "enrichment_provider_name": "ipapi.is",
    "enrichment_status": "Provider-backed network signals loaded from ipapi.is.",
    "forwarded_host": "www.ryancodes.online",
    "forwarded_proto": "https",
    "hosting_provider": "Cloud provider",
    "network_asn": "AS15169",
    "network_owner": "Google LLC",
    "public_network_enrichment_enabled": True,
    "public_security_globe_enabled": True,
    "reputation_summary": "No elevated reputation risk returned by the configured provider.",
    "request_id": "req-abc123def456",
    "request_timestamp_utc": "2026-04-22T14:30:00Z",
    "tls_protocol": "TLSv1.3",
    "transport_security": "HTTPS only",
    "vpn_proxy_status": "No proxy or VPN signal returned.",
}

_PUBLIC_SECURITY_CVE_FEED_EXAMPLE = {
    "collection_mode": "NVD CVE keyword search (1h cache)",
    "generated_at_utc": "2026-04-22T14:30:00Z",
    "items": [
        {
            "cve_id": "CVE-2026-1234",
            "cvss_score": 8.5,
            "last_modified_utc": "2026-04-21T10:00:00Z",
            "published_utc": "2026-04-20T10:00:00Z",
            "reference_url": "https://nvd.nist.gov/vuln/detail/CVE-2026-1234",
            "severity": "HIGH",
            "summary": "Sanitized public-safe CVE summary copied verbatim from the NVD feed.",
        }
    ],
    "keyword_terms": ["python", "azure"],
    "source": "https://services.nvd.nist.gov/rest/json/cves/2.0",
    "total_count": 1,
}

_PUBLIC_SECURITY_MSRC_FEED_EXAMPLE = {
    "collection_mode": "MSRC CVRF release index (6h cache)",
    "generated_at_utc": "2026-04-22T14:30:00Z",
    "items": [
        {
            "alias": "2026-Apr",
            "cvrf_url": "https://api.msrc.microsoft.com/cvrf/v3.0/document/2026-Apr",
            "document_title": "April 2026 Security Updates",
            "initial_release_utc": "2026-04-08T08:00:00Z",
            "msrc_id": "2026-Apr",
        }
    ],
    "source": "https://api.msrc.microsoft.com/cvrf/v3.0/updates",
    "total_count": 1,
}

_PUBLIC_COST_SUMMARY_EXAMPLE = {
    "anomalies": [
        {
            "amount": 24.5,
            "baseline_amount": 18.25,
            "delta_amount": 6.25,
            "direction": "spike",
            "severity": "medium",
            "summary": "Daily spend rose above the recent retained baseline.",
            "usage_date": "2026-04-20",
        }
    ],
    "collection_mode": "Durable public-safe cost history",
    "collection_window": "Latest retained snapshot plus 4 persisted CSV history rows, normalized into daily, weekly, and monthly trend slices.",
    "currency": "USD",
    "daily_cost_trend": [
        {
            "amount": 24.5,
            "label": "Apr 20",
            "period_end": "2026-04-20",
            "period_start": "2026-04-20",
        }
    ],
    "day_over_day_delta": 4.25,
    "forecast": {
        "based_on_days": 7,
        "projected_additional_cost": 95.5,
        "projected_month_end_cost": 280.0,
        "remaining_days_in_period": 10,
        "trailing_daily_average": 9.55,
    },
    "generated_at_utc": "2026-04-20T17:16:33.262741Z",
    "history_row_count": 4,
    "history_source": "Retained public cost history",
    "month_to_date_cost": 184.5,
    "monthly_cost_trend": [
        {
            "amount": 184.5,
            "label": "Apr 2026",
            "period_end": "2026-04-20",
            "period_start": "2026-04-01",
        }
    ],
    "previous_day_cost": 18.25,
    "recent_daily_costs": [
        {"amount": 22.5, "usage_date": "2026-04-19"},
        {"amount": 24.5, "usage_date": "2026-04-20"},
    ],
    "today_cost": 24.5,
    "top_resource_groups": [{"amount": 82.0, "name": "Document intake resource group"}],
    "top_resources": [{"amount": 57.5, "name": "Function runtime"}],
    "top_service_families": [{"amount": 44.0, "name": "Azure AI Services"}],
    "week_to_date_cost": 104.75,
    "weekly_cost_trend": [
        {
            "amount": 104.75,
            "label": "Week of Apr 13",
            "period_end": "2026-04-20",
            "period_start": "2026-04-13",
        }
    ],
    "year_to_date_cost": 612.25,
    "yesterday_cost": 22.5,
}

_PUBLIC_COST_LATEST_EXAMPLE = {
    "generatedAt": "2026-04-20T17:16:33.262741Z",
    "historyRow": {
        "currency": "USD",
        "day_over_day_delta": 4.25,
        "generated_at": "2026-04-20T17:16:33.262741Z",
        "month_to_date_cost": 184.5,
        "previous_day_cost": 18.25,
        "today_cost": 24.5,
        "week_to_date_cost": 104.75,
        "year_to_date_cost": 612.25,
        "yesterday_cost": 22.5,
    },
    "costSummary": {
        "currency": "USD",
        "month_to_date_cost": 184.5,
        "today_cost": 24.5,
        "top_resources": [{"amount": 57.5, "name": "Function runtime"}],
    },
}

_PUBLIC_COST_HISTORY_CSV_EXAMPLE = (
    "generated_at,currency,today_cost,week_to_date_cost,month_to_date_cost,year_to_date_cost,yesterday_cost,previous_day_cost,day_over_day_delta\n"
    "2026-04-20T17:16:33.262741Z,USD,24.5,104.75,184.5,612.25,22.5,18.25,4.25\n"
)

_LIVE_SESSION_EXAMPLE = {
    "authenticated": True,
    "authorized": True,
    "email": "reviewer@example.com",
    "identityProvider": "aad",
}

_PACKET_QUEUE_EXAMPLE = {
    "has_more": False,
    "items": [
        {
            "assigned_user_email": "reviewer@example.com",
            "assignment_state": "assigned",
            "audit_event_count": 3,
            "awaiting_review_document_count": 1,
            "classification_keys": ["bank_correspondence"],
            "completed_document_count": 0,
            "document_count": 1,
            "document_type_keys": ["bank_statement"],
            "latest_job_stage_name": "ocr",
            "latest_job_status": "completed",
            "oldest_review_task_created_at_utc": "2026-04-22T13:45:00Z",
            "operator_note_count": 1,
            "packet_id": "pkt_demo_001",
            "packet_name": "Northwind packet",
            "primary_document_id": "doc_demo_001",
            "primary_file_name": "statement.pdf",
            "primary_issuer_category": "bank",
            "primary_issuer_name": "Northwind Bank",
            "queue_age_hours": 2.5,
            "received_at_utc": "2026-04-22T13:30:00Z",
            "review_task_count": 1,
            "source": "scanned_upload",
            "source_uri": "manual://packets/pkt_demo_001",
            "stage_name": "review",
            "status": "awaiting_review",
            "submitted_by": "reviewer@example.com",
            "updated_at_utc": "2026-04-22T14:20:00Z",
        }
    ],
    "page": 1,
    "page_size": 25,
    "total_count": 1,
}

_PACKET_WORKSPACE_EXAMPLE = {
    "packet": {
        "created_at_utc": "2026-04-22T13:30:00Z",
        "packet_id": "pkt_demo_001",
        "packet_name": "Northwind packet",
        "packet_tags": ["priority"],
        "received_at_utc": "2026-04-22T13:30:00Z",
        "source": "scanned_upload",
        "source_uri": "manual://packets/pkt_demo_001",
        "status": "awaiting_review",
        "submitted_by": "reviewer@example.com",
        "updated_at_utc": "2026-04-22T14:20:00Z",
    },
    "documents": [
        {
            "account_candidates": ["acct_123"],
            "archive_preflight": {
                "disposition": "not_archive",
                "entry_count": 0,
                "is_archive": False,
                "is_multipart_archive": False,
                "nested_archive_count": 0,
                "total_uncompressed_bytes": 0,
                "uses_zip64": False,
            },
            "content_type": "application/pdf",
            "created_at_utc": "2026-04-22T13:30:00Z",
            "document_id": "doc_demo_001",
            "file_name": "statement.pdf",
            "issuer_category": "bank",
            "issuer_name": "Northwind Bank",
            "packet_id": "pkt_demo_001",
            "received_at_utc": "2026-04-22T13:30:00Z",
            "source": "scanned_upload",
            "status": "awaiting_review",
            "updated_at_utc": "2026-04-22T14:20:00Z",
        }
    ],
    "review_tasks": [
        {
            "assigned_user_email": "reviewer@example.com",
            "created_at_utc": "2026-04-22T13:45:00Z",
            "document_id": "doc_demo_001",
            "packet_id": "pkt_demo_001",
            "priority": "high",
            "reason_codes": ["account_override"],
            "review_task_id": "task_demo_001",
            "row_version": "0000000000000001",
            "selected_account_id": "acct_123",
            "status": "awaiting_review",
            "updated_at_utc": "2026-04-22T14:10:00Z",
        }
    ],
    "audit_events": [],
    "classification_results": [],
    "document_assets": [],
    "extraction_results": [],
    "ocr_results": [],
    "operator_notes": [],
    "packet_events": [],
    "processing_jobs": [],
    "recommendation_results": [],
    "recommendation_runs": [],
    "review_decisions": [],
    "account_match_runs": [],
}

_MANUAL_INTAKE_REQUEST_EXAMPLE = {
    "packet_name": "Northwind packet",
    "source": "scanned_upload",
    "source_uri": "manual://packets/northwind",
    "submitted_by": "reviewer@example.com",
    "packet_tags": ["priority"],
    "documents": [
        {
            "file_name": "statement.pdf",
            "content_type": "application/pdf",
            "document_content_base64": "JVBERi0xLjQKJ...",
            "issuer_name": "Northwind Bank",
            "issuer_category": "bank",
            "source_summary": "Uploaded from the protected intake drawer.",
        }
    ],
}

_MANUAL_INTAKE_RESPONSE_EXAMPLE = {
    "packet_id": "pkt_demo_001",
    "packet_name": "Northwind packet",
    "source": "scanned_upload",
    "source_uri": "manual://packets/northwind",
    "submitted_by": "reviewer@example.com",
    "packet_fingerprint": "a" * 64,
    "source_fingerprint": "b" * 64,
    "status": "received",
    "next_stage": "ocr",
    "document_count": 1,
    "duplicate_detection": {
        "reused_existing_packet_id": None,
        "should_skip_ingestion": False,
        "signals": [],
        "status": "unique",
    },
    "idempotency_reused_existing_packet": False,
    "received_at_utc": "2026-04-22T14:30:00Z",
    "documents": [
        {
            "archive_preflight": {
                "disposition": "not_archive",
                "entry_count": 0,
                "is_archive": False,
                "is_multipart_archive": False,
                "nested_archive_count": 0,
                "total_uncompressed_bytes": 0,
                "uses_zip64": False,
            },
            "blob_uri": "https://storage.example/raw/statement.pdf",
            "content_type": "application/pdf",
            "document_id": "doc_demo_001",
            "file_hash_sha256": "c" * 64,
            "file_name": "statement.pdf",
            "lineage": {
                "archive_depth": 0,
                "archive_member_path": None,
                "parent_document_id": None,
                "source_asset_id": None,
            },
            "processing_job_id": "job_demo_001",
            "processing_stage": "ocr",
            "processing_job_status": "queued",
            "review_task_id": None,
            "status": "received",
        }
    ],
}

_REVIEW_TASK_CREATE_REQUEST_EXAMPLE = {
    "assigned_user_email": "reviewer@example.com",
    "created_by_email": "lead.reviewer@example.com",
    "notes_summary": "Review the updated statement before approval.",
    "priority": "high",
    "selected_account_id": "acct_123",
}

_REVIEW_TASK_CREATE_RESPONSE_EXAMPLE = {
    "document_id": "doc_demo_001",
    "packet_id": "pkt_demo_001",
    "review_task_id": "task_demo_001",
}

_REVIEW_ASSIGNMENT_REQUEST_EXAMPLE = {
    "assigned_by_email": "lead.reviewer@example.com",
    "assigned_user_email": "reviewer@example.com",
    "expected_row_version": "0000000000000001",
}

_REVIEW_ASSIGNMENT_RESPONSE_EXAMPLE = {
    "assigned_user_email": "reviewer@example.com",
    "assigned_user_id": None,
    "packet_id": "pkt_demo_001",
    "review_task_id": "task_demo_001",
}

_REVIEW_DECISION_REQUEST_EXAMPLE = {
    "decided_by_email": "reviewer@example.com",
    "decision_reason_code": "account_override_confirmed",
    "decision_status": "approved",
    "expected_row_version": "0000000000000001",
    "review_notes": "Approved after validating the corrected account number.",
    "selected_account_id": "acct_123",
}

_REVIEW_DECISION_RESPONSE_EXAMPLE = {
    "decision": {
        "decided_at_utc": "2026-04-22T14:40:00Z",
        "decided_by_email": "reviewer@example.com",
        "decided_by_user_id": None,
        "decision_id": "decision_demo_001",
        "decision_reason_code": "account_override_confirmed",
        "decision_status": "approved",
        "document_id": "doc_demo_001",
        "packet_id": "pkt_demo_001",
        "review_notes": "Approved after validating the corrected account number.",
        "review_task_id": "task_demo_001",
        "selected_account_id": "acct_123",
    },
    "document_status": "ready_for_recommendation",
    "operator_note": None,
    "packet_id": "pkt_demo_001",
    "packet_status": "ready_for_recommendation",
    "queued_recommendation_job_id": "job_recommendation_001",
    "review_task_id": "task_demo_001",
    "review_task_status": "approved",
}

_REVIEW_NOTE_REQUEST_EXAMPLE = {
    "created_by_email": "reviewer@example.com",
    "expected_row_version": "0000000000000001",
    "is_private": False,
    "note_text": "Need one more statement page before approval.",
}

_REVIEW_NOTE_RESPONSE_EXAMPLE = {
    "operator_note": {
        "created_at_utc": "2026-04-22T14:35:00Z",
        "created_by_email": "reviewer@example.com",
        "created_by_user_id": None,
        "document_id": "doc_demo_001",
        "is_private": False,
        "note_id": "note_demo_001",
        "note_text": "Need one more statement page before approval.",
        "packet_id": "pkt_demo_001",
        "review_task_id": "task_demo_001",
    },
    "packet_id": "pkt_demo_001",
    "review_task_id": "task_demo_001",
}

_REVIEW_EXTRACTION_EDIT_REQUEST_EXAMPLE = {
    "edited_by_email": "reviewer@example.com",
    "expected_row_version": "0000000000000001",
    "field_edits": [{"field_name": "account_number", "value": "5678"}],
}

_REVIEW_EXTRACTION_EDIT_RESPONSE_EXAMPLE = {
    "audit_event": {
        "actor_email": "reviewer@example.com",
        "actor_user_id": None,
        "audit_event_id": 401,
        "created_at_utc": "2026-04-22T14:36:00Z",
        "document_id": "doc_demo_001",
        "event_payload": {"changedFieldCount": 1},
        "event_type": "review.extraction.fields.updated",
        "packet_id": "pkt_demo_001",
        "review_task_id": "task_demo_001",
    },
    "changed_fields": [
        {
            "confidence": 0.94,
            "current_value": "5678",
            "field_name": "account_number",
            "original_value": "1234",
        }
    ],
    "document_id": "doc_demo_001",
    "extraction_result": {
        "created_at_utc": "2026-04-22T14:36:00Z",
        "document_id": "doc_demo_001",
        "document_type": "bank_statement",
        "extraction_result_id": "ext_demo_002",
        "model_name": "gpt-5.4",
        "packet_id": "pkt_demo_001",
        "prompt_profile_id": "bank_statement",
        "provider": "azure_openai",
        "result_payload": {
            "extractedFields": [{"name": "account_number", "value": "5678"}]
        },
        "summary": "Updated extraction result.",
    },
    "packet_id": "pkt_demo_001",
    "review_task_id": "task_demo_001",
}

_PACKET_STAGE_ACTION_RESPONSE_EXAMPLE = {
    "executed_document_count": 1,
    "next_stage": "ocr",
    "packet_id": "pkt_demo_001",
    "processed_documents": [],
    "skipped_document_ids": [],
    "status": "ocr_running",
}

_PACKET_RETRY_RESPONSE_EXAMPLE = {
    "executed_document_count": 1,
    "failed_job_count": 1,
    "next_stage": "ocr",
    "packet_id": "pkt_demo_001",
    "requeued_document_count": 1,
    "skipped_document_ids": [],
    "stage_name": "ocr",
    "stale_running_job_count": 0,
    "status": "ocr_running",
}

_PACKET_REPLAY_RESPONSE_EXAMPLE = {
    "action": "retry",
    "executed_document_count": 1,
    "failed_job_count": 1,
    "message": "Ocr retried 1 document. 1 failed job and 0 stale running jobs qualified for intervention.",
    "next_stage": "ocr",
    "packet_id": "pkt_demo_001",
    "requeued_document_count": 1,
    "skipped_document_ids": [],
    "stage_name": "ocr",
    "stale_running_job_count": 0,
    "status": "ocr_running",
}

_RECOMMENDATION_REVIEW_REQUEST_EXAMPLE = {
    "disposition": "accepted",
    "reviewed_by_email": "reviewer@example.com",
}

_RECOMMENDATION_REVIEW_RESPONSE_EXAMPLE = {
    "packet_id": "pkt_demo_001",
    "recommendation_result": {
        "classification_prior_id": None,
        "classification_result_id": "class_demo_001",
        "confidence": 0.91,
        "created_at_utc": "2026-04-22T14:20:00Z",
        "disposition": "accepted",
        "document_id": "doc_demo_001",
        "packet_id": "pkt_demo_001",
        "rationale_payload": {},
        "recommendation_kind": "request_additional_document",
        "recommendation_result_id": "rec_demo_001",
        "recommendation_run_id": "rerun_demo_001",
        "reviewed_at_utc": "2026-04-22T14:45:00Z",
        "reviewed_by_email": "reviewer@example.com",
        "reviewed_by_user_id": None,
        "summary": "Accepted after matching refreshed account evidence.",
        "updated_at_utc": "2026-04-22T14:45:00Z",
    },
}

_INTAKE_SOURCE_LIST_EXAMPLE = {
    "items": [
        {
            "source_id": "src_demo_001",
            "source_name": "Watched inbox",
            "description": "Protected mailbox intake",
            "is_enabled": True,
            "owner_email": "reviewer@example.com",
            "polling_interval_minutes": 15,
            "credentials_reference": "kv://mailbox/intake",
            "configuration": {
                "source_kind": "email_connector",
                "mailbox_address": "intake@example.com",
                "folder_path": "INBOX/Statements",
                "attachment_extension_allowlist": ["pdf"],
            },
            "last_seen_at_utc": "2026-04-22T14:00:00Z",
            "last_success_at_utc": "2026-04-22T14:05:00Z",
            "last_error_at_utc": None,
            "last_error_message": None,
            "created_at_utc": "2026-04-21T12:00:00Z",
            "updated_at_utc": "2026-04-22T14:05:00Z",
        }
    ]
}

_INTAKE_SOURCE_MUTATION_EXAMPLE = {
    "source_name": "Watched inbox",
    "description": "Protected mailbox intake",
    "is_enabled": True,
    "owner_email": "reviewer@example.com",
    "polling_interval_minutes": 15,
    "credentials_reference": "kv://mailbox/intake",
    "configuration": {
        "source_kind": "email_connector",
        "mailbox_address": "intake@example.com",
        "folder_path": "INBOX/Statements",
        "attachment_extension_allowlist": ["pdf"],
    },
}

_INTAKE_SOURCE_DELETE_EXAMPLE = {
    "deleted": True,
    "source_id": "src_demo_001",
    "source_name": "Watched inbox",
}

_INTAKE_SOURCE_EXECUTION_EXAMPLE = {
    "executed_at_utc": "2026-04-22T14:50:00Z",
    "failed_blob_count": 0,
    "failures": [],
    "packet_results": [
        {
            "blob_name": "incoming/statement.pdf",
            "blob_uri": "https://storage.example/incoming/statement.pdf",
            "content_length_bytes": 1024,
            "content_type": "application/pdf",
            "document_count": 1,
            "duplicate_detection_status": "unique",
            "idempotency_reused_existing_packet": False,
            "packet_id": "pkt_demo_001",
            "packet_name": "Northwind packet",
            "status": "received",
        }
    ],
    "processed_blob_count": 1,
    "reused_packet_count": 0,
    "seen_blob_count": 1,
    "source_id": "src_demo_001",
    "source_kind": "email_connector",
    "source_name": "Watched inbox",
}


def _rewrite_schema_refs(value: Any) -> Any:
    if isinstance(value, dict):
        rewritten: dict[str, Any] = {}
        for key, nested_value in value.items():
            if (
                key == "$ref"
                and isinstance(nested_value, str)
                and nested_value.startswith("#/$defs/")
            ):
                rewritten[key] = (
                    f"#/components/schemas/{nested_value.split('/')[-1]}"
                )
            else:
                rewritten[key] = _rewrite_schema_refs(nested_value)
        return rewritten

    if isinstance(value, list):
        return [_rewrite_schema_refs(item) for item in value]

    return value


def _register_model_schema(
    components: dict[str, Any],
    schema_name: str,
    model_type: type[BaseModel],
) -> None:
    schema = model_type.model_json_schema()
    definitions = schema.pop("$defs", {})
    for definition_name, definition_schema in definitions.items():
        components.setdefault(
            definition_name,
            _rewrite_schema_refs(definition_schema),
        )
    components[schema_name] = _rewrite_schema_refs(schema)


def _build_components(
    models: tuple[tuple[str, type[BaseModel]], ...],
    *,
    include_admin_session_security: bool,
) -> dict[str, Any]:
    schemas: dict[str, Any] = {}
    for schema_name, model_type in models:
        _register_model_schema(schemas, schema_name, model_type)

    components: dict[str, Any] = {"schemas": schemas}
    if include_admin_session_security:
        components["securitySchemes"] = {
            "adminSession": {
                "type": "apiKey",
                "in": "cookie",
                "name": "AppServiceAuthSession",
                "description": (
                    "Microsoft-authenticated Easy Auth session on the private admin host. "
                    "The browser-facing proxy injects the server-side review API admin key "
                    "when it calls the Function App."
                ),
            }
        }
    return components


def _json_media_type(
    *,
    example: Any | None = None,
    schema: dict[str, Any] | None = None,
    schema_ref: str | None = None,
) -> dict[str, Any]:
    if schema is None and schema_ref is None:
        raise ValueError("A schema or schema_ref is required.")

    media_type: dict[str, Any] = {
        "schema": schema if schema is not None else {"$ref": schema_ref},
    }
    if example is not None:
        media_type["example"] = example
    return media_type


def _json_response(
    description: str,
    *,
    example: Any | None = None,
    schema: dict[str, Any] | None = None,
    schema_ref: str | None = None,
) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": _json_media_type(
                example=example,
                schema=schema,
                schema_ref=schema_ref,
            )
        },
    }


def _error_responses(
    statuses: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    return {
        status_code: _json_response(
            description,
            schema_ref="#/components/schemas/ApiErrorResponse",
        )
        for status_code, description in statuses
    }


def _parameter(
    name: str,
    *,
    location: str,
    description: str,
    required: bool = False,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "in": location,
        "name": name,
        "required": required,
        "description": description,
        "schema": schema or {"type": "string"},
    }


def _build_redoc_html(
    *,
    title: str,
    summary: str,
    auth_note: str,
    boundary_note: str,
    spec_url: str,
) -> str:
    escaped_title = escape(title)
    escaped_summary = escape(summary)
    escaped_auth_note = escape(auth_note)
    escaped_boundary_note = escape(boundary_note)
    escaped_spec_url = escape(spec_url, quote=True)
    return f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{escaped_title}</title>
    <style>
      body {{
        margin: 0;
        background: #081120;
        color: #f1f5f9;
        font-family: 'Segoe UI', sans-serif;
      }}
      .docs-shell {{
        margin: 0 auto;
        max-width: 1200px;
        padding: 2rem 1.5rem 1rem;
      }}
      .docs-card {{
        background: rgba(15, 23, 42, 0.88);
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 24px;
        box-shadow: 0 24px 60px rgba(2, 6, 23, 0.32);
        padding: 1.5rem;
      }}
      .docs-card h1 {{
        font-size: 1.9rem;
        margin: 0 0 0.75rem;
      }}
      .docs-card p {{
        color: #cbd5e1;
        line-height: 1.6;
        margin: 0.4rem 0;
      }}
      .docs-note {{
        color: #67e8f9;
      }}
      .docs-link {{
        color: #22d3ee;
        text-decoration: none;
      }}
      redoc {{
        display: block;
        margin-top: 1rem;
      }}
    </style>
  </head>
  <body>
    <main class=\"docs-shell\">
      <section class=\"docs-card\">
        <h1>{escaped_title}</h1>
        <p>{escaped_summary}</p>
        <p class=\"docs-note\"><strong>Auth note:</strong> {escaped_auth_note}</p>
        <p class=\"docs-note\"><strong>Boundary guidance:</strong> {escaped_boundary_note}</p>
        <p><a class=\"docs-link\" href=\"{escaped_spec_url}\">Open the raw OpenAPI JSON</a></p>
      </section>
      <redoc spec-url=\"{escaped_spec_url}\"></redoc>
    </main>
    <script src=\"https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js\"></script>
  </body>
</html>
"""


def build_public_api_docs_html(spec_url: str) -> str:
    """Return the anonymous Redoc page for the public API contract."""

    return _build_redoc_html(
        title="Public API Contract",
        summary=(
            "Anonymous public-safe endpoints for readiness, public request context, "
            "traffic telemetry, and cost transparency."
        ),
        auth_note="No authentication is required for the public routes on this page.",
        boundary_note=(
            "Only public-safe operational summaries appear here. Protected operator "
            "queue, packet, intake, and review workflows are intentionally excluded."
        ),
        spec_url=spec_url,
    )


def build_protected_api_docs_html(spec_url: str) -> str:
    """Return the authenticated Redoc page for the protected operator contract."""

    return _build_redoc_html(
        title="Protected Operator API Contract",
        summary=(
            "Microsoft-authenticated live-admin APIs for queue, packet, intake, review, "
            "and recommendation workflows behind the protected host."
        ),
        auth_note=(
            "These docs are only served from the private admin host. The browser-facing "
            "proxy uses the admin session and injects the server-side review API key when "
            "calling the Function App."
        ),
        boundary_note=(
            "The contract intentionally tracks the current /admin workflow shape and omits "
            "legacy review-items preview endpoints so the docs match the real operator path."
        ),
        spec_url=spec_url,
    )


def build_public_openapi_document() -> dict[str, Any]:
    """Build the anonymous public OpenAPI document."""

    models = (
        ("ApiErrorResponse", ApiErrorResponse),
        ("PublicCostMetricsSummary", PublicCostMetricsSummary),
        ("PublicHealthResponse", PublicHealthResponse),
        ("PublicRequestContext", PublicRequestContext),
        ("PublicSecurityCveFeed", PublicSecurityCveFeed),
        ("PublicSecurityMsrcFeed", PublicSecurityMsrcFeed),
        ("PublicTrafficAcceptedResponse", PublicTrafficAcceptedResponse),
        ("PublicTrafficEvent", PublicTrafficEvent),
        ("PublicTrafficMetricsSummary", PublicTrafficMetricsSummary),
    )
    paths = {
        "/health": {
            "get": {
                "operationId": "healthCheck",
                "summary": "Readiness summary",
                "description": "Returns a lightweight public-safe readiness payload for the Functions host.",
                "tags": ["Health"],
                "responses": {
                    "200": _json_response(
                        "Healthy readiness payload.",
                        example=_PUBLIC_HEALTH_EXAMPLE,
                        schema_ref="#/components/schemas/PublicHealthResponse",
                    )
                },
            }
        },
        "/public-traffic-events": {
            "post": {
                "operationId": "capturePublicTrafficEvent",
                "summary": "Capture public traffic event",
                "description": "Accepts public-safe page and health traffic events used by the public security route telemetry layer.",
                "tags": ["Security"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": _json_media_type(
                            example=_PUBLIC_TRAFFIC_EVENT_EXAMPLE,
                            schema_ref="#/components/schemas/PublicTrafficEvent",
                        )
                    },
                },
                "responses": {
                    "202": _json_response(
                        "Traffic event accepted for aggregation and optional alerting.",
                        example=_PUBLIC_TRAFFIC_ACCEPTED_EXAMPLE,
                        schema_ref="#/components/schemas/PublicTrafficAcceptedResponse",
                    ),
                    **_error_responses(
                        (("400", "Invalid public traffic event payload."),)
                    ),
                },
            }
        },
        "/public-metrics-summary": {
            "get": {
                "operationId": "getPublicMetricsSummary",
                "summary": "Aggregate public telemetry summary",
                "description": "Returns retained public-safe security telemetry, geography rollups, and monitored availability history.",
                "tags": ["Security"],
                "responses": {
                    "200": _json_response(
                        "Sanitized aggregate public telemetry summary.",
                        example=_PUBLIC_METRICS_SUMMARY_EXAMPLE,
                        schema_ref="#/components/schemas/PublicTrafficMetricsSummary",
                    )
                },
            }
        },
        "/public-request-context": {
            "get": {
                "operationId": "getPublicRequestContext",
                "summary": "Current public request context",
                "description": "Returns the public-safe request context rendered in the live security posture panel.",
                "tags": ["Security"],
                "responses": {
                    "200": _json_response(
                        "Sanitized request context for the current visitor.",
                        example=_PUBLIC_REQUEST_CONTEXT_EXAMPLE,
                        schema_ref="#/components/schemas/PublicRequestContext",
                    )
                },
            }
        },
        "/security/cves": {
            "get": {
                "operationId": "getPublicSecurityCveFeed",
                "summary": "Public NVD CVE feed",
                "description": (
                    "Returns the sanitized NVD CVE feed surfaced on the public security route. "
                    "Responses are cached in the public-security-feeds blob container for one hour "
                    "and fall back to the last successful sanitized payload when the upstream feed is "
                    "unavailable, so a brief NVD outage does not break the public security page."
                ),
                "tags": ["Security"],
                "responses": {
                    "200": _json_response(
                        "Sanitized NVD CVE feed snapshot.",
                        example=_PUBLIC_SECURITY_CVE_FEED_EXAMPLE,
                        schema_ref="#/components/schemas/PublicSecurityCveFeed",
                    )
                },
            }
        },
        "/security/msrc-latest": {
            "get": {
                "operationId": "getPublicSecurityMsrcFeed",
                "summary": "Public MSRC release index",
                "description": (
                    "Returns the sanitized MSRC CVRF release index surfaced on the public security "
                    "route. Responses are cached in the public-security-feeds blob container for six "
                    "hours and fall back to the last successful sanitized payload when the upstream "
                    "feed is unavailable, so a brief MSRC outage does not break the public security page."
                ),
                "tags": ["Security"],
                "responses": {
                    "200": _json_response(
                        "Sanitized MSRC CVRF release index snapshot.",
                        example=_PUBLIC_SECURITY_MSRC_FEED_EXAMPLE,
                        schema_ref="#/components/schemas/PublicSecurityMsrcFeed",
                    )
                },
            }
        },
        "/public-cost-summary": {
            "get": {
                "operationId": "getPublicCostSummary",
                "summary": "Public cost dashboard summary",
                "description": "Returns retained public-safe cost metrics, trend slices, anomalies, and forecast data for the public cost route.",
                "tags": ["Cost"],
                "responses": {
                    "200": _json_response(
                        "Latest retained public-safe cost summary.",
                        example=_PUBLIC_COST_SUMMARY_EXAMPLE,
                        schema_ref="#/components/schemas/PublicCostMetricsSummary",
                    ),
                    **_error_responses(
                        (("503", "Public cost history is not available yet."),)
                    ),
                },
            }
        },
        "/public-cost-latest": {
            "get": {
                "operationId": "getPublicCostLatest",
                "summary": "Latest raw public cost snapshot",
                "description": "Returns the latest retained public-safe snapshot payload used to derive the cost dashboard contract.",
                "tags": ["Cost"],
                "responses": {
                    "200": _json_response(
                        "Latest retained public-safe snapshot JSON.",
                        example=_PUBLIC_COST_LATEST_EXAMPLE,
                        schema={
                            "type": "object",
                            "description": "Snapshot payload containing the retained costSummary and historyRow objects.",
                            "additionalProperties": True,
                        },
                    ),
                    **_error_responses(
                        (("503", "Public cost history is not available yet."),)
                    ),
                },
            }
        },
        "/public-cost-history": {
            "get": {
                "operationId": "getPublicCostHistory",
                "summary": "Retained public cost CSV",
                "description": "Returns the retained public-safe CSV history consumed by the cost dashboard export flow.",
                "tags": ["Cost"],
                "responses": {
                    "200": {
                        "description": "Retained public-safe cost CSV history.",
                        "content": {
                            "text/csv": {
                                "schema": {"type": "string"},
                                "example": _PUBLIC_COST_HISTORY_CSV_EXAMPLE,
                            }
                        },
                    },
                    **_error_responses(
                        (("503", "Public cost history is not available yet."),)
                    ),
                },
            }
        },
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Hybrid Document Intelligence Public API",
            "version": "2026-04-24",
            "description": (
                "Anonymous public-safe endpoints for health, security telemetry, request context, "
                "external security signal feeds, and cost transparency. Protected operator queue, "
                "intake, packet, and review APIs are intentionally excluded from this contract."
            ),
        },
        "jsonSchemaDialect": "https://json-schema.org/draft/2020-12/schema",
        "servers": [{"url": "/api", "description": "Anonymous Functions API base path"}],
        "tags": [
            {
                "name": "Health",
                "description": "Public readiness and host-level service checks.",
            },
            {
                "name": "Security",
                "description": "Public-safe request and telemetry surfaces that power the security route.",
            },
            {
                "name": "Cost",
                "description": "Public-safe cost transparency endpoints for the cost dashboard and exports.",
            },
        ],
        "paths": paths,
        "components": _build_components(models, include_admin_session_security=False),
    }


def build_protected_openapi_document() -> dict[str, Any]:
    """Build the protected operator OpenAPI document for the live admin host."""

    models = (
        ("ApiErrorResponse", ApiErrorResponse),
        ("IntakeSourceCreateRequest", IntakeSourceCreateRequest),
        ("IntakeSourceDeleteResponse", IntakeSourceDeleteResponse),
        ("IntakeSourceEnablementRequest", IntakeSourceEnablementRequest),
        ("IntakeSourceExecutionResponse", IntakeSourceExecutionResponse),
        ("IntakeSourceListResponse", IntakeSourceListResponse),
        ("IntakeSourceRecord", IntakeSourceRecord),
        ("IntakeSourceUpdateRequest", IntakeSourceUpdateRequest),
        ("LiveSiteSessionResponse", LiveSiteSessionResponse),
        ("ManualPacketIntakeRequest", ManualPacketIntakeRequest),
        ("ManualPacketIntakeResponse", ManualPacketIntakeResponse),
        ("OperatorContractsResponse", OperatorContractsResponse),
        ("PacketClassificationExecutionResponse", PacketClassificationExecutionResponse),
        ("PacketExtractionExecutionResponse", PacketExtractionExecutionResponse),
        ("PacketOcrExecutionResponse", PacketOcrExecutionResponse),
        ("PacketQueueListResponse", PacketQueueListResponse),
        ("PacketRecommendationExecutionResponse", PacketRecommendationExecutionResponse),
        ("PacketRecommendationReviewRequest", PacketRecommendationReviewRequest),
        ("PacketRecommendationReviewResponse", PacketRecommendationReviewResponse),
        ("PacketReplayResponse", PacketReplayResponse),
        ("PacketReviewAssignmentRequest", PacketReviewAssignmentRequest),
        ("PacketReviewAssignmentResponse", PacketReviewAssignmentResponse),
        ("PacketReviewDecisionRequest", PacketReviewDecisionRequest),
        ("PacketReviewDecisionResponse", PacketReviewDecisionResponse),
        ("PacketReviewExtractionEditRequest", PacketReviewExtractionEditRequest),
        ("PacketReviewExtractionEditResponse", PacketReviewExtractionEditResponse),
        ("PacketReviewNoteRequest", PacketReviewNoteRequest),
        ("PacketReviewNoteResponse", PacketReviewNoteResponse),
        ("PacketReviewTaskCreateRequest", PacketReviewTaskCreateRequest),
        ("PacketReviewTaskCreateResponse", PacketReviewTaskCreateResponse),
        ("PacketStageRetryResponse", PacketStageRetryResponse),
        ("PacketWorkspaceSnapshot", PacketWorkspaceSnapshot),
        ("ProcessingTaxonomyResponse", ProcessingTaxonomyResponse),
    )
    common_protected_errors = _error_responses(
        (
            ("401", "The caller is missing the required private admin access."),
            ("403", "The caller is authenticated but not allowed to access this resource."),
            ("404", "The referenced packet, document, review task, or recommendation was not found."),
            ("409", "The requested mutation conflicted with the current operator-state version."),
            ("503", "The backing operator service is not configured on this host."),
        )
    )
    paths = {
        "/session": {
            "get": {
                "operationId": "getLiveSession",
                "summary": "Current admin session",
                "description": "Returns the Microsoft-authenticated principal resolved by the private admin host.",
                "tags": ["Session"],
                "responses": {
                    "200": _json_response(
                        "Authenticated private-admin session.",
                        example=_LIVE_SESSION_EXAMPLE,
                        schema_ref="#/components/schemas/LiveSiteSessionResponse",
                    ),
                    **_error_responses(
                        (("403", "This admin site only allows the configured Microsoft account."),)
                    ),
                },
            }
        },
        "/packets": {
            "get": {
                "operationId": "listPacketQueue",
                "summary": "List operator packet queue",
                "description": "Returns the SQL-backed packet queue used by the protected /admin workbench.",
                "tags": ["Packets"],
                "parameters": [
                    _parameter("page", location="query", description="1-based queue page number.", schema={"type": "integer", "minimum": 1, "default": 1}),
                    _parameter("page_size", location="query", description="Maximum rows returned per page.", schema={"type": "integer", "minimum": 1, "maximum": 100, "default": 25}),
                    _parameter("stage_name", location="query", description="Optional queue stage filter.", schema={"type": "string"}),
                    _parameter("status", location="query", description="Optional packet status filter.", schema={"type": "string"}),
                    _parameter("source", location="query", description="Optional source filter.", schema={"type": "string"}),
                    _parameter("assigned_user_email", location="query", description="Optional assigned reviewer filter.", schema={"type": "string", "format": "email"}),
                    _parameter("classification_key", location="query", description="Optional classification contract filter.", schema={"type": "string"}),
                    _parameter("document_type_key", location="query", description="Optional document-type contract filter.", schema={"type": "string"}),
                    _parameter("min_queue_age_hours", location="query", description="Optional minimum queue age filter.", schema={"type": "number", "minimum": 0}),
                ],
                "responses": {
                    "200": _json_response(
                        "Paged packet queue slice.",
                        example=_PACKET_QUEUE_EXAMPLE,
                        schema_ref="#/components/schemas/PacketQueueListResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/packets/{packet_id}/workspace": {
            "get": {
                "operationId": "getPacketWorkspace",
                "summary": "Load packet workspace",
                "description": "Returns the full packet workspace snapshot shown beside the queue in the protected admin shell.",
                "tags": ["Packets"],
                "parameters": [
                    _parameter("packet_id", location="path", description="Packet identifier.", required=True),
                ],
                "responses": {
                    "200": _json_response(
                        "Packet workspace snapshot.",
                        example=_PACKET_WORKSPACE_EXAMPLE,
                        schema_ref="#/components/schemas/PacketWorkspaceSnapshot",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/packets/{packet_id}/documents/{document_id}/content": {
            "get": {
                "operationId": "getPacketDocumentContent",
                "summary": "Fetch protected document preview",
                "description": "Returns the binary preview content used by the protected viewer tab for one packet document.",
                "tags": ["Packets"],
                "parameters": [
                    _parameter("packet_id", location="path", description="Packet identifier.", required=True),
                    _parameter("document_id", location="path", description="Document identifier.", required=True),
                ],
                "responses": {
                    "200": {
                        "description": "Binary preview payload for the requested document.",
                        "content": {
                            "application/pdf": {"schema": {"type": "string", "format": "binary"}},
                            "image/png": {"schema": {"type": "string", "format": "binary"}},
                            "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
                        },
                    },
                    **common_protected_errors,
                },
            }
        },
        "/packets/manual-intake": {
            "post": {
                "operationId": "createManualPacket",
                "summary": "Create manual intake packet",
                "description": "Stages one operator-uploaded packet into Blob storage and Azure SQL for downstream processing.",
                "tags": ["Intake"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": _json_media_type(
                            example=_MANUAL_INTAKE_REQUEST_EXAMPLE,
                            schema_ref="#/components/schemas/ManualPacketIntakeRequest",
                        )
                    },
                },
                "responses": {
                    "201": _json_response(
                        "Manual packet staged for downstream processing.",
                        example=_MANUAL_INTAKE_RESPONSE_EXAMPLE,
                        schema_ref="#/components/schemas/ManualPacketIntakeResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/packets/{packet_id}/documents/{document_id}/review-tasks": {
            "post": {
                "operationId": "createPacketReviewTask",
                "summary": "Create review task",
                "description": "Creates one SQL-backed review task for a packet document from the protected Review tab.",
                "tags": ["Review"],
                "parameters": [
                    _parameter("packet_id", location="path", description="Packet identifier.", required=True),
                    _parameter("document_id", location="path", description="Document identifier.", required=True),
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": _json_media_type(
                            example=_REVIEW_TASK_CREATE_REQUEST_EXAMPLE,
                            schema_ref="#/components/schemas/PacketReviewTaskCreateRequest",
                        )
                    },
                },
                "responses": {
                    "200": _json_response(
                        "Review task created.",
                        example=_REVIEW_TASK_CREATE_RESPONSE_EXAMPLE,
                        schema_ref="#/components/schemas/PacketReviewTaskCreateResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/review-tasks/{review_task_id}/assignment": {
            "post": {
                "operationId": "applyReviewTaskAssignment",
                "summary": "Update review assignment",
                "description": "Assigns, reassigns, or clears the owner for one SQL-backed review task.",
                "tags": ["Review"],
                "parameters": [
                    _parameter("review_task_id", location="path", description="Review task identifier.", required=True),
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": _json_media_type(
                            example=_REVIEW_ASSIGNMENT_REQUEST_EXAMPLE,
                            schema_ref="#/components/schemas/PacketReviewAssignmentRequest",
                        )
                    },
                },
                "responses": {
                    "200": _json_response(
                        "Review task assignment updated.",
                        example=_REVIEW_ASSIGNMENT_RESPONSE_EXAMPLE,
                        schema_ref="#/components/schemas/PacketReviewAssignmentResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/review-tasks/{review_task_id}/decision": {
            "post": {
                "operationId": "applyReviewTaskDecision",
                "summary": "Persist review decision",
                "description": "Approves or rejects one SQL-backed review task and advances packet state when appropriate.",
                "tags": ["Review"],
                "parameters": [
                    _parameter("review_task_id", location="path", description="Review task identifier.", required=True),
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": _json_media_type(
                            example=_REVIEW_DECISION_REQUEST_EXAMPLE,
                            schema_ref="#/components/schemas/PacketReviewDecisionRequest",
                        )
                    },
                },
                "responses": {
                    "200": _json_response(
                        "Review decision persisted.",
                        example=_REVIEW_DECISION_RESPONSE_EXAMPLE,
                        schema_ref="#/components/schemas/PacketReviewDecisionResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/review-tasks/{review_task_id}/notes": {
            "post": {
                "operationId": "applyReviewTaskNote",
                "summary": "Create review task note",
                "description": "Persists one task-scoped operator note without requiring a final review decision.",
                "tags": ["Review"],
                "parameters": [
                    _parameter("review_task_id", location="path", description="Review task identifier.", required=True),
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": _json_media_type(
                            example=_REVIEW_NOTE_REQUEST_EXAMPLE,
                            schema_ref="#/components/schemas/PacketReviewNoteRequest",
                        )
                    },
                },
                "responses": {
                    "200": _json_response(
                        "Review task note created.",
                        example=_REVIEW_NOTE_RESPONSE_EXAMPLE,
                        schema_ref="#/components/schemas/PacketReviewNoteResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/review-tasks/{review_task_id}/extraction-edits": {
            "post": {
                "operationId": "applyReviewTaskExtractionEdits",
                "summary": "Persist extraction edits",
                "description": "Stores extracted-field corrections for one review task and emits a dedicated audit event.",
                "tags": ["Review"],
                "parameters": [
                    _parameter("review_task_id", location="path", description="Review task identifier.", required=True),
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": _json_media_type(
                            example=_REVIEW_EXTRACTION_EDIT_REQUEST_EXAMPLE,
                            schema_ref="#/components/schemas/PacketReviewExtractionEditRequest",
                        )
                    },
                },
                "responses": {
                    "200": _json_response(
                        "Extraction edits persisted.",
                        example=_REVIEW_EXTRACTION_EDIT_RESPONSE_EXAMPLE,
                        schema_ref="#/components/schemas/PacketReviewExtractionEditResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/intake-sources": {
            "get": {
                "operationId": "listIntakeSources",
                "summary": "List intake sources",
                "description": "Returns the durable intake-source definitions surfaced in the protected Sources tab.",
                "tags": ["Intake"],
                "responses": {
                    "200": _json_response(
                        "Intake source list.",
                        example=_INTAKE_SOURCE_LIST_EXAMPLE,
                        schema_ref="#/components/schemas/IntakeSourceListResponse",
                    ),
                    **common_protected_errors,
                },
            },
            "post": {
                "operationId": "createIntakeSource",
                "summary": "Create intake source",
                "description": "Creates one durable intake-source definition.",
                "tags": ["Intake"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": _json_media_type(
                            example=_INTAKE_SOURCE_MUTATION_EXAMPLE,
                            schema_ref="#/components/schemas/IntakeSourceCreateRequest",
                        )
                    },
                },
                "responses": {
                    "201": _json_response(
                        "Created intake source.",
                        example=_INTAKE_SOURCE_LIST_EXAMPLE["items"][0],
                        schema_ref="#/components/schemas/IntakeSourceRecord",
                    ),
                    **common_protected_errors,
                },
            },
        },
        "/intake-sources/{source_id}": {
            "put": {
                "operationId": "updateIntakeSource",
                "summary": "Replace intake source",
                "description": "Updates one durable intake-source definition.",
                "tags": ["Intake"],
                "parameters": [
                    _parameter("source_id", location="path", description="Intake source identifier.", required=True),
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": _json_media_type(
                            example=_INTAKE_SOURCE_MUTATION_EXAMPLE,
                            schema_ref="#/components/schemas/IntakeSourceUpdateRequest",
                        )
                    },
                },
                "responses": {
                    "200": _json_response(
                        "Updated intake source.",
                        example=_INTAKE_SOURCE_LIST_EXAMPLE["items"][0],
                        schema_ref="#/components/schemas/IntakeSourceRecord",
                    ),
                    **common_protected_errors,
                },
            },
            "delete": {
                "operationId": "deleteIntakeSource",
                "summary": "Delete intake source",
                "description": "Deletes one durable intake-source definition.",
                "tags": ["Intake"],
                "parameters": [
                    _parameter("source_id", location="path", description="Intake source identifier.", required=True),
                ],
                "responses": {
                    "200": _json_response(
                        "Deleted intake source.",
                        example=_INTAKE_SOURCE_DELETE_EXAMPLE,
                        schema_ref="#/components/schemas/IntakeSourceDeleteResponse",
                    ),
                    **common_protected_errors,
                },
            },
        },
        "/intake-sources/{source_id}/enablement": {
            "post": {
                "operationId": "setIntakeSourceEnablement",
                "summary": "Pause or resume intake source",
                "description": "Toggles the enabled state for one intake-source definition.",
                "tags": ["Intake"],
                "parameters": [
                    _parameter("source_id", location="path", description="Intake source identifier.", required=True),
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": _json_media_type(
                            example={"is_enabled": True},
                            schema_ref="#/components/schemas/IntakeSourceEnablementRequest",
                        )
                    },
                },
                "responses": {
                    "200": _json_response(
                        "Updated intake source enablement.",
                        example=_INTAKE_SOURCE_LIST_EXAMPLE["items"][0],
                        schema_ref="#/components/schemas/IntakeSourceRecord",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/intake-sources/{source_id}/execute": {
            "post": {
                "operationId": "runIntakeSource",
                "summary": "Execute intake source",
                "description": "Runs one intake source against live inputs and returns the packet staging summary.",
                "tags": ["Intake"],
                "parameters": [
                    _parameter("source_id", location="path", description="Intake source identifier.", required=True),
                ],
                "responses": {
                    "200": _json_response(
                        "Intake source execution summary.",
                        example=_INTAKE_SOURCE_EXECUTION_EXAMPLE,
                        schema_ref="#/components/schemas/IntakeSourceExecutionResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/processing-taxonomy": {
            "get": {
                "operationId": "getProcessingTaxonomy",
                "summary": "Get processing taxonomy",
                "description": "Returns the canonical stage and status metadata used by the protected queue and workspace.",
                "tags": ["Contracts"],
                "responses": {
                    "200": _json_response(
                        "Processing taxonomy.",
                        example={
                            "stages": [
                                {
                                    "description": "OCR processing stage.",
                                    "display_name": "OCR",
                                    "stage_name": "ocr",
                                    "statuses": ["queued", "ocr_running", "failed"],
                                }
                            ],
                            "statuses": [
                                {
                                    "category": "in_progress",
                                    "description": "Awaiting reviewer action.",
                                    "display_name": "Awaiting review",
                                    "operator_attention_required": True,
                                    "stage_name": "review",
                                    "status": "awaiting_review",
                                    "terminal": False,
                                }
                            ],
                        },
                        schema_ref="#/components/schemas/ProcessingTaxonomyResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/operator-contracts": {
            "get": {
                "operationId": "getOperatorContracts",
                "summary": "Get operator contracts",
                "description": "Returns managed classifications, document types, prompt profiles, and recommendation guidance used by the protected admin surfaces.",
                "tags": ["Contracts"],
                "responses": {
                    "200": _json_response(
                        "Operator contracts bundle.",
                        example={
                            "classification_definitions": [],
                            "document_type_definitions": [],
                            "processing_taxonomy": {
                                "stages": [],
                                "statuses": [],
                            },
                            "prompt_profile_versions": [],
                            "prompt_profiles": [],
                            "recommendation_contract": {
                                "advisory_only": True,
                                "default_status": "queued",
                                "disposition_values": ["pending", "accepted", "rejected"],
                                "required_evidence_kinds": ["extracted_field", "ocr_excerpt", "source_document_link"],
                                "conflict_field_names": ["account_number", "statement_date"],
                                "guardrail_reason_codes": ["conflicting_packet_evidence"],
                                "minimum_confidence": 0.75,
                                "required_packet_status": "ready_for_recommendation",
                                "supported_field_names": ["account_number", "statement_date"],
                            },
                        },
                        schema_ref="#/components/schemas/OperatorContractsResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/packets/{packet_id}/classification/execute": {
            "post": {
                "operationId": "runPacketClassification",
                "summary": "Execute classification stage",
                "description": "Runs queued packet classification work and prepares OCR handoff.",
                "tags": ["Pipeline"],
                "parameters": [_parameter("packet_id", location="path", description="Packet identifier.", required=True)],
                "responses": {
                    "200": _json_response(
                        "Classification stage execution summary.",
                        example=_PACKET_STAGE_ACTION_RESPONSE_EXAMPLE,
                        schema_ref="#/components/schemas/PacketClassificationExecutionResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/packets/{packet_id}/ocr/execute": {
            "post": {
                "operationId": "runPacketOcr",
                "summary": "Execute OCR stage",
                "description": "Runs queued OCR work and prepares extraction handoff.",
                "tags": ["Pipeline"],
                "parameters": [_parameter("packet_id", location="path", description="Packet identifier.", required=True)],
                "responses": {
                    "200": _json_response(
                        "OCR stage execution summary.",
                        example={**_PACKET_STAGE_ACTION_RESPONSE_EXAMPLE, "next_stage": "extraction", "status": "extracting"},
                        schema_ref="#/components/schemas/PacketOcrExecutionResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/packets/{packet_id}/extraction/execute": {
            "post": {
                "operationId": "runPacketExtraction",
                "summary": "Execute extraction stage",
                "description": "Runs queued extraction and matching work and determines the next review or recommendation step.",
                "tags": ["Pipeline"],
                "parameters": [_parameter("packet_id", location="path", description="Packet identifier.", required=True)],
                "responses": {
                    "200": _json_response(
                        "Extraction stage execution summary.",
                        example={**_PACKET_STAGE_ACTION_RESPONSE_EXAMPLE, "next_stage": "review", "status": "awaiting_review"},
                        schema_ref="#/components/schemas/PacketExtractionExecutionResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/packets/{packet_id}/recommendation/execute": {
            "post": {
                "operationId": "runPacketRecommendation",
                "summary": "Execute recommendation stage",
                "description": "Runs queued recommendation generation for packet documents that are ready for recommendation.",
                "tags": ["Pipeline"],
                "parameters": [_parameter("packet_id", location="path", description="Packet identifier.", required=True)],
                "responses": {
                    "200": _json_response(
                        "Recommendation stage execution summary.",
                        example={**_PACKET_STAGE_ACTION_RESPONSE_EXAMPLE, "next_stage": "recommendation", "status": "completed"},
                        schema_ref="#/components/schemas/PacketRecommendationExecutionResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/packets/{packet_id}/stages/{stage_name}/retry": {
            "post": {
                "operationId": "retryPacketStage",
                "summary": "Retry packet stage",
                "description": "Retries failed or stale work for one supported packet stage.",
                "tags": ["Pipeline"],
                "parameters": [
                    _parameter("packet_id", location="path", description="Packet identifier.", required=True),
                    _parameter("stage_name", location="path", description="Stage name to retry.", required=True),
                ],
                "responses": {
                    "200": _json_response(
                        "Packet stage retry summary.",
                        example=_PACKET_RETRY_RESPONSE_EXAMPLE,
                        schema_ref="#/components/schemas/PacketStageRetryResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/packets/{packet_id}/replay": {
            "post": {
                "operationId": "replayPacket",
                "summary": "Replay next actionable packet work",
                "description": "Replays the next actionable stage from the Intake workspace and returns the resulting action summary.",
                "tags": ["Pipeline"],
                "parameters": [_parameter("packet_id", location="path", description="Packet identifier.", required=True)],
                "responses": {
                    "200": _json_response(
                        "Packet replay summary.",
                        example=_PACKET_REPLAY_RESPONSE_EXAMPLE,
                        schema_ref="#/components/schemas/PacketReplayResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
        "/packets/{packet_id}/recommendation-results/{recommendation_result_id}/review": {
            "post": {
                "operationId": "reviewPacketRecommendation",
                "summary": "Review recommendation result",
                "description": "Accepts or rejects one stored recommendation result from the protected Recommendations tab.",
                "tags": ["Recommendations"],
                "parameters": [
                    _parameter("packet_id", location="path", description="Packet identifier.", required=True),
                    _parameter("recommendation_result_id", location="path", description="Recommendation result identifier.", required=True),
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": _json_media_type(
                            example=_RECOMMENDATION_REVIEW_REQUEST_EXAMPLE,
                            schema_ref="#/components/schemas/PacketRecommendationReviewRequest",
                        )
                    },
                },
                "responses": {
                    "200": _json_response(
                        "Recommendation result reviewed.",
                        example=_RECOMMENDATION_REVIEW_RESPONSE_EXAMPLE,
                        schema_ref="#/components/schemas/PacketRecommendationReviewResponse",
                    ),
                    **common_protected_errors,
                },
            }
        },
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Hybrid Document Intelligence Protected Operator API",
            "version": "2026-04-22",
            "description": (
                "Selected live-admin APIs aligned to the protected /admin workflow. This contract covers the queue, packet workspace, intake, "
                "review-task, pipeline, and recommendation surfaces used by the authenticated operator shell. Legacy /review-items endpoints are intentionally excluded so the docs reflect the real operator path rather than the older queue prototype."
            ),
        },
        "jsonSchemaDialect": "https://json-schema.org/draft/2020-12/schema",
        "servers": [{"url": "/api", "description": "Protected live-admin proxy API base path"}],
        "security": [{"adminSession": []}],
        "tags": [
            {"name": "Session", "description": "Private admin-session identity and authorization state."},
            {"name": "Packets", "description": "Queue and workspace APIs used by the /admin packet workbench."},
            {"name": "Intake", "description": "Manual-intake and managed source operations used by the protected intake flow."},
            {"name": "Review", "description": "Review-task creation, assignment, decision, note, and extraction-edit APIs."},
            {"name": "Pipeline", "description": "Stage execution, retry, and replay APIs for live operator intervention."},
            {"name": "Recommendations", "description": "Protected recommendation review actions."},
            {"name": "Contracts", "description": "Managed taxonomy and operator contract definitions used by the admin UI."},
        ],
        "paths": paths,
        "components": _build_components(models, include_admin_session_security=True),
    }


def render_openapi_json(document: dict[str, Any]) -> str:
    """Serialize an OpenAPI document for HTTP responses."""

    return json.dumps(document, indent=2, sort_keys=True)
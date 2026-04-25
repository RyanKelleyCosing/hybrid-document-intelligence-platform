"""Unit tests for account-level review reporting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from document_intelligence.account_review_reporting import (
    build_account_review_report,
    build_account_review_report_from_files,
)


def test_build_account_review_report_filters_one_primary_account() -> None:
    """A filtered report should return only the requested account and its docs."""
    payload = build_account_review_report(
        _build_manifest_payload(),
        _build_storage_results_payload(),
        account_id="acct-3001-med-45678",
    )

    assert payload["accountCount"] == 1
    account = payload["accounts"][0]
    assert account["accountId"] == "acct-3001-med-45678"
    assert account["documentCount"] == 2
    assert account["reviewItemCount"] == 1
    assert account["readyForEnrichmentCount"] == 1
    assert [document["documentId"] for document in account["documents"]] == [
        "doc-3001-hospital-bill",
        "doc-3001-medical-summary",
    ]


def test_build_account_review_report_marks_aws_bridge_documents() -> None:
    """AWS bridge results should expose the bridged persisted document id."""
    payload = build_account_review_report(
        _build_manifest_payload(),
        _build_aws_results_payload(),
        account_id="acct-3001-med-45678",
    )

    assert payload["resultsKind"] == "aws_bridge"
    document = payload["accounts"][0]["documents"][0]
    assert document["persistedDocumentId"] == "aws-123"
    assert document["reviewItemFound"] is True
    assert document["blobCopied"] is True


def test_build_account_review_report_from_files_reads_json_files(
    tmp_path: Path,
) -> None:
    """Manifest and result files should produce an all-account report."""
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(
        json.dumps(_build_manifest_payload()),
        encoding="utf-8",
    )
    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps(_build_storage_results_payload()),
        encoding="utf-8",
    )

    payload = build_account_review_report_from_files(manifest_file, results_file)

    assert payload["accountCount"] == 2
    assert payload["resultsKind"] == "storage_backed"
    assert payload["manifestFile"] == str(manifest_file)
    assert payload["resultsFile"] == str(results_file)


def test_build_account_review_report_raises_for_missing_account() -> None:
    """Unknown account ids should fail fast."""
    with pytest.raises(ValueError, match="Account id 'acct-missing'"):
        build_account_review_report(
            _build_manifest_payload(),
            _build_storage_results_payload(),
            account_id="acct-missing",
        )


def _build_manifest_payload() -> dict[str, object]:
    return {
        "generated_at_utc": "2026-04-01T00:00:00Z",
        "scenario_set": "debt-relief-intake",
        "cases": [
            {
                "accounts": [
                    {
                        "account_id": "acct-3001-cc-987654",
                        "account_number": "987654",
                        "balance_due": "$10,842.17",
                        "debt_type": "credit card",
                        "issuer_name": "Northwind Platinum Card Services",
                    },
                    {
                        "account_id": "acct-3001-med-45678",
                        "account_number": "45678",
                        "balance_due": "$7,261.44",
                        "debt_type": "medical",
                        "issuer_name": "St. Mary Regional Medical Center",
                    },
                ],
                "case_id": "case-3001",
                "customer_alias": "Maria Gonzalez",
                "entry_point": "front_door_walk_in",
                "intake_description": "Walk-in debt-relief intake.",
                "reason_for_visiting": "Needs help with debt relief.",
                "source": "scanned_upload",
            }
        ],
        "documents": [
            {
                "account_candidates": ["acct-3001-cc-987654"],
                "case_id": "case-3001",
                "content_type": "application/pdf",
                "document_id": "doc-3001-cc-statement",
                "document_path": "cases/case-3001/cc.pdf",
                "entry_point": "front_door_walk_in",
                "file_name": "cc.pdf",
                "issuer_category": "bank",
                "issuer_name": "Northwind Platinum Card Services",
                "primary_account_id": "acct-3001-cc-987654",
                "request_path": "requests/doc-3001-cc-statement.json",
                "source": "scanned_upload",
                "source_uri": "scan://front-door/case-3001/cc.pdf",
                "workbook_path": "cases/case-3001/cc.pdf",
            },
            {
                "account_candidates": ["acct-3001-med-45678"],
                "case_id": "case-3001",
                "content_type": "image/jpeg",
                "document_id": "doc-3001-hospital-bill",
                "document_path": "cases/case-3001/hospital.jpg",
                "entry_point": "front_door_walk_in",
                "file_name": "hospital.jpg",
                "issuer_category": "healthcare_provider",
                "issuer_name": "St. Mary Regional Medical Center",
                "primary_account_id": "acct-3001-med-45678",
                "request_path": "requests/doc-3001-hospital-bill.json",
                "source": "scanned_upload",
                "source_uri": "scan://front-door/case-3001/hospital.jpg",
                "workbook_path": "cases/case-3001/hospital.jpg",
            },
            {
                "account_candidates": ["acct-3001-med-45678"],
                "case_id": "case-3001",
                "content_type": "application/msword",
                "document_id": "doc-3001-medical-summary",
                "document_path": "cases/case-3001/summary.doc",
                "entry_point": "front_door_walk_in",
                "file_name": "summary.doc",
                "issuer_category": "healthcare_provider",
                "issuer_name": "St. Mary Regional Medical Center",
                "primary_account_id": "acct-3001-med-45678",
                "request_path": "requests/doc-3001-medical-summary.json",
                "source": "scanned_upload",
                "source_uri": "scan://front-door/case-3001/summary.doc",
                "workbook_path": "cases/case-3001/summary.doc",
            },
        ],
    }


def _build_storage_results_payload() -> dict[str, object]:
    return {
        "blobPrefix": "storage-backed/debt-relief-intake/20260401220712",
        "bundleDir": "samples/synthetic/generated/debt-relief-intake",
        "errorCount": 0,
        "processedCount": 3,
        "requestedCount": 3,
        "results": [
            {
                "blobName": "storage-backed/debt-relief-intake/cc.pdf",
                "documentId": "doc-3001-cc-statement",
                "fileName": "cc.pdf",
                "logicalSource": "scanned_upload",
                "reviewItemDocumentId": None,
                "reviewItemStatus": None,
                "runtimeStatus": "Completed",
                "sourceUri": "az://raw-documents/storage-backed/debt-relief-intake/cc.pdf",
                "targetStatus": "ready_for_enrichment",
                "workflowMode": "synchronous",
            },
            {
                "blobName": "storage-backed/debt-relief-intake/hospital.jpg",
                "documentId": "doc-3001-hospital-bill",
                "fileName": "hospital.jpg",
                "logicalSource": "scanned_upload",
                "reviewItemDocumentId": "doc-3001-hospital-bill",
                "reviewItemStatus": "pending_review",
                "runtimeStatus": "Completed",
                "sourceUri": (
                    "az://raw-documents/storage-backed/debt-relief-intake/"
                    "hospital.jpg"
                ),
                "targetStatus": "pending_review",
                "workflowMode": "synchronous",
            },
            {
                "blobName": "storage-backed/debt-relief-intake/summary.doc",
                "documentId": "doc-3001-medical-summary",
                "fileName": "summary.doc",
                "logicalSource": "scanned_upload",
                "reviewItemDocumentId": None,
                "reviewItemStatus": None,
                "runtimeStatus": "Completed",
                "sourceUri": (
                    "az://raw-documents/storage-backed/debt-relief-intake/"
                    "summary.doc"
                ),
                "targetStatus": "ready_for_enrichment",
                "workflowMode": "synchronous",
            },
        ],
        "reviewItemCount": 1,
    }


def _build_aws_results_payload() -> dict[str, object]:
    return {
        "blobCopiedCount": 1,
        "errorCount": 0,
        "objectPrefix": "incoming/aws-bridge-bulk/debt-relief-intake/20260401222127",
        "processedCount": 1,
        "requestedCount": 1,
        "results": [
            {
                "blobCopied": True,
                "blobName": "aws-s3/aws-bridge-bulk/debt-relief-intake/hospital.jpg",
                "documentId": "doc-3001-hospital-bill",
                "fileName": "hospital.jpg",
                "logicalSource": "scanned_upload",
                "reviewItemDocumentId": "aws-123",
                "reviewItemFound": True,
                "reviewItemStatus": "pending_review",
                "sourceUri": "az://raw-documents/aws-s3/aws-bridge-bulk/debt-relief-intake/hospital.jpg",
                "storageBridgeDocumentId": "aws-123",
            }
        ],
        "reviewItemCount": 1,
    }
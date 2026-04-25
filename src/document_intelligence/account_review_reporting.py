"""Join synthetic manifest account metadata to execution results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]


def load_json_object(file_path: Path) -> JsonObject:
    """Load a JSON object from disk."""
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected '{file_path}' to contain a JSON object.")
    return payload


def build_account_review_report_from_files(
    manifest_file: Path,
    results_file: Path,
    account_id: str | None = None,
) -> JsonObject:
    """Build an account report from manifest and run-result files."""
    manifest_payload = load_json_object(manifest_file)
    results_payload = load_json_object(results_file)
    payload = build_account_review_report(
        manifest_payload,
        results_payload,
        account_id=account_id,
    )
    payload["manifestFile"] = str(manifest_file)
    payload["resultsFile"] = str(results_file)
    return payload


def build_account_review_report(
    manifest_payload: JsonObject,
    results_payload: JsonObject,
    account_id: str | None = None,
) -> JsonObject:
    """Join synthetic manifest accounts with scenario run results."""
    requested_account_id = _normalize_str(account_id)
    cases = _read_object_list(manifest_payload, "cases")
    documents = _read_object_list(manifest_payload, "documents")
    results = _index_results_by_document_id(
        _read_object_list(results_payload, "results")
    )

    accounts: list[JsonObject] = []
    for case in cases:
        case_id = _normalize_str(case.get("case_id"))
        if case_id is None:
            continue

        case_documents = [
            document
            for document in documents
            if _normalize_str(document.get("case_id")) == case_id
        ]
        for account in _read_nested_object_list(case, "accounts"):
            normalized_account_id = _normalize_str(account.get("account_id"))
            if normalized_account_id is None:
                continue
            if (
                requested_account_id is not None
                and normalized_account_id != requested_account_id
            ):
                continue

            account_documents = [
                _build_document_record(document, results.get(document["document_id"]))
                for document in case_documents
                if _document_matches_account(document, normalized_account_id)
                and _normalize_str(document.get("document_id")) is not None
            ]
            account_documents.sort(key=lambda item: str(item["documentId"]))
            accounts.append(
                _build_account_record(
                    account,
                    case,
                    account_documents,
                )
            )

    accounts.sort(key=lambda item: str(item["accountId"]))
    if requested_account_id is not None and not accounts:
        raise ValueError(
            f"Account id '{requested_account_id}' was not found in the manifest."
        )

    return {
        "accountCount": len(accounts),
        "accounts": accounts,
        "generatedAtUtc": manifest_payload.get("generated_at_utc"),
        "resultsKind": _detect_results_kind(results_payload),
        "resultsSummary": _build_results_summary(results_payload),
        "scenarioSet": manifest_payload.get("scenario_set"),
    }


def _build_account_record(
    account: JsonObject,
    case: JsonObject,
    documents: list[JsonObject],
) -> JsonObject:
    review_item_count = sum(1 for document in documents if document["reviewItemFound"])
    return {
        "accountId": _normalize_str(account.get("account_id")),
        "accountNumber": _normalize_str(account.get("account_number")),
        "balanceDue": _normalize_str(account.get("balance_due")),
        "caseId": _normalize_str(case.get("case_id")),
        "customerAlias": _normalize_str(case.get("customer_alias")),
        "debtType": _normalize_str(account.get("debt_type")),
        "documentCount": len(documents),
        "documents": documents,
        "documentsWithResults": sum(
            1 for document in documents if document["resultFound"]
        ),
        "downloadableCount": sum(
            1 for document in documents if document["downloadable"]
        ),
        "entryPoint": _normalize_str(case.get("entry_point")),
        "errorCount": sum(1 for document in documents if document["error"] is not None),
        "intakeDescription": _normalize_str(case.get("intake_description")),
        "issuerName": _normalize_str(account.get("issuer_name")),
        "pendingReviewCount": sum(
            1
            for document in documents
            if document["reviewItemStatus"] == "pending_review"
        ),
        "readyForEnrichmentCount": sum(
            1
            for document in documents
            if document["targetStatus"] == "ready_for_enrichment"
        ),
        "reasonForVisiting": _normalize_str(case.get("reason_for_visiting")),
        "reviewItemCount": review_item_count,
        "source": _normalize_str(case.get("source")),
    }


def _build_document_record(
    document: JsonObject,
    result: JsonObject | None,
) -> JsonObject:
    result_payload = result or {}
    review_item_document_id = _normalize_str(
        result_payload.get("reviewItemDocumentId")
    )
    storage_bridge_document_id = _normalize_str(
        result_payload.get("storageBridgeDocumentId")
    )
    blob_source_uri = _normalize_str(result_payload.get("sourceUri"))
    blob_name = _normalize_str(result_payload.get("blobName"))
    review_item_found = bool(result_payload.get("reviewItemFound")) or (
        review_item_document_id is not None
    )

    if "blobCopied" in result_payload:
        blob_copied = bool(result_payload.get("blobCopied"))
    else:
        blob_copied = blob_source_uri is not None or blob_name is not None

    return {
        "accountCandidates": _normalize_string_list(
            document.get("account_candidates")
        ),
        "blobCopied": blob_copied,
        "blobName": blob_name,
        "blobSourceUri": blob_source_uri,
        "caseId": _normalize_str(document.get("case_id")),
        "contentType": _normalize_str(document.get("content_type")),
        "documentId": _normalize_str(document.get("document_id")),
        "documentPath": _normalize_str(document.get("document_path")),
        "downloadable": blob_source_uri is not None,
        "entryPoint": _normalize_str(document.get("entry_point")),
        "error": _normalize_str(result_payload.get("error")),
        "fileName": _normalize_str(document.get("file_name")),
        "issuerCategory": _normalize_str(document.get("issuer_category")),
        "issuerName": _normalize_str(document.get("issuer_name")),
        "logicalSource": _normalize_str(result_payload.get("logicalSource"))
        or _normalize_str(document.get("source")),
        "originalSourceUri": _normalize_str(document.get("source_uri")),
        "persistedDocumentId": review_item_document_id or storage_bridge_document_id,
        "primaryAccountId": _normalize_str(document.get("primary_account_id")),
        "requestPath": _normalize_str(document.get("request_path")),
        "resultFound": result is not None,
        "reviewItemDocumentId": review_item_document_id,
        "reviewItemFound": review_item_found,
        "reviewItemStatus": _normalize_str(result_payload.get("reviewItemStatus")),
        "runtimeStatus": _normalize_str(result_payload.get("runtimeStatus")),
        "source": _normalize_str(document.get("source")),
        "storageBridgeDocumentId": storage_bridge_document_id,
        "targetStatus": _normalize_str(result_payload.get("targetStatus")),
        "workflowMode": _normalize_str(result_payload.get("workflowMode")),
        "workbookPath": _normalize_str(document.get("workbook_path")),
    }


def _build_results_summary(results_payload: JsonObject) -> JsonObject:
    return {
        "blobCopiedCount": results_payload.get("blobCopiedCount"),
        "containerName": results_payload.get("containerName"),
        "errorCount": results_payload.get("errorCount"),
        "objectPrefix": results_payload.get("objectPrefix"),
        "processedCount": results_payload.get("processedCount"),
        "requestedCount": results_payload.get("requestedCount"),
        "reviewItemCount": results_payload.get("reviewItemCount"),
        "storageAccountName": results_payload.get("storageAccountName"),
    }


def _detect_results_kind(results_payload: JsonObject) -> str:
    if "objectPrefix" in results_payload:
        return "aws_bridge"
    if "blobPrefix" in results_payload:
        return "storage_backed"
    return "unknown"


def _document_matches_account(document: JsonObject, account_id: str) -> bool:
    primary_account_id = _normalize_str(document.get("primary_account_id"))
    if primary_account_id is not None:
        return primary_account_id == account_id

    return account_id in _normalize_string_list(document.get("account_candidates"))


def _index_results_by_document_id(results: list[JsonObject]) -> dict[str, JsonObject]:
    indexed_results: dict[str, JsonObject] = {}
    for result in results:
        document_id = _normalize_str(result.get("documentId"))
        if document_id is not None:
            indexed_results[document_id] = result
    return indexed_results


def _normalize_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized_value = str(value).strip()
    return normalized_value or None


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    normalized_values: list[str] = []
    for item in value:
        normalized_item = _normalize_str(item)
        if normalized_item is not None:
            normalized_values.append(normalized_item)
    return normalized_values


def _read_nested_object_list(payload: JsonObject, key: str) -> list[JsonObject]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _read_object_list(payload: JsonObject, key: str) -> list[JsonObject]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"Expected '{key}' to contain a JSON array.")
    return [item for item in value if isinstance(item, dict)]
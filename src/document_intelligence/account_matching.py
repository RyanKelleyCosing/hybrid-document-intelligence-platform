"""Azure SQL account matching and fuzzy ranking helpers."""

from __future__ import annotations

from collections.abc import Mapping
from difflib import SequenceMatcher
from typing import Any

from document_intelligence.models import (
    AccountMatchCandidate,
    AccountMatchResult,
    AccountMatchStatus,
    DocumentAnalysisResult,
    DocumentIngestionRequest,
)
from document_intelligence.settings import AppSettings
from document_intelligence.utils.sql import open_sql_connection


def normalize_match_text(value: str | None) -> str:
    """Normalize text for fuzzy comparisons."""
    if not value:
        return ""

    characters = [
        character.lower() if character.isalnum() else " "
        for character in value
    ]
    return " ".join("".join(characters).split())


def similarity_score(left: str | None, right: str | None) -> float:
    """Return a fuzzy similarity score between two strings."""
    normalized_left = normalize_match_text(left)
    normalized_right = normalize_match_text(right)
    if not normalized_left or not normalized_right:
        return 0.0

    similarity = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    return round(similarity * 100, 2)


def get_field_value(extraction: DocumentAnalysisResult, field_name: str) -> str | None:
    """Return the first extracted field value that matches a logical field name."""
    for field in extraction.extracted_fields:
        if field.name == field_name:
            return field.value
    return None


def build_search_terms(
    request: DocumentIngestionRequest,
    extraction: DocumentAnalysisResult,
    *,
    matching_path: str | None = None,
) -> dict[str, str]:
    """Build the search terms used for Azure SQL account lookup."""
    search_terms = {
        "account_number": get_field_value(extraction, "account_number")
        or get_field_value(extraction, "account_reference")
        or "",
        "debtor_name": get_field_value(extraction, "debtor_name")
        or get_field_value(extraction, "account_holder")
        or get_field_value(extraction, "patient_name")
        or "",
        "issuer_name": request.issuer_name
        or get_field_value(extraction, "issuer_name")
        or "",
    }

    if matching_path == "account_number_lookup":
        allowed_keys = {"account_number", "issuer_name"}
    elif matching_path == "party_name_lookup":
        allowed_keys = {"debtor_name", "issuer_name"}
    else:
        allowed_keys = set(search_terms)

    return {
        key: value
        for key, value in search_terms.items()
        if key in allowed_keys and value
    }


def resolve_fallback_match_result(
    request: DocumentIngestionRequest,
) -> AccountMatchResult:
    """Resolve the match result when only request-level hints are available."""

    fallback_candidates = build_fallback_candidates(request)
    if not fallback_candidates:
        return AccountMatchResult(
            rationale=(
                "No SQL candidates or request-level account hints were available."
            ),
            status=AccountMatchStatus.UNMATCHED,
        )

    if len(fallback_candidates) == 1:
        selected_candidate = fallback_candidates[0]
        return AccountMatchResult(
            candidates=fallback_candidates,
            rationale="Used the single request-level account candidate.",
            selected_account_id=selected_candidate.account_id,
            status=AccountMatchStatus.MATCHED,
        )

    return AccountMatchResult(
        candidates=fallback_candidates,
        rationale="Multiple request-level account candidates need manual review.",
        status=AccountMatchStatus.AMBIGUOUS,
    )


def build_sql_query(
    search_terms: dict[str, str],
    table_name: str,
    top_n: int,
) -> tuple[str, tuple[str, ...]]:
    """Build the SQL query and parameters for account lookup."""
    clauses: list[str] = []
    parameters: list[str] = []

    account_number = search_terms.get("account_number")
    debtor_name = search_terms.get("debtor_name")
    issuer_name = search_terms.get("issuer_name")

    if account_number:
        clauses.append("accountNumber = %s")
        parameters.append(account_number)
    if debtor_name:
        clauses.append("debtorName LIKE %s")
        parameters.append(f"%{debtor_name}%")
    if issuer_name:
        clauses.append("issuerName LIKE %s")
        parameters.append(f"%{issuer_name}%")

    if not clauses:
        return "", ()

    query = (
        f"SELECT TOP {top_n} accountId, accountNumber, debtorName, issuerName "
        f"FROM {table_name} WHERE {' OR '.join(clauses)}"
    )
    return query, tuple(parameters)


def get_row_value(row: Mapping[str, Any], *candidate_keys: str) -> str | None:
    """Return the first matching row value for the supplied keys."""
    for candidate_key in candidate_keys:
        for key, value in row.items():
            if key.lower() == candidate_key.lower() and value is not None:
                return str(value)
    return None


def score_candidate(
    row: Mapping[str, Any],
    search_terms: Mapping[str, str],
    existing_candidate_ids: set[str],
) -> AccountMatchCandidate:
    """Score a candidate account row against extracted search terms."""
    account_id = get_row_value(row, "accountId", "account_id") or "unknown-account"
    account_number = get_row_value(row, "accountNumber", "account_number")
    debtor_name = get_row_value(row, "debtorName", "debtor_name")
    issuer_name = get_row_value(row, "issuerName", "issuer_name")

    matched_on: list[str] = []
    score = 0.0

    if account_number and search_terms.get("account_number"):
        if normalize_match_text(account_number) == normalize_match_text(
            search_terms["account_number"]
        ):
            score += 70.0
            matched_on.append("account_number_exact")

    debtor_score = similarity_score(debtor_name, search_terms.get("debtor_name"))
    if debtor_score >= 80.0:
        score += 20.0
        matched_on.append("debtor_name_fuzzy")

    issuer_score = similarity_score(issuer_name, search_terms.get("issuer_name"))
    if issuer_score >= 75.0:
        score += 15.0
        matched_on.append("issuer_name_fuzzy")

    if account_id in existing_candidate_ids:
        score += 10.0
        matched_on.append("request_candidate_hint")

    return AccountMatchCandidate(
        account_id=account_id,
        account_number=account_number,
        debtor_name=debtor_name,
        issuer_name=issuer_name,
        matched_on=tuple(matched_on),
        score=min(score, 100.0),
    )


def build_fallback_candidates(
    request: DocumentIngestionRequest,
) -> tuple[AccountMatchCandidate, ...]:
    """Build fallback candidates from request hints when Azure SQL is absent."""
    fallback_candidates = []
    for account_candidate in request.account_candidates:
        fallback_candidates.append(
            AccountMatchCandidate(
                account_id=account_candidate,
                matched_on=("request_candidate_hint",),
                score=55.0 if len(request.account_candidates) == 1 else 45.0,
            )
        )
    return tuple(fallback_candidates)


def rank_candidates(
    candidate_rows: tuple[Mapping[str, Any], ...],
    search_terms: Mapping[str, str],
    existing_candidate_ids: set[str],
) -> tuple[AccountMatchCandidate, ...]:
    """Rank Azure SQL account candidates by match score."""
    ranked_candidates = [
        score_candidate(row, search_terms, existing_candidate_ids)
        for row in candidate_rows
    ]
    return tuple(
        sorted(
            ranked_candidates,
            key=lambda candidate: candidate.score,
            reverse=True,
        )
    )


def query_account_master(
    settings: AppSettings,
    search_terms: dict[str, str],
) -> tuple[dict[str, Any], ...]:
    """Query Azure SQL for candidate account rows."""
    if not settings.sql_connection_string:
        return ()

    query, parameters = build_sql_query(
        search_terms,
        settings.sql_account_table_name,
        settings.sql_lookup_top_n,
    )
    if not query:
        return ()

    with open_sql_connection(
        settings.sql_connection_string,
        autocommit=True,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            columns = [column[0] for column in cursor.description]
            rows = [
                dict(zip(columns, row, strict=False))
                for row in cursor.fetchall()
            ]

    return tuple(rows)


def match_document_to_account(
    request: DocumentIngestionRequest,
    extraction: DocumentAnalysisResult,
    settings: AppSettings,
    *,
    matching_path: str | None = None,
) -> AccountMatchResult:
    """Match an extracted document to the account master data in Azure SQL."""
    if matching_path == "request_candidate_hints":
        return resolve_fallback_match_result(request)

    search_terms = build_search_terms(
        request,
        extraction,
        matching_path=matching_path,
    )
    existing_candidate_ids = set(request.account_candidates)
    sql_rows = query_account_master(settings, search_terms)
    ranked_candidates = rank_candidates(sql_rows, search_terms, existing_candidate_ids)

    if not ranked_candidates:
        return resolve_fallback_match_result(request)

    top_candidate = ranked_candidates[0]
    second_score = ranked_candidates[1].score if len(ranked_candidates) > 1 else 0.0

    if top_candidate.score < 55.0:
        return AccountMatchResult(
            candidates=ranked_candidates,
            rationale="SQL candidates were found, but confidence was too low.",
            status=AccountMatchStatus.UNMATCHED,
        )

    if len(ranked_candidates) > 1 and top_candidate.score - second_score < 10.0:
        return AccountMatchResult(
            candidates=ranked_candidates,
            rationale="Multiple SQL candidates scored too closely to auto-link.",
            status=AccountMatchStatus.AMBIGUOUS,
        )

    return AccountMatchResult(
        candidates=ranked_candidates,
        rationale="Matched to the highest-ranked Azure SQL account candidate.",
        selected_account_id=top_candidate.account_id,
        status=AccountMatchStatus.MATCHED,
    )
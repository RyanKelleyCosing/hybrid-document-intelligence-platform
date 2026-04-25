"""Recommendation review helpers for the Epic 3 operator shell."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from document_intelligence.models import (
    AuditEventRecord,
    PacketRecommendationReviewRequest,
    PacketRecommendationReviewResponse,
    RecommendationDisposition,
    RecommendationResultRecord,
)
from document_intelligence.operator_state import SqlOperatorStateRepository
from document_intelligence.safety import mask_history_payload
from document_intelligence.settings import AppSettings
from document_intelligence.utils.sql import open_sql_connection


class PacketRecommendationReviewConfigurationError(RuntimeError):
    """Raised when recommendation review actions cannot run."""


def _resolve_recommendation_result(
    packet_id: str,
    recommendation_result_id: str,
    settings: AppSettings,
) -> RecommendationResultRecord:
    """Return one stored recommendation result for the packet."""

    repository = SqlOperatorStateRepository(settings)
    if not repository.is_configured():
        raise PacketRecommendationReviewConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    snapshot = repository.get_packet_workspace_snapshot(packet_id)
    for recommendation_result in snapshot.recommendation_results:
        if recommendation_result.recommendation_result_id == recommendation_result_id:
            return recommendation_result

    raise RuntimeError(
        f"Recommendation result '{recommendation_result_id}' could not be loaded."
    )


def _insert_packet_event(
    cursor: Any,
    *,
    document_id: str | None,
    event_payload: dict[str, Any],
    event_type: str,
    packet_id: str,
) -> None:
    """Append one packet event row."""

    cursor.execute(
        """
        INSERT INTO dbo.PacketEvents (
            packetId,
            documentId,
            eventType,
            eventPayloadJson,
            createdAtUtc
        )
        VALUES (%s, %s, %s, %s, SYSUTCDATETIME())
        """,
        (packet_id, document_id, event_type, json.dumps(event_payload)),
    )


def _insert_audit_event(cursor: Any, *, event: AuditEventRecord) -> None:
    """Append one audit event row."""

    cursor.execute(
        """
        INSERT INTO dbo.AuditEvents (
            actorUserId,
            actorEmail,
            packetId,
            documentId,
            reviewTaskId,
            eventType,
            eventPayloadJson,
            createdAtUtc
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            event.actor_user_id,
            event.actor_email,
            event.packet_id,
            event.document_id,
            event.review_task_id,
            event.event_type,
            json.dumps(event.event_payload or {}),
            event.created_at_utc,
        ),
    )


def review_packet_recommendation(
    packet_id: str,
    recommendation_result_id: str,
    request: PacketRecommendationReviewRequest,
    settings: AppSettings,
) -> PacketRecommendationReviewResponse:
    """Approve or reject one stored recommendation result."""

    existing_result = _resolve_recommendation_result(
        packet_id,
        recommendation_result_id,
        settings,
    )
    if existing_result.disposition != RecommendationDisposition.PENDING:
        raise RuntimeError(
            f"Recommendation result '{recommendation_result_id}' already has a "
            "recorded disposition."
        )

    reviewed_at_utc = datetime.now(UTC)
    reviewed_result = existing_result.model_copy(
        update={
            "disposition": request.disposition,
            "reviewed_at_utc": reviewed_at_utc,
            "reviewed_by_email": request.reviewed_by_email,
            "reviewed_by_user_id": request.reviewed_by_user_id,
            "updated_at_utc": reviewed_at_utc,
        }
    )
    audit_event = AuditEventRecord(
        audit_event_id=1,
        actor_user_id=request.reviewed_by_user_id,
        actor_email=request.reviewed_by_email,
        packet_id=packet_id,
        document_id=reviewed_result.document_id,
        review_task_id=None,
        event_type="recommendation.review.recorded",
        event_payload=(
            mask_history_payload(
                {
                    "disposition": reviewed_result.disposition.value,
                    "priorDisposition": existing_result.disposition.value,
                    "recommendationKind": reviewed_result.recommendation_kind,
                    "recommendationResultId": reviewed_result.recommendation_result_id,
                },
                retention_class="recommendation_history",
            )
            if settings.mask_sensitive_history
            else {
                "disposition": reviewed_result.disposition.value,
                "priorDisposition": existing_result.disposition.value,
                "recommendationKind": reviewed_result.recommendation_kind,
                "recommendationResultId": reviewed_result.recommendation_result_id,
            }
        ),
        created_at_utc=reviewed_at_utc,
    )
    connection_string = settings.sql_connection_string
    if not connection_string:
        raise PacketRecommendationReviewConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    with open_sql_connection(connection_string, autocommit=False) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE dbo.RecommendationResults
                    SET
                        disposition = %s,
                        reviewedByUserId = %s,
                        reviewedByEmail = %s,
                        reviewedAtUtc = %s,
                        updatedAtUtc = %s
                    WHERE recommendationResultId = %s
                    """,
                    (
                        reviewed_result.disposition.value,
                        reviewed_result.reviewed_by_user_id,
                        reviewed_result.reviewed_by_email,
                        reviewed_result.reviewed_at_utc,
                        reviewed_result.updated_at_utc,
                        reviewed_result.recommendation_result_id,
                    ),
                )
                _insert_packet_event(
                    cursor,
                    document_id=reviewed_result.document_id,
                    event_payload={
                        "disposition": reviewed_result.disposition.value,
                        "recommendationKind": reviewed_result.recommendation_kind,
                        "recommendationResultId": reviewed_result.recommendation_result_id,
                    },
                    event_type="document.recommendation.reviewed",
                    packet_id=packet_id,
                )
                _insert_audit_event(cursor, event=audit_event)

            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return PacketRecommendationReviewResponse(
        packet_id=packet_id,
        recommendation_result=reviewed_result,
    )

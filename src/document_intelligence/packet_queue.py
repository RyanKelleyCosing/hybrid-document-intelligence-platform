"""Packet queue list helpers for the Epic 3 operator shell."""

from __future__ import annotations

from document_intelligence.models import PacketQueueListRequest, PacketQueueListResponse
from document_intelligence.operator_state import SqlOperatorStateRepository
from document_intelligence.processing_taxonomy import get_statuses_for_stage
from document_intelligence.settings import AppSettings


class PacketQueueConfigurationError(RuntimeError):
    """Raised when the packet queue cannot run against the current environment."""


def list_packet_queue(
    request: PacketQueueListRequest,
    settings: AppSettings,
) -> PacketQueueListResponse:
    """Return the paged operator packet queue from Azure SQL."""

    repository = SqlOperatorStateRepository(settings)
    if not repository.is_configured():
        raise PacketQueueConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    stage_statuses = (
        get_statuses_for_stage(request.stage_name)
        if request.stage_name is not None
        else ()
    )
    return repository.list_packet_queue(request, stage_statuses=stage_statuses)
"""Canonical packet-processing taxonomy exposed to operator APIs and UI."""

from __future__ import annotations

from document_intelligence.models import (
    PacketStatus,
    PacketStatusCategory,
    PacketStatusDefinition,
    ProcessingStageDefinition,
    ProcessingStageName,
    ProcessingTaxonomyResponse,
)

_STATUS_DEFINITIONS: tuple[PacketStatusDefinition, ...] = (
    PacketStatusDefinition(
        status=PacketStatus.RECEIVED,
        display_name="Received",
        description="The packet has been accepted and is waiting for pipeline work.",
        category=PacketStatusCategory.WAITING,
        stage_name=ProcessingStageName.INTAKE,
    ),
    PacketStatusDefinition(
        status=PacketStatus.ARCHIVE_EXPANDING,
        display_name="Archive expanding",
        description=(
            "The packet is being inspected and expanded from an archive "
            "envelope."
        ),
        category=PacketStatusCategory.ACTIVE,
        stage_name=ProcessingStageName.ARCHIVE_EXPANSION,
    ),
    PacketStatusDefinition(
        status=PacketStatus.CLASSIFYING,
        display_name="Classifying",
        description=(
            "The platform is determining the document type and downstream "
            "routing hints."
        ),
        category=PacketStatusCategory.ACTIVE,
        stage_name=ProcessingStageName.CLASSIFICATION,
    ),
    PacketStatusDefinition(
        status=PacketStatus.OCR_RUNNING,
        display_name="OCR running",
        description=(
            "OCR is running to produce text and page-level structure for the "
            "packet."
        ),
        category=PacketStatusCategory.ACTIVE,
        stage_name=ProcessingStageName.OCR,
    ),
    PacketStatusDefinition(
        status=PacketStatus.EXTRACTING,
        display_name="Extracting",
        description=(
            "Extraction is generating structured fields from the packet "
            "content."
        ),
        category=PacketStatusCategory.ACTIVE,
        stage_name=ProcessingStageName.EXTRACTION,
    ),
    PacketStatusDefinition(
        status=PacketStatus.MATCHING,
        display_name="Matching",
        description="Account and business-entity matching is in progress.",
        category=PacketStatusCategory.ACTIVE,
        stage_name=ProcessingStageName.MATCHING,
    ),
    PacketStatusDefinition(
        status=PacketStatus.AWAITING_REVIEW,
        display_name="Awaiting review",
        description="The packet needs operator review before work can continue.",
        category=PacketStatusCategory.WAITING,
        operator_attention_required=True,
        stage_name=ProcessingStageName.REVIEW,
    ),
    PacketStatusDefinition(
        status=PacketStatus.READY_FOR_RECOMMENDATION,
        display_name="Ready for recommendation",
        description=(
            "The packet has enough reviewed evidence for recommendation "
            "generation."
        ),
        category=PacketStatusCategory.WAITING,
        stage_name=ProcessingStageName.RECOMMENDATION,
    ),
    PacketStatusDefinition(
        status=PacketStatus.COMPLETED,
        display_name="Completed",
        description="All required packet work is finished.",
        category=PacketStatusCategory.TERMINAL,
        stage_name=ProcessingStageName.RECOMMENDATION,
        terminal=True,
    ),
    PacketStatusDefinition(
        status=PacketStatus.BLOCKED,
        display_name="Blocked",
        description=(
            "The packet cannot proceed until an operator resolves the "
            "blocking issue."
        ),
        category=PacketStatusCategory.WAITING,
        operator_attention_required=True,
        stage_name=ProcessingStageName.REVIEW,
    ),
    PacketStatusDefinition(
        status=PacketStatus.FAILED,
        display_name="Failed",
        description="A pipeline stage failed and requires investigation or retry.",
        category=PacketStatusCategory.TERMINAL,
        operator_attention_required=True,
        stage_name=ProcessingStageName.REVIEW,
        terminal=True,
    ),
    PacketStatusDefinition(
        status=PacketStatus.QUARANTINED,
        display_name="Quarantined",
        description=(
            "The packet has been isolated because it is unsafe, corrupt, or "
            "unsupported."
        ),
        category=PacketStatusCategory.TERMINAL,
        operator_attention_required=True,
        stage_name=ProcessingStageName.QUARANTINE,
        terminal=True,
    ),
)

_STAGE_DEFINITIONS: tuple[ProcessingStageDefinition, ...] = (
    ProcessingStageDefinition(
        stage_name=ProcessingStageName.INTAKE,
        display_name="Intake",
        description="Accept inbound packets and persist their initial packet metadata.",
        statuses=(PacketStatus.RECEIVED,),
    ),
    ProcessingStageDefinition(
        stage_name=ProcessingStageName.ARCHIVE_EXPANSION,
        display_name="Archive expansion",
        description=(
            "Open archive packets and materialize their child documents "
            "safely."
        ),
        statuses=(PacketStatus.ARCHIVE_EXPANDING, PacketStatus.QUARANTINED),
    ),
    ProcessingStageDefinition(
        stage_name=ProcessingStageName.CLASSIFICATION,
        display_name="Classification",
        description=(
            "Classify the document set before downstream extraction and "
            "routing."
        ),
        statuses=(PacketStatus.CLASSIFYING,),
    ),
    ProcessingStageDefinition(
        stage_name=ProcessingStageName.OCR,
        display_name="OCR",
        description="Generate OCR text and page structure for the packet.",
        statuses=(PacketStatus.OCR_RUNNING,),
    ),
    ProcessingStageDefinition(
        stage_name=ProcessingStageName.EXTRACTION,
        display_name="Extraction",
        description="Extract structured fields and evidence from the packet content.",
        statuses=(PacketStatus.EXTRACTING,),
    ),
    ProcessingStageDefinition(
        stage_name=ProcessingStageName.MATCHING,
        display_name="Matching",
        description="Resolve account and entity matches using extracted evidence.",
        statuses=(PacketStatus.MATCHING,),
    ),
    ProcessingStageDefinition(
        stage_name=ProcessingStageName.REVIEW,
        display_name="Review",
        description="Hold packets for operator review, blockers, and retry decisions.",
        statuses=(
            PacketStatus.AWAITING_REVIEW,
            PacketStatus.BLOCKED,
            PacketStatus.FAILED,
        ),
    ),
    ProcessingStageDefinition(
        stage_name=ProcessingStageName.RECOMMENDATION,
        display_name="Recommendation",
        description="Prepare and finalize operator-reviewed recommendation outputs.",
        statuses=(
            PacketStatus.READY_FOR_RECOMMENDATION,
            PacketStatus.COMPLETED,
        ),
    ),
    ProcessingStageDefinition(
        stage_name=ProcessingStageName.QUARANTINE,
        display_name="Quarantine",
        description=(
            "Isolate unsupported or unsafe packets for explicit operator "
            "handling."
        ),
        statuses=(PacketStatus.QUARANTINED,),
    ),
)

_STATUS_TO_STAGE_NAME = {
    definition.status: definition.stage_name for definition in _STATUS_DEFINITIONS
}
_STAGE_TO_STATUSES = {
    definition.stage_name: definition.statuses for definition in _STAGE_DEFINITIONS
}


def get_processing_taxonomy() -> ProcessingTaxonomyResponse:
    """Return the canonical packet-processing taxonomy for operator clients."""

    return ProcessingTaxonomyResponse(
        stages=_STAGE_DEFINITIONS,
        statuses=_STATUS_DEFINITIONS,
    )


def get_stage_name_for_status(status: PacketStatus) -> ProcessingStageName:
    """Return the canonical stage name for one packet status."""

    return _STATUS_TO_STAGE_NAME[status]


def get_statuses_for_stage(
    stage_name: ProcessingStageName,
) -> tuple[PacketStatus, ...]:
    """Return the packet statuses grouped under one processing stage."""

    return _STAGE_TO_STATUSES.get(stage_name, ())
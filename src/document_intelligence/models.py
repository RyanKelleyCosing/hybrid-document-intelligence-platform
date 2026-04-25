"""Pydantic models shared across the backend workflow and review app."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class DocumentSource(StrEnum):
    """Known ingestion sources for the MVP."""

    AZURE_BLOB = "azure_blob"
    AZURE_SFTP = "azure_sftp"
    CONFIGURED_FOLDER = "configured_folder"
    EMAIL_CONNECTOR = "email_connector"
    AWS_S3 = "aws_s3"
    PARTNER_API_FEED = "partner_api_feed"
    SCANNED_UPLOAD = "scanned_upload"


class IssuerCategory(StrEnum):
    """Issuer families that influence extraction strategy."""

    UNKNOWN = "unknown"
    BANK = "bank"
    COLLECTION_AGENCY = "collection_agency"
    COURT = "court"
    GOVERNMENT = "government"
    HEALTHCARE_PROVIDER = "healthcare_provider"
    LAW_FIRM = "law_firm"
    UTILITY_PROVIDER = "utility_provider"


class PromptProfileId(StrEnum):
    """Source-aware prompt profiles used to steer extraction."""

    BANK_STATEMENT = "bank_statement"
    COLLECTION_NOTICE = "collection_notice"
    COURT_FILING = "court_filing"
    GENERIC_CORRESPONDENCE = "generic_correspondence"
    GOVERNMENT_NOTICE = "government_notice"
    HEALTHCARE_BILL = "healthcare_bill"
    LAW_FIRM_CORRESPONDENCE = "law_firm_correspondence"
    UTILITY_BILL = "utility_bill"


class ProfileSelectionMode(StrEnum):
    """How the prompt profile was selected."""

    EXPLICIT = "explicit"
    FALLBACK = "fallback"
    HEURISTIC = "heuristic"


class ReviewStatus(StrEnum):
    """Workflow states used by persisted review items."""

    APPROVED = "approved"
    PENDING_REVIEW = "pending_review"
    READY_FOR_ENRICHMENT = "ready_for_enrichment"
    REJECTED = "rejected"
    REPROCESS_REQUESTED = "reprocess_requested"


class AccountMatchStatus(StrEnum):
    """Matching outcomes for an account lookup attempt."""

    AMBIGUOUS = "ambiguous"
    MATCHED = "matched"
    UNMATCHED = "unmatched"


class ReviewReason(StrEnum):
    """Reasons a document requires manual intervention."""

    CLASSIFICATION_DRIFT = "classification_drift"
    CONFLICTING_PACKET_EVIDENCE = "conflicting_packet_evidence"
    HALLUCINATED_RECOMMENDATION_FIELD = "hallucinated_recommendation_field"
    LOW_CONFIDENCE = "low_confidence"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    MIXED_CONTENT_PACKET = "mixed_content_packet"
    MULTIPLE_ACCOUNT_CANDIDATES = "multiple_account_candidates"
    OCR_QUALITY_WARNING = "ocr_quality_warning"
    RECOMMENDATION_GUARDRAIL = "recommendation_guardrail"
    UNSEEN_DOCUMENT_TYPE = "unseen_document_type"
    UNMATCHED_ACCOUNT = "unmatched_account"


class IntakeSourceKind(StrEnum):
    """Supported operator-configured intake-source types."""

    CONFIGURED_FOLDER = "configured_folder"
    EMAIL_CONNECTOR = "email_connector"
    MANUAL_UPLOAD = "manual_upload"
    PARTNER_API_FEED = "partner_api_feed"
    WATCHED_BLOB_PREFIX = "watched_blob_prefix"
    WATCHED_SFTP_PATH = "watched_sftp_path"


class PacketStatus(StrEnum):
    """States used by packet-level operator workflows."""

    ARCHIVE_EXPANDING = "archive_expanding"
    AWAITING_REVIEW = "awaiting_review"
    BLOCKED = "blocked"
    CLASSIFYING = "classifying"
    COMPLETED = "completed"
    EXTRACTING = "extracting"
    FAILED = "failed"
    MATCHING = "matching"
    OCR_RUNNING = "ocr_running"
    QUARANTINED = "quarantined"
    READY_FOR_RECOMMENDATION = "ready_for_recommendation"
    RECEIVED = "received"


class ProcessingStageName(StrEnum):
    """Named stages in the operator processing pipeline."""

    ARCHIVE_EXPANSION = "archive_expansion"
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    INTAKE = "intake"
    MATCHING = "matching"
    OCR = "ocr"
    QUARANTINE = "quarantine"
    RECOMMENDATION = "recommendation"
    REVIEW = "review"


class SafetyIssueSeverity(StrEnum):
    """Severity applied to pipeline safety issues and guardrails."""

    BLOCKING = "blocking"
    WARNING = "warning"


class SafetyIssue(BaseModel):
    """Structured safety metadata persisted with pipeline events and reviews."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: SafetyIssueSeverity = SafetyIssueSeverity.WARNING
    stage_name: ProcessingStageName | None = None


class ProcessingJobStatus(StrEnum):
    """Statuses used by persisted packet-processing jobs."""

    FAILED = "failed"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"


class ArchivePreflightDisposition(StrEnum):
    """Outcome of archive inspection before downstream processing begins."""

    CORRUPT_ARCHIVE = "corrupt_archive"
    ENCRYPTED_ARCHIVE = "encrypted_archive"
    NOT_ARCHIVE = "not_archive"
    READY_FOR_EXPANSION = "ready_for_expansion"
    UNSAFE_ARCHIVE = "unsafe_archive"
    UNSUPPORTED_ARCHIVE = "unsupported_archive"


class PacketStatusCategory(StrEnum):
    """Categories used to group packet statuses in the operator UI."""

    ACTIVE = "active"
    TERMINAL = "terminal"
    WAITING = "waiting"


class PacketStatusDefinition(BaseModel):
    """Canonical metadata for a supported packet-processing status."""

    category: PacketStatusCategory
    description: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    operator_attention_required: bool = False
    stage_name: ProcessingStageName
    status: PacketStatus
    terminal: bool = False


class ProcessingStageDefinition(BaseModel):
    """Canonical metadata for a named packet-processing stage."""

    description: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    stage_name: ProcessingStageName
    statuses: tuple[PacketStatus, ...] = Field(default_factory=tuple)


class ProcessingTaxonomyResponse(BaseModel):
    """Supported packet statuses and stages used by the operator surfaces."""

    stages: tuple[ProcessingStageDefinition, ...] = Field(default_factory=tuple)
    statuses: tuple[PacketStatusDefinition, ...] = Field(default_factory=tuple)


class ArchivePreflightResult(BaseModel):
    """Archive inspection metadata captured during manual packet intake."""

    archive_format: str | None = None
    disposition: ArchivePreflightDisposition = (
        ArchivePreflightDisposition.NOT_ARCHIVE
    )
    expected_disk_count: int | None = Field(default=None, ge=1)
    entry_count: int = Field(default=0, ge=0)
    is_archive: bool = False
    is_multipart_archive: bool = False
    message: str | None = None
    nested_archive_count: int = Field(default=0, ge=0)
    total_uncompressed_bytes: int = Field(default=0, ge=0)
    uses_zip64: bool = False


class ArchiveDocumentLineage(BaseModel):
    """Relationship metadata linking archive parents to extracted children."""

    archive_depth: int = Field(default=0, ge=0)
    archive_member_path: str | None = None
    parent_document_id: str | None = None
    source_asset_id: str | None = None


class DuplicateSignalType(StrEnum):
    """Signals used to determine whether a packet is a duplicate."""

    ACCOUNT_LINKED_HINT = "account_linked_hint"
    FILE_HASH = "file_hash"
    PACKET_FINGERPRINT = "packet_fingerprint"
    SOURCE_FINGERPRINT = "source_fingerprint"


class DuplicateDetectionStatus(StrEnum):
    """Outcomes for packet idempotency and duplicate inspection."""

    EXACT_DUPLICATE = "exact_duplicate"
    POSSIBLE_DUPLICATE = "possible_duplicate"
    UNIQUE = "unique"


class ClassificationResultSource(StrEnum):
    """Sources that can produce a stored classification result."""

    AI = "ai"
    OPERATOR_CONFIRMED = "operator_confirmed"
    PRIOR_REUSE = "prior_reuse"
    RULE = "rule"


class ReviewTaskPriority(StrEnum):
    """Priority levels used by persisted review tasks."""

    HIGH = "high"
    LOW = "low"
    NORMAL = "normal"
    URGENT = "urgent"


class PacketAssignmentState(StrEnum):
    """Assignment summary states exposed by the packet queue."""

    ASSIGNED = "assigned"
    MIXED = "mixed"
    UNASSIGNED = "unassigned"


class RecommendationRunStatus(StrEnum):
    """Statuses used by persisted recommendation runs."""

    ACCEPTED = "accepted"
    FAILED = "failed"
    QUEUED = "queued"
    READY_FOR_REVIEW = "ready_for_review"
    REJECTED = "rejected"
    RUNNING = "running"


class RecommendationDisposition(StrEnum):
    """Disposition values for stored recommendation results."""

    ACCEPTED = "accepted"
    PENDING = "pending"
    REJECTED = "rejected"


class DuplicateDetectionSignal(BaseModel):
    """A single signal discovered during duplicate inspection."""

    description: str = Field(min_length=1)
    matched_account_id: str | None = None
    matched_document_id: str | None = None
    matched_packet_id: str | None = None
    signal_type: DuplicateSignalType
    signal_value: str | None = None


class DuplicateDetectionResult(BaseModel):
    """The stored duplicate-detection result for a packet intake attempt."""

    reused_existing_packet_id: str | None = None
    should_skip_ingestion: bool = False
    signals: tuple[DuplicateDetectionSignal, ...] = Field(default_factory=tuple)
    status: DuplicateDetectionStatus = DuplicateDetectionStatus.UNIQUE


class ManualUploadSourceConfiguration(BaseModel):
    """Configuration for a manual operator-driven upload source."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_kind: Literal[IntakeSourceKind.MANUAL_UPLOAD] = (
        IntakeSourceKind.MANUAL_UPLOAD
    )
    entry_point_name: str = Field(
        default="operator_portal",
        min_length=1,
        max_length=120,
    )
    max_documents_per_packet: int = Field(default=25, ge=1, le=250)


class WatchedBlobPrefixSourceConfiguration(BaseModel):
    """Configuration for a watched Azure Blob prefix source."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_kind: Literal[IntakeSourceKind.WATCHED_BLOB_PREFIX] = (
        IntakeSourceKind.WATCHED_BLOB_PREFIX
    )
    storage_account_name: str = Field(min_length=1, max_length=120)
    container_name: str = Field(min_length=1, max_length=63)
    blob_prefix: str = Field(min_length=1, max_length=1024)
    include_subdirectories: bool = True


class WatchedSftpPathSourceConfiguration(BaseModel):
    """Configuration for a watched Azure Storage SFTP path source."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_kind: Literal[IntakeSourceKind.WATCHED_SFTP_PATH] = (
        IntakeSourceKind.WATCHED_SFTP_PATH
    )
    storage_account_name: str = Field(min_length=1, max_length=120)
    sftp_path: str = Field(min_length=1, max_length=1024)
    local_user_name: str = Field(min_length=1, max_length=120)


class EmailConnectorSourceConfiguration(BaseModel):
    """Configuration for a polled mailbox or email connector source."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_kind: Literal[IntakeSourceKind.EMAIL_CONNECTOR] = (
        IntakeSourceKind.EMAIL_CONNECTOR
    )
    mailbox_address: str = Field(min_length=3, max_length=320)
    folder_path: str = Field(default="INBOX", min_length=1, max_length=400)
    attachment_extension_allowlist: tuple[str, ...] = Field(default_factory=tuple)


class PartnerApiFeedSourceConfiguration(BaseModel):
    """Configuration for a partner API feed source."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_kind: Literal[IntakeSourceKind.PARTNER_API_FEED] = (
        IntakeSourceKind.PARTNER_API_FEED
    )
    partner_name: str = Field(min_length=1, max_length=200)
    relative_path: str = Field(min_length=1, max_length=400)
    auth_scheme: str = Field(default="api_key", min_length=1, max_length=80)


class ConfiguredFolderSourceConfiguration(BaseModel):
    """Configuration for a watched mounted-share or folder source."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_kind: Literal[IntakeSourceKind.CONFIGURED_FOLDER] = (
        IntakeSourceKind.CONFIGURED_FOLDER
    )
    folder_path: str = Field(min_length=1, max_length=1024)
    file_pattern: str = Field(default="*", min_length=1, max_length=200)
    recursive: bool = False


IntakeSourceConfiguration: TypeAlias = Annotated[
    ManualUploadSourceConfiguration
    | WatchedBlobPrefixSourceConfiguration
    | WatchedSftpPathSourceConfiguration
    | EmailConnectorSourceConfiguration
    | PartnerApiFeedSourceConfiguration
    | ConfiguredFolderSourceConfiguration,
    Field(discriminator="source_kind"),
]

_INTAKE_SOURCE_CONFIGURATION_ADAPTER: TypeAdapter[IntakeSourceConfiguration] = (
    TypeAdapter(IntakeSourceConfiguration)
)


def validate_intake_source_configuration(
    payload: object,
) -> IntakeSourceConfiguration:
    """Validate a persisted or requested intake-source configuration."""

    return _INTAKE_SOURCE_CONFIGURATION_ADAPTER.validate_python(payload)


class ExtractedField(BaseModel):
    """A single extracted field and its confidence score."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    name: str = Field(min_length=1)
    value: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class PromptProfileCandidate(BaseModel):
    """A scored prompt-profile candidate considered during selection."""

    profile_id: PromptProfileId
    issuer_category: IssuerCategory
    rationale: tuple[str, ...] = Field(default_factory=tuple)
    score: int = Field(ge=0)


class PromptProfileSelection(BaseModel):
    """The selected issuer-aware prompt profile."""

    candidate_profiles: tuple[PromptProfileCandidate, ...] = Field(
        default_factory=tuple
    )
    document_type_hints: tuple[str, ...] = Field(default_factory=tuple)
    issuer_category: IssuerCategory
    keyword_hints: tuple[str, ...] = Field(default_factory=tuple)
    primary_profile_id: PromptProfileId
    prompt_focus: tuple[str, ...] = Field(default_factory=tuple)
    selection_mode: ProfileSelectionMode
    system_prompt: str = Field(min_length=1)


class AccountMatchCandidate(BaseModel):
    """A ranked account candidate returned from the account master lookup."""

    account_id: str = Field(min_length=1)
    account_number: str | None = None
    debtor_name: str | None = None
    issuer_name: str | None = None
    matched_on: tuple[str, ...] = Field(default_factory=tuple)
    score: float = Field(ge=0.0, le=100.0)


class AccountMatchResult(BaseModel):
    """The outcome of an account master lookup."""

    candidates: tuple[AccountMatchCandidate, ...] = Field(default_factory=tuple)
    rationale: str | None = None
    selected_account_id: str | None = None
    status: AccountMatchStatus


class DocumentAnalysisResult(BaseModel):
    """The output of OCR plus issuer-aware LLM extraction."""

    document_type: str = Field(min_length=1)
    extracted_fields: tuple[ExtractedField, ...] = Field(default_factory=tuple)
    model_name: str = Field(min_length=1)
    ocr_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ocr_text: str | None = None
    page_count: int = Field(default=0, ge=0)
    prompt_profile: PromptProfileSelection
    provider: str = Field(min_length=1)
    summary: str | None = None
    warnings: tuple[str, ...] = Field(default_factory=tuple)


class DocumentIngestionRequest(BaseModel):
    """Public-safe ingestion request payload used for preview and orchestration."""

    model_config = ConfigDict(str_strip_whitespace=True)

    document_id: str = Field(min_length=1)
    source: DocumentSource
    source_uri: str = Field(min_length=1)
    issuer_name: str | None = None
    issuer_category: IssuerCategory = IssuerCategory.UNKNOWN
    requested_prompt_profile_id: PromptProfileId | None = None
    source_summary: str | None = None
    source_tags: tuple[str, ...] = Field(default_factory=tuple)
    document_content_base64: str | None = None
    document_text: str | None = None
    file_name: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    received_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    extracted_fields: tuple[ExtractedField, ...] = Field(default_factory=tuple)
    account_candidates: tuple[str, ...] = Field(default_factory=tuple)


class ReviewDecision(BaseModel):
    """The outcome of confidence-based routing."""

    requires_manual_review: bool
    reasons: tuple[ReviewReason, ...] = Field(default_factory=tuple)
    average_confidence: float = Field(ge=0.0, le=1.0)
    minimum_confidence: float = Field(ge=0.0, le=1.0)
    missing_required_fields: tuple[str, ...] = Field(default_factory=tuple)


class ReviewQueueItem(BaseModel):
    """Serialized payload expected by the manual review queue."""

    status: ReviewStatus = ReviewStatus.PENDING_REVIEW
    document_id: str
    file_name: str
    source: DocumentSource
    source_uri: str
    issuer_name: str | None = None
    issuer_category: IssuerCategory
    document_type: str | None = None
    account_match: AccountMatchResult | None = None
    selected_account_id: str | None = None
    prompt_profile: PromptProfileSelection
    received_at_utc: datetime
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reviewed_at_utc: datetime | None = None
    reviewer_name: str | None = None
    review_notes: str | None = None
    ocr_text_excerpt: str | None = None
    reasons: tuple[ReviewReason, ...] = Field(default_factory=tuple)
    average_confidence: float = Field(ge=0.0, le=1.0)
    minimum_confidence: float = Field(ge=0.0, le=1.0)
    account_candidates: tuple[str, ...] = Field(default_factory=tuple)
    extracted_fields: tuple[ExtractedField, ...] = Field(default_factory=tuple)


class ReviewDecisionUpdate(BaseModel):
    """Decision payload submitted by a manual reviewer."""

    review_notes: str | None = None
    reviewer_name: str = Field(min_length=1)
    selected_account_id: str | None = None
    status: Literal[
        ReviewStatus.APPROVED,
        ReviewStatus.REJECTED,
        ReviewStatus.REPROCESS_REQUESTED,
    ]


class ReviewItemListResponse(BaseModel):
    """A response wrapper for review-item list APIs."""

    items: tuple[ReviewQueueItem, ...] = Field(default_factory=tuple)


class IngestionWorkflowResult(BaseModel):
    """The result of the end-to-end ingestion workflow."""

    account_match: AccountMatchResult
    document_id: str
    extraction_result: DocumentAnalysisResult
    review_decision: ReviewDecision
    review_item: ReviewQueueItem | None = None
    target_status: ReviewStatus


class ProcessingPreview(BaseModel):
    """Preview payload returned by the current orchestration scaffold."""

    target_status: Literal["pending_review", "ready_for_enrichment"]
    normalized_request: DocumentIngestionRequest
    prompt_profile: PromptProfileSelection
    review_decision: ReviewDecision
    review_item: ReviewQueueItem | None = None


class IntakeSourceCreateRequest(BaseModel):
    """Request payload used to create a durable intake-source definition."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_id: str | None = None
    source_name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    is_enabled: bool = True
    owner_email: str | None = Field(default=None, max_length=320)
    polling_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    credentials_reference: str | None = Field(default=None, max_length=200)
    configuration: IntakeSourceConfiguration


class IntakeSourceUpdateRequest(BaseModel):
    """Request payload used to replace a durable intake-source definition."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    is_enabled: bool = True
    owner_email: str | None = Field(default=None, max_length=320)
    polling_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    credentials_reference: str | None = Field(default=None, max_length=200)
    configuration: IntakeSourceConfiguration


class IntakeSourceEnablementRequest(BaseModel):
    """Request payload used to pause or resume one intake source."""

    is_enabled: bool


class IntakeSourceRecord(BaseModel):
    """Persisted intake-source definition returned by the operator API."""

    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    description: str | None = None
    is_enabled: bool = True
    owner_email: str | None = None
    polling_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    credentials_reference: str | None = None
    configuration: IntakeSourceConfiguration
    last_seen_at_utc: datetime | None = None
    last_success_at_utc: datetime | None = None
    last_error_at_utc: datetime | None = None
    last_error_message: str | None = None
    created_at_utc: datetime
    updated_at_utc: datetime


class IntakeSourceListResponse(BaseModel):
    """A response wrapper for operator intake-source list APIs."""

    items: tuple[IntakeSourceRecord, ...] = Field(default_factory=tuple)


class IntakeSourceDeleteResponse(BaseModel):
    """Summary returned after one intake-source definition is deleted."""

    deleted: bool = True
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)


class IntakeSourceExecutionFailure(BaseModel):
    """One blob candidate that failed during intake-source execution."""

    blob_name: str = Field(min_length=1)
    blob_uri: str = Field(min_length=1)
    message: str = Field(min_length=1)


class IntakeSourceExecutionPacketResult(BaseModel):
    """One packet created or reused by a non-manual intake-source run."""

    blob_name: str = Field(min_length=1)
    blob_uri: str = Field(min_length=1)
    content_length_bytes: int = Field(ge=0)
    content_type: str = Field(min_length=1)
    document_count: int = Field(ge=1)
    duplicate_detection_status: DuplicateDetectionStatus
    idempotency_reused_existing_packet: bool = False
    packet_id: str = Field(min_length=1)
    packet_name: str = Field(min_length=1)
    status: PacketStatus


class IntakeSourceExecutionResponse(BaseModel):
    """Summary returned after one intake source executes against live inputs."""

    executed_at_utc: datetime
    failed_blob_count: int = Field(default=0, ge=0)
    failures: tuple[IntakeSourceExecutionFailure, ...] = Field(default_factory=tuple)
    packet_results: tuple[IntakeSourceExecutionPacketResult, ...] = Field(
        default_factory=tuple
    )
    processed_blob_count: int = Field(default=0, ge=0)
    reused_packet_count: int = Field(default=0, ge=0)
    seen_blob_count: int = Field(default=0, ge=0)
    source_id: str = Field(min_length=1)
    source_kind: IntakeSourceKind
    source_name: str = Field(min_length=1)


class ManagedClassificationDefinitionRecord(BaseModel):
    """A managed classification definition stored in Azure SQL."""

    classification_id: str = Field(min_length=1)
    classification_key: str = Field(min_length=1)
    created_at_utc: datetime
    default_prompt_profile_id: PromptProfileId | None = None
    description: str | None = None
    display_name: str = Field(min_length=1)
    is_enabled: bool = True
    issuer_category: IssuerCategory = IssuerCategory.UNKNOWN
    updated_at_utc: datetime


class ManagedDocumentTypeDefinitionRecord(BaseModel):
    """A managed document-type definition stored in Azure SQL."""

    classification_id: str | None = None
    created_at_utc: datetime
    default_prompt_profile_id: PromptProfileId | None = None
    description: str | None = None
    display_name: str = Field(min_length=1)
    document_type_id: str = Field(min_length=1)
    document_type_key: str = Field(min_length=1)
    is_enabled: bool = True
    required_fields: tuple[str, ...] = Field(default_factory=tuple)
    updated_at_utc: datetime


class ManagedPromptProfileRecord(BaseModel):
    """A managed prompt-profile definition stored in Azure SQL."""

    created_at_utc: datetime
    description: str | None = None
    display_name: str = Field(min_length=1)
    is_enabled: bool = True
    issuer_category: IssuerCategory
    prompt_profile_id: PromptProfileId
    updated_at_utc: datetime


class PromptProfileVersionRecord(BaseModel):
    """A persisted prompt-profile version stored in Azure SQL."""

    created_at_utc: datetime
    definition_payload: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    prompt_profile_id: PromptProfileId
    prompt_profile_version_id: str = Field(min_length=1)
    version_number: int = Field(ge=1)


class RecommendationContractDefinition(BaseModel):
    """The persisted recommendation contract exposed to later UI flows."""

    advisory_only: bool = True
    default_status: RecommendationRunStatus = RecommendationRunStatus.QUEUED
    disposition_values: tuple[RecommendationDisposition, ...] = Field(
        default=(
            RecommendationDisposition.PENDING,
            RecommendationDisposition.ACCEPTED,
            RecommendationDisposition.REJECTED,
        )
    )
    required_evidence_kinds: tuple[str, ...] = Field(
        default=("extracted_field", "ocr_excerpt", "source_document_link")
    )
    conflict_field_names: tuple[str, ...] = Field(
        default=("account_number", "statement_date", "amount_due", "balance")
    )
    guardrail_reason_codes: tuple[str, ...] = Field(
        default=(
            ReviewReason.CONFLICTING_PACKET_EVIDENCE.value,
            ReviewReason.HALLUCINATED_RECOMMENDATION_FIELD.value,
            ReviewReason.MIXED_CONTENT_PACKET.value,
            ReviewReason.RECOMMENDATION_GUARDRAIL.value,
        )
    )
    minimum_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    required_packet_status: PacketStatus = PacketStatus.READY_FOR_RECOMMENDATION
    supported_field_names: tuple[str, ...] = Field(
        default=(
            "account_holder",
            "account_number",
            "account_reference",
            "amount_due",
            "balance",
            "balance_due",
            "bill_date",
            "creditor_name",
            "debtor_name",
            "debt_type",
            "due_date",
            "ending_balance",
            "issuer_name",
            "patient_name",
            "service_address",
            "statement_date",
        )
    )


class OperatorContractsResponse(BaseModel):
    """Canonical operator-state definitions exposed for later app surfaces."""

    classification_definitions: tuple[ManagedClassificationDefinitionRecord, ...] = (
        Field(default_factory=tuple)
    )
    document_type_definitions: tuple[ManagedDocumentTypeDefinitionRecord, ...] = (
        Field(default_factory=tuple)
    )
    processing_taxonomy: ProcessingTaxonomyResponse
    prompt_profile_versions: tuple[PromptProfileVersionRecord, ...] = Field(
        default_factory=tuple
    )
    prompt_profiles: tuple[ManagedPromptProfileRecord, ...] = Field(
        default_factory=tuple
    )
    recommendation_contract: RecommendationContractDefinition


class ManualPacketDocumentInput(BaseModel):
    """A single document uploaded through the operator manual-intake flow."""

    model_config = ConfigDict(str_strip_whitespace=True)

    document_id: str | None = None
    file_name: str = Field(min_length=1, max_length=260)
    content_type: str = Field(min_length=1, max_length=200)
    document_content_base64: str = Field(min_length=1)
    document_text: str | None = None
    issuer_name: str | None = None
    issuer_category: IssuerCategory = IssuerCategory.UNKNOWN
    requested_prompt_profile_id: PromptProfileId | None = None
    source_summary: str | None = None
    source_tags: tuple[str, ...] = Field(default_factory=tuple)
    account_candidates: tuple[str, ...] = Field(default_factory=tuple)


class ManualPacketIntakeRequest(BaseModel):
    """Operator request that stages packet assets into Blob and Azure SQL."""

    model_config = ConfigDict(str_strip_whitespace=True)

    packet_id: str | None = None
    packet_name: str = Field(min_length=1, max_length=200)
    source: DocumentSource = DocumentSource.SCANNED_UPLOAD
    source_uri: str | None = None
    submitted_by: str | None = None
    packet_tags: tuple[str, ...] = Field(default_factory=tuple)
    received_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    documents: tuple[ManualPacketDocumentInput, ...] = Field(
        default_factory=tuple,
        min_length=1,
        max_length=25,
    )


class SourcePacketIngestionRequest(BaseModel):
    """Packet payload submitted by one source-managed push integration."""

    model_config = ConfigDict(str_strip_whitespace=True)

    packet_id: str | None = None
    packet_name: str = Field(min_length=1, max_length=200)
    source_uri: str | None = None
    submitted_by: str | None = None
    packet_tags: tuple[str, ...] = Field(default_factory=tuple)
    received_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    documents: tuple[ManualPacketDocumentInput, ...] = Field(
        default_factory=tuple,
        min_length=1,
        max_length=25,
    )


class ManualPacketStagedDocument(BaseModel):
    """Metadata for a staged manual-intake document asset."""

    asset_role: str = Field(default="original_upload", min_length=1)
    archive_preflight: ArchivePreflightResult = Field(
        default_factory=ArchivePreflightResult
    )
    safety_issues: tuple[SafetyIssue, ...] = Field(default_factory=tuple)
    document_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    lineage: ArchiveDocumentLineage = Field(
        default_factory=ArchiveDocumentLineage
    )
    blob_container_name: str = Field(min_length=1)
    blob_name: str = Field(min_length=1)
    blob_uri: str = Field(min_length=1)
    content_length_bytes: int = Field(ge=1)
    file_hash_sha256: str = Field(min_length=64, max_length=64)
    initial_processing_job_status: ProcessingJobStatus = ProcessingJobStatus.QUEUED
    initial_processing_stage: ProcessingStageName = ProcessingStageName.OCR
    issuer_name: str | None = None
    issuer_category: IssuerCategory = IssuerCategory.UNKNOWN
    requested_prompt_profile_id: PromptProfileId | None = None
    source_summary: str | None = None
    source_tags: tuple[str, ...] = Field(default_factory=tuple)
    account_candidates: tuple[str, ...] = Field(default_factory=tuple)
    document_text: str | None = None
    source_uri: str | None = None
    status: PacketStatus = PacketStatus.RECEIVED


class ManualPacketDocumentRecord(BaseModel):
    """Created-state details for a staged packet document."""

    archive_preflight: ArchivePreflightResult = Field(
        default_factory=ArchivePreflightResult
    )
    document_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    blob_uri: str = Field(min_length=1)
    file_hash_sha256: str = Field(min_length=64, max_length=64)
    lineage: ArchiveDocumentLineage = Field(
        default_factory=ArchiveDocumentLineage
    )
    processing_job_id: str = Field(min_length=1)
    processing_stage: ProcessingStageName = ProcessingStageName.OCR
    processing_job_status: ProcessingJobStatus = ProcessingJobStatus.QUEUED
    review_task_id: str | None = None
    status: PacketStatus = PacketStatus.RECEIVED


class ManualPacketIntakeResponse(BaseModel):
    """Response returned after a packet is staged for downstream processing."""

    packet_id: str = Field(min_length=1)
    packet_name: str = Field(min_length=1)
    source: DocumentSource
    source_uri: str = Field(min_length=1)
    submitted_by: str | None = None
    packet_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)
    source_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)
    status: PacketStatus = PacketStatus.RECEIVED
    next_stage: ProcessingStageName = ProcessingStageName.OCR
    document_count: int = Field(ge=1)
    duplicate_detection: DuplicateDetectionResult = Field(
        default_factory=DuplicateDetectionResult
    )
    idempotency_reused_existing_packet: bool = False
    received_at_utc: datetime
    documents: tuple[ManualPacketDocumentRecord, ...] = Field(default_factory=tuple)


class PacketRecord(BaseModel):
    """A persisted operator packet record."""

    created_at_utc: datetime
    duplicate_detection: DuplicateDetectionResult = Field(
        default_factory=DuplicateDetectionResult
    )
    duplicate_of_packet_id: str | None = None
    packet_fingerprint: str | None = None
    packet_id: str = Field(min_length=1)
    packet_name: str = Field(min_length=1)
    packet_tags: tuple[str, ...] = Field(default_factory=tuple)
    received_at_utc: datetime
    source: DocumentSource
    source_fingerprint: str | None = None
    source_uri: str | None = None
    status: PacketStatus
    submitted_by: str | None = None
    updated_at_utc: datetime


class PacketDocumentRecord(BaseModel):
    """A persisted packet-document record."""

    account_candidates: tuple[str, ...] = Field(default_factory=tuple)
    archive_preflight: ArchivePreflightResult = Field(
        default_factory=ArchivePreflightResult
    )
    content_type: str = Field(min_length=1)
    created_at_utc: datetime
    document_id: str = Field(min_length=1)
    document_text: str | None = None
    file_hash_sha256: str | None = None
    file_name: str = Field(min_length=1)
    issuer_category: IssuerCategory = IssuerCategory.UNKNOWN
    issuer_name: str | None = None
    lineage: ArchiveDocumentLineage = Field(
        default_factory=ArchiveDocumentLineage
    )
    packet_id: str = Field(min_length=1)
    received_at_utc: datetime
    requested_prompt_profile_id: PromptProfileId | None = None
    source: DocumentSource
    source_summary: str | None = None
    source_tags: tuple[str, ...] = Field(default_factory=tuple)
    source_uri: str | None = None
    status: PacketStatus
    updated_at_utc: datetime


class DocumentAssetRecord(BaseModel):
    """A persisted document-asset record."""

    asset_id: str = Field(min_length=1)
    asset_role: str = Field(min_length=1)
    blob_name: str = Field(min_length=1)
    container_name: str = Field(min_length=1)
    content_length_bytes: int = Field(ge=0)
    content_type: str = Field(min_length=1)
    created_at_utc: datetime
    document_id: str = Field(min_length=1)
    packet_id: str = Field(min_length=1)
    storage_uri: str = Field(min_length=1)


class PacketEventRecord(BaseModel):
    """A persisted packet event."""

    created_at_utc: datetime
    document_id: str | None = None
    event_id: int = Field(ge=1)
    event_payload: dict[str, Any] | None = None
    event_type: str = Field(min_length=1)
    packet_id: str = Field(min_length=1)


class ProcessingJobRecord(BaseModel):
    """A persisted packet-processing job."""

    attempt_number: int = Field(ge=1)
    completed_at_utc: datetime | None = None
    created_at_utc: datetime
    document_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    job_id: str = Field(min_length=1)
    packet_id: str = Field(min_length=1)
    queued_at_utc: datetime
    stage_name: ProcessingStageName
    started_at_utc: datetime | None = None
    status: ProcessingJobStatus
    updated_at_utc: datetime


class OcrResultCreateRequest(BaseModel):
    """Create request for a persisted OCR result."""

    document_id: str = Field(min_length=1)
    model_name: str | None = None
    ocr_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ocr_result_id: str | None = None
    packet_id: str = Field(min_length=1)
    page_count: int = Field(default=0, ge=0)
    provider: str = Field(min_length=1)
    text_excerpt: str | None = None
    text_storage_uri: str | None = None


class OcrResultRecord(BaseModel):
    """A persisted OCR result."""

    created_at_utc: datetime
    document_id: str = Field(min_length=1)
    model_name: str | None = None
    ocr_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ocr_result_id: str = Field(min_length=1)
    packet_id: str = Field(min_length=1)
    page_count: int = Field(default=0, ge=0)
    provider: str = Field(min_length=1)
    text_excerpt: str | None = None
    text_storage_uri: str | None = None


class ExtractionResultCreateRequest(BaseModel):
    """Create request for a persisted extraction result."""

    document_id: str = Field(min_length=1)
    document_type: str | None = None
    extraction_result_id: str | None = None
    model_name: str | None = None
    packet_id: str = Field(min_length=1)
    prompt_profile_id: PromptProfileId | None = None
    provider: str = Field(min_length=1)
    result_payload: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None


class ExtractionResultRecord(BaseModel):
    """A persisted extraction result."""

    created_at_utc: datetime
    document_id: str = Field(min_length=1)
    document_type: str | None = None
    extraction_result_id: str = Field(min_length=1)
    model_name: str | None = None
    packet_id: str = Field(min_length=1)
    prompt_profile_id: PromptProfileId | None = None
    provider: str = Field(min_length=1)
    result_payload: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None


class ClassificationResultCreateRequest(BaseModel):
    """Create request for a persisted classification result."""

    classification_id: str | None = None
    classification_result_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    document_id: str = Field(min_length=1)
    document_type_id: str | None = None
    packet_id: str = Field(min_length=1)
    prompt_profile_id: PromptProfileId | None = None
    result_payload: dict[str, Any] = Field(default_factory=dict)
    result_source: ClassificationResultSource


class ClassificationResultRecord(BaseModel):
    """A persisted classification result."""

    classification_id: str | None = None
    classification_result_id: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    created_at_utc: datetime
    document_id: str = Field(min_length=1)
    document_type_id: str | None = None
    packet_id: str = Field(min_length=1)
    prompt_profile_id: PromptProfileId | None = None
    result_payload: dict[str, Any] = Field(default_factory=dict)
    result_source: ClassificationResultSource


class ExtractionStrategySelection(BaseModel):
    """Resolved extraction routing for one packet document."""

    classification_result_id: str | None = None
    document_type_id: str | None = None
    document_type_key: str | None = None
    matching_path: str = Field(min_length=1)
    prompt_profile_id: PromptProfileId | None = None
    required_fields: tuple[str, ...] = Field(default_factory=tuple)
    strategy_source: Literal["classification_contract", "request_heuristics"]


class PacketClassificationExecutionDocumentResult(BaseModel):
    """One document advanced through packet classification into OCR handoff."""

    classification_id: str | None = None
    classification_job_id: str = Field(min_length=1)
    classification_result_id: str | None = None
    document_id: str = Field(min_length=1)
    document_type_id: str | None = None
    ocr_job_id: str | None = None
    packet_id: str = Field(min_length=1)
    prompt_profile_id: PromptProfileId | None = None
    result_source: ClassificationResultSource | None = None
    review_task_id: str | None = None
    status: PacketStatus = PacketStatus.OCR_RUNNING


class PacketClassificationExecutionResponse(BaseModel):
    """Summary returned after packet classification executes queued documents."""

    executed_document_count: int = Field(default=0, ge=0)
    next_stage: ProcessingStageName = ProcessingStageName.OCR
    packet_id: str = Field(min_length=1)
    processed_documents: tuple[PacketClassificationExecutionDocumentResult, ...] = (
        Field(default_factory=tuple)
    )
    skipped_document_ids: tuple[str, ...] = Field(default_factory=tuple)
    status: PacketStatus = PacketStatus.OCR_RUNNING


class PacketOcrExecutionDocumentResult(BaseModel):
    """One document advanced through packet OCR into extraction handoff."""

    classification_result_id: str | None = None
    document_id: str = Field(min_length=1)
    extraction_job_id: str | None = None
    extraction_strategy: ExtractionStrategySelection
    ocr_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ocr_job_id: str = Field(min_length=1)
    ocr_result_id: str = Field(min_length=1)
    packet_id: str = Field(min_length=1)
    page_count: int = Field(default=0, ge=0)
    provider: str = Field(min_length=1)
    review_task_id: str | None = None
    status: PacketStatus = PacketStatus.EXTRACTING
    text_storage_uri: str | None = None


class PacketOcrExecutionResponse(BaseModel):
    """Summary returned after packet OCR executes queued documents."""

    executed_document_count: int = Field(default=0, ge=0)
    next_stage: ProcessingStageName = ProcessingStageName.EXTRACTION
    packet_id: str = Field(min_length=1)
    processed_documents: tuple[PacketOcrExecutionDocumentResult, ...] = Field(
        default_factory=tuple
    )
    skipped_document_ids: tuple[str, ...] = Field(default_factory=tuple)
    status: PacketStatus = PacketStatus.EXTRACTING


class PacketExtractionExecutionDocumentResult(BaseModel):
    """One document advanced through packet extraction and matching."""

    account_match: AccountMatchResult
    classification_result_id: str | None = None
    document_id: str = Field(min_length=1)
    extraction_job_id: str = Field(min_length=1)
    extraction_result_id: str = Field(min_length=1)
    extraction_strategy: ExtractionStrategySelection
    match_run_id: str = Field(min_length=1)
    packet_id: str = Field(min_length=1)
    prompt_profile_id: PromptProfileId | None = None
    recommendation_job_id: str | None = None
    review_task_id: str | None = None
    review_decision: ReviewDecision
    selected_account_id: str | None = None
    status: PacketStatus


class PacketExtractionExecutionResponse(BaseModel):
    """Summary returned after packet extraction executes queued documents."""

    executed_document_count: int = Field(default=0, ge=0)
    next_stage: ProcessingStageName
    packet_id: str = Field(min_length=1)
    processed_documents: tuple[PacketExtractionExecutionDocumentResult, ...] = Field(
        default_factory=tuple
    )
    skipped_document_ids: tuple[str, ...] = Field(default_factory=tuple)
    status: PacketStatus


class PacketRecommendationExecutionDocumentResult(BaseModel):
    """One document advanced through packet recommendation generation."""

    classification_prior_id: str | None = None
    classification_result_id: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    disposition: RecommendationDisposition = RecommendationDisposition.PENDING
    document_id: str = Field(min_length=1)
    packet_id: str = Field(min_length=1)
    recommendation_job_id: str = Field(min_length=1)
    recommendation_kind: str = Field(min_length=1)
    recommendation_result_id: str = Field(min_length=1)
    recommendation_run_id: str = Field(min_length=1)
    review_task_id: str | None = None
    selected_account_id: str | None = None
    status: PacketStatus = PacketStatus.COMPLETED
    summary: str = Field(min_length=1)


class PacketRecommendationExecutionResponse(BaseModel):
    """Summary returned after packet recommendation executes queued documents."""

    executed_document_count: int = Field(default=0, ge=0)
    next_stage: ProcessingStageName = ProcessingStageName.RECOMMENDATION
    packet_id: str = Field(min_length=1)
    processed_documents: tuple[PacketRecommendationExecutionDocumentResult, ...] = (
        Field(default_factory=tuple)
    )
    skipped_document_ids: tuple[str, ...] = Field(default_factory=tuple)
    status: PacketStatus = PacketStatus.COMPLETED


class PacketStageRetryResponse(BaseModel):
    """Summary returned after packet-stage retry work is requeued and executed."""

    executed_document_count: int = Field(default=0, ge=0)
    failed_job_count: int = Field(default=0, ge=0)
    next_stage: ProcessingStageName | None = None
    packet_id: str = Field(min_length=1)
    requeued_document_count: int = Field(default=0, ge=0)
    skipped_document_ids: tuple[str, ...] = Field(default_factory=tuple)
    stage_name: ProcessingStageName
    stale_running_job_count: int = Field(default=0, ge=0)
    status: PacketStatus


class PacketReplayResponse(BaseModel):
    """Summary returned after replaying packet work from the intake workspace."""

    action: Literal["execute", "retry"]
    executed_document_count: int = Field(default=0, ge=0)
    failed_job_count: int = Field(default=0, ge=0)
    message: str = Field(min_length=1)
    next_stage: ProcessingStageName | None = None
    packet_id: str = Field(min_length=1)
    requeued_document_count: int = Field(default=0, ge=0)
    skipped_document_ids: tuple[str, ...] = Field(default_factory=tuple)
    stage_name: ProcessingStageName
    stale_running_job_count: int = Field(default=0, ge=0)
    status: PacketStatus


class ClassificationPriorCreateRequest(BaseModel):
    """Create request for a reusable operator-confirmed classification prior."""

    account_id: str | None = None
    classification_id: str = Field(min_length=1)
    classification_prior_id: str | None = None
    confidence_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    confirmed_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    confirmed_by_email: str | None = None
    confirmed_by_user_id: str | None = None
    document_fingerprint: str | None = None
    document_type_id: str = Field(min_length=1)
    issuer_name_normalized: str | None = None
    packet_id: str | None = None
    prompt_profile_id: PromptProfileId
    source_document_id: str | None = None
    source_fingerprint: str | None = None


class ClassificationPriorRecord(BaseModel):
    """A reusable operator-confirmed classification prior."""

    account_id: str | None = None
    classification_id: str = Field(min_length=1)
    classification_prior_id: str = Field(min_length=1)
    confidence_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    confirmed_at_utc: datetime
    confirmed_by_email: str | None = None
    confirmed_by_user_id: str | None = None
    created_at_utc: datetime
    document_fingerprint: str | None = None
    document_type_id: str = Field(min_length=1)
    is_enabled: bool = True
    issuer_name_normalized: str | None = None
    packet_id: str | None = None
    prompt_profile_id: PromptProfileId
    source_document_id: str | None = None
    source_fingerprint: str | None = None
    updated_at_utc: datetime


class AccountMatchRunCreateRequest(BaseModel):
    """Create request for a persisted account-match run."""

    candidates: tuple[AccountMatchCandidate, ...] = Field(default_factory=tuple)
    document_id: str = Field(min_length=1)
    match_run_id: str | None = None
    packet_id: str = Field(min_length=1)
    rationale: str | None = None
    selected_account_id: str | None = None
    status: AccountMatchStatus


class AccountMatchRunRecord(BaseModel):
    """A persisted account-match run."""

    candidates: tuple[AccountMatchCandidate, ...] = Field(default_factory=tuple)
    created_at_utc: datetime
    document_id: str = Field(min_length=1)
    match_run_id: str = Field(min_length=1)
    packet_id: str = Field(min_length=1)
    rationale: str | None = None
    selected_account_id: str | None = None
    status: AccountMatchStatus


class ReviewTaskCreateRequest(BaseModel):
    """Create request for a persisted review task."""

    assigned_user_email: str | None = None
    assigned_user_id: str | None = None
    document_id: str = Field(min_length=1)
    due_at_utc: datetime | None = None
    notes_summary: str | None = None
    packet_id: str = Field(min_length=1)
    priority: ReviewTaskPriority = ReviewTaskPriority.NORMAL
    reason_codes: tuple[str, ...] = Field(default_factory=tuple)
    review_task_id: str | None = None
    selected_account_id: str | None = None
    status: PacketStatus = PacketStatus.AWAITING_REVIEW


class ReviewTaskRecord(BaseModel):
    """A persisted review task."""

    assigned_user_email: str | None = None
    assigned_user_id: str | None = None
    created_at_utc: datetime
    document_id: str = Field(min_length=1)
    due_at_utc: datetime | None = None
    notes_summary: str | None = None
    packet_id: str = Field(min_length=1)
    priority: ReviewTaskPriority
    reason_codes: tuple[str, ...] = Field(default_factory=tuple)
    review_task_id: str = Field(min_length=1)
    row_version: str | None = None
    selected_account_id: str | None = None
    status: PacketStatus
    updated_at_utc: datetime


class ReviewDecisionCreateRequest(BaseModel):
    """Create request for a persisted review decision."""

    decided_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_by_email: str | None = None
    decided_by_user_id: str | None = None
    decision_id: str | None = None
    decision_reason_code: str | None = None
    decision_status: ReviewStatus
    document_id: str = Field(min_length=1)
    packet_id: str = Field(min_length=1)
    review_notes: str | None = None
    review_task_id: str = Field(min_length=1)
    selected_account_id: str | None = None


class PacketReviewDecisionRequest(BaseModel):
    """Decision payload submitted against a SQL-backed review task."""

    decided_by_email: str | None = None
    decided_by_user_id: str | None = None
    decision_reason_code: str | None = None
    decision_status: Literal[
        ReviewStatus.APPROVED,
        ReviewStatus.REJECTED,
    ]
    expected_row_version: str = Field(min_length=1)
    review_notes: str | None = None
    selected_account_id: str | None = None


class ReviewDecisionRecord(BaseModel):
    """A persisted review decision."""

    decided_at_utc: datetime
    decided_by_email: str | None = None
    decided_by_user_id: str | None = None
    decision_id: str = Field(min_length=1)
    decision_reason_code: str | None = None
    decision_status: ReviewStatus
    document_id: str = Field(min_length=1)
    packet_id: str = Field(min_length=1)
    review_notes: str | None = None
    review_task_id: str = Field(min_length=1)
    selected_account_id: str | None = None


class OperatorNoteCreateRequest(BaseModel):
    """Create request for a persisted operator note."""

    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by_email: str | None = None
    created_by_user_id: str | None = None
    document_id: str | None = None
    is_private: bool = False
    note_id: str | None = None
    note_text: str = Field(min_length=1)
    packet_id: str | None = None
    review_task_id: str | None = None


class OperatorNoteRecord(BaseModel):
    """A persisted operator note."""

    created_at_utc: datetime
    created_by_email: str | None = None
    created_by_user_id: str | None = None
    document_id: str | None = None
    is_private: bool = False
    note_id: str = Field(min_length=1)
    note_text: str = Field(min_length=1)
    packet_id: str | None = None
    review_task_id: str | None = None


class AuditEventCreateRequest(BaseModel):
    """Create request for a persisted audit event."""

    actor_email: str | None = None
    actor_user_id: str | None = None
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    document_id: str | None = None
    event_payload: dict[str, Any] = Field(default_factory=dict)
    event_type: str = Field(min_length=1)
    packet_id: str | None = None
    review_task_id: str | None = None


class AuditEventRecord(BaseModel):
    """A persisted audit event."""

    actor_email: str | None = None
    actor_user_id: str | None = None
    audit_event_id: int = Field(ge=1)
    created_at_utc: datetime
    document_id: str | None = None
    event_payload: dict[str, Any] | None = None
    event_type: str = Field(min_length=1)
    packet_id: str | None = None
    review_task_id: str | None = None


class RecommendationEvidenceItem(BaseModel):
    """One evidence item attached to a recommendation result."""

    evidence_kind: str = Field(min_length=1)
    field_name: str | None = None
    source_document_id: str | None = None
    source_excerpt: str | None = None
    storage_uri: str | None = None


class RecommendationRunCreateRequest(BaseModel):
    """Create request for a persisted recommendation run."""

    document_id: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    packet_id: str = Field(min_length=1)
    prompt_profile_id: PromptProfileId | None = None
    recommendation_run_id: str | None = None
    requested_by_email: str | None = None
    requested_by_user_id: str | None = None
    review_task_id: str | None = None
    status: RecommendationRunStatus = RecommendationRunStatus.QUEUED


class RecommendationRunRecord(BaseModel):
    """A persisted recommendation run."""

    completed_at_utc: datetime | None = None
    created_at_utc: datetime
    document_id: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    packet_id: str = Field(min_length=1)
    prompt_profile_id: PromptProfileId | None = None
    recommendation_run_id: str = Field(min_length=1)
    requested_by_email: str | None = None
    requested_by_user_id: str | None = None
    review_task_id: str | None = None
    status: RecommendationRunStatus
    updated_at_utc: datetime


class RecommendationResultCreateRequest(BaseModel):
    """Create request for a persisted recommendation result."""

    advisory_text: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    disposition: RecommendationDisposition = RecommendationDisposition.PENDING
    document_id: str | None = None
    evidence_items: tuple[RecommendationEvidenceItem, ...] = Field(
        default_factory=tuple
    )
    packet_id: str = Field(min_length=1)
    rationale_payload: dict[str, Any] = Field(default_factory=dict)
    recommendation_kind: str = Field(min_length=1)
    recommendation_result_id: str | None = None
    recommendation_run_id: str = Field(min_length=1)
    reviewed_at_utc: datetime | None = None
    reviewed_by_email: str | None = None
    reviewed_by_user_id: str | None = None
    summary: str = Field(min_length=1)


class RecommendationResultRecord(BaseModel):
    """A persisted recommendation result."""

    advisory_text: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at_utc: datetime
    disposition: RecommendationDisposition
    document_id: str | None = None
    evidence_items: tuple[RecommendationEvidenceItem, ...] = Field(
        default_factory=tuple
    )
    packet_id: str = Field(min_length=1)
    rationale_payload: dict[str, Any] = Field(default_factory=dict)
    recommendation_kind: str = Field(min_length=1)
    recommendation_result_id: str = Field(min_length=1)
    recommendation_run_id: str = Field(min_length=1)
    reviewed_at_utc: datetime | None = None
    reviewed_by_email: str | None = None
    reviewed_by_user_id: str | None = None
    summary: str = Field(min_length=1)
    updated_at_utc: datetime


class PacketReviewDecisionResponse(BaseModel):
    """Result returned after applying a SQL-backed packet review decision."""

    decision: ReviewDecisionRecord
    document_status: PacketStatus
    operator_note: OperatorNoteRecord | None = None
    packet_id: str = Field(min_length=1)
    packet_status: PacketStatus
    queued_recommendation_job_id: str | None = None
    review_task_id: str = Field(min_length=1)
    review_task_status: PacketStatus


class PacketReviewAssignmentRequest(BaseModel):
    """Payload submitted to update one SQL-backed review-task assignment."""

    assigned_by_email: str | None = None
    assigned_by_user_id: str | None = None
    assigned_user_email: str | None = None
    assigned_user_id: str | None = None
    expected_row_version: str = Field(min_length=1)


class PacketReviewAssignmentResponse(BaseModel):
    """Result returned after updating one review-task assignment."""

    assigned_user_email: str | None = None
    assigned_user_id: str | None = None
    packet_id: str = Field(min_length=1)
    review_task_id: str = Field(min_length=1)


class PacketReviewTaskCreateRequest(BaseModel):
    """Payload submitted to create one SQL-backed review task."""

    assigned_user_email: str | None = None
    assigned_user_id: str | None = None
    created_by_email: str | None = None
    created_by_user_id: str | None = None
    notes_summary: str | None = None
    priority: ReviewTaskPriority = ReviewTaskPriority.NORMAL
    selected_account_id: str | None = None


class PacketReviewTaskCreateResponse(BaseModel):
    """Result returned after creating one SQL-backed review task."""

    document_id: str = Field(min_length=1)
    packet_id: str = Field(min_length=1)
    review_task_id: str = Field(min_length=1)


class PacketReviewNoteRequest(BaseModel):
    """Create request for a SQL-backed review-task operator note."""

    created_by_email: str | None = None
    created_by_user_id: str | None = None
    expected_row_version: str = Field(min_length=1)
    is_private: bool = False
    note_text: str = Field(min_length=1)


class PacketReviewNoteResponse(BaseModel):
    """Result returned after creating a SQL-backed review-task operator note."""

    operator_note: OperatorNoteRecord
    packet_id: str = Field(min_length=1)
    review_task_id: str = Field(min_length=1)


class ExtractionFieldEditInput(BaseModel):
    """One extracted-field edit submitted from the review workspace."""

    field_name: str = Field(min_length=1)
    value: str = ""


class ExtractionFieldChangeRecord(BaseModel):
    """One persisted extracted-field change recorded through review."""

    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    current_value: str = ""
    field_name: str = Field(min_length=1)
    original_value: str = ""


class PacketReviewExtractionEditRequest(BaseModel):
    """Payload submitted to persist extracted-field edits for one review task."""

    edited_by_email: str | None = None
    edited_by_user_id: str | None = None
    expected_row_version: str = Field(min_length=1)
    field_edits: tuple[ExtractionFieldEditInput, ...] = Field(min_length=1)


class PacketReviewExtractionEditResponse(BaseModel):
    """Result returned after persisting extracted-field edits for one review task."""

    audit_event: AuditEventRecord
    changed_fields: tuple[ExtractionFieldChangeRecord, ...] = Field(
        default_factory=tuple
    )
    document_id: str = Field(min_length=1)
    extraction_result: ExtractionResultRecord
    packet_id: str = Field(min_length=1)
    review_task_id: str = Field(min_length=1)


class PacketRecommendationReviewRequest(BaseModel):
    """Review payload submitted against one stored recommendation result."""

    disposition: Literal[
        RecommendationDisposition.ACCEPTED,
        RecommendationDisposition.REJECTED,
    ]
    reviewed_by_email: str | None = None
    reviewed_by_user_id: str | None = None


class PacketRecommendationReviewResponse(BaseModel):
    """Result returned after reviewing one stored recommendation result."""

    packet_id: str = Field(min_length=1)
    recommendation_result: RecommendationResultRecord


class PacketWorkspaceSnapshot(BaseModel):
    """All persisted operator-state entities associated with one packet."""

    account_match_runs: tuple[AccountMatchRunRecord, ...] = Field(default_factory=tuple)
    audit_events: tuple[AuditEventRecord, ...] = Field(default_factory=tuple)
    classification_results: tuple[ClassificationResultRecord, ...] = Field(
        default_factory=tuple
    )
    document_assets: tuple[DocumentAssetRecord, ...] = Field(default_factory=tuple)
    documents: tuple[PacketDocumentRecord, ...] = Field(default_factory=tuple)
    extraction_results: tuple[ExtractionResultRecord, ...] = Field(
        default_factory=tuple
    )
    ocr_results: tuple[OcrResultRecord, ...] = Field(default_factory=tuple)
    operator_notes: tuple[OperatorNoteRecord, ...] = Field(default_factory=tuple)
    packet: PacketRecord
    packet_events: tuple[PacketEventRecord, ...] = Field(default_factory=tuple)
    processing_jobs: tuple[ProcessingJobRecord, ...] = Field(default_factory=tuple)
    recommendation_results: tuple[RecommendationResultRecord, ...] = Field(
        default_factory=tuple
    )
    recommendation_runs: tuple[RecommendationRunRecord, ...] = Field(
        default_factory=tuple
    )
    review_decisions: tuple[ReviewDecisionRecord, ...] = Field(
        default_factory=tuple
    )
    review_tasks: tuple[ReviewTaskRecord, ...] = Field(default_factory=tuple)


class PacketQueueListRequest(BaseModel):
    """Query parameters accepted by the paged operator packet queue."""

    assigned_user_email: str | None = None
    classification_key: str | None = None
    document_type_key: str | None = None
    min_queue_age_hours: float | None = Field(default=None, ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)
    source: DocumentSource | None = None
    stage_name: ProcessingStageName | None = None
    status: PacketStatus | None = None


class PacketQueueItem(BaseModel):
    """One row returned by the paged operator packet queue."""

    assigned_user_email: str | None = None
    assignment_state: PacketAssignmentState = PacketAssignmentState.UNASSIGNED
    audit_event_count: int = Field(ge=0)
    awaiting_review_document_count: int = Field(ge=0)
    classification_keys: tuple[str, ...] = Field(default_factory=tuple)
    completed_document_count: int = Field(ge=0)
    document_count: int = Field(ge=0)
    document_type_keys: tuple[str, ...] = Field(default_factory=tuple)
    latest_job_stage_name: ProcessingStageName | None = None
    latest_job_status: ProcessingJobStatus | None = None
    oldest_review_task_created_at_utc: datetime | None = None
    operator_note_count: int = Field(ge=0)
    packet_id: str = Field(min_length=1)
    packet_name: str = Field(min_length=1)
    primary_document_id: str | None = None
    primary_file_name: str | None = None
    primary_issuer_category: IssuerCategory = IssuerCategory.UNKNOWN
    primary_issuer_name: str | None = None
    queue_age_hours: float = Field(ge=0)
    received_at_utc: datetime
    review_task_count: int = Field(ge=0)
    source: DocumentSource
    source_uri: str | None = None
    stage_name: ProcessingStageName
    status: PacketStatus
    submitted_by: str | None = None
    updated_at_utc: datetime


class PacketQueueListResponse(BaseModel):
    """A paged operator packet queue response."""

    has_more: bool = False
    items: tuple[PacketQueueItem, ...] = Field(default_factory=tuple)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_count: int = Field(ge=0)
"""Services for durable operator-managed intake-source definitions."""

from __future__ import annotations

import base64
import mimetypes
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from document_intelligence.manual_intake import create_manual_packet_intake
from document_intelligence.models import (
    ConfiguredFolderSourceConfiguration,
    DocumentSource,
    EmailConnectorSourceConfiguration,
    IntakeSourceCreateRequest,
    IntakeSourceDeleteResponse,
    IntakeSourceEnablementRequest,
    IntakeSourceExecutionFailure,
    IntakeSourceExecutionPacketResult,
    IntakeSourceExecutionResponse,
    IntakeSourceListResponse,
    IntakeSourceRecord,
    IntakeSourceUpdateRequest,
    ManualPacketDocumentInput,
    ManualPacketIntakeRequest,
    ManualPacketIntakeResponse,
    PartnerApiFeedSourceConfiguration,
    SourcePacketIngestionRequest,
    WatchedBlobPrefixSourceConfiguration,
    WatchedSftpPathSourceConfiguration,
)
from document_intelligence.persistence import SqlIntakeSourceRepository
from document_intelligence.settings import AppSettings
from document_intelligence.utils.blob_storage import (
    ListedBlobAsset,
    download_blob_bytes,
    list_blob_assets,
)
from document_intelligence.utils.configured_folder import (
    ListedConfiguredFolderAsset,
    list_configured_folder_assets,
    read_configured_folder_file_bytes,
)
from document_intelligence.utils.email_connector import (
    ListedEmailConnectorAsset,
    list_email_connector_assets,
)
from document_intelligence.utils.watched_sftp import (
    ListedWatchedSftpAsset,
    list_watched_sftp_assets,
    read_watched_sftp_asset_bytes,
)


class IntakeSourceConfigurationError(RuntimeError):
    """Raised when durable intake-source storage is not configured."""


_GENERIC_SOURCE_CONTENT_TYPES = frozenset(
    {"application/octet-stream", "binary/octet-stream"}
)


def _get_repository(settings: AppSettings) -> SqlIntakeSourceRepository:
    """Return the configured SQL intake-source repository."""

    repository = SqlIntakeSourceRepository(settings)
    if repository.is_configured():
        return repository

    raise IntakeSourceConfigurationError(
        "Azure SQL source configuration storage is not configured."
    )


def list_intake_sources(settings: AppSettings) -> IntakeSourceListResponse:
    """Return the configured operator intake sources from SQL."""

    return _get_repository(settings).list_intake_sources()


def create_intake_source(
    request: IntakeSourceCreateRequest,
    settings: AppSettings,
) -> IntakeSourceRecord:
    """Create a durable operator intake-source definition in SQL."""

    return _get_repository(settings).create_intake_source(request)


def update_intake_source(
    source_id: str,
    request: IntakeSourceUpdateRequest,
    settings: AppSettings,
) -> IntakeSourceRecord:
    """Replace a durable operator intake-source definition in SQL."""

    return _get_repository(settings).update_intake_source(source_id, request)


def set_intake_source_enablement(
    source_id: str,
    request: IntakeSourceEnablementRequest,
    settings: AppSettings,
) -> IntakeSourceRecord:
    """Pause or resume one durable operator intake-source definition."""

    return _get_repository(settings).set_intake_source_enablement(source_id, request)


def delete_intake_source(
    source_id: str,
    settings: AppSettings,
) -> IntakeSourceDeleteResponse:
    """Delete one durable operator intake-source definition from SQL."""

    return _get_repository(settings).delete_intake_source(source_id)


def _require_watched_blob_configuration(
    source: IntakeSourceRecord,
) -> WatchedBlobPrefixSourceConfiguration:
    """Return the watched-blob configuration or raise for unsupported kinds."""

    configuration = source.configuration
    if isinstance(configuration, WatchedBlobPrefixSourceConfiguration):
        return configuration

    raise IntakeSourceConfigurationError(
        "Only watched Azure Blob prefix sources are supported by this execution route."
    )


def _require_configured_folder_configuration(
    source: IntakeSourceRecord,
) -> ConfiguredFolderSourceConfiguration:
    """Return the configured-folder configuration or raise for unsupported kinds."""

    configuration = source.configuration
    if isinstance(configuration, ConfiguredFolderSourceConfiguration):
        return configuration

    raise IntakeSourceConfigurationError(
        "Only configured folder sources are supported by this execution route."
    )


def _require_watched_sftp_configuration(
    source: IntakeSourceRecord,
) -> WatchedSftpPathSourceConfiguration:
    """Return the watched-SFTP configuration or raise for unsupported kinds."""

    configuration = source.configuration
    if isinstance(configuration, WatchedSftpPathSourceConfiguration):
        return configuration

    raise IntakeSourceConfigurationError(
        "Only watched SFTP path sources are supported by this execution route."
    )


def _require_email_connector_configuration(
    source: IntakeSourceRecord,
) -> EmailConnectorSourceConfiguration:
    """Return the email-connector configuration or raise for other kinds."""

    configuration = source.configuration
    if isinstance(configuration, EmailConnectorSourceConfiguration):
        return configuration

    raise IntakeSourceConfigurationError(
        "Only email connector sources are supported by this execution route."
    )


def _require_partner_api_configuration(
    source: IntakeSourceRecord,
) -> PartnerApiFeedSourceConfiguration:
    """Return the partner API configuration or raise for other kinds."""

    configuration = source.configuration
    if isinstance(configuration, PartnerApiFeedSourceConfiguration):
        return configuration

    raise IntakeSourceConfigurationError(
        "Only partner API feed sources are supported by this ingestion route."
    )


def _resolve_packet_name(blob: ListedBlobAsset) -> str:
    """Return a human-readable packet name derived from the blob path."""

    file_name = Path(blob.blob_name).name.strip()
    return file_name or blob.blob_name


def _resolve_blob_content_type(blob: ListedBlobAsset) -> str:
    """Return the content type used for the staged blob document."""

    return _resolve_source_content_type(
        blob.content_type,
        file_name=blob.blob_name,
    )


def _resolve_configured_folder_content_type(
    file_asset: ListedConfiguredFolderAsset,
) -> str:
    """Return the content type used for a configured-folder document."""

    return _resolve_source_content_type(
        file_asset.content_type,
        file_name=file_asset.file_path.name,
    )


def _resolve_watched_sftp_content_type(asset: ListedWatchedSftpAsset) -> str:
    """Return the content type used for a watched SFTP document."""

    return _resolve_source_content_type(
        asset.content_type,
        file_name=asset.relative_path,
    )


def _resolve_source_content_type(
    raw_content_type: str | None,
    *,
    file_name: str,
) -> str:
    """Return the best available content type for one discovered source file."""

    normalized_content_type = raw_content_type.strip() if raw_content_type else ""
    if (
        normalized_content_type
        and normalized_content_type.lower() not in _GENERIC_SOURCE_CONTENT_TYPES
    ):
        return normalized_content_type

    guessed_type, _ = mimetypes.guess_type(file_name)
    if guessed_type:
        return guessed_type

    return normalized_content_type or "application/octet-stream"


def _resolve_source_uri(blob: ListedBlobAsset) -> str:
    """Return a stable source URI that distinguishes blob revisions."""

    if blob.etag is None:
        return blob.storage_uri

    normalized_etag = blob.etag.strip('"')
    if not normalized_etag:
        return blob.storage_uri

    return f"{blob.storage_uri}?{urlencode({'etag': normalized_etag})}"


def _filter_candidate_blobs(
    *,
    configuration: WatchedBlobPrefixSourceConfiguration,
    listed_blobs: tuple[ListedBlobAsset, ...],
) -> tuple[ListedBlobAsset, ...]:
    """Apply the configured subdirectory policy to listed blobs."""

    if configuration.include_subdirectories:
        return tuple(sorted(listed_blobs, key=lambda blob: blob.blob_name.lower()))

    filtered_blobs: list[ListedBlobAsset] = []
    normalized_prefix = configuration.blob_prefix
    for blob in listed_blobs:
        relative_name = blob.blob_name.removeprefix(normalized_prefix).lstrip("/")
        if "/" in relative_name:
            continue

        filtered_blobs.append(blob)

    return tuple(sorted(filtered_blobs, key=lambda blob: blob.blob_name.lower()))


def _build_blob_intake_request(
    *,
    blob: ListedBlobAsset,
    blob_bytes: bytes,
    source: IntakeSourceRecord,
) -> ManualPacketIntakeRequest:
    """Build a packet-intake request from one watched blob."""

    packet_name = _resolve_packet_name(blob)
    return ManualPacketIntakeRequest(
        packet_name=packet_name,
        packet_tags=(
            f"source_id:{source.source_id}",
            f"source_kind:{source.configuration.source_kind.value}",
        ),
        source=DocumentSource.AZURE_BLOB,
        source_uri=_resolve_source_uri(blob),
        submitted_by=source.owner_email or f"intake-source:{source.source_id}",
        documents=(
            ManualPacketDocumentInput(
                content_type=_resolve_blob_content_type(blob),
                document_content_base64=base64.b64encode(blob_bytes).decode("ascii"),
                file_name=packet_name,
                source_summary=(
                    f"Discovered by watched blob source '{source.source_name}'."
                ),
                source_tags=(
                    source.source_id,
                    source.configuration.source_kind.value,
                ),
            ),
        ),
    )


def _build_configured_folder_intake_request(
    *,
    file_asset: ListedConfiguredFolderAsset,
    file_bytes: bytes,
    source: IntakeSourceRecord,
) -> ManualPacketIntakeRequest:
    """Build a packet-intake request from one configured-folder file."""

    packet_name = (
        Path(file_asset.relative_path).name.strip() or file_asset.relative_path
    )
    return ManualPacketIntakeRequest(
        packet_name=packet_name,
        packet_tags=(
            f"source_id:{source.source_id}",
            f"source_kind:{source.configuration.source_kind.value}",
        ),
        source=DocumentSource.CONFIGURED_FOLDER,
        source_uri=file_asset.source_uri,
        submitted_by=source.owner_email or f"intake-source:{source.source_id}",
        documents=(
            ManualPacketDocumentInput(
                content_type=_resolve_configured_folder_content_type(file_asset),
                document_content_base64=base64.b64encode(file_bytes).decode("ascii"),
                file_name=packet_name,
                source_summary=(
                    f"Imported from configured folder source '{source.source_name}'."
                ),
                source_tags=(
                    source.source_id,
                    source.configuration.source_kind.value,
                    f"relative_path:{file_asset.relative_path}",
                ),
            ),
        ),
    )


def _build_watched_sftp_intake_request(
    *,
    asset: ListedWatchedSftpAsset,
    asset_bytes: bytes,
    source: IntakeSourceRecord,
) -> ManualPacketIntakeRequest:
    """Build a packet-intake request from one watched SFTP asset."""

    configuration = _require_watched_sftp_configuration(source)
    packet_name = Path(asset.relative_path).name.strip() or asset.relative_path
    return ManualPacketIntakeRequest(
        packet_name=packet_name,
        packet_tags=(
            f"source_id:{source.source_id}",
            f"source_kind:{source.configuration.source_kind.value}",
        ),
        source=DocumentSource.AZURE_SFTP,
        source_uri=asset.source_uri,
        submitted_by=source.owner_email or f"intake-source:{source.source_id}",
        documents=(
            ManualPacketDocumentInput(
                content_type=_resolve_watched_sftp_content_type(asset),
                document_content_base64=base64.b64encode(asset_bytes).decode("ascii"),
                file_name=packet_name,
                source_summary=(
                    f"Discovered by watched SFTP source '{source.source_name}'."
                ),
                source_tags=(
                    source.source_id,
                    source.configuration.source_kind.value,
                    f"local_user:{configuration.local_user_name}",
                    f"relative_path:{asset.relative_path}",
                ),
            ),
        ),
    )


def _combine_tags(*tag_groups: tuple[str, ...]) -> tuple[str, ...]:
    """Combine tag groups while preserving the first occurrence of each value."""

    combined_tags: list[str] = []
    seen_tags: set[str] = set()
    for tag_group in tag_groups:
        for tag in tag_group:
            if tag in seen_tags:
                continue

            seen_tags.add(tag)
            combined_tags.append(tag)

    return tuple(combined_tags)


def _build_email_connector_intake_request(
    *,
    asset: ListedEmailConnectorAsset,
    source: IntakeSourceRecord,
) -> ManualPacketIntakeRequest:
    """Build a packet-intake request from one staged email asset."""

    configuration = _require_email_connector_configuration(source)
    if not asset.documents:
        raise ValueError(
            "Email intake requires at least one supported attachment or staged "
            "document."
        )

    packet_name = asset.packet_name.strip() or asset.file_name
    return ManualPacketIntakeRequest(
        packet_name=packet_name,
        packet_tags=(
            f"source_id:{source.source_id}",
            f"source_kind:{source.configuration.source_kind.value}",
        ),
        source=DocumentSource.EMAIL_CONNECTOR,
        source_uri=asset.source_uri,
        submitted_by=source.owner_email or configuration.mailbox_address,
        documents=tuple(
            ManualPacketDocumentInput(
                content_type=_resolve_source_content_type(
                    document.content_type,
                    file_name=document.file_name,
                ),
                document_content_base64=base64.b64encode(
                    document.content_bytes
                ).decode("ascii"),
                file_name=document.file_name,
                source_summary=(
                    f"Imported from email connector source '{source.source_name}'."
                ),
                source_tags=_combine_tags(
                    (
                        source.source_id,
                        source.configuration.source_kind.value,
                        f"mailbox:{configuration.mailbox_address.lower()}",
                        f"folder:{configuration.folder_path}",
                        f"relative_path:{asset.relative_path}",
                    ),
                    ((f"subject:{asset.subject}",) if asset.subject else ()),
                    (f"attachment:{document.file_name}",),
                ),
            )
            for document in asset.documents
        ),
    )


def _build_partner_api_intake_request(
    *,
    request: SourcePacketIngestionRequest,
    source: IntakeSourceRecord,
) -> ManualPacketIntakeRequest:
    """Build a packet-intake request from one partner API submission."""

    configuration = _require_partner_api_configuration(source)
    source_uri = request.source_uri or (
        f"partner://{source.source_id}{configuration.relative_path}"
    )
    return ManualPacketIntakeRequest(
        packet_id=request.packet_id,
        packet_name=request.packet_name,
        packet_tags=_combine_tags(
            (
                f"source_id:{source.source_id}",
                f"source_kind:{source.configuration.source_kind.value}",
                f"partner_name:{configuration.partner_name}",
                f"auth_scheme:{configuration.auth_scheme}",
            ),
            request.packet_tags,
        ),
        source=DocumentSource.PARTNER_API_FEED,
        source_uri=source_uri,
        submitted_by=(
            request.submitted_by
            or source.owner_email
            or f"partner-source:{source.source_id}"
        ),
        received_at_utc=request.received_at_utc,
        documents=tuple(
            document.model_copy(
                update={
                    "source_summary": (
                        document.source_summary
                        or f"Submitted by partner feed '{source.source_name}'."
                    ),
                    "source_tags": _combine_tags(
                        (
                            source.source_id,
                            source.configuration.source_kind.value,
                            f"partner_name:{configuration.partner_name}",
                            f"relative_path:{configuration.relative_path}",
                            f"auth_scheme:{configuration.auth_scheme}",
                        ),
                        document.source_tags,
                    ),
                }
            )
            for document in request.documents
        ),
    )


def _build_packet_result(
    *,
    content_length_bytes: int,
    content_type: str,
    packet_response: object,
    source_asset_name: str,
    source_asset_uri: str,
) -> IntakeSourceExecutionPacketResult:
    """Project a manual-intake packet response into the source execution shape."""

    from document_intelligence.models import ManualPacketIntakeResponse

    typed_response = ManualPacketIntakeResponse.model_validate(packet_response)
    return IntakeSourceExecutionPacketResult(
        blob_name=source_asset_name,
        blob_uri=source_asset_uri,
        content_length_bytes=content_length_bytes,
        content_type=content_type,
        document_count=typed_response.document_count,
        duplicate_detection_status=typed_response.duplicate_detection.status,
        idempotency_reused_existing_packet=(
            typed_response.idempotency_reused_existing_packet
        ),
        packet_id=typed_response.packet_id,
        packet_name=typed_response.packet_name,
        status=typed_response.status,
    )


def _build_error_message(
    failures: tuple[IntakeSourceExecutionFailure, ...],
    *,
    source: IntakeSourceRecord,
) -> str | None:
    """Return the persisted error summary for the latest source execution."""

    if not failures:
        return None

    first_failure = failures[0]
    if len(failures) == 1:
        return f"{first_failure.blob_name}: {first_failure.message}"

    input_kind = "blobs"
    execution_label = "watched blob intake"
    if isinstance(source.configuration, ConfiguredFolderSourceConfiguration):
        input_kind = "files"
        execution_label = "configured folder intake"
    elif isinstance(source.configuration, EmailConnectorSourceConfiguration):
        input_kind = "messages"
        execution_label = "email connector intake"
    elif isinstance(source.configuration, WatchedSftpPathSourceConfiguration):
        input_kind = "files"
        execution_label = "watched SFTP intake"

    return (
        f"{len(failures)} {input_kind} failed during {execution_label}. First "
        f"failure: "
        f"{first_failure.blob_name}: {first_failure.message}"
    )


def _build_execution_response(
    *,
    executed_at_utc: datetime,
    failures: tuple[IntakeSourceExecutionFailure, ...],
    packet_results: tuple[IntakeSourceExecutionPacketResult, ...],
    seen_asset_count: int,
    source: IntakeSourceRecord,
) -> IntakeSourceExecutionResponse:
    """Build the common response shape for one source execution run."""

    return IntakeSourceExecutionResponse(
        executed_at_utc=executed_at_utc,
        failed_blob_count=len(failures),
        failures=failures,
        packet_results=packet_results,
        processed_blob_count=len(packet_results),
        reused_packet_count=sum(
            1 for result in packet_results if result.idempotency_reused_existing_packet
        ),
        seen_blob_count=seen_asset_count,
        source_id=source.source_id,
        source_kind=source.configuration.source_kind,
        source_name=source.source_name,
    )


def _record_source_execution(
    *,
    executed_at_utc: datetime,
    failures: tuple[IntakeSourceExecutionFailure, ...],
    packet_results: tuple[IntakeSourceExecutionPacketResult, ...],
    repository: SqlIntakeSourceRepository,
    source: IntakeSourceRecord,
) -> None:
    """Persist execution timestamps and the latest execution error summary."""

    repository.record_intake_source_execution(
        source.source_id,
        last_error_message=_build_error_message(failures, source=source),
        last_seen_at_utc=executed_at_utc,
        last_success_at_utc=(
            executed_at_utc if packet_results or not failures else None
        ),
    )


def _record_source_listing_failure(
    *,
    error: Exception,
    executed_at_utc: datetime,
    repository: SqlIntakeSourceRepository,
    source: IntakeSourceRecord,
) -> None:
    """Persist a fatal source-listing failure before re-raising."""

    repository.record_intake_source_execution(
        source.source_id,
        last_error_message=str(error),
        last_seen_at_utc=executed_at_utc,
        last_success_at_utc=None,
    )


def _list_watched_blob_candidates(
    *,
    executed_at_utc: datetime,
    repository: SqlIntakeSourceRepository,
    source: IntakeSourceRecord,
    storage_connection_string: str,
) -> tuple[ListedBlobAsset, ...]:
    """List the watched-Blob candidates for one source definition."""

    configuration = _require_watched_blob_configuration(source)
    try:
        listed_blobs = list_blob_assets(
            blob_prefix=configuration.blob_prefix,
            container_name=configuration.container_name,
            storage_connection_string=storage_connection_string,
        )
    except Exception as error:
        _record_source_listing_failure(
            error=error,
            executed_at_utc=executed_at_utc,
            repository=repository,
            source=source,
        )
        raise RuntimeError(
            f"Failed to read watched blob source '{source.source_id}': {error}"
        ) from error

    return _filter_candidate_blobs(
        configuration=configuration,
        listed_blobs=listed_blobs,
    )


def _collect_watched_blob_results(
    *,
    candidate_blobs: tuple[ListedBlobAsset, ...],
    settings: AppSettings,
    source: IntakeSourceRecord,
    storage_connection_string: str,
) -> tuple[
    tuple[IntakeSourceExecutionFailure, ...],
    tuple[IntakeSourceExecutionPacketResult, ...],
]:
    """Process watched-Blob candidates through the manual intake path."""

    failures: list[IntakeSourceExecutionFailure] = []
    packet_results: list[IntakeSourceExecutionPacketResult] = []
    for blob in candidate_blobs:
        try:
            blob_bytes = download_blob_bytes(
                blob_name=blob.blob_name,
                container_name=blob.container_name,
                storage_connection_string=storage_connection_string,
            )
            packet_response = create_manual_packet_intake(
                _build_blob_intake_request(
                    blob=blob,
                    blob_bytes=blob_bytes,
                    source=source,
                ),
                settings,
            )
        except Exception as error:
            failures.append(
                IntakeSourceExecutionFailure(
                    blob_name=blob.blob_name,
                    blob_uri=blob.storage_uri,
                    message=str(error),
                )
            )
            continue

        packet_results.append(
            _build_packet_result(
                content_length_bytes=blob.content_length_bytes,
                content_type=_resolve_blob_content_type(blob),
                packet_response=packet_response,
                source_asset_name=blob.blob_name,
                source_asset_uri=blob.storage_uri,
            )
        )

    return tuple(failures), tuple(packet_results)


def _list_configured_folder_candidates(
    *,
    executed_at_utc: datetime,
    repository: SqlIntakeSourceRepository,
    settings: AppSettings,
    source: IntakeSourceRecord,
) -> tuple[ListedConfiguredFolderAsset, ...]:
    """List the configured-folder candidates for one source definition."""

    configuration = _require_configured_folder_configuration(source)
    try:
        return list_configured_folder_assets(
            file_pattern=configuration.file_pattern,
            folder_path=configuration.folder_path,
            min_stable_age_seconds=settings.configured_folder_min_stable_age_seconds,
            recursive=configuration.recursive,
        )
    except Exception as error:
        _record_source_listing_failure(
            error=error,
            executed_at_utc=executed_at_utc,
            repository=repository,
            source=source,
        )
        raise RuntimeError(
            f"Failed to read configured folder source '{source.source_id}': {error}"
        ) from error


def _collect_configured_folder_results(
    *,
    listed_files: tuple[ListedConfiguredFolderAsset, ...],
    settings: AppSettings,
    source: IntakeSourceRecord,
) -> tuple[
    tuple[IntakeSourceExecutionFailure, ...],
    tuple[IntakeSourceExecutionPacketResult, ...],
]:
    """Process configured-folder files through the manual intake path."""

    failures: list[IntakeSourceExecutionFailure] = []
    packet_results: list[IntakeSourceExecutionPacketResult] = []
    for file_asset in listed_files:
        try:
            file_bytes = read_configured_folder_file_bytes(file_asset.file_path)
            packet_response = create_manual_packet_intake(
                _build_configured_folder_intake_request(
                    file_asset=file_asset,
                    file_bytes=file_bytes,
                    source=source,
                ),
                settings,
            )
        except Exception as error:
            failures.append(
                IntakeSourceExecutionFailure(
                    blob_name=file_asset.relative_path,
                    blob_uri=file_asset.source_uri,
                    message=str(error),
                )
            )
            continue

        packet_results.append(
            _build_packet_result(
                content_length_bytes=file_asset.content_length_bytes,
                content_type=_resolve_configured_folder_content_type(file_asset),
                packet_response=packet_response,
                source_asset_name=file_asset.relative_path,
                source_asset_uri=file_asset.source_uri,
            )
        )

    return tuple(failures), tuple(packet_results)


def _list_watched_sftp_candidates(
    *,
    executed_at_utc: datetime,
    repository: SqlIntakeSourceRepository,
    source: IntakeSourceRecord,
    storage_connection_string: str,
) -> tuple[ListedWatchedSftpAsset, ...]:
    """List the watched-SFTP candidates for one source definition."""

    configuration = _require_watched_sftp_configuration(source)
    try:
        return list_watched_sftp_assets(
            sftp_path=configuration.sftp_path,
            storage_account_name=configuration.storage_account_name,
            storage_connection_string=storage_connection_string,
        )
    except Exception as error:
        _record_source_listing_failure(
            error=error,
            executed_at_utc=executed_at_utc,
            repository=repository,
            source=source,
        )
        raise RuntimeError(
            f"Failed to read watched SFTP source '{source.source_id}': {error}"
        ) from error


def _collect_watched_sftp_results(
    *,
    listed_assets: tuple[ListedWatchedSftpAsset, ...],
    settings: AppSettings,
    source: IntakeSourceRecord,
    storage_connection_string: str,
) -> tuple[
    tuple[IntakeSourceExecutionFailure, ...],
    tuple[IntakeSourceExecutionPacketResult, ...],
]:
    """Process watched-SFTP assets through the manual intake path."""

    failures: list[IntakeSourceExecutionFailure] = []
    packet_results: list[IntakeSourceExecutionPacketResult] = []
    for asset in listed_assets:
        try:
            asset_bytes = read_watched_sftp_asset_bytes(
                asset,
                storage_connection_string=storage_connection_string,
            )
            packet_response = create_manual_packet_intake(
                _build_watched_sftp_intake_request(
                    asset=asset,
                    asset_bytes=asset_bytes,
                    source=source,
                ),
                settings,
            )
        except Exception as error:
            failures.append(
                IntakeSourceExecutionFailure(
                    blob_name=asset.source_path,
                    blob_uri=asset.source_uri,
                    message=str(error),
                )
            )
            continue

        packet_results.append(
            _build_packet_result(
                content_length_bytes=asset.content_length_bytes,
                content_type=_resolve_watched_sftp_content_type(asset),
                packet_response=packet_response,
                source_asset_name=asset.source_path,
                source_asset_uri=asset.source_uri,
            )
        )

    return tuple(failures), tuple(packet_results)


def _list_email_connector_candidates(
    *,
    executed_at_utc: datetime,
    repository: SqlIntakeSourceRepository,
    source: IntakeSourceRecord,
) -> tuple[ListedEmailConnectorAsset, ...]:
    """List staged email assets for one connector source definition."""

    configuration = _require_email_connector_configuration(source)
    try:
        return list_email_connector_assets(
            attachment_extension_allowlist=(
                configuration.attachment_extension_allowlist
            ),
            folder_path=configuration.folder_path,
            mailbox_address=configuration.mailbox_address,
        )
    except Exception as error:
        _record_source_listing_failure(
            error=error,
            executed_at_utc=executed_at_utc,
            repository=repository,
            source=source,
        )
        raise RuntimeError(
            f"Failed to read email connector source '{source.source_id}': {error}"
        ) from error


def _collect_email_connector_results(
    *,
    listed_assets: tuple[ListedEmailConnectorAsset, ...],
    settings: AppSettings,
    source: IntakeSourceRecord,
) -> tuple[
    tuple[IntakeSourceExecutionFailure, ...],
    tuple[IntakeSourceExecutionPacketResult, ...],
]:
    """Process staged email assets through the manual intake path."""

    failures: list[IntakeSourceExecutionFailure] = []
    packet_results: list[IntakeSourceExecutionPacketResult] = []
    for asset in listed_assets:
        try:
            packet_response = create_manual_packet_intake(
                _build_email_connector_intake_request(
                    asset=asset,
                    source=source,
                ),
                settings,
            )
        except Exception as error:
            failures.append(
                IntakeSourceExecutionFailure(
                    blob_name=asset.relative_path,
                    blob_uri=asset.source_uri,
                    message=str(error),
                )
            )
            continue

        packet_results.append(
            _build_packet_result(
                content_length_bytes=asset.content_length_bytes,
                content_type=asset.content_type or "message/rfc822",
                packet_response=packet_response,
                source_asset_name=asset.relative_path,
                source_asset_uri=asset.source_uri,
            )
        )

    return tuple(failures), tuple(packet_results)


def _execute_watched_blob_source(
    *,
    executed_at_utc: datetime,
    repository: SqlIntakeSourceRepository,
    settings: AppSettings,
    source: IntakeSourceRecord,
) -> IntakeSourceExecutionResponse:
    """Execute one watched-Blob source definition."""

    storage_connection_string = settings.storage_connection_string
    if not storage_connection_string:
        raise IntakeSourceConfigurationError(
            "Blob storage is not configured for watched blob intake execution."
        )

    candidate_blobs = _list_watched_blob_candidates(
        executed_at_utc=executed_at_utc,
        repository=repository,
        source=source,
        storage_connection_string=storage_connection_string,
    )
    failure_records, packet_result_records = _collect_watched_blob_results(
        candidate_blobs=candidate_blobs,
        settings=settings,
        source=source,
        storage_connection_string=storage_connection_string,
    )
    _record_source_execution(
        executed_at_utc=executed_at_utc,
        failures=failure_records,
        packet_results=packet_result_records,
        repository=repository,
        source=source,
    )
    return _build_execution_response(
        executed_at_utc=executed_at_utc,
        failures=failure_records,
        packet_results=packet_result_records,
        seen_asset_count=len(candidate_blobs),
        source=source,
    )


def _execute_configured_folder_source(
    *,
    executed_at_utc: datetime,
    repository: SqlIntakeSourceRepository,
    settings: AppSettings,
    source: IntakeSourceRecord,
) -> IntakeSourceExecutionResponse:
    """Execute one configured-folder source definition."""

    listed_files = _list_configured_folder_candidates(
        executed_at_utc=executed_at_utc,
        repository=repository,
        settings=settings,
        source=source,
    )
    failure_records, packet_result_records = _collect_configured_folder_results(
        listed_files=listed_files,
        settings=settings,
        source=source,
    )
    _record_source_execution(
        executed_at_utc=executed_at_utc,
        failures=failure_records,
        packet_results=packet_result_records,
        repository=repository,
        source=source,
    )
    return _build_execution_response(
        executed_at_utc=executed_at_utc,
        failures=failure_records,
        packet_results=packet_result_records,
        seen_asset_count=len(listed_files),
        source=source,
    )


def _execute_watched_sftp_source(
    *,
    executed_at_utc: datetime,
    repository: SqlIntakeSourceRepository,
    settings: AppSettings,
    source: IntakeSourceRecord,
) -> IntakeSourceExecutionResponse:
    """Execute one watched-SFTP source definition."""

    storage_connection_string = settings.storage_connection_string
    if not storage_connection_string:
        raise IntakeSourceConfigurationError(
            "Blob storage is not configured for watched SFTP intake execution."
        )

    listed_assets = _list_watched_sftp_candidates(
        executed_at_utc=executed_at_utc,
        repository=repository,
        source=source,
        storage_connection_string=storage_connection_string,
    )
    failure_records, packet_result_records = _collect_watched_sftp_results(
        listed_assets=listed_assets,
        settings=settings,
        source=source,
        storage_connection_string=storage_connection_string,
    )
    _record_source_execution(
        executed_at_utc=executed_at_utc,
        failures=failure_records,
        packet_results=packet_result_records,
        repository=repository,
        source=source,
    )
    return _build_execution_response(
        executed_at_utc=executed_at_utc,
        failures=failure_records,
        packet_results=packet_result_records,
        seen_asset_count=len(listed_assets),
        source=source,
    )


def _execute_email_connector_source(
    *,
    executed_at_utc: datetime,
    repository: SqlIntakeSourceRepository,
    settings: AppSettings,
    source: IntakeSourceRecord,
) -> IntakeSourceExecutionResponse:
    """Execute one staged email-connector source definition."""

    listed_assets = _list_email_connector_candidates(
        executed_at_utc=executed_at_utc,
        repository=repository,
        source=source,
    )
    failure_records, packet_result_records = _collect_email_connector_results(
        listed_assets=listed_assets,
        settings=settings,
        source=source,
    )
    _record_source_execution(
        executed_at_utc=executed_at_utc,
        failures=failure_records,
        packet_results=packet_result_records,
        repository=repository,
        source=source,
    )
    return _build_execution_response(
        executed_at_utc=executed_at_utc,
        failures=failure_records,
        packet_results=packet_result_records,
        seen_asset_count=len(listed_assets),
        source=source,
    )


def ingest_partner_source_packet(
    source_id: str,
    request: SourcePacketIngestionRequest,
    settings: AppSettings,
) -> ManualPacketIntakeResponse:
    """Stage one partner-submitted packet through the manual intake path."""

    repository = _get_repository(settings)
    source = repository.get_intake_source(source_id)
    if not source.is_enabled:
        raise IntakeSourceConfigurationError(
            f"Intake source '{source_id}' is disabled."
        )

    _require_partner_api_configuration(source)
    executed_at_utc = datetime.now(UTC)
    try:
        response = create_manual_packet_intake(
            _build_partner_api_intake_request(
                request=request,
                source=source,
            ),
            settings,
        )
    except Exception as error:
        repository.record_intake_source_execution(
            source.source_id,
            last_error_message=str(error),
            last_seen_at_utc=executed_at_utc,
            last_success_at_utc=None,
        )
        raise

    repository.record_intake_source_execution(
        source.source_id,
        last_error_message=None,
        last_seen_at_utc=executed_at_utc,
        last_success_at_utc=executed_at_utc,
    )
    return response


def execute_intake_source(
    source_id: str,
    settings: AppSettings,
) -> IntakeSourceExecutionResponse:
    """Execute one supported operator-configured intake source."""

    repository = _get_repository(settings)
    source = repository.get_intake_source(source_id)
    if not source.is_enabled:
        raise IntakeSourceConfigurationError(
            f"Intake source '{source_id}' is disabled."
        )

    executed_at_utc = datetime.now(UTC)
    if isinstance(source.configuration, WatchedBlobPrefixSourceConfiguration):
        return _execute_watched_blob_source(
            executed_at_utc=executed_at_utc,
            repository=repository,
            settings=settings,
            source=source,
        )
    if isinstance(source.configuration, ConfiguredFolderSourceConfiguration):
        return _execute_configured_folder_source(
            executed_at_utc=executed_at_utc,
            repository=repository,
            settings=settings,
            source=source,
        )
    if isinstance(source.configuration, WatchedSftpPathSourceConfiguration):
        return _execute_watched_sftp_source(
            executed_at_utc=executed_at_utc,
            repository=repository,
            settings=settings,
            source=source,
        )
    if isinstance(source.configuration, EmailConnectorSourceConfiguration):
        return _execute_email_connector_source(
            executed_at_utc=executed_at_utc,
            repository=repository,
            settings=settings,
            source=source,
        )

    raise IntakeSourceConfigurationError(
        "Only watched Azure Blob prefix, configured folder, watched SFTP "
        "path, and email connector sources are supported by this execution "
        "route."
    )

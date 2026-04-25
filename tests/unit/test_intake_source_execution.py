"""Unit tests for supported intake-source execution paths."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from document_intelligence import intake_sources
from document_intelligence.models import (
    ConfiguredFolderSourceConfiguration,
    DocumentSource,
    DuplicateDetectionResult,
    DuplicateDetectionStatus,
    EmailConnectorSourceConfiguration,
    IntakeSourceRecord,
    ManualPacketDocumentInput,
    ManualPacketDocumentRecord,
    ManualPacketIntakeRequest,
    ManualPacketIntakeResponse,
    PacketStatus,
    PartnerApiFeedSourceConfiguration,
    ProcessingJobStatus,
    ProcessingStageName,
    SourcePacketIngestionRequest,
    WatchedBlobPrefixSourceConfiguration,
    WatchedSftpPathSourceConfiguration,
)
from document_intelligence.settings import AppSettings
from document_intelligence.utils.blob_storage import ListedBlobAsset
from document_intelligence.utils.watched_sftp import ListedWatchedSftpAsset


def build_settings(**overrides: object) -> AppSettings:
    """Build app settings for watched blob execution tests."""

    values: dict[str, object] = {
        "sql_connection_string": (
            "Server=tcp:test-sql.database.windows.net,1433;"
            "Database=docintel;User ID=docintel;Password=Password123!"
        ),
        "storage_connection_string": "UseDevelopmentStorage=true",
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


def build_source_record() -> IntakeSourceRecord:
    """Build a watched blob intake-source definition for execution tests."""

    return IntakeSourceRecord(
        source_id="src_ops_blob",
        source_name="Ops blob watcher",
        owner_email="ops@example.com",
        polling_interval_minutes=5,
        configuration=WatchedBlobPrefixSourceConfiguration(
            storage_account_name="stdocdev123",
            container_name="landing-documents",
            blob_prefix="ops/inbox/",
            include_subdirectories=False,
        ),
        created_at_utc=datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
    )


def build_configured_folder_source_record(
    folder_path: str,
    *,
    file_pattern: str = "*",
    recursive: bool = False,
) -> IntakeSourceRecord:
    """Build a configured-folder intake-source definition for execution tests."""

    return IntakeSourceRecord(
        source_id="src_ops_folder",
        source_name="Ops folder watcher",
        owner_email="ops@example.com",
        polling_interval_minutes=5,
        configuration=ConfiguredFolderSourceConfiguration(
            folder_path=folder_path,
            file_pattern=file_pattern,
            recursive=recursive,
        ),
        created_at_utc=datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
    )


def build_watched_sftp_source_record() -> IntakeSourceRecord:
    """Build a watched-SFTP intake-source definition for execution tests."""

    return IntakeSourceRecord(
        source_id="src_ops_sftp",
        source_name="Ops SFTP watcher",
        owner_email="ops@example.com",
        polling_interval_minutes=5,
        configuration=WatchedSftpPathSourceConfiguration(
            storage_account_name="stdoctestnwigok",
            sftp_path="/landing-documents/ops/sftp-inbox/",
            local_user_name="ingest-user",
        ),
        created_at_utc=datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
    )


def build_email_connector_source_record(folder_path: str) -> IntakeSourceRecord:
    """Build an email-connector intake-source definition for execution tests."""

    return IntakeSourceRecord(
        source_id="src_ops_email",
        source_name="Ops inbox connector",
        owner_email="ops@example.com",
        polling_interval_minutes=5,
        configuration=EmailConnectorSourceConfiguration(
            mailbox_address="ops@example.com",
            folder_path=folder_path,
            attachment_extension_allowlist=(".pdf", ".docx"),
        ),
        created_at_utc=datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
    )


def build_partner_source_record() -> IntakeSourceRecord:
    """Build a partner API intake-source definition for ingestion tests."""

    return IntakeSourceRecord(
        source_id="src_partner_api",
        source_name="County referrals",
        owner_email="partners@example.com",
        polling_interval_minutes=5,
        credentials_reference="kv://partner/referrals",
        configuration=PartnerApiFeedSourceConfiguration(
            partner_name="County court partner",
            relative_path="/api/intake/partner-referrals/v1",
            auth_scheme="hmac",
        ),
        created_at_utc=datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
    )


def build_email_message_bytes() -> bytes:
    """Build a staged .eml message with two supported attachments."""

    message = EmailMessage()
    message["From"] = "borrower@example.com"
    message["To"] = "ops@example.com"
    message["Subject"] = "Borrower hardship packet"
    message.set_content("Please find the supporting documents attached.")
    message.add_attachment(
        b"%PDF-1.4 email attachment",
        maintype="application",
        subtype="pdf",
        filename="statement.pdf",
    )
    message.add_attachment(
        b"PK\x03\x04docx attachment",
        maintype="application",
        subtype=(
            "vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        filename="hardship-letter.docx",
    )
    return message.as_bytes()


def build_packet_response(
    *,
    document_count: int = 1,
    duplicate_detection_status: DuplicateDetectionStatus = (
        DuplicateDetectionStatus.UNIQUE
    ),
    idempotency_reused_existing_packet: bool = False,
    packet_id: str,
    packet_name: str,
    reused_existing_packet_id: str | None = None,
    should_skip_ingestion: bool = False,
    source: DocumentSource,
    source_uri: str,
) -> ManualPacketIntakeResponse:
    """Build a reusable manual-packet response payload for execution tests."""

    return ManualPacketIntakeResponse(
        packet_id=packet_id,
        packet_name=packet_name,
        source=source,
        source_uri=source_uri,
        submitted_by="ops@example.com",
        document_count=document_count,
        duplicate_detection=DuplicateDetectionResult(
            reused_existing_packet_id=reused_existing_packet_id,
            should_skip_ingestion=should_skip_ingestion,
            status=duplicate_detection_status,
        ),
        idempotency_reused_existing_packet=idempotency_reused_existing_packet,
        received_at_utc=datetime(2026, 4, 7, 9, 8, tzinfo=UTC),
        documents=tuple(
            ManualPacketDocumentRecord(
                document_id=f"doc_{packet_id}_{index + 1}",
                file_name=packet_name,
                content_type="application/pdf",
                blob_uri=(
                    "https://storage.example/raw/"
                    f"{packet_id}-{index + 1}.pdf"
                ),
                file_hash_sha256="a" * 64,
                processing_job_id=f"job_{packet_id}_{index + 1}",
                processing_stage=ProcessingStageName.OCR,
                processing_job_status=ProcessingJobStatus.QUEUED,
                status=PacketStatus.RECEIVED,
            )
            for index in range(document_count)
        ),
    )


class FakeRepository:
    """Repository stub that records source execution state updates."""

    def __init__(self, source: IntakeSourceRecord) -> None:
        self.source = source
        self.recorded_error_message: str | None = None
        self.recorded_last_seen_at_utc: datetime | None = None
        self.recorded_last_success_at_utc: datetime | None = None

    def get_intake_source(self, source_id: str) -> IntakeSourceRecord:
        assert source_id == self.source.source_id
        return self.source

    def record_intake_source_execution(
        self,
        source_id: str,
        *,
        last_error_message: str | None,
        last_seen_at_utc: datetime,
        last_success_at_utc: datetime | None,
    ) -> None:
        assert source_id == self.source.source_id
        self.recorded_error_message = last_error_message
        self.recorded_last_seen_at_utc = last_seen_at_utc
        self.recorded_last_success_at_utc = last_success_at_utc


def test_execute_intake_source_processes_watched_blob_prefix(
    monkeypatch: MonkeyPatch,
) -> None:
    """Watched blob execution should create packets and record failures."""

    repository = FakeRepository(build_source_record())
    captured_request: dict[str, ManualPacketIntakeRequest] = {}

    monkeypatch.setattr(intake_sources, "_get_repository", lambda settings: repository)
    monkeypatch.setattr(
        intake_sources,
        "list_blob_assets",
        lambda **kwargs: (
            ListedBlobAsset(
                blob_name="ops/inbox/statement.pdf",
                container_name="landing-documents",
                content_length_bytes=64,
                content_type=None,
                etag='"etag-1"',
                last_modified_utc=datetime(2026, 4, 7, 9, 5, tzinfo=UTC),
                storage_uri="https://storage.example/landing-documents/ops/inbox/statement.pdf",
            ),
            ListedBlobAsset(
                blob_name="ops/inbox/subdir/ignored.pdf",
                container_name="landing-documents",
                content_length_bytes=32,
                content_type="application/pdf",
                etag='"etag-ignore"',
                last_modified_utc=datetime(2026, 4, 7, 9, 6, tzinfo=UTC),
                storage_uri="https://storage.example/landing-documents/ops/inbox/subdir/ignored.pdf",
            ),
            ListedBlobAsset(
                blob_name="ops/inbox/broken.pdf",
                container_name="landing-documents",
                content_length_bytes=12,
                content_type="application/pdf",
                etag='"etag-2"',
                last_modified_utc=datetime(2026, 4, 7, 9, 7, tzinfo=UTC),
                storage_uri="https://storage.example/landing-documents/ops/inbox/broken.pdf",
            ),
        ),
    )

    def fake_download_blob_bytes(**kwargs: object) -> bytes:
        blob_name = str(kwargs["blob_name"])
        if blob_name.endswith("broken.pdf"):
            raise RuntimeError("download failed")

        return b"%PDF-1.4 watched blob"

    def fake_create_manual_packet_intake(
        request: ManualPacketIntakeRequest,
        settings: object,
    ) -> ManualPacketIntakeResponse:
        del settings
        captured_request["request"] = request
        return build_packet_response(
            duplicate_detection_status=DuplicateDetectionStatus.EXACT_DUPLICATE,
            idempotency_reused_existing_packet=True,
            packet_id="pkt_existing_001",
            packet_name="statement.pdf",
            reused_existing_packet_id="pkt_existing_001",
            should_skip_ingestion=True,
            source=DocumentSource.AZURE_BLOB,
            source_uri=(
                "https://storage.example/landing-documents/ops/inbox/statement.pdf"
                "?etag=etag-1"
            ),
        )

    monkeypatch.setattr(
        intake_sources,
        "download_blob_bytes",
        fake_download_blob_bytes,
    )
    monkeypatch.setattr(
        intake_sources,
        "create_manual_packet_intake",
        fake_create_manual_packet_intake,
    )

    response = intake_sources.execute_intake_source(
        "src_ops_blob",
        build_settings(),
    )

    typed_request = captured_request["request"]
    assert response.source_id == "src_ops_blob"
    assert response.seen_blob_count == 2
    assert response.processed_blob_count == 1
    assert response.reused_packet_count == 1
    assert response.failed_blob_count == 1
    assert response.packet_results[0].packet_id == "pkt_existing_001"
    assert response.failures[0].blob_name == "ops/inbox/broken.pdf"
    assert repository.recorded_last_seen_at_utc is not None
    assert repository.recorded_last_success_at_utc is not None
    assert repository.recorded_error_message is not None
    assert "broken.pdf" in repository.recorded_error_message
    assert typed_request.source == DocumentSource.AZURE_BLOB
    assert typed_request.source_uri == (
        "https://storage.example/landing-documents/ops/inbox/statement.pdf?etag=etag-1"
    )
    assert typed_request.packet_tags == (
        "source_id:src_ops_blob",
        "source_kind:watched_blob_prefix",
    )
    assert typed_request.documents[0].file_name == "statement.pdf"
    assert typed_request.documents[0].content_type == "application/pdf"


def test_execute_intake_source_processes_configured_folder(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Configured-folder execution should auto-import matching top-level files."""

    source_root = tmp_path / "watched"
    source_root.mkdir()
    (source_root / "statement.pdf").write_bytes(b"%PDF-1.4 configured folder")
    (source_root / "notes.txt").write_text("skip me", encoding="utf-8")
    nested_dir = source_root / "subdir"
    nested_dir.mkdir()
    (nested_dir / "nested.pdf").write_bytes(b"%PDF-1.4 nested")

    repository = FakeRepository(
        build_configured_folder_source_record(
            str(source_root),
            file_pattern="*.pdf",
            recursive=False,
        )
    )
    captured_requests: list[ManualPacketIntakeRequest] = []

    monkeypatch.setattr(intake_sources, "_get_repository", lambda settings: repository)

    def fake_create_manual_packet_intake(
        request: ManualPacketIntakeRequest,
        settings: object,
    ) -> ManualPacketIntakeResponse:
        del settings
        captured_requests.append(request)
        assert request.source_uri is not None
        return build_packet_response(
            packet_id="pkt_folder_001",
            packet_name=request.packet_name,
            source=DocumentSource.CONFIGURED_FOLDER,
            source_uri=request.source_uri,
        )

    monkeypatch.setattr(
        intake_sources,
        "create_manual_packet_intake",
        fake_create_manual_packet_intake,
    )

    response = intake_sources.execute_intake_source(
        "src_ops_folder",
        build_settings(),
    )

    assert response.source_kind == repository.source.configuration.source_kind
    assert response.seen_blob_count == 1
    assert response.processed_blob_count == 1
    assert response.failed_blob_count == 0
    assert response.packet_results[0].blob_name == "statement.pdf"
    assert repository.recorded_error_message is None
    assert repository.recorded_last_success_at_utc is not None
    assert len(captured_requests) == 1
    assert captured_requests[0].source == DocumentSource.CONFIGURED_FOLDER
    assert captured_requests[0].packet_name == "statement.pdf"
    assert captured_requests[0].packet_tags == (
        "source_id:src_ops_folder",
        "source_kind:configured_folder",
    )
    assert captured_requests[0].source_uri is not None
    assert captured_requests[0].source_uri.startswith("file:///")
    assert "mtime_ns=" in captured_requests[0].source_uri
    assert captured_requests[0].documents[0].file_name == "statement.pdf"
    assert captured_requests[0].documents[0].content_type == "application/pdf"
    assert captured_requests[0].documents[0].source_tags == (
        "src_ops_folder",
        "configured_folder",
        "relative_path:statement.pdf",
    )


def test_execute_intake_source_processes_watched_sftp_path(
    monkeypatch: MonkeyPatch,
) -> None:
    """Watched-SFTP execution should create packets and record failures."""

    repository = FakeRepository(build_watched_sftp_source_record())
    captured_request: dict[str, ManualPacketIntakeRequest] = {}

    monkeypatch.setattr(intake_sources, "_get_repository", lambda settings: repository)
    monkeypatch.setattr(
        intake_sources,
        "list_watched_sftp_assets",
        lambda **kwargs: (
            ListedWatchedSftpAsset(
                blob_name="ops/sftp-inbox/statement.pdf",
                container_name="landing-documents",
                content_length_bytes=64,
                content_type=None,
                etag='"etag-1"',
                last_modified_utc=datetime(2026, 4, 7, 9, 5, tzinfo=UTC),
                relative_path="statement.pdf",
                source_path="landing-documents/ops/sftp-inbox/statement.pdf",
                source_uri=(
                    "sftp://stdoctestnwigok/landing-documents/ops/sftp-inbox/"
                    "statement.pdf?etag=etag-1"
                ),
            ),
            ListedWatchedSftpAsset(
                blob_name="ops/sftp-inbox/broken.pdf",
                container_name="landing-documents",
                content_length_bytes=12,
                content_type="application/pdf",
                etag='"etag-2"',
                last_modified_utc=datetime(2026, 4, 7, 9, 6, tzinfo=UTC),
                relative_path="broken.pdf",
                source_path="landing-documents/ops/sftp-inbox/broken.pdf",
                source_uri=(
                    "sftp://stdoctestnwigok/landing-documents/ops/sftp-inbox/"
                    "broken.pdf?etag=etag-2"
                ),
            ),
        ),
    )

    def fake_read_watched_sftp_asset_bytes(
        asset: ListedWatchedSftpAsset,
        *,
        storage_connection_string: str,
    ) -> bytes:
        del storage_connection_string
        if asset.relative_path.endswith("broken.pdf"):
            raise RuntimeError("download failed")

        return b"%PDF-1.4 watched sftp"

    def fake_create_manual_packet_intake(
        request: ManualPacketIntakeRequest,
        settings: object,
    ) -> ManualPacketIntakeResponse:
        del settings
        captured_request["request"] = request
        assert request.source_uri is not None
        return build_packet_response(
            packet_id="pkt_sftp_001",
            packet_name=request.packet_name,
            source=DocumentSource.AZURE_SFTP,
            source_uri=request.source_uri,
        )

    monkeypatch.setattr(
        intake_sources,
        "read_watched_sftp_asset_bytes",
        fake_read_watched_sftp_asset_bytes,
    )
    monkeypatch.setattr(
        intake_sources,
        "create_manual_packet_intake",
        fake_create_manual_packet_intake,
    )

    response = intake_sources.execute_intake_source(
        "src_ops_sftp",
        build_settings(),
    )

    typed_request = captured_request["request"]
    assert response.source_id == "src_ops_sftp"
    assert response.seen_blob_count == 2
    assert response.processed_blob_count == 1
    assert response.failed_blob_count == 1
    assert response.packet_results[0].packet_id == "pkt_sftp_001"
    assert response.failures[0].blob_name == (
        "landing-documents/ops/sftp-inbox/broken.pdf"
    )
    assert repository.recorded_last_seen_at_utc is not None
    assert repository.recorded_last_success_at_utc is not None
    assert repository.recorded_error_message is not None
    assert "broken.pdf" in repository.recorded_error_message
    assert typed_request.source == DocumentSource.AZURE_SFTP
    assert typed_request.source_uri == (
        "sftp://stdoctestnwigok/landing-documents/ops/sftp-inbox/"
        "statement.pdf?etag=etag-1"
    )
    assert typed_request.packet_tags == (
        "source_id:src_ops_sftp",
        "source_kind:watched_sftp_path",
    )
    assert typed_request.documents[0].file_name == "statement.pdf"
    assert typed_request.documents[0].content_type == "application/pdf"
    assert typed_request.documents[0].source_tags == (
        "src_ops_sftp",
        "watched_sftp_path",
        "local_user:ingest-user",
        "relative_path:statement.pdf",
    )


def test_watched_sftp_content_type_falls_back_from_octet_stream() -> None:
    """Watched-SFTP execution should not preserve a generic binary MIME type."""

    asset = ListedWatchedSftpAsset(
        blob_name="ops/sftp-inbox/statement.pdf",
        container_name="landing-documents",
        content_length_bytes=64,
        content_type="application/octet-stream",
        etag='"etag-1"',
        last_modified_utc=datetime(2026, 4, 7, 9, 5, tzinfo=UTC),
        relative_path="statement.pdf",
        source_path="landing-documents/ops/sftp-inbox/statement.pdf",
        source_uri=(
            "sftp://stdoctestnwigok/landing-documents/ops/sftp-inbox/"
            "statement.pdf?etag=etag-1"
        ),
    )

    assert intake_sources._resolve_watched_sftp_content_type(asset) == "application/pdf"


def test_execute_intake_source_processes_email_connector(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Email connector execution should create one packet per staged message."""

    message_path = tmp_path / "borrower-hardship.eml"
    message_path.write_bytes(build_email_message_bytes())
    repository = FakeRepository(
        build_email_connector_source_record(str(tmp_path))
    )
    captured_request: dict[str, ManualPacketIntakeRequest] = {}

    monkeypatch.setattr(intake_sources, "_get_repository", lambda settings: repository)

    def fake_create_manual_packet_intake(
        request: ManualPacketIntakeRequest,
        settings: object,
    ) -> ManualPacketIntakeResponse:
        del settings
        captured_request["request"] = request
        assert request.source_uri is not None
        return build_packet_response(
            document_count=len(request.documents),
            packet_id="pkt_email_001",
            packet_name=request.packet_name,
            source=DocumentSource.EMAIL_CONNECTOR,
            source_uri=request.source_uri,
        )

    monkeypatch.setattr(
        intake_sources,
        "create_manual_packet_intake",
        fake_create_manual_packet_intake,
    )

    response = intake_sources.execute_intake_source(
        "src_ops_email",
        build_settings(),
    )

    typed_request = captured_request["request"]
    assert response.source_id == "src_ops_email"
    assert response.seen_blob_count == 1
    assert response.processed_blob_count == 1
    assert response.failed_blob_count == 0
    assert response.packet_results[0].document_count == 2
    assert response.packet_results[0].blob_name == message_path.name
    assert repository.recorded_error_message is None
    assert repository.recorded_last_success_at_utc is not None
    assert typed_request.source == DocumentSource.EMAIL_CONNECTOR
    assert typed_request.packet_name == "Borrower hardship packet"
    assert typed_request.packet_tags == (
        "source_id:src_ops_email",
        "source_kind:email_connector",
    )
    assert len(typed_request.documents) == 2
    assert typed_request.documents[0].file_name == "statement.pdf"
    assert typed_request.documents[0].source_tags == (
        "src_ops_email",
        "email_connector",
        "mailbox:ops@example.com",
        f"folder:{tmp_path}",
        f"relative_path:{message_path.name}",
        "subject:Borrower hardship packet",
        "attachment:statement.pdf",
    )


def test_ingest_partner_source_packet_creates_manual_packet(
    monkeypatch: MonkeyPatch,
) -> None:
    """Partner API ingestion should stage the submitted packet through manual intake."""

    repository = FakeRepository(build_partner_source_record())
    captured_request: dict[str, ManualPacketIntakeRequest] = {}

    monkeypatch.setattr(intake_sources, "_get_repository", lambda settings: repository)

    def fake_create_manual_packet_intake(
        request: ManualPacketIntakeRequest,
        settings: object,
    ) -> ManualPacketIntakeResponse:
        del settings
        captured_request["request"] = request
        return build_packet_response(
            document_count=len(request.documents),
            packet_id="pkt_partner_001",
            packet_name=request.packet_name,
            source=DocumentSource.PARTNER_API_FEED,
            source_uri=request.source_uri or "partner://src_partner_api",
        )

    monkeypatch.setattr(
        intake_sources,
        "create_manual_packet_intake",
        fake_create_manual_packet_intake,
    )

    response = intake_sources.ingest_partner_source_packet(
        "src_partner_api",
        SourcePacketIngestionRequest(
            packet_name="county-referral-1001",
            documents=(
                ManualPacketDocumentInput(
                    file_name="referral.pdf",
                    content_type="application/pdf",
                    document_content_base64="JVBERi0xLjQ=",
                ),
            ),
        ),
        build_settings(),
    )

    typed_request = captured_request["request"]
    assert response.packet_id == "pkt_partner_001"
    assert repository.recorded_error_message is None
    assert repository.recorded_last_seen_at_utc is not None
    assert repository.recorded_last_success_at_utc is not None
    assert typed_request.source == DocumentSource.PARTNER_API_FEED
    assert typed_request.source_uri == (
        "partner://src_partner_api/api/intake/partner-referrals/v1"
    )
    assert typed_request.packet_tags == (
        "source_id:src_partner_api",
        "source_kind:partner_api_feed",
        "partner_name:County court partner",
        "auth_scheme:hmac",
    )
    assert typed_request.documents[0].source_tags == (
        "src_partner_api",
        "partner_api_feed",
        "partner_name:County court partner",
        "relative_path:/api/intake/partner-referrals/v1",
        "auth_scheme:hmac",
    )


def test_execute_intake_source_processes_configured_folder_recursively(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Configured-folder execution should honor recursive file discovery."""

    source_root = tmp_path / "recursive"
    nested_dir = source_root / "a" / "b"
    nested_dir.mkdir(parents=True)
    (source_root / "top.pdf").write_bytes(b"%PDF-1.4 top")
    (nested_dir / "nested.pdf").write_bytes(b"%PDF-1.4 nested")

    repository = FakeRepository(
        build_configured_folder_source_record(
            str(source_root),
            file_pattern="*.pdf",
            recursive=True,
        )
    )
    captured_packet_names: list[str] = []

    monkeypatch.setattr(intake_sources, "_get_repository", lambda settings: repository)

    def fake_create_manual_packet_intake(
        request: ManualPacketIntakeRequest,
        settings: object,
    ) -> ManualPacketIntakeResponse:
        del settings
        captured_packet_names.append(request.packet_name)
        assert request.source_uri is not None
        return build_packet_response(
            packet_id=f"pkt_{request.packet_name.replace('.', '_')}",
            packet_name=request.packet_name,
            source=DocumentSource.CONFIGURED_FOLDER,
            source_uri=request.source_uri,
        )

    monkeypatch.setattr(
        intake_sources,
        "create_manual_packet_intake",
        fake_create_manual_packet_intake,
    )

    response = intake_sources.execute_intake_source(
        "src_ops_folder",
        build_settings(),
    )

    assert response.seen_blob_count == 2
    assert response.processed_blob_count == 2
    assert response.failed_blob_count == 0
    assert set(captured_packet_names) == {"top.pdf", "nested.pdf"}
    assert {result.blob_name for result in response.packet_results} == {
        "top.pdf",
        "a/b/nested.pdf",
    }


def test_execute_intake_source_skips_unstable_configured_folder_files(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Configured-folder execution should ignore files that are still too fresh."""

    source_root = tmp_path / "stability"
    source_root.mkdir()
    stable_file = source_root / "stable.pdf"
    fresh_file = source_root / "fresh.pdf"
    stable_file.write_bytes(b"stable")
    fresh_file.write_bytes(b"fresh")

    old_timestamp = (datetime.now(UTC) - timedelta(minutes=5)).timestamp()
    os.utime(stable_file, (old_timestamp, old_timestamp))

    repository = FakeRepository(
        build_configured_folder_source_record(
            str(source_root),
            file_pattern="*.pdf",
            recursive=False,
        )
    )
    captured_packet_names: list[str] = []

    monkeypatch.setattr(intake_sources, "_get_repository", lambda settings: repository)

    def fake_create_manual_packet_intake(
        request: ManualPacketIntakeRequest,
        settings: object,
    ) -> ManualPacketIntakeResponse:
        del settings
        captured_packet_names.append(request.packet_name)
        assert request.source_uri is not None
        return build_packet_response(
            packet_id="pkt_folder_stable_001",
            packet_name=request.packet_name,
            source=DocumentSource.CONFIGURED_FOLDER,
            source_uri=request.source_uri,
        )

    monkeypatch.setattr(
        intake_sources,
        "create_manual_packet_intake",
        fake_create_manual_packet_intake,
    )

    response = intake_sources.execute_intake_source(
        "src_ops_folder",
        build_settings(configured_folder_min_stable_age_seconds=60),
    )

    assert response.seen_blob_count == 1
    assert response.processed_blob_count == 1
    assert response.failed_blob_count == 0
    assert captured_packet_names == ["stable.pdf"]


def test_execute_intake_source_records_configured_folder_listing_failure(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Configured-folder execution should persist listing failures."""

    missing_path = tmp_path / "missing"
    repository = FakeRepository(
        build_configured_folder_source_record(str(missing_path))
    )
    monkeypatch.setattr(intake_sources, "_get_repository", lambda settings: repository)

    with pytest.raises(RuntimeError, match="Failed to read configured folder source"):
        intake_sources.execute_intake_source("src_ops_folder", build_settings())

    assert repository.recorded_last_seen_at_utc is not None
    assert repository.recorded_last_success_at_utc is None
    assert repository.recorded_error_message is not None
    assert "does not exist" in repository.recorded_error_message


def test_execute_intake_source_rejects_unsupported_source_kind(
    monkeypatch: MonkeyPatch,
) -> None:
    """Only implemented executable source kinds should run through this route."""

    source = build_source_record().model_copy(
        update={
            "configuration": PartnerApiFeedSourceConfiguration(
                partner_name="County court partner",
                relative_path="/api/intake/partner-referrals/v1",
                auth_scheme="hmac",
            )
        }
    )
    repository = FakeRepository(source)
    monkeypatch.setattr(intake_sources, "_get_repository", lambda settings: repository)

    with pytest.raises(
        intake_sources.IntakeSourceConfigurationError,
        match=(
            "Only watched Azure Blob prefix, configured folder, watched SFTP "
            "path, and email connector sources"
        ),
    ):
        intake_sources.execute_intake_source("src_ops_blob", build_settings())

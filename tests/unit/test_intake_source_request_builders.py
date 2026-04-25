"""Unit tests for intake-source request builder helpers."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from pathlib import Path

import pytest

from document_intelligence import intake_sources
from document_intelligence.models import (
    ConfiguredFolderSourceConfiguration,
    DocumentSource,
    EmailConnectorSourceConfiguration,
    IntakeSourceRecord,
    ManualPacketDocumentInput,
    PartnerApiFeedSourceConfiguration,
    SourcePacketIngestionRequest,
    WatchedBlobPrefixSourceConfiguration,
    WatchedSftpPathSourceConfiguration,
)
from document_intelligence.utils.blob_storage import ListedBlobAsset
from document_intelligence.utils.configured_folder import ListedConfiguredFolderAsset
from document_intelligence.utils.email_connector import (
    ListedEmailConnectorAsset,
    ListedEmailConnectorDocument,
)
from document_intelligence.utils.watched_sftp import ListedWatchedSftpAsset


def build_blob_source_record() -> IntakeSourceRecord:
    """Build a watched-blob source definition for builder tests."""

    return IntakeSourceRecord(
        source_id="src_ops_blob",
        source_name="Ops blob watcher",
        polling_interval_minutes=5,
        configuration=WatchedBlobPrefixSourceConfiguration(
            storage_account_name="stdocdev123",
            container_name="landing-documents",
            blob_prefix="ops/inbox/",
            include_subdirectories=False,
        ),
        created_at_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
    )


def build_configured_folder_source_record() -> IntakeSourceRecord:
    """Build a configured-folder source definition for builder tests."""

    return IntakeSourceRecord(
        source_id="src_ops_folder",
        source_name="Ops folder watcher",
        polling_interval_minutes=5,
        configuration=ConfiguredFolderSourceConfiguration(
            folder_path="C:/watched",
            file_pattern="*.pdf",
            recursive=True,
        ),
        created_at_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
    )


def build_watched_sftp_source_record() -> IntakeSourceRecord:
    """Build a watched-SFTP source definition for builder tests."""

    return IntakeSourceRecord(
        source_id="src_ops_sftp",
        source_name="Ops SFTP watcher",
        polling_interval_minutes=5,
        configuration=WatchedSftpPathSourceConfiguration(
            storage_account_name="stdoctestnwigok",
            sftp_path="/landing-documents/ops/sftp-inbox/",
            local_user_name="ingest-user",
        ),
        created_at_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
    )


def build_email_source_record() -> IntakeSourceRecord:
    """Build an email-connector source definition for builder tests."""

    return IntakeSourceRecord(
        source_id="src_ops_email",
        source_name="Ops inbox connector",
        polling_interval_minutes=5,
        configuration=EmailConnectorSourceConfiguration(
            mailbox_address="ops@example.com",
            folder_path="Inbox/Hardship",
            attachment_extension_allowlist=(".pdf", ".txt"),
        ),
        created_at_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
    )


def build_partner_source_record() -> IntakeSourceRecord:
    """Build a partner-feed source definition for builder tests."""

    return IntakeSourceRecord(
        source_id="src_partner_api",
        source_name="County referrals",
        polling_interval_minutes=5,
        configuration=PartnerApiFeedSourceConfiguration(
            partner_name="County court partner",
            relative_path="/api/intake/partner-referrals/v1",
            auth_scheme="hmac",
        ),
        created_at_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
    )


def test_build_blob_intake_request_normalizes_blob_metadata() -> None:
    """Watched-blob builders should derive stable packet names, URIs, and tags."""

    blob_bytes = b"%PDF-1.4 watched blob"
    request = intake_sources._build_blob_intake_request(
        blob=ListedBlobAsset(
            blob_name="ops/inbox/statement.pdf",
            container_name="landing-documents",
            content_length_bytes=len(blob_bytes),
            content_type="application/octet-stream",
            etag='"etag-1"',
            last_modified_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
            storage_uri=(
                "https://storage.example/landing-documents/ops/inbox/statement.pdf"
            ),
        ),
        blob_bytes=blob_bytes,
        source=build_blob_source_record(),
    )

    assert request.packet_name == "statement.pdf"
    assert request.source == DocumentSource.AZURE_BLOB
    assert request.source_uri == (
        "https://storage.example/landing-documents/ops/inbox/statement.pdf"
        "?etag=etag-1"
    )
    assert request.submitted_by == "intake-source:src_ops_blob"
    assert request.packet_tags == (
        "source_id:src_ops_blob",
        "source_kind:watched_blob_prefix",
    )
    assert request.documents[0].content_type == "application/pdf"
    assert request.documents[0].file_name == "statement.pdf"
    assert request.documents[0].source_tags == (
        "src_ops_blob",
        "watched_blob_prefix",
    )
    assert base64.b64decode(request.documents[0].document_content_base64) == blob_bytes


def test_build_configured_folder_intake_request_uses_relative_path_metadata() -> None:
    """Configured-folder builders should preserve source URIs and relative-path tags."""

    file_bytes = b"%PDF-1.4 configured folder"
    request = intake_sources._build_configured_folder_intake_request(
        file_asset=ListedConfiguredFolderAsset(
            content_length_bytes=len(file_bytes),
            content_type=None,
            file_path=Path("C:/watched/cases/case-1001/statement.pdf"),
            last_modified_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
            relative_path="cases/case-1001/statement.pdf",
            source_uri=(
                "file:///C:/watched/cases/case-1001/statement.pdf?"
                "mtime_ns=1&size=27"
            ),
        ),
        file_bytes=file_bytes,
        source=build_configured_folder_source_record(),
    )

    assert request.packet_name == "statement.pdf"
    assert request.source == DocumentSource.CONFIGURED_FOLDER
    assert request.source_uri == (
        "file:///C:/watched/cases/case-1001/statement.pdf?mtime_ns=1&size=27"
    )
    assert request.submitted_by == "intake-source:src_ops_folder"
    assert request.documents[0].content_type == "application/pdf"
    assert request.documents[0].source_tags == (
        "src_ops_folder",
        "configured_folder",
        "relative_path:cases/case-1001/statement.pdf",
    )
    assert base64.b64decode(request.documents[0].document_content_base64) == file_bytes


def test_build_watched_sftp_intake_request_captures_local_user_context() -> None:
    """Watched-SFTP builders should include local-user and relative-path tags."""

    asset_bytes = b"%PDF-1.4 watched sftp"
    request = intake_sources._build_watched_sftp_intake_request(
        asset=ListedWatchedSftpAsset(
            blob_name="landing-documents/ops/sftp-inbox/statement.pdf",
            container_name="landing-documents",
            content_length_bytes=len(asset_bytes),
            content_type="application/octet-stream",
            etag='"etag-2"',
            last_modified_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
            relative_path="ops/sftp-inbox/statement.pdf",
            source_path="/landing-documents/ops/sftp-inbox/statement.pdf",
            source_uri=(
                "sftp://stdoctestnwigok/landing-documents/ops/sftp-inbox/"
                "statement.pdf?etag=etag-2"
            ),
        ),
        asset_bytes=asset_bytes,
        source=build_watched_sftp_source_record(),
    )

    assert request.packet_name == "statement.pdf"
    assert request.source == DocumentSource.AZURE_SFTP
    assert request.source_uri == (
        "sftp://stdoctestnwigok/landing-documents/ops/sftp-inbox/"
        "statement.pdf?etag=etag-2"
    )
    assert request.submitted_by == "intake-source:src_ops_sftp"
    assert request.documents[0].content_type == "application/pdf"
    assert request.documents[0].source_tags == (
        "src_ops_sftp",
        "watched_sftp_path",
        "local_user:ingest-user",
        "relative_path:ops/sftp-inbox/statement.pdf",
    )


def test_build_email_connector_intake_request_builds_attachment_documents() -> None:
    """Email builders should fall back to mailbox metadata and one doc per attachment."""

    asset = ListedEmailConnectorAsset(
        content_length_bytes=256,
        content_type="message/rfc822",
        documents=(
            ListedEmailConnectorDocument(
                content_bytes=b"%PDF-1.4 email attachment",
                content_type="application/octet-stream",
                file_name="statement.pdf",
            ),
            ListedEmailConnectorDocument(
                content_bytes=b"borrower note",
                content_type=None,
                file_name="borrower-note.txt",
            ),
        ),
        file_name="hardship-case.eml",
        last_modified_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        packet_name="   ",
        relative_path="2026/04/hardship-case.eml",
        source_uri=(
            "email://connector/ops@example.com/hardship/2026/04/"
            "hardship-case.eml?mtime_ns=1&size=256"
        ),
        subject="Borrower hardship packet",
    )

    request = intake_sources._build_email_connector_intake_request(
        asset=asset,
        source=build_email_source_record(),
    )

    assert request.packet_name == "hardship-case.eml"
    assert request.source == DocumentSource.EMAIL_CONNECTOR
    assert request.source_uri == asset.source_uri
    assert request.submitted_by == "ops@example.com"
    assert len(request.documents) == 2
    assert request.documents[0].content_type == "application/pdf"
    assert request.documents[0].source_tags == (
        "src_ops_email",
        "email_connector",
        "mailbox:ops@example.com",
        "folder:Inbox/Hardship",
        "relative_path:2026/04/hardship-case.eml",
        "subject:Borrower hardship packet",
        "attachment:statement.pdf",
    )
    assert request.documents[1].content_type == "text/plain"
    assert request.documents[1].source_tags == (
        "src_ops_email",
        "email_connector",
        "mailbox:ops@example.com",
        "folder:Inbox/Hardship",
        "relative_path:2026/04/hardship-case.eml",
        "subject:Borrower hardship packet",
        "attachment:borrower-note.txt",
    )


def test_build_email_connector_intake_request_requires_documents() -> None:
    """Email builders should reject staged messages without supported documents."""

    with pytest.raises(ValueError, match="at least one supported attachment"):
        intake_sources._build_email_connector_intake_request(
            asset=ListedEmailConnectorAsset(
                content_length_bytes=1,
                content_type="message/rfc822",
                documents=(),
                file_name="empty.eml",
                last_modified_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
                packet_name="empty",
                relative_path="2026/04/empty.eml",
                source_uri="email://connector/ops@example.com/hardship/empty.eml",
                subject="Empty",
            ),
            source=build_email_source_record(),
        )


def test_build_partner_api_intake_request_merges_tags_and_defaults() -> None:
    """Partner builders should add canonical packet and document metadata once."""

    request = intake_sources._build_partner_api_intake_request(
        request=SourcePacketIngestionRequest(
            packet_id="pkt_partner_001",
            packet_name="Court referral packet",
            packet_tags=(
                "partner_name:County court partner",
                "tenant:public-demo",
            ),
            received_at_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
            documents=(
                ManualPacketDocumentInput(
                    file_name="referral.pdf",
                    content_type="application/pdf",
                    document_content_base64=base64.b64encode(
                        b"%PDF-1.4 partner packet"
                    ).decode("ascii"),
                    source_tags=(
                        "relative_path:/api/intake/partner-referrals/v1",
                        "tenant:public-demo",
                    ),
                ),
            ),
        ),
        source=build_partner_source_record(),
    )

    assert request.packet_id == "pkt_partner_001"
    assert request.source == DocumentSource.PARTNER_API_FEED
    assert request.source_uri == (
        "partner://src_partner_api/api/intake/partner-referrals/v1"
    )
    assert request.submitted_by == "partner-source:src_partner_api"
    assert request.packet_tags == (
        "source_id:src_partner_api",
        "source_kind:partner_api_feed",
        "partner_name:County court partner",
        "auth_scheme:hmac",
        "tenant:public-demo",
    )
    assert request.documents[0].source_summary == (
        "Submitted by partner feed 'County referrals'."
    )
    assert request.documents[0].source_tags == (
        "src_partner_api",
        "partner_api_feed",
        "partner_name:County court partner",
        "relative_path:/api/intake/partner-referrals/v1",
        "auth_scheme:hmac",
        "tenant:public-demo",
    )
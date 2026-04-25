"""Unit tests for archive-aware intake preflight helpers."""

from __future__ import annotations

from io import BytesIO
from struct import pack, pack_into, unpack_from
from zipfile import ZIP_DEFLATED, ZipFile

from document_intelligence.models import ArchivePreflightDisposition
from document_intelligence.utils.archive_preflight import (
    inspect_document_archive_preflight,
)


def build_zip_bytes() -> bytes:
    """Build a ZIP payload with one nested ZIP entry name for inspection tests."""

    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("supporting-document.pdf", b"%PDF-1.4 archive test")
        archive.writestr("nested/archive-child.zip", b"nested zip placeholder")
    return buffer.getvalue()


def build_zip64_bytes() -> bytes:
    """Build a small but valid ZIP64 payload for policy tests."""

    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("supporting-document.pdf", b"%PDF-1.4 zip64 test")

    document_bytes = buffer.getvalue()
    end_of_central_directory_offset = document_bytes.rfind(b"PK\x05\x06")
    if end_of_central_directory_offset < 0:
        raise AssertionError("Expected the test ZIP payload to contain an EOCD")

    (
        _,
        _,
        _,
        entries_on_this_disk,
        total_entries,
        central_directory_size,
        central_directory_offset,
        _,
    ) = unpack_from("<4s4H2LH", document_bytes, end_of_central_directory_offset)
    without_end_of_central_directory = document_bytes[
        :end_of_central_directory_offset
    ]
    zip64_end_of_central_directory_offset = len(without_end_of_central_directory)
    zip64_end_of_central_directory = pack(
        "<4sQ2H2L4Q",
        b"PK\x06\x06",
        44,
        45,
        45,
        0,
        0,
        entries_on_this_disk,
        total_entries,
        central_directory_size,
        central_directory_offset,
    )
    zip64_locator = pack(
        "<4sLQL",
        b"PK\x06\x07",
        0,
        zip64_end_of_central_directory_offset,
        1,
    )
    end_of_central_directory = pack(
        "<4s4H2LH",
        b"PK\x05\x06",
        0xFFFF,
        0xFFFF,
        0xFFFF,
        0xFFFF,
        0xFFFFFFFF,
        0xFFFFFFFF,
        0,
    )
    return (
        without_end_of_central_directory
        + zip64_end_of_central_directory
        + zip64_locator
        + end_of_central_directory
    )


def build_spanned_zip_bytes() -> bytes:
    """Build a ZIP payload whose EOCD advertises a multi-disk archive."""

    document_bytes = bytearray(build_zip_bytes())
    end_of_central_directory_offset = document_bytes.rfind(b"PK\x05\x06")
    if end_of_central_directory_offset < 0:
        raise AssertionError("Expected the test ZIP payload to contain an EOCD")

    pack_into("<H", document_bytes, end_of_central_directory_offset + 4, 1)
    pack_into("<H", document_bytes, end_of_central_directory_offset + 6, 1)
    return bytes(document_bytes)


def test_inspect_document_archive_preflight_returns_not_archive_for_pdf() -> None:
    """Regular PDF uploads should not be treated as archive work."""

    result = inspect_document_archive_preflight(
        content_type="application/pdf",
        document_bytes=b"%PDF-1.4 test",
        file_name="statement.pdf",
    )

    assert result.is_archive is False
    assert result.disposition == ArchivePreflightDisposition.NOT_ARCHIVE
    assert result.entry_count == 0


def test_inspect_document_archive_preflight_detects_zip_and_nested_entries() -> None:
    """Valid ZIP uploads should be routed to archive expansion."""

    result = inspect_document_archive_preflight(
        content_type="application/zip",
        document_bytes=build_zip_bytes(),
        file_name="packet-batch.zip",
    )

    assert result.is_archive is True
    assert result.archive_format == "zip"
    assert result.disposition == ArchivePreflightDisposition.READY_FOR_EXPANSION
    assert result.entry_count == 2
    assert result.uses_zip64 is False
    assert result.nested_archive_count == 1


def test_inspect_document_archive_preflight_marks_zip64_ready() -> None:
    """Single-file ZIP64 uploads should stay eligible for expansion."""

    result = inspect_document_archive_preflight(
        content_type="application/zip",
        document_bytes=build_zip64_bytes(),
        file_name="packet-batch.zip",
    )

    assert result.is_archive is True
    assert result.archive_format == "zip64"
    assert result.disposition == ArchivePreflightDisposition.READY_FOR_EXPANSION
    assert result.uses_zip64 is True
    assert result.is_multipart_archive is False
    assert result.expected_disk_count == 1


def test_inspect_document_archive_preflight_rejects_spanned_zip() -> None:
    """Multipart or spanned ZIP uploads should be quarantined explicitly."""

    result = inspect_document_archive_preflight(
        content_type="application/zip",
        document_bytes=build_spanned_zip_bytes(),
        file_name="packet-batch.zip",
    )

    assert result.is_archive is True
    assert result.disposition == ArchivePreflightDisposition.UNSUPPORTED_ARCHIVE
    assert result.is_multipart_archive is True
    assert result.expected_disk_count == 2
    assert result.message is not None
    assert "Multipart or spanned ZIP archives" in result.message


def test_inspect_document_archive_preflight_marks_corrupt_zip() -> None:
    """Broken ZIP uploads should be flagged for quarantine."""

    result = inspect_document_archive_preflight(
        content_type="application/zip",
        document_bytes=b"PK\x03\x04broken archive",
        file_name="broken-packet.zip",
    )

    assert result.is_archive is True
    assert result.disposition == ArchivePreflightDisposition.CORRUPT_ARCHIVE
    assert result.message is not None


def test_inspect_document_archive_preflight_marks_unsupported_archive() -> None:
    """Recognized non-ZIP archive families should be quarantined early."""

    result = inspect_document_archive_preflight(
        content_type="application/vnd.rar",
        document_bytes=b"Rar! archive",
        file_name="collector-drop.rar",
    )

    assert result.is_archive is True
    assert result.archive_format == "rar"
    assert result.disposition == ArchivePreflightDisposition.UNSUPPORTED_ARCHIVE
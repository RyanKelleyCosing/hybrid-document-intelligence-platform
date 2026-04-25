"""Unit tests for archive expansion helpers."""

from __future__ import annotations

from io import BytesIO
from struct import pack, unpack_from
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from document_intelligence.models import ArchivePreflightDisposition
from document_intelligence.utils.archive_expansion import (
    ArchiveExpansionLimits,
    UnsafeArchiveExpansionError,
    expand_zip_archive,
)


def build_zip_payload(*members: tuple[str, bytes]) -> bytes:
    """Build a ZIP payload containing the supplied members."""

    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        for file_name, content in members:
            archive.writestr(file_name, content)
    return buffer.getvalue()


def build_zip64_payload(*members: tuple[str, bytes]) -> bytes:
    """Build a small but valid ZIP64 payload for expansion tests."""

    document_bytes = build_zip_payload(*members)
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


def test_expand_zip_archive_returns_member_metadata() -> None:
    """Archive expansion should preserve member paths and extracted bytes."""

    payload = build_zip_payload(
        ("nested/supporting-document.pdf", b"%PDF-1.4 child"),
    )

    expanded_members = expand_zip_archive(payload)

    assert len(expanded_members) == 1
    assert expanded_members[0].archive_member_path == "nested/supporting-document.pdf"
    assert expanded_members[0].file_name == "supporting-document.pdf"
    assert expanded_members[0].content_type == "application/pdf"
    assert expanded_members[0].document_bytes == b"%PDF-1.4 child"


def test_expand_zip_archive_supports_zip64_payloads() -> None:
    """ZIP64 payloads should expand like ordinary single-file ZIP archives."""

    payload = build_zip64_payload(("nested/supporting-document.pdf", b"%PDF-1.4"))

    expanded_members = expand_zip_archive(payload)

    assert len(expanded_members) == 1
    assert expanded_members[0].archive_preflight.uses_zip64 is False
    assert expanded_members[0].archive_member_path == "nested/supporting-document.pdf"


def test_expand_zip_archive_normalizes_member_paths() -> None:
    """Relative path segments should be removed from extracted member metadata."""

    payload = build_zip_payload(("../unsafe/../member.txt", b"hello"))

    expanded_members = expand_zip_archive(payload)

    assert expanded_members[0].archive_member_path == "unsafe/member.txt"
    assert expanded_members[0].file_name == "member.txt"


def test_expand_zip_archive_quarantines_duplicate_member_paths() -> None:
    """Duplicate archive member paths should be surfaced as quarantine items."""

    with pytest.warns(UserWarning, match="Duplicate name"):
        payload = build_zip_payload(
            ("duplicate/statement.pdf", b"first"),
            ("duplicate/statement.pdf", b"second"),
        )

    expanded_members = expand_zip_archive(payload)

    assert len(expanded_members) == 2
    assert expanded_members[0].archive_preflight.disposition == (
        ArchivePreflightDisposition.NOT_ARCHIVE
    )
    assert expanded_members[1].archive_preflight.disposition == (
        ArchivePreflightDisposition.UNSAFE_ARCHIVE
    )
    assert "duplicate member path" in (
        expanded_members[1].archive_preflight.message or ""
    )
    assert expanded_members[1].document_bytes == b"second"


def test_expand_zip_archive_recurses_into_nested_zip_members() -> None:
    """Nested ZIP members should appear as first-class lineage nodes."""

    nested_payload = build_zip_payload(("evidence/statement.pdf", b"%PDF-1.4 nested"))
    payload = build_zip_payload(("nested/archive-child.zip", nested_payload))

    expanded_members = expand_zip_archive(payload)

    assert len(expanded_members) == 2
    assert expanded_members[0].archive_depth == 1
    assert expanded_members[0].archive_member_path == "nested/archive-child.zip"
    assert expanded_members[0].archive_preflight.disposition == (
        ArchivePreflightDisposition.READY_FOR_EXPANSION
    )
    assert expanded_members[1].archive_depth == 2
    assert expanded_members[1].parent_archive_member_path == "nested/archive-child.zip"
    assert expanded_members[1].archive_member_path == (
        "nested/archive-child.zip/evidence/statement.pdf"
    )


def test_expand_zip_archive_marks_nested_member_unsafe_when_depth_limit_is_hit(
) -> None:
    """Nested ZIP members beyond the depth limit should be quarantined."""

    deep_payload = build_zip_payload(("evidence/statement.pdf", b"%PDF-1.4 nested"))
    payload = build_zip_payload(("nested/archive-child.zip", deep_payload))

    expanded_members = expand_zip_archive(
        payload,
        limits=ArchiveExpansionLimits(max_archive_depth=1),
    )

    assert len(expanded_members) == 1
    assert expanded_members[0].archive_member_path == "nested/archive-child.zip"
    assert expanded_members[0].archive_preflight.disposition == (
        ArchivePreflightDisposition.UNSAFE_ARCHIVE
    )


def test_expand_zip_archive_raises_for_oversized_expansion() -> None:
    """Root archive expansion should stop when expanded bytes exceed the limit."""

    payload = build_zip_payload(
        ("member-one.pdf", b"12345"),
        ("member-two.pdf", b"67890"),
    )

    with pytest.raises(UnsafeArchiveExpansionError, match="expanded content size"):
        expand_zip_archive(
            payload,
            limits=ArchiveExpansionLimits(max_total_uncompressed_bytes=5),
        )
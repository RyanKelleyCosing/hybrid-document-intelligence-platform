"""Archive inspection helpers used by the Epic 2 intake preflight path."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from struct import error as StructError
from struct import unpack_from
from zipfile import BadZipFile, LargeZipFile, ZipFile

from document_intelligence.models import (
    ArchivePreflightDisposition,
    ArchivePreflightResult,
)

_UNSUPPORTED_ARCHIVE_CONTENT_TYPES = frozenset(
    {
        "application/gzip",
        "application/vnd.rar",
        "application/x-7z-compressed",
        "application/x-bzip2",
        "application/x-gzip",
        "application/x-rar-compressed",
        "application/x-tar",
    }
)
_UNSUPPORTED_ARCHIVE_SUFFIXES = frozenset(
    {
        ".7z",
        ".bz2",
        ".gz",
        ".rar",
        ".tar",
        ".tgz",
        ".txz",
        ".xz",
        ".zipx",
    }
)
_ZIP_CONTENT_TYPES = frozenset(
    {
        "application/x-zip-compressed",
        "application/zip",
    }
)
_ZIP_SIGNATURES = (
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"PK\x07\x08",
)
_END_OF_CENTRAL_DIRECTORY_SIGNATURE = b"PK\x05\x06"
_ZIP64_END_OF_CENTRAL_DIRECTORY_LOCATOR_SIGNATURE = b"PK\x06\x07"
_END_OF_CENTRAL_DIRECTORY_MIN_BYTES = 22
_END_OF_CENTRAL_DIRECTORY_SCAN_BYTES = 65535 + _END_OF_CENTRAL_DIRECTORY_MIN_BYTES
_ZIP64_LOCATOR_BYTES = 20
_MAX_ZIP16_VALUE = 0xFFFF
_MAX_ZIP32_VALUE = 0xFFFFFFFF


@dataclass(frozen=True)
class _ZipEnvelopeInspection:
    """ZIP envelope hints derived before Python opens the archive."""

    expected_disk_count: int | None = None
    is_multipart_archive: bool = False
    uses_zip64: bool = False


def _normalize_content_type(content_type: str) -> str:
    """Return a normalized media type without parameters."""

    return content_type.split(";", maxsplit=1)[0].strip().lower()


def _has_zip_signature(document_bytes: bytes) -> bool:
    """Return whether the byte stream looks like a ZIP payload."""

    return document_bytes.startswith(_ZIP_SIGNATURES)


def _looks_like_zip_upload(
    *,
    file_name: str,
    normalized_content_type: str,
    document_bytes: bytes,
) -> bool:
    """Return whether the upload should be inspected as a ZIP archive."""

    return (
        Path(file_name).suffix.lower() == ".zip"
        or normalized_content_type in _ZIP_CONTENT_TYPES
        or _has_zip_signature(document_bytes)
    )


def _looks_like_unsupported_archive(
    *,
    file_name: str,
    normalized_content_type: str,
) -> bool:
    """Return whether the upload is an archive family we do not expand yet."""

    suffixes = {suffix.lower() for suffix in Path(file_name).suffixes}
    return bool(suffixes & _UNSUPPORTED_ARCHIVE_SUFFIXES) or (
        normalized_content_type in _UNSUPPORTED_ARCHIVE_CONTENT_TYPES
    )


def _resolve_archive_format(file_name: str, normalized_content_type: str) -> str:
    """Return a short format label for archive diagnostics."""

    suffixes = [suffix.lower().lstrip(".") for suffix in Path(file_name).suffixes]
    if suffixes:
        return suffixes[-1]

    if "/" in normalized_content_type:
        return normalized_content_type.rsplit("/", maxsplit=1)[-1]

    return "archive"


def _find_end_of_central_directory_offset(document_bytes: bytes) -> int | None:
    """Return the EOCD offset when the byte stream exposes one."""

    search_start = max(
        0,
        len(document_bytes) - _END_OF_CENTRAL_DIRECTORY_SCAN_BYTES,
    )
    offset = document_bytes.rfind(_END_OF_CENTRAL_DIRECTORY_SIGNATURE, search_start)
    if offset < 0:
        return None

    return offset


def _inspect_zip_envelope(document_bytes: bytes) -> _ZipEnvelopeInspection:
    """Inspect the ZIP envelope for ZIP64 and multipart or spanned hints."""

    eocd_offset = _find_end_of_central_directory_offset(document_bytes)
    if eocd_offset is None:
        return _ZipEnvelopeInspection()

    try:
        (
            _,
            disk_number,
            central_directory_disk_number,
            entries_on_this_disk,
            total_entries,
            central_directory_size,
            central_directory_offset,
            _,
        ) = unpack_from("<4s4H2LH", document_bytes, eocd_offset)
    except StructError:
        return _ZipEnvelopeInspection()

    uses_zip64 = any(
        value == _MAX_ZIP16_VALUE
        for value in (
            disk_number,
            central_directory_disk_number,
            entries_on_this_disk,
            total_entries,
        )
    ) or any(
        value == _MAX_ZIP32_VALUE
        for value in (
            central_directory_size,
            central_directory_offset,
        )
    )
    expected_disk_count = None
    effective_disk_number = disk_number
    effective_central_directory_disk_number = central_directory_disk_number
    effective_entries_on_this_disk = entries_on_this_disk
    effective_total_entries = total_entries
    locator_offset = eocd_offset - _ZIP64_LOCATOR_BYTES
    if locator_offset >= 0 and (
        document_bytes[
            locator_offset : locator_offset + 4
        ]
        == _ZIP64_END_OF_CENTRAL_DIRECTORY_LOCATOR_SIGNATURE
    ):
        try:
            _, _, zip64_end_of_central_directory_offset, total_disk_count = unpack_from(
                "<4sLQL",
                document_bytes,
                locator_offset,
            )
        except StructError:
            total_disk_count = 0
            zip64_end_of_central_directory_offset = 0

        if zip64_end_of_central_directory_offset > 0:
            try:
                (
                    _,
                    _,
                    _,
                    _,
                    effective_disk_number,
                    effective_central_directory_disk_number,
                    effective_entries_on_this_disk,
                    effective_total_entries,
                    _,
                    _,
                ) = unpack_from(
                    "<4sQ2H2L4Q",
                    document_bytes,
                    zip64_end_of_central_directory_offset,
                )
            except StructError:
                effective_disk_number = disk_number
                effective_central_directory_disk_number = (
                    central_directory_disk_number
                )
                effective_entries_on_this_disk = entries_on_this_disk
                effective_total_entries = total_entries

        if total_disk_count > 0:
            expected_disk_count = total_disk_count
        uses_zip64 = True

    if expected_disk_count is None and (
        effective_disk_number > 0 or effective_central_directory_disk_number > 0
    ):
        expected_disk_count = (
            max(
                effective_disk_number,
                effective_central_directory_disk_number,
            )
            + 1
        )

    is_multipart_archive = (
        effective_disk_number > 0
        or effective_central_directory_disk_number > 0
        or effective_entries_on_this_disk != effective_total_entries
        or (expected_disk_count is not None and expected_disk_count > 1)
    )
    return _ZipEnvelopeInspection(
        expected_disk_count=expected_disk_count,
        is_multipart_archive=is_multipart_archive,
        uses_zip64=uses_zip64,
    )


def inspect_document_archive_preflight(
    *,
    content_type: str,
    document_bytes: bytes,
    file_name: str,
) -> ArchivePreflightResult:
    """Inspect one uploaded document and return archive-routing metadata."""

    normalized_content_type = _normalize_content_type(content_type)

    if _looks_like_zip_upload(
        file_name=file_name,
        normalized_content_type=normalized_content_type,
        document_bytes=document_bytes,
    ):
        zip_envelope = _inspect_zip_envelope(document_bytes)
        if zip_envelope.is_multipart_archive:
            return ArchivePreflightResult(
                archive_format="zip64" if zip_envelope.uses_zip64 else "zip",
                disposition=ArchivePreflightDisposition.UNSUPPORTED_ARCHIVE,
                expected_disk_count=zip_envelope.expected_disk_count,
                is_archive=True,
                is_multipart_archive=True,
                message=(
                    "Multipart or spanned ZIP archives are not supported by the "
                    "current intake path and were routed to quarantine."
                ),
                uses_zip64=zip_envelope.uses_zip64,
            )

        try:
            with ZipFile(BytesIO(document_bytes), mode="r", allowZip64=True) as archive:
                file_entries = tuple(
                    archive_info
                    for archive_info in archive.infolist()
                    if not archive_info.is_dir()
                )
        except BadZipFile:
            return ArchivePreflightResult(
                archive_format="zip64" if zip_envelope.uses_zip64 else "zip",
                disposition=ArchivePreflightDisposition.CORRUPT_ARCHIVE,
                expected_disk_count=zip_envelope.expected_disk_count,
                is_archive=True,
                is_multipart_archive=zip_envelope.is_multipart_archive,
                message=(
                    "The uploaded ZIP archive could not be read and was routed "
                    "to quarantine."
                ),
                uses_zip64=zip_envelope.uses_zip64,
            )
        except LargeZipFile:
            return ArchivePreflightResult(
                archive_format="zip64",
                disposition=ArchivePreflightDisposition.CORRUPT_ARCHIVE,
                expected_disk_count=zip_envelope.expected_disk_count,
                is_archive=True,
                is_multipart_archive=zip_envelope.is_multipart_archive,
                message=(
                    "The uploaded ZIP64 archive could not be read and was routed "
                    "to quarantine."
                ),
                uses_zip64=True,
            )

        is_encrypted = any(
            archive_info.flag_bits & 0x1 for archive_info in file_entries
        )
        nested_archive_count = sum(
            1
            for archive_info in file_entries
            if Path(archive_info.filename).suffix.lower() == ".zip"
        )
        total_uncompressed_bytes = sum(
            max(archive_info.file_size, 0) for archive_info in file_entries
        )
        if is_encrypted:
            return ArchivePreflightResult(
                archive_format="zip64" if zip_envelope.uses_zip64 else "zip",
                disposition=ArchivePreflightDisposition.ENCRYPTED_ARCHIVE,
                expected_disk_count=zip_envelope.expected_disk_count,
                entry_count=len(file_entries),
                is_archive=True,
                is_multipart_archive=zip_envelope.is_multipart_archive,
                message=(
                    "Password-protected ZIP archives are quarantined until "
                    "archive decryption support is implemented."
                ),
                nested_archive_count=nested_archive_count,
                total_uncompressed_bytes=total_uncompressed_bytes,
                uses_zip64=zip_envelope.uses_zip64,
            )

        return ArchivePreflightResult(
            archive_format="zip64" if zip_envelope.uses_zip64 else "zip",
            disposition=ArchivePreflightDisposition.READY_FOR_EXPANSION,
            expected_disk_count=zip_envelope.expected_disk_count,
            entry_count=len(file_entries),
            is_archive=True,
            is_multipart_archive=zip_envelope.is_multipart_archive,
            message=(
                "ZIP64 archive detected and queued for archive expansion."
                if zip_envelope.uses_zip64
                else "ZIP archive detected and queued for archive expansion."
            ),
            nested_archive_count=nested_archive_count,
            total_uncompressed_bytes=total_uncompressed_bytes,
            uses_zip64=zip_envelope.uses_zip64,
        )

    if _looks_like_unsupported_archive(
        file_name=file_name,
        normalized_content_type=normalized_content_type,
    ):
        archive_format = _resolve_archive_format(file_name, normalized_content_type)
        return ArchivePreflightResult(
            archive_format=archive_format,
            disposition=ArchivePreflightDisposition.UNSUPPORTED_ARCHIVE,
            is_archive=True,
            message=(
                f"The uploaded {archive_format.upper()} archive is recognized but "
                "not supported by the current archive expansion path."
            ),
        )

    return ArchivePreflightResult()
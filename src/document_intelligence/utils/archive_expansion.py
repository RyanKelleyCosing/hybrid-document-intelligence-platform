"""Helpers for expanding supported archive uploads into child documents."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field, replace
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from document_intelligence.models import (
    ArchivePreflightDisposition,
    ArchivePreflightResult,
)
from document_intelligence.utils.archive_preflight import (
    inspect_document_archive_preflight,
)

MAX_ARCHIVE_EXPANSION_COMPRESSION_RATIO = 100.0
MAX_ARCHIVE_EXPANSION_DEPTH = 3
MAX_ARCHIVE_EXPANSION_ENTRY_COUNT = 100
MAX_ARCHIVE_EXPANSION_TOTAL_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
_MIN_ARCHIVE_BOMB_CHECK_BYTES = 1024


@dataclass(frozen=True)
class ArchiveExpansionLimits:
    """Safety rails applied while expanding nested ZIP archives."""

    max_archive_depth: int = MAX_ARCHIVE_EXPANSION_DEPTH
    max_compression_ratio: float = MAX_ARCHIVE_EXPANSION_COMPRESSION_RATIO
    max_entry_count: int = MAX_ARCHIVE_EXPANSION_ENTRY_COUNT
    max_total_uncompressed_bytes: int = (
        MAX_ARCHIVE_EXPANSION_TOTAL_UNCOMPRESSED_BYTES
    )


@dataclass
class _ArchiveExpansionState:
    """Mutable state shared across one recursive archive expansion run."""

    entry_count: int = 0
    seen_member_paths: set[str] = field(default_factory=set)
    total_uncompressed_bytes: int = 0


DEFAULT_ARCHIVE_EXPANSION_LIMITS = ArchiveExpansionLimits()


class UnsafeArchiveExpansionError(RuntimeError):
    """Raised when archive expansion trips one of the safety guards."""

    def __init__(self, archive_preflight: ArchivePreflightResult) -> None:
        super().__init__(archive_preflight.message or "Archive expansion is unsafe.")
        self.archive_preflight = archive_preflight


@dataclass(frozen=True)
class ArchiveExpandedMember:
    """One file member extracted from a supported archive."""

    archive_depth: int
    archive_member_path: str
    archive_preflight: ArchivePreflightResult
    content_type: str
    document_bytes: bytes
    file_name: str
    parent_archive_member_path: str | None = None


def _guess_member_content_type(file_name: str) -> str:
    """Return the best-effort content type for an extracted archive member."""

    guessed_type, _ = mimetypes.guess_type(file_name)
    if guessed_type:
        return guessed_type

    if Path(file_name).suffix.lower() == ".zip":
        return "application/zip"

    return "application/octet-stream"


def _normalize_member_path(member_name: str) -> str:
    """Return a normalized archive-member path for metadata persistence."""

    normalized_parts = [
        part
        for part in PurePosixPath(member_name).parts
        if part not in {"", ".", ".."}
    ]
    if not normalized_parts:
        return "unnamed-member.bin"

    return "/".join(normalized_parts)


def _resolve_member_file_name(member_path: str) -> str:
    """Return the persisted file name for an extracted archive member."""

    file_name = Path(member_path).name
    return file_name or "unnamed-member.bin"


def _join_archive_member_path(
    *,
    member_path: str,
    parent_archive_member_path: str | None,
) -> str:
    """Return the full persisted path for one extracted archive member."""

    if not parent_archive_member_path:
        return member_path

    return f"{parent_archive_member_path}/{member_path}"


def _build_unsafe_archive_preflight(
    *,
    entry_count: int,
    message: str,
    total_uncompressed_bytes: int,
) -> ArchivePreflightResult:
    """Return a quarantine-ready archive-preflight result."""

    return ArchivePreflightResult(
        archive_format="zip",
        disposition=ArchivePreflightDisposition.UNSAFE_ARCHIVE,
        entry_count=entry_count,
        is_archive=True,
        message=message,
        total_uncompressed_bytes=total_uncompressed_bytes,
    )


def _guard_archive_member(
    *,
    archive_member_path: str,
    compressed_size: int,
    file_size: int,
    limits: ArchiveExpansionLimits,
    state: _ArchiveExpansionState,
) -> None:
    """Raise when a member would violate archive-expansion safety limits."""

    projected_entry_count = state.entry_count + 1
    if projected_entry_count > limits.max_entry_count:
        raise UnsafeArchiveExpansionError(
            _build_unsafe_archive_preflight(
                entry_count=state.entry_count,
                message=(
                    "Archive expansion stopped because extracted item count "
                    f"would exceed the limit of {limits.max_entry_count} at "
                    f"'{archive_member_path}'."
                ),
                total_uncompressed_bytes=state.total_uncompressed_bytes,
            )
        )

    projected_total_uncompressed_bytes = (
        state.total_uncompressed_bytes + max(file_size, 0)
    )
    if projected_total_uncompressed_bytes > limits.max_total_uncompressed_bytes:
        raise UnsafeArchiveExpansionError(
            _build_unsafe_archive_preflight(
                entry_count=projected_entry_count,
                message=(
                    "Archive expansion stopped because expanded content size "
                    "would exceed the limit of "
                    f"{limits.max_total_uncompressed_bytes} bytes at "
                    f"'{archive_member_path}'."
                ),
                total_uncompressed_bytes=projected_total_uncompressed_bytes,
            )
        )

    if max(file_size, 0) >= _MIN_ARCHIVE_BOMB_CHECK_BYTES:
        if compressed_size <= 0:
            raise UnsafeArchiveExpansionError(
                _build_unsafe_archive_preflight(
                    entry_count=projected_entry_count,
                    message=(
                        "Archive expansion stopped because member "
                        f"'{archive_member_path}' reported an invalid compressed "
                        "size and tripped the archive-bomb guard."
                    ),
                    total_uncompressed_bytes=projected_total_uncompressed_bytes,
                )
            )

        compression_ratio = max(file_size, 0) / compressed_size
        if compression_ratio > limits.max_compression_ratio:
            raise UnsafeArchiveExpansionError(
                _build_unsafe_archive_preflight(
                    entry_count=projected_entry_count,
                    message=(
                        "Archive expansion stopped because member "
                        f"'{archive_member_path}' exceeded the compression-ratio "
                        "guard "
                        f"({compression_ratio:.2f}:1 > "
                        f"{limits.max_compression_ratio:.2f}:1)."
                    ),
                    total_uncompressed_bytes=projected_total_uncompressed_bytes,
                )
            )

    state.entry_count = projected_entry_count
    state.total_uncompressed_bytes = projected_total_uncompressed_bytes


def _expand_zip_archive_members(
    document_bytes: bytes,
    *,
    archive_depth: int,
    limits: ArchiveExpansionLimits,
    parent_archive_member_path: str | None,
    state: _ArchiveExpansionState,
) -> tuple[ArchiveExpandedMember, ...]:
    """Expand one ZIP payload and recurse into safe nested ZIP children."""

    expanded_members: list[ArchiveExpandedMember] = []
    with ZipFile(BytesIO(document_bytes), mode="r", allowZip64=True) as archive:
        for archive_info in archive.infolist():
            if archive_info.is_dir():
                continue

            member_path = _join_archive_member_path(
                member_path=_normalize_member_path(archive_info.filename),
                parent_archive_member_path=parent_archive_member_path,
            )
            _guard_archive_member(
                archive_member_path=member_path,
                compressed_size=max(archive_info.compress_size, 0),
                file_size=max(archive_info.file_size, 0),
                limits=limits,
                state=state,
            )
            if member_path in state.seen_member_paths:
                expanded_members.append(
                    ArchiveExpandedMember(
                        archive_depth=archive_depth,
                        archive_member_path=member_path,
                        archive_preflight=_build_unsafe_archive_preflight(
                            entry_count=state.entry_count,
                            message=(
                                "Archive expansion quarantined duplicate member "
                                f"path '{member_path}' so operators can review "
                                "the conflicting archive payload."
                            ),
                            total_uncompressed_bytes=state.total_uncompressed_bytes,
                        ),
                        content_type=_guess_member_content_type(member_path),
                        document_bytes=archive.read(archive_info),
                        file_name=_resolve_member_file_name(member_path),
                        parent_archive_member_path=parent_archive_member_path,
                    )
                )
                continue

            state.seen_member_paths.add(member_path)
            member_bytes = archive.read(archive_info)
            member_content_type = _guess_member_content_type(member_path)
            member_preflight = inspect_document_archive_preflight(
                content_type=member_content_type,
                document_bytes=member_bytes,
                file_name=_resolve_member_file_name(member_path),
            )
            member = ArchiveExpandedMember(
                archive_depth=archive_depth,
                archive_member_path=member_path,
                archive_preflight=member_preflight,
                content_type=member_content_type,
                document_bytes=member_bytes,
                file_name=_resolve_member_file_name(member_path),
                parent_archive_member_path=parent_archive_member_path,
            )

            if (
                member_preflight.disposition
                == ArchivePreflightDisposition.READY_FOR_EXPANSION
            ):
                if archive_depth >= limits.max_archive_depth:
                    expanded_members.append(
                        replace(
                            member,
                            archive_preflight=_build_unsafe_archive_preflight(
                                entry_count=state.entry_count,
                                message=(
                                    "Archive expansion stopped because nested ZIP "
                                    "depth would exceed the limit of "
                                    f"{limits.max_archive_depth} at '{member_path}'."
                                ),
                                total_uncompressed_bytes=(
                                    state.total_uncompressed_bytes
                                ),
                            ),
                        )
                    )
                    continue

                nested_entry_count = state.entry_count
                nested_total_uncompressed_bytes = state.total_uncompressed_bytes
                try:
                    nested_members = _expand_zip_archive_members(
                        member_bytes,
                        archive_depth=archive_depth + 1,
                        limits=limits,
                        parent_archive_member_path=member_path,
                        state=state,
                    )
                except UnsafeArchiveExpansionError as error:
                    state.entry_count = nested_entry_count
                    state.total_uncompressed_bytes = nested_total_uncompressed_bytes
                    expanded_members.append(
                        replace(member, archive_preflight=error.archive_preflight)
                    )
                    continue

                expanded_members.append(member)
                expanded_members.extend(nested_members)
                continue

            expanded_members.append(member)

    return tuple(expanded_members)


def expand_zip_archive(
    document_bytes: bytes,
    *,
    limits: ArchiveExpansionLimits = DEFAULT_ARCHIVE_EXPANSION_LIMITS,
) -> tuple[ArchiveExpandedMember, ...]:
    """Expand a ZIP payload into persisted child-document inputs."""

    return _expand_zip_archive_members(
        document_bytes,
        archive_depth=1,
        limits=limits,
        parent_archive_member_path=None,
        state=_ArchiveExpansionState(),
    )
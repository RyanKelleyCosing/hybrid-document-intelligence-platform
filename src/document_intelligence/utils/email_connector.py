"""Helpers for staged email-connector intake sources."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from os import stat_result
from pathlib import Path
from urllib.parse import urlencode


@dataclass(frozen=True)
class ListedEmailConnectorDocument:
    """One email attachment or staged document prepared for packet intake."""

    content_bytes: bytes
    content_type: str | None
    file_name: str


@dataclass(frozen=True)
class ListedEmailConnectorAsset:
    """One staged email message or dropped attachment discovered for intake."""

    content_length_bytes: int
    content_type: str | None
    documents: tuple[ListedEmailConnectorDocument, ...]
    file_name: str
    last_modified_utc: datetime | None
    packet_name: str
    relative_path: str
    source_uri: str
    subject: str | None


def _resolve_email_connector_root(folder_path: str) -> Path:
    """Return the resolved staged-mail root path."""

    folder_root = Path(folder_path).expanduser().resolve()
    if not folder_root.exists():
        raise FileNotFoundError(
            f"Email connector folder path '{folder_root}' does not exist."
        )
    if not folder_root.is_dir():
        raise NotADirectoryError(
            f"Email connector folder path '{folder_root}' is not a directory."
        )

    return folder_root


def _build_source_uri(
    *,
    content_length_bytes: int,
    file_path: Path,
    folder_path: str,
    last_modified_ns: int,
    mailbox_address: str,
    relative_path: str,
) -> str:
    """Return a stable source URI for one staged email asset."""

    folder_label = Path(folder_path).name or "mailbox"
    normalized_mailbox = mailbox_address.strip().lower() or "unknown-mailbox"
    encoded_query = urlencode(
        {
            "mtime_ns": last_modified_ns,
            "path": file_path.as_posix(),
            "size": content_length_bytes,
        }
    )
    return (
        f"email://connector/{normalized_mailbox}/{folder_label}/"
        f"{relative_path}?{encoded_query}"
    )


def _normalize_allowlist(
    attachment_extension_allowlist: tuple[str, ...],
) -> frozenset[str]:
    """Normalize the configured attachment extension allowlist."""

    normalized_extensions = {
        (
            extension.strip().lower()
            if extension.strip().startswith(".")
            else f".{extension.strip().lower()}"
        )
        for extension in attachment_extension_allowlist
        if extension.strip()
    }
    return frozenset(normalized_extensions)


def _should_include_path(path: Path, allowlist: frozenset[str]) -> bool:
    """Return whether one staged file should be processed."""

    if path.suffix.lower() == ".eml":
        return True
    if not allowlist:
        return True

    return path.suffix.lower() in allowlist


def _guess_content_type(file_name: str) -> str | None:
    """Guess the most specific content type for one file name."""

    guessed_type, _ = mimetypes.guess_type(file_name)
    return guessed_type


def _build_direct_file_asset(
    *,
    file_path: Path,
    folder_path: str,
    mailbox_address: str,
    relative_path: str,
    stat_result: stat_result,
) -> ListedEmailConnectorAsset:
    """Build one email-connector asset from a direct staged document file."""

    document_bytes = file_path.read_bytes()
    content_type = _guess_content_type(file_path.name)
    return ListedEmailConnectorAsset(
        content_length_bytes=file_path.stat().st_size,
        content_type=content_type,
        documents=(
            ListedEmailConnectorDocument(
                content_bytes=document_bytes,
                content_type=content_type,
                file_name=file_path.name,
            ),
        ),
        file_name=file_path.name,
        last_modified_utc=datetime.fromtimestamp(stat_result.st_mtime, tz=UTC),
        packet_name=file_path.name,
        relative_path=relative_path,
        source_uri=_build_source_uri(
            content_length_bytes=stat_result.st_size,
            file_path=file_path,
            folder_path=folder_path,
            last_modified_ns=stat_result.st_mtime_ns,
            mailbox_address=mailbox_address,
            relative_path=relative_path,
        ),
        subject=None,
    )


def _build_message_asset(
    *,
    allowlist: frozenset[str],
    file_path: Path,
    folder_path: str,
    mailbox_address: str,
    relative_path: str,
    stat_result: stat_result,
) -> ListedEmailConnectorAsset:
    """Build one email-connector asset from a staged .eml message."""

    message_bytes = file_path.read_bytes()
    message = BytesParser(policy=policy.default).parsebytes(message_bytes)
    documents: list[ListedEmailConnectorDocument] = []
    for attachment in message.iter_attachments():
        file_name = attachment.get_filename()
        if not file_name:
            continue

        suffix = Path(file_name).suffix.lower()
        if allowlist and suffix not in allowlist:
            continue

        attachment_payload = attachment.get_payload(decode=True)
        if not attachment_payload:
            continue

        attachment_bytes = bytes(attachment_payload)

        content_type = attachment.get_content_type() or _guess_content_type(file_name)
        documents.append(
            ListedEmailConnectorDocument(
                content_bytes=attachment_bytes,
                content_type=content_type,
                file_name=file_name,
            )
        )

    subject = str(message.get("Subject") or "").strip() or None
    return ListedEmailConnectorAsset(
        content_length_bytes=stat_result.st_size,
        content_type="message/rfc822",
        documents=tuple(documents),
        file_name=file_path.name,
        last_modified_utc=datetime.fromtimestamp(stat_result.st_mtime, tz=UTC),
        packet_name=(subject or file_path.stem or file_path.name)[:200],
        relative_path=relative_path,
        source_uri=_build_source_uri(
            content_length_bytes=stat_result.st_size,
            file_path=file_path,
            folder_path=folder_path,
            last_modified_ns=stat_result.st_mtime_ns,
            mailbox_address=mailbox_address,
            relative_path=relative_path,
        ),
        subject=subject,
    )


def list_email_connector_assets(
    *,
    attachment_extension_allowlist: tuple[str, ...],
    folder_path: str,
    mailbox_address: str,
) -> tuple[ListedEmailConnectorAsset, ...]:
    """List staged email message assets from one connector folder."""

    folder_root = _resolve_email_connector_root(folder_path)
    allowlist = _normalize_allowlist(attachment_extension_allowlist)
    listed_assets: list[ListedEmailConnectorAsset] = []
    for candidate_path in sorted(
        folder_root.rglob("*"),
        key=lambda path: str(path).lower(),
    ):
        if not candidate_path.is_file():
            continue

        resolved_path = candidate_path.resolve()
        if not _should_include_path(resolved_path, allowlist):
            continue

        stat_result = resolved_path.stat()
        relative_path = resolved_path.relative_to(folder_root).as_posix()
        if resolved_path.suffix.lower() == ".eml":
            listed_assets.append(
                _build_message_asset(
                    allowlist=allowlist,
                    file_path=resolved_path,
                    folder_path=folder_path,
                    mailbox_address=mailbox_address,
                    relative_path=relative_path,
                    stat_result=stat_result,
                )
            )
            continue

        listed_assets.append(
            _build_direct_file_asset(
                file_path=resolved_path,
                folder_path=folder_path,
                mailbox_address=mailbox_address,
                relative_path=relative_path,
                stat_result=stat_result,
            )
        )

    return tuple(listed_assets)
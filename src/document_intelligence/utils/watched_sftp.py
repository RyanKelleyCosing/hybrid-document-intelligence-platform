"""Helpers for watched Azure Storage SFTP intake sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import urlencode, urlparse

from document_intelligence.utils.blob_storage import (
    download_blob_bytes,
    list_blob_assets,
)


@dataclass(frozen=True)
class ListedWatchedSftpAsset:
    """Metadata returned after listing candidate files from a watched SFTP path."""

    blob_name: str
    container_name: str
    content_length_bytes: int
    content_type: str | None
    etag: str | None
    last_modified_utc: datetime | None
    relative_path: str
    source_path: str
    source_uri: str


def _extract_storage_account_name(storage_connection_string: str) -> str | None:
    """Return the storage account name embedded in a connection string."""

    for segment in storage_connection_string.split(";"):
        if segment.lower().startswith("accountname="):
            account_name = segment.split("=", maxsplit=1)[1].strip()
            if account_name:
                return account_name

    return None


def _normalize_sftp_path(sftp_path: str) -> str:
    """Return a normalized watched SFTP path without a scheme or leading slash."""

    normalized_path = sftp_path.strip().replace("\\", "/")
    if normalized_path.startswith("sftp://"):
        normalized_path = urlparse(normalized_path).path

    cleaned_path = str(PurePosixPath(normalized_path.lstrip("/")))
    if cleaned_path == ".":
        return ""

    return cleaned_path.rstrip("/")


def _resolve_container_and_prefix(sftp_path: str) -> tuple[str, str]:
    """Resolve the filesystem container and prefix from one watched SFTP path."""

    normalized_path = _normalize_sftp_path(sftp_path)
    container_name, _, relative_prefix = normalized_path.partition("/")
    if not container_name:
        raise ValueError("The watched SFTP path must include a filesystem name.")

    normalized_prefix = relative_prefix.strip("/")
    if normalized_prefix:
        return container_name, f"{normalized_prefix}/"

    return container_name, ""


def _build_sftp_source_uri(
    *,
    etag: str | None,
    source_path: str,
    storage_account_name: str,
) -> str:
    """Build a stable SFTP source URI for one watched asset."""

    base_uri = f"sftp://{storage_account_name.strip()}/{source_path.lstrip('/')}"
    if etag is None:
        return base_uri

    normalized_etag = etag.strip('"')
    if not normalized_etag:
        return base_uri

    return f"{base_uri}?{urlencode({'etag': normalized_etag})}"


def list_watched_sftp_assets(
    *,
    sftp_path: str,
    storage_account_name: str,
    storage_connection_string: str,
) -> tuple[ListedWatchedSftpAsset, ...]:
    """List files written under one Azure Storage SFTP path."""

    resolved_account_name = _extract_storage_account_name(storage_connection_string)
    if (
        resolved_account_name is not None
        and resolved_account_name.lower() != storage_account_name.strip().lower()
    ):
        raise ValueError(
            "The watched SFTP source points to a storage account that does not "
            "match the configured DOCINT_STORAGE_CONNECTION_STRING account."
        )

    container_name, blob_prefix = _resolve_container_and_prefix(sftp_path)
    listed_blobs = list_blob_assets(
        blob_prefix=blob_prefix,
        container_name=container_name,
        storage_connection_string=storage_connection_string,
    )
    listed_assets: list[ListedWatchedSftpAsset] = []
    for blob in listed_blobs:
        relative_path = blob.blob_name.removeprefix(blob_prefix).lstrip("/")
        source_path = f"{container_name}/{blob.blob_name}"
        listed_assets.append(
            ListedWatchedSftpAsset(
                blob_name=blob.blob_name,
                container_name=blob.container_name,
                content_length_bytes=blob.content_length_bytes,
                content_type=blob.content_type,
                etag=blob.etag,
                last_modified_utc=blob.last_modified_utc,
                relative_path=relative_path or blob.blob_name,
                source_path=source_path,
                source_uri=_build_sftp_source_uri(
                    etag=blob.etag,
                    source_path=source_path,
                    storage_account_name=storage_account_name,
                ),
            )
        )

    return tuple(listed_assets)


def read_watched_sftp_asset_bytes(
    asset: ListedWatchedSftpAsset,
    *,
    storage_connection_string: str,
) -> bytes:
    """Read one watched SFTP asset as raw bytes."""

    return download_blob_bytes(
        blob_name=asset.blob_name,
        container_name=asset.container_name,
        storage_connection_string=storage_connection_string,
    )

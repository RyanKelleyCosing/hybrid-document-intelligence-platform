"""Blob storage helpers for operator-state document assets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import unquote

from azure.storage.blob import BlobClient, BlobServiceClient, ContentSettings

from document_intelligence.inspection import parse_blob_source_uri


@dataclass(frozen=True)
class BlobAsset:
    """Metadata returned after a document asset is written to Blob storage."""

    blob_name: str
    container_name: str
    content_length_bytes: int
    storage_uri: str


@dataclass(frozen=True)
class ListedBlobAsset:
    """Metadata returned after listing candidate blobs from a source container."""

    blob_name: str
    container_name: str
    content_length_bytes: int
    content_type: str | None
    etag: str | None
    last_modified_utc: datetime | None
    storage_uri: str


def upload_blob_bytes(
    *,
    blob_name: str,
    container_name: str,
    content_type: str,
    data: bytes,
    storage_connection_string: str,
) -> BlobAsset:
    """Upload bytes to Blob storage and return the stored asset metadata."""
    blob_client = BlobClient.from_connection_string(
        conn_str=storage_connection_string,
        container_name=container_name,
        blob_name=blob_name,
    )
    blob_client.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type),
    )
    return BlobAsset(
        blob_name=blob_name,
        container_name=container_name,
        content_length_bytes=len(data),
        storage_uri=blob_client.url,
    )


def list_blob_assets(
    *,
    blob_prefix: str,
    container_name: str,
    storage_connection_string: str,
) -> tuple[ListedBlobAsset, ...]:
    """List blobs under one prefix and return stable metadata for each item."""

    blob_service_client = BlobServiceClient.from_connection_string(
        conn_str=storage_connection_string
    )
    container_client = blob_service_client.get_container_client(container_name)
    listed_assets: list[ListedBlobAsset] = []
    for blob_properties in container_client.list_blobs(name_starts_with=blob_prefix):
        content_settings = getattr(blob_properties, "content_settings", None)
        content_type = (
            content_settings.content_type if content_settings is not None else None
        )
        blob_name = str(blob_properties.name)
        listed_assets.append(
            ListedBlobAsset(
                blob_name=blob_name,
                container_name=container_name,
                content_length_bytes=int(getattr(blob_properties, "size", 0) or 0),
                content_type=content_type,
                etag=str(getattr(blob_properties, "etag", "") or "") or None,
                last_modified_utc=getattr(blob_properties, "last_modified", None),
                storage_uri=container_client.get_blob_client(blob_name).url,
            )
        )

    return tuple(listed_assets)


def delete_blob_asset(
    *,
    blob_name: str,
    container_name: str,
    storage_connection_string: str,
) -> None:
    """Delete a staged Blob asset during best-effort rollback."""
    blob_client = BlobClient.from_connection_string(
        conn_str=storage_connection_string,
        container_name=container_name,
        blob_name=blob_name,
    )
    blob_client.delete_blob(delete_snapshots="include")


def download_blob_bytes(
    *,
    blob_name: str,
    container_name: str,
    storage_connection_string: str,
) -> bytes:
    """Download raw bytes from Blob storage."""

    blob_client = BlobClient.from_connection_string(
        conn_str=storage_connection_string,
        container_name=container_name,
        blob_name=blob_name,
    )
    return blob_client.download_blob().readall()


def download_blob_text(
    *,
    source_uri: str,
    storage_connection_string: str,
    encoding: str = "utf-8",
) -> str:
    """Download a UTF-8 text blob using its Azure-style storage URI."""

    blob_reference = parse_blob_source_uri(source_uri)
    if blob_reference is None:
        raise ValueError(f"'{source_uri}' is not a supported Azure blob URI.")

    container_name, blob_name = blob_reference
    blob_client = BlobClient.from_connection_string(
        conn_str=storage_connection_string,
        container_name=container_name,
        blob_name=unquote(blob_name),
    )
    return blob_client.download_blob().readall().decode(encoding)
"""Helpers for bridging S3 objects into Azure Blob-backed ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any

DEFAULT_SOURCE_PREFIX = "incoming/"
DEFAULT_TARGET_PREFIX = "aws-s3/"
DEFAULT_SOURCE_TAGS = ("aws_bridge", "s3_drop")


@dataclass(frozen=True)
class BlobBridgeTarget:
    """Resolved Azure Blob target details for a bridged S3 object."""

    blob_name: str
    source_uri: str


def normalize_prefix(prefix: str) -> str:
    """Normalize a virtual-folder prefix into a slash-terminated value."""
    stripped = prefix.strip().strip("/")
    return f"{stripped}/" if stripped else ""


def build_blob_name(
    source_key: str,
    source_prefix: str = DEFAULT_SOURCE_PREFIX,
    target_prefix: str = DEFAULT_TARGET_PREFIX,
) -> str:
    """Build the destination blob name for a bridged S3 object."""
    normalized_key = source_key.strip().lstrip("/")
    if not normalized_key:
        raise ValueError("source_key must not be empty")

    normalized_source_prefix = normalize_prefix(source_prefix)
    if normalized_source_prefix and normalized_key.startswith(normalized_source_prefix):
        normalized_key = normalized_key[len(normalized_source_prefix) :]

    normalized_key = normalized_key.lstrip("/")
    if not normalized_key:
        raise ValueError(
            "source_key must include a file name after the source prefix"
        )

    normalized_target_prefix = normalize_prefix(target_prefix)
    return f"{normalized_target_prefix}{normalized_key}"


def build_blob_target(
    container_name: str,
    source_key: str,
    source_prefix: str = DEFAULT_SOURCE_PREFIX,
    target_prefix: str = DEFAULT_TARGET_PREFIX,
) -> BlobBridgeTarget:
    """Build the Azure Blob destination for a bridged S3 object."""
    blob_name = build_blob_name(
        source_key,
        source_prefix=source_prefix,
        target_prefix=target_prefix,
    )
    return BlobBridgeTarget(
        blob_name=blob_name,
        source_uri=f"az://{container_name}/{blob_name}",
    )


def build_document_id(
    bucket_name: str,
    source_key: str,
    *,
    e_tag: str | None = None,
    version_id: str | None = None,
) -> str:
    """Build a stable document id for an S3-backed ingestion request."""
    fingerprint = "|".join(
        part
        for part in (bucket_name, source_key, version_id or "", e_tag or "")
        if part is not None
    )
    digest = sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
    return f"aws-{digest}"


def build_ingestion_request(
    *,
    bucket_name: str,
    source_key: str,
    container_name: str,
    content_type: str | None,
    source_prefix: str = DEFAULT_SOURCE_PREFIX,
    target_prefix: str = DEFAULT_TARGET_PREFIX,
    e_tag: str | None = None,
    version_id: str | None = None,
    source_tags: tuple[str, ...] = DEFAULT_SOURCE_TAGS,
) -> dict[str, Any]:
    """Build the Function App ingestion payload for a bridged S3 object."""
    target = build_blob_target(
        container_name=container_name,
        source_key=source_key,
        source_prefix=source_prefix,
        target_prefix=target_prefix,
    )
    file_name = PurePosixPath(source_key).name
    if not file_name:
        raise ValueError("source_key must include a file name")

    return {
        "document_id": build_document_id(
            bucket_name,
            source_key,
            e_tag=e_tag,
            version_id=version_id,
        ),
        "source": "aws_s3",
        "source_uri": target.source_uri,
        "issuer_category": "unknown",
        "source_summary": f"Copied from s3://{bucket_name}/{source_key}",
        "source_tags": list(source_tags),
        "file_name": file_name,
        "content_type": content_type or "application/octet-stream",
    }
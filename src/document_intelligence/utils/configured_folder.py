"""Filesystem helpers for configured-folder intake sources."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode


@dataclass(frozen=True)
class ListedConfiguredFolderAsset:
    """Metadata returned after listing candidate files from a configured folder."""

    content_length_bytes: int
    content_type: str | None
    file_path: Path
    last_modified_utc: datetime | None
    relative_path: str
    source_uri: str


def _resolve_folder_root(folder_path: str) -> Path:
    """Return the resolved configured-folder root path."""

    folder_root = Path(folder_path).expanduser().resolve()
    if not folder_root.exists():
        raise FileNotFoundError(
            f"Configured folder path '{folder_root}' does not exist."
        )
    if not folder_root.is_dir():
        raise NotADirectoryError(
            f"Configured folder path '{folder_root}' is not a directory."
        )

    return folder_root


def _build_source_uri(
    *,
    content_length_bytes: int,
    file_path: Path,
    last_modified_ns: int,
) -> str:
    """Return a stable source URI that distinguishes file revisions."""

    return (
        f"{file_path.as_uri()}?"
        f"{urlencode({'mtime_ns': last_modified_ns, 'size': content_length_bytes})}"
    )


def list_configured_folder_assets(
    *,
    file_pattern: str,
    folder_path: str,
    min_stable_age_seconds: int = 0,
    recursive: bool,
) -> tuple[ListedConfiguredFolderAsset, ...]:
    """List files that match one configured folder source definition."""

    folder_root = _resolve_folder_root(folder_path)
    now_utc = datetime.now(UTC)
    candidate_paths = (
        folder_root.rglob(file_pattern) if recursive else folder_root.glob(file_pattern)
    )
    listed_assets: list[ListedConfiguredFolderAsset] = []
    for candidate_path in sorted(candidate_paths, key=lambda path: str(path).lower()):
        try:
            if not candidate_path.is_file():
                continue

            resolved_path = candidate_path.resolve()
            if resolved_path.name.startswith("~$"):
                continue

            stat_result = resolved_path.stat()
            last_modified_utc = datetime.fromtimestamp(stat_result.st_mtime, tz=UTC)
            if stat_result.st_size <= 0:
                continue
            if min_stable_age_seconds > 0 and (
                now_utc - last_modified_utc
            ).total_seconds() < min_stable_age_seconds:
                continue

            content_type, _ = mimetypes.guess_type(resolved_path.name)
            listed_assets.append(
                ListedConfiguredFolderAsset(
                    content_length_bytes=stat_result.st_size,
                    content_type=content_type,
                    file_path=resolved_path,
                    last_modified_utc=last_modified_utc,
                    relative_path=resolved_path.relative_to(folder_root).as_posix(),
                    source_uri=_build_source_uri(
                        content_length_bytes=stat_result.st_size,
                        file_path=resolved_path,
                        last_modified_ns=stat_result.st_mtime_ns,
                    ),
                )
            )
        except OSError:
            continue

    return tuple(listed_assets)


def read_configured_folder_file_bytes(file_path: Path) -> bytes:
    """Read one configured-folder file as raw bytes."""

    return file_path.read_bytes()

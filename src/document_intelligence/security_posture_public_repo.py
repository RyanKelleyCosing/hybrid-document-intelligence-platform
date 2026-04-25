"""Export helpers for a standalone public security-posture repository."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from shutil import copy2

from .security_posture_public_subtree import DEFAULT_SECURITY_POSTURE_SUBTREE_OUTPUT

DEFAULT_SECURITY_POSTURE_PUBLIC_REPO_OUTPUT = Path(
    "public-repo-staging/security-posture-platform"
)


@dataclass(frozen=True)
class SecurityPosturePublicRepoExport:
    """A standalone public-repo export copied from the staged subtree."""

    exported_files: tuple[str, ...]
    source_relative_path: str


def export_security_posture_public_repo(
    repo_root: Path,
    output_directory: Path,
    *,
    subtree_directory: Path = DEFAULT_SECURITY_POSTURE_SUBTREE_OUTPUT,
) -> SecurityPosturePublicRepoExport:
    """Copy the declared public subtree into a standalone repo staging directory."""

    source_directory = _resolve_repo_path(repo_root, subtree_directory)
    if not source_directory.is_dir():
        raise FileNotFoundError(
            f"Public subtree not found: '{source_directory.as_posix()}'."
        )

    _reset_directory(output_directory)

    exported_files = _collect_declared_files(source_directory)
    for relative_path in exported_files:
        source_path = source_directory / relative_path
        destination_path = output_directory / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        copy2(source_path, destination_path)

    return SecurityPosturePublicRepoExport(
        exported_files=exported_files,
        source_relative_path=source_directory.relative_to(repo_root).as_posix(),
    )


def _resolve_repo_path(repo_root: Path, candidate_path: Path) -> Path:
    if candidate_path.is_absolute():
        return candidate_path
    return repo_root / candidate_path


def _reset_directory(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for child in directory.iterdir():
        if child.is_dir():
            _clear_directory_contents(child)
        else:
            child.unlink()


def _clear_directory_contents(directory: Path) -> None:
    for child in directory.iterdir():
        if child.is_dir():
            _clear_directory_contents(child)
            child.rmdir()
        else:
            child.unlink()


def _collect_declared_files(source_directory: Path) -> tuple[str, ...]:
    metadata_path = source_directory / "subtree-sources.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(
            f"Subtree metadata not found: '{metadata_path.as_posix()}'."
        )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    declared_files = {
        relative_path
        for relative_path in metadata.get("generated_files", [])
        if isinstance(relative_path, str)
    }

    for package in metadata.get("packages", []):
        if not isinstance(package, dict):
            continue

        destination_directory_name = package.get("destination_directory_name")
        included_files = package.get("included_files")
        if not isinstance(destination_directory_name, str) or not isinstance(
            included_files, list
        ):
            continue

        declared_files.update(
            f"{destination_directory_name}/{relative_path}"
            for relative_path in included_files
            if isinstance(relative_path, str)
        )

    return tuple(sorted(declared_files))
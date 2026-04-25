"""Unit tests for the standalone public security-posture repo exporter."""

from __future__ import annotations

import json
from pathlib import Path

from document_intelligence.security_posture_public_repo import (
    export_security_posture_public_repo,
)


def test_export_security_posture_public_repo_copies_declared_files_only(
    tmp_path: Path,
) -> None:
    """The repo exporter should copy only files declared in subtree metadata."""

    repo_root = tmp_path / "repo"
    source_subtree = repo_root / "public-subtrees" / "security-posture-platform"
    source_subtree.mkdir(parents=True)
    _write_file(source_subtree / ".gitignore", "*.tmp\n")
    _write_file(
        source_subtree / ".github" / "workflows" / "validate.yml",
        "name: Validate\n",
    )
    _write_file(source_subtree / "README.md", "# Security Posture Platform\n")
    _write_file(
        source_subtree / "security-posture-site" / "README.md",
        "site-readme\n",
    )
    _write_file(
        source_subtree / "security-posture-site" / "src" / "App.tsx",
        "site-app\n",
    )
    _write_file(
        source_subtree / "security-posture-api" / "README.md",
        "api-readme\n",
    )
    _write_file(
        source_subtree / "security-posture-api" / "function_app.py",
        "api-function\n",
    )
    _write_file(
        source_subtree / "security-posture-site" / "node_modules" / "left-pad" / "index.js",
        "undeclared\n",
    )

    (source_subtree / "subtree-sources.json").write_text(
        json.dumps(
            {
                "generated_files": [
                    ".github/workflows/validate.yml",
                    ".gitignore",
                    "README.md",
                    "subtree-sources.json",
                ],
                "packages": [
                    {
                        "destination_directory_name": "security-posture-site",
                        "included_files": ["README.md", "src/App.tsx"],
                        "source_relative_path": "public-derivatives/security-posture-site",
                    },
                    {
                        "destination_directory_name": "security-posture-api",
                        "included_files": ["README.md", "function_app.py"],
                        "source_relative_path": "public-derivatives/security-posture-api",
                    },
                ],
                "subtree_name": "security-posture-platform",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    output_directory = repo_root / "public-repo-staging" / "security-posture-platform"
    export = export_security_posture_public_repo(
        repo_root=repo_root,
        output_directory=output_directory,
        subtree_directory=Path("public-subtrees/security-posture-platform"),
    )

    assert (output_directory / ".github" / "workflows" / "validate.yml").is_file()
    assert (output_directory / "security-posture-site" / "src" / "App.tsx").is_file()
    assert (output_directory / "security-posture-api" / "function_app.py").is_file()
    assert not (
        output_directory
        / "security-posture-site"
        / "node_modules"
        / "left-pad"
        / "index.js"
    ).exists()
    assert export.source_relative_path == "public-subtrees/security-posture-platform"
    assert ".github/workflows/validate.yml" in export.exported_files


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
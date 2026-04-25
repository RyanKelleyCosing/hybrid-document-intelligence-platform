"""Unit tests for the public security-site derivative extractor."""

from __future__ import annotations

import json
from pathlib import Path

from document_intelligence.repo_boundary import load_repo_boundary_manifest
from document_intelligence.security_site_derivative import (
    build_security_site_derivative_plan,
    extract_security_site_derivative_package,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _manifest_path() -> Path:
    return _repo_root() / "docs" / "private-repo-boundary-manifest.json"


def test_build_security_site_derivative_plan_selects_manifest_approved_sources() -> None:
    """The derivative plan should only copy manifest-approved security-site paths."""

    manifest = load_repo_boundary_manifest(_manifest_path())
    plan = build_security_site_derivative_plan(manifest)
    copied_files = {
        (item.source_relative_path, item.destination_relative_path)
        for item in plan.copied_files
    }

    assert (
        "review-app/src/components/SecurityPostureSite.tsx",
        "src/components/SecurityPostureSite.tsx",
    ) in copied_files
    assert (
        "review-app/src/data/securitySiteContent.ts",
        "src/data/securitySiteContent.ts",
    ) in copied_files
    assert (
        "src/document_intelligence/public_request_context.py"
        in plan.deferred_candidate_sources
    )
    assert "function_app.py" not in plan.deferred_candidate_sources


def test_extract_security_site_derivative_package_writes_expected_files(
    tmp_path: Path,
) -> None:
    """The extractor should create a standalone package with tracked source metadata."""

    manifest = load_repo_boundary_manifest(_manifest_path())
    output_directory = tmp_path / "security-posture-site"

    extract_security_site_derivative_package(
        repo_root=_repo_root(),
        output_directory=output_directory,
        manifest=manifest,
        manifest_path=_manifest_path(),
    )

    assert (output_directory / "README.md").is_file()
    assert (output_directory / "package.json").is_file()
    assert (output_directory / "src" / "App.tsx").is_file()
    readme = (output_directory / "README.md").read_text(encoding="utf-8")
    assert (
        output_directory / "src" / "components" / "SecurityPostureSite.tsx"
    ).read_text(encoding="utf-8") == (
        _repo_root()
        / "review-app"
        / "src"
        / "components"
        / "SecurityPostureSite.tsx"
    ).read_text(encoding="utf-8")
    assert readme.startswith("# Ryan Security Posture Site\n")
    assert "public demonstration only" in readme
    assert "private repo boundary manifest" in readme
    assert _repo_root().as_posix() not in readme
    assert "src/components/SecurityPostureSite.tsx" in readme

    derivative_sources = json.loads(
        (output_directory / "derivative-sources.json").read_text(encoding="utf-8")
    )
    assert derivative_sources["package_name"] == "ryan-security-posture-site"
    assert derivative_sources["manifest_reference"] == "private repo boundary manifest"
    assert derivative_sources["package_purpose"] == "public_demonstration_only"
    assert "manifest_path" not in derivative_sources
    assert "src/components/SecurityPostureSite.tsx" in derivative_sources["copied_files"]
    assert "public-repo-staging/security-posture-platform" not in json.dumps(
        derivative_sources,
        sort_keys=True,
    )
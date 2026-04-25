"""Unit tests for the public security API derivative extractor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from document_intelligence.repo_boundary import load_repo_boundary_manifest
from document_intelligence.security_posture_api_derivative import (
    build_security_posture_api_derivative_plan,
    extract_security_posture_api_derivative_package,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _manifest_path() -> Path:
    return _repo_root() / "docs" / "private-repo-boundary-manifest.json"


# The boundary manifest enumerates private architecture and is intentionally
# excluded from the public mirror; skip when it isn't available.
pytestmark = pytest.mark.skipif(
    not _manifest_path().is_file(),
    reason="private-repo boundary manifest is private-only and not present in this checkout",
)

def test_build_security_posture_api_derivative_plan_selects_manifest_sources() -> None:
    """The derivative plan should only copy manifest-approved backend sources."""

    manifest = load_repo_boundary_manifest(_manifest_path())
    plan = build_security_posture_api_derivative_plan(manifest)
    copied_files = {
        (item.source_relative_path, item.destination_relative_path)
        for item in plan.copied_files
    }

    assert (
        "src/document_intelligence/public_request_context.py",
        "src/security_posture_api/public_request_context.py",
    ) in copied_files
    assert (
        "src/document_intelligence/public_traffic_metrics.py",
        "src/security_posture_api/public_traffic_metrics.py",
    ) in copied_files
    assert (
        "review-app/src/components/SecurityPostureSite.tsx"
        in plan.deferred_candidate_sources
    )
    assert "function_app.py" not in plan.deferred_candidate_sources


def test_extract_security_posture_api_derivative_package_writes_expected_files(
    tmp_path: Path,
) -> None:
    """The extractor should create a standalone API package with rewritten imports."""

    manifest = load_repo_boundary_manifest(_manifest_path())
    output_directory = tmp_path / "security-posture-api"

    extract_security_posture_api_derivative_package(
        repo_root=_repo_root(),
        output_directory=output_directory,
        manifest=manifest,
        manifest_path=_manifest_path(),
    )

    assert (output_directory / "README.md").is_file()
    assert (output_directory / "function_app.py").is_file()
    assert (output_directory / "pyproject.toml").is_file()
    readme = (output_directory / "README.md").read_text(encoding="utf-8")
    runtime_module = (
        output_directory / "src" / "security_posture_api" / "public_request_context.py"
    ).read_text(encoding="utf-8")
    verifier_script = (
        output_directory / "scripts" / "verify_public_simulation_stack.py"
    ).read_text(encoding="utf-8")

    assert "from security_posture_api.traffic_alerts import extract_client_ip" in runtime_module
    assert "from security_posture_api.verification_settings import" in verifier_script
    assert "from security_posture_api.public_traffic_metrics import" in verifier_script
    assert readme.startswith("# Ryan Security Posture API\n")
    assert "public demonstration only" in readme
    assert "private repo boundary manifest" in readme
    assert _repo_root().as_posix() not in readme
    assert "src/security_posture_api/public_request_context.py" in readme

    derivative_sources = json.loads(
        (output_directory / "derivative-sources.json").read_text(encoding="utf-8")
    )
    assert derivative_sources["package_name"] == "ryan-security-posture-api"
    assert derivative_sources["manifest_reference"] == "private repo boundary manifest"
    assert derivative_sources["package_purpose"] == "public_demonstration_only"
    assert "manifest_path" not in derivative_sources
    assert (
        "src/security_posture_api/public_request_context.py"
        in derivative_sources["copied_files"]
    )
    assert "tests/unit/test_public_site_monitor.py" in derivative_sources["validation_files"]
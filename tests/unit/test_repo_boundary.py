"""Unit tests for the Epic 6 repo-boundary report helpers."""

from __future__ import annotations

from pathlib import Path

from document_intelligence.repo_boundary import (
    build_repo_boundary_report,
    load_repo_boundary_manifest,
    render_repo_boundary_report_markdown,
    summarize_repo_boundary_report,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _manifest_path() -> Path:
    return _repo_root() / "docs" / "private-repo-boundary-manifest.json"


def test_load_repo_boundary_manifest_reads_expected_entries() -> None:
    """The boundary manifest should load the key private and public candidate paths."""

    manifest = load_repo_boundary_manifest(_manifest_path())
    entries = {entry.relative_path: entry for entry in manifest.entries}

    assert manifest.repo_name == "hybrid-document-intelligence-platform"
    assert entries["local.settings.json"].exposure == "private_secret_bearing"
    assert entries["function_app.py"].exposure == "private_operational"
    assert (
        entries["src/document_intelligence/public_request_context.py"].exposure
        == "public_derivative_candidate"
    )


def test_build_repo_boundary_report_resolves_expected_paths() -> None:
    """The boundary report should resolve real files and directories in the repo."""

    manifest = load_repo_boundary_manifest(_manifest_path())
    report = build_repo_boundary_report(_repo_root(), manifest, _manifest_path())
    items = {item.relative_path: item for item in report.items}

    assert items["local.settings.json"].exists is True
    assert items["local.settings.json"].path_kind == "file"
    assert items["deployment-records"].path_kind == "directory"
    assert items["review-app"].exposure == "private_operational"
    assert (
        items["review-app/src/components/SecurityPostureSite.tsx"].exposure
        == "public_derivative_candidate"
    )


def test_render_repo_boundary_report_markdown_includes_summary() -> None:
    """The Markdown report should show the grouped Epic 6 boundary summary."""

    manifest = load_repo_boundary_manifest(_manifest_path())
    report = build_repo_boundary_report(_repo_root(), manifest, _manifest_path())
    summary = summarize_repo_boundary_report(report)
    markdown = render_repo_boundary_report_markdown(report)

    assert summary["private_secret_bearing"] >= 3
    assert summary["private_operational"] >= 6
    assert summary["public_derivative_candidate"] >= 8
    assert "# Repo Boundary Report" in markdown
    assert "private_secret_bearing" in markdown
    assert "`deployment-records`" in markdown
    assert "`review-app/src/components/SecurityPostureSite.tsx`" in markdown
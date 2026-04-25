"""Unit tests for synthetic workbook sample generation."""

from __future__ import annotations

import json
from pathlib import Path

from document_intelligence.synthetic_samples import (
    create_debt_relief_intake_cases,
    create_default_synthetic_cases,
    generate_sample_bundle,
)


def test_default_synthetic_cases_include_bankers_box_and_sftp() -> None:
    """The default bundle should include both intake patterns requested by the MVP."""
    cases = create_default_synthetic_cases()

    assert len(cases) == 2
    assert {case.source.value for case in cases} == {"azure_sftp", "scanned_upload"}


def test_debt_relief_intake_cases_cover_all_six_operator_profiles() -> None:
    """The extended intake pack should mirror the six requested operator profiles."""
    cases = create_debt_relief_intake_cases()

    assert len(cases) == 6
    assert {case.case_id for case in cases} == {
        "case-3001",
        "case-3002",
        "case-3003",
        "case-3004",
        "case-3005",
        "case-3006",
    }
    assert all(len(case.accounts) >= 2 for case in cases)


def test_generate_sample_bundle_writes_manifest_and_request_payloads(
    tmp_path: Path,
) -> None:
    """Generated sample bundles should include workbooks and inline request payloads."""
    manifest = generate_sample_bundle(tmp_path)
    request_files = sorted((tmp_path / "requests").glob("*.json"))
    workbook_files = sorted((tmp_path / "cases").rglob("*.xlsx"))

    assert len(manifest["cases"]) == 2
    assert request_files
    assert workbook_files

    first_payload = json.loads(request_files[0].read_text(encoding="utf-8"))

    assert first_payload["document_content_base64"]
    assert first_payload["content_type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_generate_debt_relief_intake_bundle_writes_mixed_formats(
    tmp_path: Path,
) -> None:
    """The extended intake pack should render mixed formats and manifest accounts."""
    manifest = generate_sample_bundle(tmp_path, scenario_set="debt-relief-intake")
    generated_files = {
        file_path.suffix.lower()
        for file_path in (tmp_path / "cases").rglob("*")
        if file_path.is_file()
    }
    request_files = sorted((tmp_path / "requests").glob("*.json"))

    assert manifest["scenario_set"] == "debt-relief-intake"
    assert len(manifest["cases"]) == 6
    assert len(manifest["documents"]) == 54
    assert {".doc", ".jpg", ".pdf", ".png", ".xlsx", ".zip"}.issubset(
        generated_files
    )
    assert request_files
    assert all(case["accounts"] for case in manifest["cases"])

    zip_payload = json.loads(
        (tmp_path / "requests" / "doc-3006-portal-batch.json").read_text(
            encoding="utf-8"
        )
    )

    assert zip_payload["content_type"] == "application/zip"
    assert zip_payload["document_content_base64"] is None
    assert "archive_entries:" in zip_payload["document_text"]
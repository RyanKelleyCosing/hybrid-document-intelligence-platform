"""Unit tests for shared safety and masking helpers."""

from __future__ import annotations

from document_intelligence import safety
from document_intelligence.models import ProcessingStageName, SafetyIssueSeverity


def build_pdf_bytes(*, body: bytes = b"demo") -> bytes:
    """Build a minimal PDF-like payload for safety tests."""

    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n" + body + b"\n%%EOF"


def test_build_content_controls_marks_masked_payloads_sensitive() -> None:
    """Masked-field metadata should imply sensitive content by default."""

    controls = safety.build_content_controls(
        masked_fields=("note",),
        retention_class="audit_history",
    )

    assert controls == {
        "containsSensitiveContent": True,
        "maskedFields": ["note"],
        "retentionClass": "audit_history",
    }


def test_mask_history_payload_masks_nested_values_and_tracks_fields() -> None:
    """Nested audit payloads should mask obvious PII-like strings."""

    masked_payload = safety.mask_history_payload(
        {
            "note": "Contact owner@example.com about 4111 1111 1111 1111.",
            "nested": {"account": "1234567890"},
        },
        retention_class="review_history",
    )

    assert masked_payload["note"] == "Contact o***@example.com about xxxx xxxx xxxx 1111."
    assert masked_payload["nested"]["account"] == "xxxxxx7890"
    assert masked_payload["contentControls"] == {
        "containsSensitiveContent": True,
        "maskedFields": ["nested.account", "note"],
        "retentionClass": "review_history",
    }


def test_inspect_document_safety_flags_password_protected_pdf() -> None:
    """Password-protected PDFs should be routed to quarantine."""

    issues = safety.inspect_document_safety(
        content_type="application/pdf",
        document_bytes=build_pdf_bytes(body=b"<< /Encrypt 5 0 R >>"),
        file_name="protected.pdf",
    )

    assert len(issues) == 1
    assert issues[0].code == "password_protected_pdf"
    assert issues[0].severity == SafetyIssueSeverity.BLOCKING
    assert issues[0].stage_name == ProcessingStageName.QUARANTINE


def test_inspect_document_safety_flags_malformed_openxml_payload() -> None:
    """Broken OpenXML payloads should be quarantined before downstream stages."""

    issues = safety.inspect_document_safety(
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        document_bytes=b"not-a-valid-docx",
        file_name="broken.docx",
    )

    assert len(issues) == 1
    assert issues[0].code == "malformed_office_file"
    assert issues[0].severity == SafetyIssueSeverity.BLOCKING
    assert issues[0].stage_name == ProcessingStageName.QUARANTINE
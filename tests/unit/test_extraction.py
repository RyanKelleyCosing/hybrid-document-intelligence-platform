"""Unit tests for OCR adapter behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from pytest import MonkeyPatch

from document_intelligence.extraction import extract_ocr_text
from document_intelligence.models import DocumentIngestionRequest, DocumentSource
from document_intelligence.settings import AppSettings


def test_extract_ocr_text_uses_document_text_for_unsupported_blob_content_type(
    monkeypatch: MonkeyPatch,
) -> None:
    """Unsupported blob types should fall back to request text instead of DI OCR."""

    def fake_resolve_document_bytes(
        request: DocumentIngestionRequest,
        settings: AppSettings,
    ) -> bytes:
        del request, settings
        return b"zip-bytes"

    monkeypatch.setattr(
        "document_intelligence.extraction.resolve_document_bytes",
        fake_resolve_document_bytes,
    )

    request = DocumentIngestionRequest(
        document_id="doc-zip-001",
        source=DocumentSource.AZURE_BLOB,
        source_uri="az://raw-documents/portal/batch.zip",
        file_name="portal_upload_batch.zip",
        content_type="application/zip",
        document_text="Portal archive summary for Michael Rodriguez.",
        received_at_utc=datetime(2026, 4, 1, 20, 0, tzinfo=UTC),
    )
    settings = AppSettings(
        document_intelligence_endpoint="https://example.cognitiveservices.azure.com/",
        document_intelligence_key="test-key",
    )

    ocr_text, ocr_confidence, page_count, warnings, provider = extract_ocr_text(
        request,
        settings,
    )

    assert ocr_text == "Portal archive summary for Michael Rodriguez."
    assert ocr_confidence == 1.0
    assert page_count == 0
    assert provider == "request_document_text"
    assert any(
        "does not support content_type 'application/zip'" in warning
        for warning in warnings
    )


def test_extract_ocr_text_adds_quality_warnings_from_page_metadata(
    monkeypatch: MonkeyPatch,
) -> None:
    """DI OCR should surface page-quality warnings from page metadata."""

    def fake_resolve_document_bytes(
        request: DocumentIngestionRequest,
        settings: AppSettings,
    ) -> bytes:
        del request, settings
        return b"%PDF-1.7 test"

    class FakeDocumentIntelligenceClient:
        """Document Intelligence stub that returns one low-quality page."""

        def __init__(self, **kwargs: object) -> None:
            del kwargs

        def begin_analyze_document(self, **kwargs: object) -> SimpleNamespace:
            del kwargs
            result = SimpleNamespace(
                content="Detected text",
                pages=[
                    SimpleNamespace(
                        angle=12.5,
                        height=600,
                        unit="pixel",
                        width=800,
                        words=[SimpleNamespace(confidence=0.91)],
                    )
                ],
            )
            return SimpleNamespace(result=lambda: result)

    monkeypatch.setattr(
        "document_intelligence.extraction.resolve_document_bytes",
        fake_resolve_document_bytes,
    )
    monkeypatch.setattr(
        "document_intelligence.extraction.DocumentIntelligenceClient",
        FakeDocumentIntelligenceClient,
    )

    request = DocumentIngestionRequest(
        document_id="doc-pdf-001",
        source=DocumentSource.SCANNED_UPLOAD,
        source_uri="manual://packets/doc-pdf-001",
        file_name="scan.pdf",
        content_type="application/pdf",
        received_at_utc=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
    )
    settings = AppSettings(
        document_intelligence_endpoint="https://example.cognitiveservices.azure.com/",
        document_intelligence_key="test-key",
        ocr_low_resolution_page_pixels=1000,
        ocr_rotation_angle_warning_degrees=5.0,
    )

    ocr_text, ocr_confidence, page_count, warnings, provider = extract_ocr_text(
        request,
        settings,
    )

    assert ocr_text == "Detected text"
    assert ocr_confidence == 0.91
    assert page_count == 1
    assert provider == "azure_document_intelligence"
    assert any("rotation angle 12.5 degrees exceeded" in warning for warning in warnings)
    assert any("shorter pixel edge 600 was below" in warning for warning in warnings)
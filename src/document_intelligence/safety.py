"""Shared safety, guardrail, and masking helpers for operator workflows."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from document_intelligence.models import (
    ProcessingStageName,
    SafetyIssue,
    SafetyIssueSeverity,
)

_EMAIL_RE = re.compile(
    r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b"
)
_LONG_NUMBER_RE = re.compile(r"\b(?:\d[ -]?){6,}\d\b")
_OPENXML_CONTENT_TYPES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)
_OPENXML_REQUIRED_MEMBER_BY_SUFFIX = {
    ".docx": "word/document.xml",
    ".pptx": "ppt/presentation.xml",
    ".xlsx": "xl/workbook.xml",
}
_PDF_CONTENT_TYPE = "application/pdf"
_PDF_ENCRYPTION_MARKERS = (b"/Encrypt", b"/Filter /Standard")
_PDF_HEADER = b"%PDF-"


def build_content_controls(
    *,
    masked_fields: tuple[str, ...],
    retention_class: str,
    contains_sensitive_content: bool | None = None,
) -> dict[str, object]:
    """Return content-control metadata for audit and history payloads."""

    return {
        "containsSensitiveContent": (
            bool(masked_fields)
            if contains_sensitive_content is None
            else contains_sensitive_content
        ),
        "maskedFields": list(masked_fields),
        "retentionClass": retention_class,
    }


def attach_content_controls(
    payload: dict[str, object] | None,
    *,
    masked_fields: tuple[str, ...] = (),
    retention_class: str,
    contains_sensitive_content: bool | None = None,
) -> dict[str, object]:
    """Return one payload with attached content-control metadata."""

    controlled_payload = dict(payload or {})
    controlled_payload["contentControls"] = build_content_controls(
        masked_fields=masked_fields,
        retention_class=retention_class,
        contains_sensitive_content=contains_sensitive_content,
    )
    return controlled_payload


def inspect_document_safety(
    *,
    content_type: str,
    document_bytes: bytes,
    file_name: str,
) -> tuple[SafetyIssue, ...]:
    """Inspect non-archive documents for malformed or blocked input states."""

    normalized_content_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    normalized_suffix = Path(file_name).suffix.lower()
    issues: list[SafetyIssue] = []

    if normalized_content_type == _PDF_CONTENT_TYPE or normalized_suffix == ".pdf":
        issues.extend(_inspect_pdf_document(document_bytes))

    if (
        normalized_content_type in _OPENXML_CONTENT_TYPES
        or normalized_suffix in _OPENXML_REQUIRED_MEMBER_BY_SUFFIX
    ):
        issues.extend(_inspect_openxml_document(document_bytes, normalized_suffix))

    return tuple(issues)


def mask_sensitive_text(value: str | None) -> str | None:
    """Mask obvious PII-like content in operator history fields."""

    if value is None:
        return None

    masked_value = _EMAIL_RE.sub(r"\1***\2", value)
    return _LONG_NUMBER_RE.sub(_mask_long_number_match, masked_value)


def mask_sensitive_payload(
    payload: object,
    *,
    field_path: str = "value",
) -> tuple[object, tuple[str, ...]]:
    """Mask strings in nested payloads and return the changed field paths."""

    if isinstance(payload, str):
        masked_value = mask_sensitive_text(payload)
        if masked_value != payload:
            return masked_value, (field_path,)

        return payload, ()

    if isinstance(payload, list):
        masked_items: list[object] = []
        masked_fields: list[str] = []
        for index, item in enumerate(payload):
            masked_item, item_fields = mask_sensitive_payload(
                item,
                field_path=f"{field_path}[{index}]",
            )
            masked_items.append(masked_item)
            masked_fields.extend(item_fields)

        return masked_items, tuple(masked_fields)

    if isinstance(payload, dict):
        masked_payload: dict[str, object] = {}
        masked_fields: list[str] = []
        for key, value in payload.items():
            normalized_key = str(key)
            masked_value, value_fields = mask_sensitive_payload(
                value,
                field_path=(
                    f"{field_path}.{normalized_key}"
                    if field_path
                    else normalized_key
                ),
            )
            masked_payload[normalized_key] = masked_value
            masked_fields.extend(value_fields)

        return masked_payload, tuple(masked_fields)

    return payload, ()


def mask_history_payload(
    payload: dict[str, object] | None,
    *,
    retention_class: str,
) -> dict[str, object]:
    """Mask one history payload and append content-control metadata."""

    masked_payload, masked_fields = mask_sensitive_payload(payload or {}, field_path="")
    if not isinstance(masked_payload, dict):
        masked_payload = {}

    return attach_content_controls(
        masked_payload,
        masked_fields=tuple(sorted(field for field in masked_fields if field)),
        retention_class=retention_class,
    )


def parse_safety_issues(payload: object) -> tuple[SafetyIssue, ...]:
    """Parse a serialized safety-issue list from event or result payloads."""

    if not isinstance(payload, list):
        return ()

    parsed_issues: list[SafetyIssue] = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        try:
            parsed_issues.append(SafetyIssue.model_validate(item))
        except Exception:
            continue

    return tuple(parsed_issues)


def serialize_safety_issues(
    issues: tuple[SafetyIssue, ...],
) -> list[dict[str, object]]:
    """Serialize safety issues for SQL JSON payloads."""

    return [issue.model_dump(mode="json") for issue in issues]


def _inspect_openxml_document(
    document_bytes: bytes,
    normalized_suffix: str,
) -> tuple[SafetyIssue, ...]:
    """Inspect one OpenXML document for basic structural validity."""

    required_member = _OPENXML_REQUIRED_MEMBER_BY_SUFFIX.get(normalized_suffix)
    try:
        with ZipFile(BytesIO(document_bytes), mode="r", allowZip64=True) as archive:
            member_names = tuple(archive.namelist())
    except BadZipFile:
        return (
            SafetyIssue(
                code="malformed_office_file",
                message=(
                    "The uploaded Office file could not be opened and was routed "
                    "to quarantine."
                ),
                severity=SafetyIssueSeverity.BLOCKING,
                stage_name=ProcessingStageName.QUARANTINE,
            ),
        )

    if "[Content_Types].xml" not in member_names or (
        required_member is not None and required_member not in member_names
    ):
        return (
            SafetyIssue(
                code="malformed_office_file",
                message=(
                    "The uploaded Office file is missing required OpenXML parts "
                    "and was routed to quarantine."
                ),
                severity=SafetyIssueSeverity.BLOCKING,
                stage_name=ProcessingStageName.QUARANTINE,
            ),
        )

    return ()


def _inspect_pdf_document(document_bytes: bytes) -> tuple[SafetyIssue, ...]:
    """Inspect one PDF for encryption or obvious non-PDF content."""

    if not document_bytes.startswith(_PDF_HEADER):
        return (
            SafetyIssue(
                code="malformed_pdf",
                message=(
                    "The uploaded PDF does not expose a valid PDF header and was "
                    "routed to quarantine."
                ),
                severity=SafetyIssueSeverity.BLOCKING,
                stage_name=ProcessingStageName.QUARANTINE,
            ),
        )

    searchable_bytes = document_bytes[:65536] + document_bytes[-65536:]
    if any(marker in searchable_bytes for marker in _PDF_ENCRYPTION_MARKERS):
        return (
            SafetyIssue(
                code="password_protected_pdf",
                message=(
                    "Password-protected PDFs are quarantined until document "
                    "decryption support is implemented."
                ),
                severity=SafetyIssueSeverity.BLOCKING,
                stage_name=ProcessingStageName.QUARANTINE,
            ),
        )

    return ()


def _mask_long_number_match(match: re.Match[str]) -> str:
    """Mask a long numeric sequence while preserving the final four digits."""

    matched_text = match.group(0)
    digits = [character for character in matched_text if character.isdigit()]
    if len(digits) <= 4:
        return matched_text

    visible_start = len(digits) - 4
    digit_index = 0
    masked_characters: list[str] = []
    for character in matched_text:
        if not character.isdigit():
            masked_characters.append(character)
            continue

        masked_characters.append("x" if digit_index < visible_start else character)
        digit_index += 1

    return "".join(masked_characters)

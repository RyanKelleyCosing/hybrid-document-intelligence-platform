"""Real extraction adapters for OCR and issuer-aware LLM enrichment."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Iterable
from io import BytesIO
from statistics import fmean
from typing import Any
from urllib.parse import unquote

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from azure.storage.blob import BlobClient
from openai import AzureOpenAI

from document_intelligence.inspection import parse_blob_source_uri
from document_intelligence.models import (
    AccountMatchResult,
    AccountMatchStatus,
    ClassificationResultRecord,
    DocumentAnalysisResult,
    DocumentIngestionRequest,
    ExtractedField,
    ExtractionStrategySelection,
    ManagedDocumentTypeDefinitionRecord,
)
from document_intelligence.profiles import select_prompt_profile
from document_intelligence.settings import AppSettings

MAX_PROMPT_TEXT_CHARS = 12000
OCR_QUALITY_WARNING_PREFIX = "ocr_quality_warning:"
AZURE_DOCUMENT_INTELLIGENCE_SUPPORTED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
ACCOUNT_NUMBER_MATCH_FIELDS = frozenset({"account_number", "account_reference"})
PARTY_NAME_MATCH_FIELDS = frozenset(
    {"account_holder", "debtor_name", "patient_name"}
)


def collapse_fields(fields: Iterable[ExtractedField]) -> tuple[ExtractedField, ...]:
    """Keep only the highest-confidence value for each field name."""
    collapsed: dict[str, ExtractedField] = {}

    for field in fields:
        normalized_name = field.name.strip().lower()
        candidate = field.model_copy(update={"name": normalized_name})
        current = collapsed.get(normalized_name)
        if current is None or candidate.confidence > current.confidence:
            collapsed[normalized_name] = candidate

    return tuple(collapsed[name] for name in sorted(collapsed))


def decode_document_bytes(request: DocumentIngestionRequest) -> bytes | None:
    """Decode an inline base64 document payload if one was provided."""
    if not request.document_content_base64:
        return None

    try:
        return base64.b64decode(request.document_content_base64, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("document_content_base64 is not valid base64") from error


def parse_blob_reference(source_uri: str) -> tuple[str, str] | None:
    """Extract a container and blob path from an Azure blob-style URI."""
    blob_reference = parse_blob_source_uri(source_uri)
    if blob_reference is None:
        return None

    container_name, blob_name = blob_reference
    return container_name, unquote(blob_name)


def resolve_matching_path(required_fields: Iterable[str]) -> str:
    """Choose the account-matching path implied by the extraction contract."""

    normalized_required_fields = {
        field_name.strip().lower()
        for field_name in required_fields
        if field_name.strip()
    }
    if normalized_required_fields & ACCOUNT_NUMBER_MATCH_FIELDS:
        return "account_number_lookup"

    if normalized_required_fields & PARTY_NAME_MATCH_FIELDS:
        return "party_name_lookup"

    return "request_candidate_hints"


def _coerce_optional_float(value: object) -> float | None:
    """Return a float when the supplied value can be parsed."""

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_ocr_quality_warnings(
    result: Any,
    settings: AppSettings,
) -> tuple[str, ...]:
    """Return OCR page-quality warnings derived from DI page metadata."""

    warnings: list[str] = []
    for page_number, page in enumerate(result.pages or [], start=1):
        angle = _coerce_optional_float(getattr(page, "angle", None))
        if (
            angle is not None
            and abs(angle) > settings.ocr_rotation_angle_warning_degrees
        ):
            warnings.append(
                f"{OCR_QUALITY_WARNING_PREFIX} Page {page_number} rotation angle "
                f"{angle:.1f} degrees exceeded the warning threshold of "
                f"{settings.ocr_rotation_angle_warning_degrees:.1f}."
            )

        width = _coerce_optional_float(getattr(page, "width", None))
        height = _coerce_optional_float(getattr(page, "height", None))
        unit = str(getattr(page, "unit", "") or "").strip().lower()
        if width is None or height is None or unit != "pixel":
            continue

        shorter_edge = int(round(min(width, height)))
        if shorter_edge < settings.ocr_low_resolution_page_pixels:
            warnings.append(
                f"{OCR_QUALITY_WARNING_PREFIX} Page {page_number} shorter pixel "
                f"edge {shorter_edge} was below the minimum threshold of "
                f"{settings.ocr_low_resolution_page_pixels}."
            )

    return tuple(warnings)


def build_match_request(
    request: DocumentIngestionRequest,
    account_match: AccountMatchResult,
) -> DocumentIngestionRequest:
    """Project resolved account candidates back onto the request payload."""

    account_candidates = tuple(
        candidate.account_id for candidate in account_match.candidates
    )
    if (
        account_match.status == AccountMatchStatus.MATCHED
        and account_match.selected_account_id is not None
    ):
        account_candidates = (account_match.selected_account_id,)

    return request.model_copy(
        update={
            "account_candidates": account_candidates
        }
    )


def select_extraction_strategy(
    *,
    classification_result: ClassificationResultRecord | None,
    document_type_definitions: tuple[ManagedDocumentTypeDefinitionRecord, ...],
    request: DocumentIngestionRequest,
    settings: AppSettings,
) -> ExtractionStrategySelection:
    """Resolve the extraction contract for one packet document."""

    if classification_result is not None:
        document_type_id = classification_result.document_type_id
        if document_type_id is None:
            raise ValueError(
                "A classified document must include document_type_id before OCR runs."
            )

        document_type_definition = next(
            (
                definition
                for definition in document_type_definitions
                if definition.document_type_id == document_type_id
                and definition.is_enabled
            ),
            None,
        )
        if document_type_definition is None:
            raise ValueError(
                f"Managed document type '{document_type_id}' is not available."
            )

        required_fields = (
            document_type_definition.required_fields or settings.required_fields
        )
        prompt_profile_id = (
            classification_result.prompt_profile_id
            or document_type_definition.default_prompt_profile_id
            or request.requested_prompt_profile_id
        )
        return ExtractionStrategySelection(
            classification_result_id=classification_result.classification_result_id,
            document_type_id=document_type_definition.document_type_id,
            document_type_key=document_type_definition.document_type_key,
            matching_path=resolve_matching_path(required_fields),
            prompt_profile_id=prompt_profile_id,
            required_fields=required_fields,
            strategy_source="classification_contract",
        )

    prompt_profile = select_prompt_profile(request)
    document_type_key = (
        prompt_profile.document_type_hints[0]
        if prompt_profile.document_type_hints
        else None
    )
    return ExtractionStrategySelection(
        document_type_key=document_type_key,
        matching_path=resolve_matching_path(settings.required_fields),
        prompt_profile_id=prompt_profile.primary_profile_id,
        required_fields=settings.required_fields,
        strategy_source="request_heuristics",
    )


def apply_extraction_strategy(
    request: DocumentIngestionRequest,
    strategy: ExtractionStrategySelection,
) -> DocumentIngestionRequest:
    """Apply a persisted extraction strategy to a normalized request."""

    return request.model_copy(
        update={
            "requested_prompt_profile_id": (
                strategy.prompt_profile_id or request.requested_prompt_profile_id
            ),
            "source_tags": tuple(
                tag
                for tag in (
                    *request.source_tags,
                    strategy.document_type_key or "",
                )
                if tag
            ),
        }
    )


def resolve_document_bytes(
    request: DocumentIngestionRequest,
    settings: AppSettings,
) -> bytes | None:
    """Resolve document bytes from inline content or Azure Blob storage."""
    inline_bytes = decode_document_bytes(request)
    if inline_bytes is not None:
        return inline_bytes

    blob_reference = parse_blob_reference(request.source_uri)
    if blob_reference is None or not settings.storage_connection_string:
        return None

    container_name, blob_name = blob_reference
    blob_client = BlobClient.from_connection_string(
        conn_str=settings.storage_connection_string,
        container_name=container_name,
        blob_name=blob_name,
    )
    return blob_client.download_blob().readall()


def is_azure_document_intelligence_supported(content_type: str) -> bool:
    """Return whether a content type should be sent to Azure DI OCR."""
    normalized_content_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    return normalized_content_type.startswith("image/") or (
        normalized_content_type
        in AZURE_DOCUMENT_INTELLIGENCE_SUPPORTED_CONTENT_TYPES
    )


def extract_ocr_text(
    request: DocumentIngestionRequest,
    settings: AppSettings,
) -> tuple[str, float, int, tuple[str, ...], str]:
    """Run OCR through Azure Document Intelligence when configuration is present."""
    warnings: list[str] = []
    document_bytes = resolve_document_bytes(request, settings)

    if (
        document_bytes is not None
        and settings.document_intelligence_endpoint
        and settings.document_intelligence_key
    ):
        if not is_azure_document_intelligence_supported(request.content_type):
            warnings.append(
                "used document_text because Azure Document Intelligence does "
                f"not support content_type '{request.content_type}'"
            )
            if request.document_text:
                return (
                    request.document_text,
                    1.0,
                    0,
                    tuple(warnings),
                    "request_document_text",
                )

            warnings.append(
                "document_text was not provided for the unsupported content type"
            )
            return "", 0.0, 0, tuple(warnings), "ocr_unsupported_content_type"

        client = DocumentIntelligenceClient(
            endpoint=settings.document_intelligence_endpoint,
            credential=AzureKeyCredential(settings.document_intelligence_key),
        )
        poller = client.begin_analyze_document(
            model_id=settings.document_intelligence_model_id,
            body=BytesIO(document_bytes),
            content_type=request.content_type,
        )
        result = poller.result()
        word_confidences = [
            float(word.confidence)
            for page in (result.pages or [])
            for word in (page.words or [])
            if word.confidence is not None
        ]
        ocr_confidence = fmean(word_confidences) if word_confidences else 0.0
        page_count = len(result.pages or [])
        warnings.extend(_build_ocr_quality_warnings(result, settings))
        return (
            result.content or request.document_text or "",
            ocr_confidence,
            page_count,
            tuple(warnings),
            "azure_document_intelligence",
        )

    if request.document_text:
        warnings.append(
            "used document_text because Azure Document Intelligence input bytes "
            "were not available"
        )
        return request.document_text, 1.0, 0, tuple(warnings), "request_document_text"

    if document_bytes is None:
        warnings.append("no document bytes were available for OCR")
    else:
        warnings.append("Azure Document Intelligence is not configured")

    return "", 0.0, 0, tuple(warnings), "ocr_unavailable"


def build_llm_user_prompt(
    request: DocumentIngestionRequest,
    ocr_text: str,
    settings: AppSettings,
    *,
    required_fields: Iterable[str] | None = None,
) -> str:
    """Build the issuer-aware user prompt for Azure OpenAI extraction."""
    selected_profile = select_prompt_profile(request)
    effective_required_fields = tuple(required_fields or settings.required_fields)
    existing_fields = [
        {
            "name": field.name,
            "value": field.value,
            "confidence": field.confidence,
        }
        for field in request.extracted_fields
    ]

    prompt_payload = {
        "source": request.source.value,
        "source_uri": request.source_uri,
        "issuer_name": request.issuer_name,
        "issuer_category": request.issuer_category.value,
        "requested_prompt_profile": (
            request.requested_prompt_profile_id.value
            if request.requested_prompt_profile_id is not None
            else None
        ),
        "document_type_hints": list(selected_profile.document_type_hints),
        "keyword_hints": list(selected_profile.keyword_hints),
        "prompt_focus": list(selected_profile.prompt_focus),
        "required_fields": list(effective_required_fields),
        "existing_fields": existing_fields,
        "ocr_text": ocr_text[:MAX_PROMPT_TEXT_CHARS],
    }
    return (
        "Extract structured debt-relief fields from the document evidence below. "
        "Respond only with JSON using this shape: "
        '{"document_type":"string","summary":"string","fields":['
        '{"name":"string","value":"string","confidence":0.0}]}.\n\n'
        f"{json.dumps(prompt_payload, indent=2)}"
    )


def parse_llm_fields(payload: dict[str, Any]) -> tuple[ExtractedField, ...]:
    """Parse extracted fields from an Azure OpenAI JSON response."""
    field_items = payload.get("fields", [])
    parsed_fields: list[ExtractedField] = []
    if not isinstance(field_items, list):
        return ()

    for item in field_items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        value = str(item.get("value", "")).strip()
        if not name or not value:
            continue
        confidence_value = item.get("confidence", 0.5)
        try:
            confidence = max(0.0, min(1.0, float(confidence_value)))
        except (TypeError, ValueError):
            confidence = 0.5

        parsed_fields.append(
            ExtractedField(name=name, value=value, confidence=confidence)
        )

    return tuple(parsed_fields)


def run_openai_enrichment(
    request: DocumentIngestionRequest,
    settings: AppSettings,
    ocr_text: str,
    *,
    required_fields: Iterable[str] | None = None,
) -> tuple[str, str | None, tuple[ExtractedField, ...], tuple[str, ...], str]:
    """Run issuer-aware extraction through Azure OpenAI when configured."""
    warnings: list[str] = []
    prompt_profile = select_prompt_profile(request)

    if not (
        settings.azure_openai_endpoint
        and settings.azure_openai_api_key
        and settings.azure_openai_deployment
    ):
        warnings.append(
            "Azure OpenAI is not configured; using existing extracted fields"
        )
        default_document_type = (
            prompt_profile.document_type_hints[0]
            if prompt_profile.document_type_hints
            else "correspondence"
        )
        return (
            default_document_type,
            request.source_summary,
            collapse_fields(request.extracted_fields),
            tuple(warnings),
            "openai_unavailable",
        )

    client = AzureOpenAI(
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        azure_endpoint=settings.azure_openai_endpoint,
    )
    response = client.chat.completions.create(
        model=settings.azure_openai_deployment,
        response_format={"type": "json_object"},
        temperature=0.1,
        messages=[
            {
                "role": "system",
                "content": (
                    f"{prompt_profile.system_prompt} Respond only with valid JSON."
                ),
            },
            {
                "role": "user",
                "content": build_llm_user_prompt(
                    request,
                    ocr_text,
                    settings,
                    required_fields=required_fields,
                ),
            },
        ],
    )
    response_text = response.choices[0].message.content or "{}"
    payload = json.loads(response_text)
    llm_fields = parse_llm_fields(payload)
    merged_fields = collapse_fields((*request.extracted_fields, *llm_fields))
    default_document_type = (
        prompt_profile.document_type_hints[0]
        if prompt_profile.document_type_hints
        else "correspondence"
    )
    document_type = str(payload.get("document_type") or default_document_type)
    summary_value = payload.get("summary")
    summary = str(summary_value).strip() if summary_value else request.source_summary
    return document_type, summary, merged_fields, tuple(warnings), "azure_openai"


def extract_document(
    request: DocumentIngestionRequest,
    settings: AppSettings,
    *,
    required_fields: Iterable[str] | None = None,
) -> DocumentAnalysisResult:
    """Run the first real extraction pass across OCR and Azure OpenAI."""
    prompt_profile = select_prompt_profile(request)
    ocr_text, ocr_confidence, page_count, ocr_warnings, ocr_provider = extract_ocr_text(
        request,
        settings,
    )
    document_type, summary, extracted_fields, llm_warnings, llm_provider = (
        run_openai_enrichment(
            request,
            settings,
            ocr_text,
            required_fields=required_fields,
        )
    )
    provider_name = f"{ocr_provider}+{llm_provider}"

    return DocumentAnalysisResult(
        document_type=document_type,
        extracted_fields=extracted_fields,
        model_name=(
            f"{settings.document_intelligence_model_id}+{settings.azure_openai_deployment}"
        ),
        ocr_confidence=ocr_confidence,
        ocr_text=ocr_text or None,
        page_count=page_count,
        prompt_profile=prompt_profile,
        provider=provider_name,
        summary=summary,
        warnings=tuple((*ocr_warnings, *llm_warnings)),
    )


def extract_document_from_ocr(
    request: DocumentIngestionRequest,
    settings: AppSettings,
    *,
    ocr_confidence: float,
    ocr_provider: str,
    ocr_text: str,
    page_count: int,
    required_fields: Iterable[str] | None = None,
) -> DocumentAnalysisResult:
    """Run extraction from an already-persisted OCR result."""

    prompt_profile = select_prompt_profile(request)
    document_type, summary, extracted_fields, llm_warnings, llm_provider = (
        run_openai_enrichment(
            request,
            settings,
            ocr_text,
            required_fields=required_fields,
        )
    )
    provider_name = f"{ocr_provider}+{llm_provider}"

    return DocumentAnalysisResult(
        document_type=document_type,
        extracted_fields=extracted_fields,
        model_name=(
            f"{settings.document_intelligence_model_id}+{settings.azure_openai_deployment}"
        ),
        ocr_confidence=ocr_confidence,
        ocr_text=ocr_text or None,
        page_count=page_count,
        prompt_profile=prompt_profile,
        provider=provider_name,
        summary=summary,
        warnings=tuple(llm_warnings),
    )
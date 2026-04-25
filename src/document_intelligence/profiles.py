"""Source-aware prompt profile selection for extraction and classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from document_intelligence.models import (
    DocumentIngestionRequest,
    IssuerCategory,
    ProfileSelectionMode,
    PromptProfileCandidate,
    PromptProfileId,
    PromptProfileSelection,
)


@dataclass(frozen=True)
class ProfileDefinition:
    """Static configuration for a prompt profile."""

    document_type_hints: tuple[str, ...]
    issuer_category: IssuerCategory
    keyword_hints: tuple[str, ...]
    match_terms: tuple[str, ...]
    profile_id: PromptProfileId
    prompt_focus: tuple[str, ...]
    system_prompt: str


PROFILE_CATALOG: Final[tuple[ProfileDefinition, ...]] = (
    ProfileDefinition(
        profile_id=PromptProfileId.BANK_STATEMENT,
        issuer_category=IssuerCategory.BANK,
        document_type_hints=(
            "statement",
            "payment letter",
            "charge-off summary",
        ),
        keyword_hints=(
            "account number",
            "statement date",
            "current balance",
            "institution name",
        ),
        match_terms=(
            "bank",
            "statement",
            "checking",
            "savings",
            "routing",
            "cardmember",
            "credit union",
        ),
        prompt_focus=(
            "account identifiers",
            "statement periods",
            "balances",
            "institution evidence",
        ),
        system_prompt=(
            "You extract debt-relief evidence from bank-issued documents. "
            "Prioritize account numbers, statement dates, balances, institution "
            "names, payment due language, and account holder identity. Treat "
            "transaction tables as secondary unless they clarify ownership or "
            "debt amount."
        ),
    ),
    ProfileDefinition(
        profile_id=PromptProfileId.COURT_FILING,
        issuer_category=IssuerCategory.COURT,
        document_type_hints=("court filing", "judgment", "docket notice"),
        keyword_hints=(
            "case number",
            "court name",
            "filing date",
            "judgment amount",
        ),
        match_terms=(
            "court",
            "judgment",
            "docket",
            "summons",
            "complaint",
            "clerk",
            "superior court",
        ),
        prompt_focus=("case metadata", "party names", "venue", "deadlines"),
        system_prompt=(
            "You extract legal case metadata from court-issued documents. "
            "Prioritize court name, case number, plaintiff and defendant "
            "names, filing or judgment dates, amounts awarded, venue, and "
            "hearing deadlines. Distinguish stamped filing dates from service "
            "or correspondence dates."
        ),
    ),
    ProfileDefinition(
        profile_id=PromptProfileId.COLLECTION_NOTICE,
        issuer_category=IssuerCategory.COLLECTION_AGENCY,
        document_type_hints=(
            "collection notice",
            "validation notice",
            "demand letter",
        ),
        keyword_hints=(
            "collector name",
            "original creditor",
            "account reference",
            "dispute deadline",
        ),
        match_terms=(
            "collection",
            "debt collector",
            "validation notice",
            "mini-miranda",
            "agency",
            "charge-off",
        ),
        prompt_focus=(
            "creditor chain",
            "dispute rights",
            "amount claimed",
            "collector contact data",
        ),
        system_prompt=(
            "You extract debt-collection metadata from collector correspondence. "
            "Prioritize collector identity, original creditor, account "
            "reference numbers, balance claimed, validation or dispute "
            "deadlines, and mailing addresses. Separate the current collector "
            "from the original creditor when both appear."
        ),
    ),
    ProfileDefinition(
        profile_id=PromptProfileId.LAW_FIRM_CORRESPONDENCE,
        issuer_category=IssuerCategory.LAW_FIRM,
        document_type_hints=(
            "attorney letter",
            "legal notice",
            "representation letter",
        ),
        keyword_hints=(
            "law firm",
            "attorney",
            "matter number",
            "client reference",
        ),
        match_terms=(
            "law office",
            "attorney",
            "esq",
            "legal",
            "matter",
            "counsel",
        ),
        prompt_focus=(
            "matter identifiers",
            "client names",
            "representation details",
            "response dates",
        ),
        system_prompt=(
            "You extract case and correspondence details from law-firm "
            "documents. Prioritize firm name, attorney names, matter or file "
            "numbers, client references, deadlines, and any account "
            "identifiers cited in the letter."
        ),
    ),
    ProfileDefinition(
        profile_id=PromptProfileId.HEALTHCARE_BILL,
        issuer_category=IssuerCategory.HEALTHCARE_PROVIDER,
        document_type_hints=(
            "medical bill",
            "patient statement",
            "provider notice",
        ),
        keyword_hints=(
            "patient name",
            "service date",
            "provider account",
            "balance due",
        ),
        match_terms=(
            "hospital",
            "clinic",
            "patient",
            "provider",
            "medical",
            "health",
            "service date",
        ),
        prompt_focus=(
            "patient identity",
            "provider identifiers",
            "service dates",
            "balance breakdown",
        ),
        system_prompt=(
            "You extract debt-relevant information from healthcare billing "
            "documents. Prioritize patient name, provider name, service dates, "
            "account numbers, guarantor names, and outstanding balances. "
            "Distinguish service dates from billing dates."
        ),
    ),
    ProfileDefinition(
        profile_id=PromptProfileId.UTILITY_BILL,
        issuer_category=IssuerCategory.UTILITY_PROVIDER,
        document_type_hints=(
            "utility bill",
            "disconnect notice",
            "service statement",
        ),
        keyword_hints=(
            "service address",
            "account number",
            "billing period",
            "amount due",
        ),
        match_terms=(
            "utility",
            "electric",
            "water",
            "gas",
            "service address",
            "meter",
            "disconnect",
        ),
        prompt_focus=(
            "service account data",
            "billing period",
            "service address",
            "amount due",
        ),
        system_prompt=(
            "You extract debt-relevant information from utility-provider "
            "documents. Prioritize service address, account number, billing "
            "period, balance due, provider identity, and shutoff or disconnect "
            "deadlines."
        ),
    ),
    ProfileDefinition(
        profile_id=PromptProfileId.GOVERNMENT_NOTICE,
        issuer_category=IssuerCategory.GOVERNMENT,
        document_type_hints=(
            "government notice",
            "agency letter",
            "compliance notice",
        ),
        keyword_hints=(
            "agency name",
            "notice id",
            "deadline",
            "amount assessed",
        ),
        match_terms=(
            "department",
            "state",
            "county",
            "agency",
            "notice",
            "compliance",
            "treasury",
        ),
        prompt_focus=(
            "agency references",
            "notice numbers",
            "deadlines",
            "amounts due",
        ),
        system_prompt=(
            "You extract action-oriented metadata from government notices. "
            "Prioritize agency name, notice identifiers, assessed amounts, "
            "deadlines, addresses, and any account or case references that "
            "connect the notice to a debtor record."
        ),
    ),
    ProfileDefinition(
        profile_id=PromptProfileId.GENERIC_CORRESPONDENCE,
        issuer_category=IssuerCategory.UNKNOWN,
        document_type_hints=("correspondence", "statement", "notice"),
        keyword_hints=(
            "account number",
            "statement date",
            "issuer name",
            "balance",
        ),
        match_terms=(),
        prompt_focus=(
            "account identifiers",
            "dates",
            "amounts",
            "issuer identity",
        ),
        system_prompt=(
            "You extract debt-relief evidence from mixed-source correspondence. "
            "Prioritize any account identifiers, issuer names, dates, balances, "
            "addresses, and legal or payment deadlines, then preserve enough "
            "context for downstream manual review."
        ),
    ),
)

PROFILE_BY_ID: Final[dict[PromptProfileId, ProfileDefinition]] = {
    profile.profile_id: profile for profile in PROFILE_CATALOG
}

DEFAULT_PROFILE_BY_CATEGORY: Final[dict[IssuerCategory, PromptProfileId]] = {
    IssuerCategory.BANK: PromptProfileId.BANK_STATEMENT,
    IssuerCategory.COLLECTION_AGENCY: PromptProfileId.COLLECTION_NOTICE,
    IssuerCategory.COURT: PromptProfileId.COURT_FILING,
    IssuerCategory.GOVERNMENT: PromptProfileId.GOVERNMENT_NOTICE,
    IssuerCategory.HEALTHCARE_PROVIDER: PromptProfileId.HEALTHCARE_BILL,
    IssuerCategory.LAW_FIRM: PromptProfileId.LAW_FIRM_CORRESPONDENCE,
    IssuerCategory.UNKNOWN: PromptProfileId.GENERIC_CORRESPONDENCE,
    IssuerCategory.UTILITY_PROVIDER: PromptProfileId.UTILITY_BILL,
}


def build_profile_selection(
    definition: ProfileDefinition,
    selection_mode: ProfileSelectionMode,
    candidates: tuple[PromptProfileCandidate, ...],
) -> PromptProfileSelection:
    """Create the external prompt-profile payload."""
    return PromptProfileSelection(
        candidate_profiles=candidates,
        document_type_hints=definition.document_type_hints,
        issuer_category=definition.issuer_category,
        keyword_hints=definition.keyword_hints,
        primary_profile_id=definition.profile_id,
        prompt_focus=definition.prompt_focus,
        selection_mode=selection_mode,
        system_prompt=definition.system_prompt,
    )


def build_search_text(request: DocumentIngestionRequest) -> str:
    """Assemble the normalized text used for profile scoring."""
    parts = [
        request.file_name,
        request.source_uri,
        request.issuer_name or "",
        request.source_summary or "",
        " ".join(request.source_tags),
        " ".join(field.name for field in request.extracted_fields),
        " ".join(field.value for field in request.extracted_fields),
    ]
    return " ".join(parts).lower()


def create_explicit_candidate(
    definition: ProfileDefinition,
    issuer_category: IssuerCategory,
) -> PromptProfileCandidate:
    """Create the candidate payload when the caller provides the issuer category."""
    return PromptProfileCandidate(
        profile_id=definition.profile_id,
        issuer_category=definition.issuer_category,
        rationale=(
            f"issuer category was provided explicitly as '{issuer_category.value}'",
        ),
        score=100,
    )


def find_definition(profile_id: PromptProfileId) -> ProfileDefinition:
    """Return the static definition for a prompt profile."""
    return PROFILE_BY_ID[profile_id]


def normalize_tags(source_tags: tuple[str, ...]) -> set[str]:
    """Normalize source tags into a lookup-friendly set."""
    return {
        tag.strip().lower().replace(" ", "_")
        for tag in source_tags
        if tag.strip()
    }


def score_profile(
    definition: ProfileDefinition,
    normalized_tags: set[str],
    search_text: str,
) -> PromptProfileCandidate:
    """Score a profile against the request context."""
    matched_terms = tuple(
        sorted(term for term in definition.match_terms if term in search_text)
    )
    score = len(matched_terms) * 12
    rationale: list[str] = []

    if definition.issuer_category.value in normalized_tags:
        score += 45
        rationale.append(
            f"source tags include issuer category '{definition.issuer_category.value}'"
        )

    if definition.profile_id.value in normalized_tags:
        score += 35
        rationale.append(
            f"source tags include prompt profile '{definition.profile_id.value}'"
        )

    if matched_terms:
        rationale.append(f"matched terms: {', '.join(matched_terms[:4])}")

    return PromptProfileCandidate(
        profile_id=definition.profile_id,
        issuer_category=definition.issuer_category,
        rationale=tuple(rationale),
        score=score,
    )


def select_prompt_profile(request: DocumentIngestionRequest) -> PromptProfileSelection:
    """Choose the prompt profile that best fits the incoming document signals."""
    if request.requested_prompt_profile_id is not None:
        definition = find_definition(request.requested_prompt_profile_id)
        requested_profile_id = request.requested_prompt_profile_id.value
        candidate = PromptProfileCandidate(
            profile_id=definition.profile_id,
            issuer_category=definition.issuer_category,
            rationale=(f"requested prompt profile was '{requested_profile_id}'",),
            score=100,
        )
        return build_profile_selection(
            definition,
            ProfileSelectionMode.EXPLICIT,
            (candidate,),
        )

    if request.issuer_category != IssuerCategory.UNKNOWN:
        profile_id = DEFAULT_PROFILE_BY_CATEGORY[request.issuer_category]
        definition = find_definition(profile_id)
        candidate = create_explicit_candidate(definition, request.issuer_category)
        return build_profile_selection(
            definition,
            ProfileSelectionMode.EXPLICIT,
            (candidate,),
        )

    normalized_tags = normalize_tags(request.source_tags)
    search_text = build_search_text(request)
    heuristic_candidates = tuple(
        sorted(
            (
                score_profile(definition, normalized_tags, search_text)
                for definition in PROFILE_CATALOG
                if definition.profile_id != PromptProfileId.GENERIC_CORRESPONDENCE
            ),
            key=lambda candidate: candidate.score,
            reverse=True,
        )
    )

    top_candidate = heuristic_candidates[0]
    if top_candidate.score == 0:
        definition = find_definition(PromptProfileId.GENERIC_CORRESPONDENCE)
        candidate = PromptProfileCandidate(
            profile_id=definition.profile_id,
            issuer_category=definition.issuer_category,
            rationale=(
                "no strong issuer signals were found, so the generic profile "
                "was selected",
            ),
            score=0,
        )
        return build_profile_selection(
            definition,
            ProfileSelectionMode.FALLBACK,
            (candidate,),
        )

    top_candidates = tuple(
        candidate for candidate in heuristic_candidates[:3] if candidate.score > 0
    )
    definition = find_definition(top_candidate.profile_id)
    return build_profile_selection(
        definition,
        ProfileSelectionMode.HEURISTIC,
        top_candidates,
    )
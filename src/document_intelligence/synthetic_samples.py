"""Synthetic sample generation for safe Azure and local workflow tests."""

from __future__ import annotations

import base64
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from textwrap import wrap
from typing import Any, Literal
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from document_intelligence.models import (
    DocumentIngestionRequest,
    DocumentSource,
    IssuerCategory,
    PromptProfileId,
)

DocumentRenderKind = Literal["jpg", "pdf", "png", "rtf", "xlsx", "zip"]
InlineContentMode = Literal["bytes", "text_only"]
ScenarioSet = Literal["all", "debt-relief-intake", "default"]

EXCEL_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@dataclass(frozen=True)
class SyntheticArchiveEntrySpec:
    """A file embedded within a synthetic archive."""

    content_type: str
    file_name: str
    render_kind: DocumentRenderKind
    text_lines: tuple[str, ...]


@dataclass(frozen=True)
class SyntheticAccountSpec:
    """Synthetic account metadata associated with a scenario."""

    account_id: str
    account_number: str
    balance_due: str
    debt_type: str
    issuer_name: str


@dataclass(frozen=True)
class SyntheticDocumentSpec:
    """Metadata and rendering hints for a synthetic document."""

    content_type: str
    document_id: str
    file_name: str
    inline_content_mode: InlineContentMode
    issuer_name: str
    issuer_category: IssuerCategory
    received_at_utc: datetime
    render_kind: DocumentRenderKind
    source: DocumentSource
    source_summary: str
    source_tags: tuple[str, ...]
    source_uri: str
    account_candidates: tuple[str, ...] = ()
    archive_entries: tuple[SyntheticArchiveEntrySpec, ...] = ()
    headers: tuple[str, ...] = ()
    primary_account_id: str | None = None
    requested_prompt_profile_id: PromptProfileId | None = None
    rows: tuple[tuple[str, ...], ...] = ()
    text_lines: tuple[str, ...] = ()
    worksheet_name: str = "Document"


@dataclass(frozen=True)
class SyntheticCaseSpec:
    """A customer-level bundle of synthetic documents."""

    accounts: tuple[SyntheticAccountSpec, ...]
    case_id: str
    customer_alias: str
    documents: tuple[SyntheticDocumentSpec, ...]
    entry_point: str
    intake_description: str
    reason_for_visiting: str
    source: DocumentSource


def make_account(
    account_id: str,
    account_number: str,
    debt_type: str,
    issuer_name: str,
    balance_due: str,
) -> SyntheticAccountSpec:
    """Create a synthetic account definition."""
    return SyntheticAccountSpec(
        account_id=account_id,
        account_number=account_number,
        balance_due=balance_due,
        debt_type=debt_type,
        issuer_name=issuer_name,
    )


def make_archive_entry(
    file_name: str,
    text_lines: tuple[str, ...],
) -> SyntheticArchiveEntrySpec:
    """Create an archive entry for a synthetic portal batch."""
    return SyntheticArchiveEntrySpec(
        content_type="application/pdf",
        file_name=file_name,
        render_kind="pdf",
        text_lines=text_lines,
    )


def infer_render_profile(
    file_name: str,
) -> tuple[DocumentRenderKind, str, InlineContentMode]:
    """Infer rendering and inline-request behavior from a file name."""
    suffix = Path(file_name).suffix.lower()
    if suffix == ".pdf":
        return "pdf", "application/pdf", "bytes"
    if suffix in {".jpg", ".jpeg"}:
        return "jpg", "image/jpeg", "bytes"
    if suffix == ".png":
        return "png", "image/png", "bytes"
    if suffix == ".doc":
        return "rtf", "application/msword", "text_only"
    if suffix == ".xlsx":
        return "xlsx", EXCEL_CONTENT_TYPE, "bytes"
    if suffix == ".zip":
        return "zip", "application/zip", "text_only"
    raise ValueError(f"Unsupported synthetic file extension for '{file_name}'.")


def make_document(
    document_id: str,
    file_name: str,
    issuer_name: str,
    issuer_category: IssuerCategory,
    source_summary: str,
    source_tags: tuple[str, ...],
    source_uri: str,
    source: DocumentSource,
    received_at_utc: datetime,
    *,
    account_candidates: tuple[str, ...] = (),
    archive_entries: tuple[SyntheticArchiveEntrySpec, ...] = (),
    headers: tuple[str, ...] = (),
    primary_account_id: str | None = None,
    requested_prompt_profile_id: PromptProfileId | None = None,
    rows: tuple[tuple[str, ...], ...] = (),
    text_lines: tuple[str, ...] = (),
    worksheet_name: str = "Document",
) -> SyntheticDocumentSpec:
    """Create a synthetic document specification."""
    render_kind, content_type, inline_content_mode = infer_render_profile(file_name)
    return SyntheticDocumentSpec(
        account_candidates=account_candidates,
        archive_entries=archive_entries,
        content_type=content_type,
        document_id=document_id,
        file_name=file_name,
        headers=headers,
        inline_content_mode=inline_content_mode,
        issuer_category=issuer_category,
        issuer_name=issuer_name,
        primary_account_id=primary_account_id,
        received_at_utc=received_at_utc,
        render_kind=render_kind,
        requested_prompt_profile_id=requested_prompt_profile_id,
        rows=rows,
        source=source,
        source_summary=source_summary,
        source_tags=source_tags,
        source_uri=source_uri,
        text_lines=text_lines,
        worksheet_name=worksheet_name,
    )


def build_bankers_box_case() -> SyntheticCaseSpec:
    """Create a messy scanned-upload case with mixed creditor evidence."""
    received_at = datetime(2026, 4, 1, 9, 15, tzinfo=UTC)
    return SyntheticCaseSpec(
        accounts=(
            make_account(
                "acct-1001-checking",
                "ACCT-1001",
                "checking support evidence",
                "Northwind Credit Union",
                "$1,248.51",
            ),
            make_account(
                "acct-1001-utility",
                "UTIL-2201",
                "utility arrears",
                "City Utility Billing",
                "$186.22",
            ),
        ),
        case_id="case-1001",
        customer_alias="Avery-Cole",
        documents=(
            make_document(
                "doc-1001-payroll",
                "pay-history-q1-avery-cole.xlsx",
                "Tailspin Manufacturing Payroll",
                IssuerCategory.GOVERNMENT,
                "Quarterly pay history recovered from a mixed banker box.",
                ("pay-history", "income", "workbook"),
                "scan://bankers-box/case-1001/pay-history-q1-avery-cole.xlsx",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                headers=("pay_date", "gross_pay", "net_pay", "employer"),
                rows=(
                    (
                        "2026-01-15",
                        "$2,410.21",
                        "$1,864.14",
                        "Tailspin Manufacturing",
                    ),
                    (
                        "2026-01-30",
                        "$2,410.21",
                        "$1,861.02",
                        "Tailspin Manufacturing",
                    ),
                    (
                        "2026-02-15",
                        "$2,430.10",
                        "$1,875.84",
                        "Tailspin Manufacturing",
                    ),
                    (
                        "2026-02-28",
                        "$2,430.10",
                        "$1,872.79",
                        "Tailspin Manufacturing",
                    ),
                ),
                worksheet_name="Pay History",
            ),
            make_document(
                "doc-1001-bank-statement",
                "northwind-bank-statement-march.xlsx",
                "Northwind Credit Union",
                IssuerCategory.BANK,
                "Consumer checking account statement used during debt review.",
                ("bank", "statement", "checking"),
                "scan://bankers-box/case-1001/northwind-bank-statement-march.xlsx",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-1001-checking",),
                headers=(
                    "statement_date",
                    "account_number",
                    "debtor_name",
                    "ending_balance",
                ),
                primary_account_id="acct-1001-checking",
                requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                rows=(("2026-03-31", "ACCT-1001", "Avery Cole", "$1,248.51"),),
                worksheet_name="Statement",
            ),
            make_document(
                "doc-1001-utility",
                "city-utility-bill-march.xlsx",
                "City Utility Billing",
                IssuerCategory.UTILITY_PROVIDER,
                "Past-due utility bill mixed into the same intake box.",
                ("utility", "bill", "overdue"),
                "scan://bankers-box/case-1001/city-utility-bill-march.xlsx",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-1001-utility",),
                headers=("bill_date", "service_address", "amount_due", "due_date"),
                primary_account_id="acct-1001-utility",
                requested_prompt_profile_id=PromptProfileId.UTILITY_BILL,
                rows=(("2026-03-25", "1220 Cedar Ave", "$186.22", "2026-04-14"),),
                worksheet_name="Utility Bill",
            ),
            make_document(
                "doc-1001-receipts",
                "misc-receipts-march.xlsx",
                "Various Merchants",
                IssuerCategory.UNKNOWN,
                "Receipts and handwritten tracking recreated as a workbook.",
                ("receipts", "expenses", "mixed"),
                "scan://bankers-box/case-1001/misc-receipts-march.xlsx",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                headers=("purchase_date", "merchant", "category", "amount"),
                rows=(
                    ("2026-03-02", "Mercury Grocer", "groceries", "$94.10"),
                    ("2026-03-09", "Fabrikam Fuel", "gas", "$42.87"),
                    ("2026-03-12", "Contoso Pharmacy", "medical", "$18.34"),
                ),
                worksheet_name="Receipts",
            ),
        ),
        entry_point="bankers_box_scan",
        intake_description="Banker's box of mixed statements, bills, and receipts.",
        reason_for_visiting="Baseline synthetic smoke-test intake with mixed evidence.",
        source=DocumentSource.SCANNED_UPLOAD,
    )


def build_sftp_drop_case() -> SyntheticCaseSpec:
    """Create a cleaner SFTP drop with legal and collection documents."""
    received_at = datetime(2026, 4, 1, 10, 35, tzinfo=UTC)
    return SyntheticCaseSpec(
        accounts=(
            make_account(
                "acct-2001-collection",
                "ACCT-4002",
                "collection balance",
                "Contoso Collections",
                "$4,925.50",
            ),
            make_account(
                "acct-2001-court",
                "CV2026-2044",
                "court judgment",
                "Superior Court of Maricopa County",
                "$4,925.50",
            ),
        ),
        case_id="case-2001",
        customer_alias="Jordan-Patel",
        documents=(
            make_document(
                "doc-2001-collection",
                "contoso-collections-demand.xlsx",
                "Contoso Collections",
                IssuerCategory.COLLECTION_AGENCY,
                "Collection demand sheet delivered through SFTP.",
                ("collections", "demand", "sftp"),
                "sftp://landing-boxes/client-b/case-2001/contoso-collections-demand.xlsx",
                DocumentSource.AZURE_SFTP,
                received_at,
                account_candidates=("acct-2001-collection",),
                headers=(
                    "notice_date",
                    "debtor_name",
                    "account_number",
                    "balance_due",
                ),
                primary_account_id="acct-2001-collection",
                requested_prompt_profile_id=PromptProfileId.COLLECTION_NOTICE,
                rows=(("2026-03-20", "Jordan Patel", "ACCT-4002", "$4,925.50"),),
                worksheet_name="Collection Notice",
            ),
            make_document(
                "doc-2001-court",
                "maricopa-court-filing-summary.xlsx",
                "Superior Court of Maricopa County",
                IssuerCategory.COURT,
                "Court filing summary present in the same FTP drop.",
                ("court", "judgment", "filing"),
                "sftp://landing-boxes/client-b/case-2001/maricopa-court-filing-summary.xlsx",
                DocumentSource.AZURE_SFTP,
                received_at,
                account_candidates=("acct-2001-court", "acct-2001-collection"),
                headers=(
                    "case_number",
                    "filing_date",
                    "debtor_name",
                    "judgment_amount",
                ),
                primary_account_id="acct-2001-court",
                requested_prompt_profile_id=PromptProfileId.COURT_FILING,
                rows=(("CV2026-2044", "2026-03-18", "Jordan Patel", "$4,925.50"),),
                worksheet_name="Court Filing",
            ),
            make_document(
                "doc-2001-payroll",
                "pay-history-backfill-jordan-patel.xlsx",
                "Fabrikam Distribution Payroll",
                IssuerCategory.GOVERNMENT,
                "Supporting income workbook from the FTP drop.",
                ("pay-history", "income", "sftp"),
                "sftp://landing-boxes/client-b/case-2001/pay-history-backfill-jordan-patel.xlsx",
                DocumentSource.AZURE_SFTP,
                received_at,
                headers=("pay_date", "gross_pay", "net_pay", "employer"),
                rows=(
                    (
                        "2026-02-14",
                        "$2,180.48",
                        "$1,701.33",
                        "Fabrikam Distribution",
                    ),
                    (
                        "2026-02-28",
                        "$2,180.48",
                        "$1,698.22",
                        "Fabrikam Distribution",
                    ),
                    (
                        "2026-03-14",
                        "$2,205.12",
                        "$1,716.54",
                        "Fabrikam Distribution",
                    ),
                    (
                        "2026-03-28",
                        "$2,205.12",
                        "$1,713.18",
                        "Fabrikam Distribution",
                    ),
                ),
                worksheet_name="Pay History",
            ),
        ),
        entry_point="azure_sftp_drop",
        intake_description=(
            "Bulk FTP drop with limited sorting from a counselor portal."
        ),
        reason_for_visiting=(
            "Baseline FTP-driven intake case that mixes court, collection, and "
            "income support evidence."
        ),
        source=DocumentSource.AZURE_SFTP,
    )


def build_front_door_case() -> SyntheticCaseSpec:
    """Create a walk-in intake packet with credit-card and medical debt."""
    received_at = datetime(2026, 4, 1, 11, 5, tzinfo=UTC)
    base_uri = "scan://front-door/case-3001"
    return SyntheticCaseSpec(
        accounts=(
            make_account(
                "acct-3001-cc-987654",
                "987654",
                "credit card",
                "Northwind Platinum Card Services",
                "$10,842.17",
            ),
            make_account(
                "acct-3001-med-45678",
                "45678",
                "medical",
                "St. Mary Regional Medical Center",
                "$7,261.44",
            ),
            make_account(
                "acct-3001-checking-45678",
                "45678",
                "checking support evidence",
                "Northwind Credit Union",
                "$1,084.22",
            ),
        ),
        case_id="case-3001",
        customer_alias="Maria Gonzalez",
        documents=(
            make_document(
                "doc-3001-cc-statement",
                "CC_Statement_Dec_2023_Acc987654.pdf",
                "Northwind Platinum Card Services",
                IssuerCategory.BANK,
                "Walk-in credit-card statement captured during front-desk intake.",
                ("front-door", "credit-card", "statement"),
                f"{base_uri}/CC_Statement_Dec_2023_Acc987654.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-3001-cc-987654",),
                primary_account_id="acct-3001-cc-987654",
                requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                text_lines=(
                    "Account Statement",
                    "Customer: Maria Gonzalez",
                    "Account number: 987654",
                    "Statement date: 2023-12-28",
                    "Total balance due: $10,842.17",
                    "Minimum payment due: $394.00 by 2024-01-15",
                    "Past-due amount: $712.00",
                ),
            ),
            make_document(
                "doc-3001-hospital-bill",
                "hospital_bill_jan2024_scan001.jpg",
                "St. Mary Regional Medical Center",
                IssuerCategory.HEALTHCARE_PROVIDER,
                "Phone-scanned hospital bill included in the walk-in packet.",
                ("front-door", "medical", "scan"),
                f"{base_uri}/hospital_bill_jan2024_scan001.jpg",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-3001-med-45678",),
                primary_account_id="acct-3001-med-45678",
                requested_prompt_profile_id=PromptProfileId.HEALTHCARE_BILL,
                text_lines=(
                    "Hospital Bill",
                    "Patient: Maria Gonzalez",
                    "Account reference: 45678",
                    "Date of service: 2024-01-07",
                    "Procedure: Emergency appendectomy follow-up",
                    "Balance due: $4,980.22",
                    "Provider phone: 602-555-0104",
                ),
            ),
            make_document(
                "doc-3001-medical-summary",
                "acct_45678_medical_summary.doc",
                "St. Mary Regional Medical Center",
                IssuerCategory.HEALTHCARE_PROVIDER,
                "Legacy Word-export summary of treatment charges.",
                ("front-door", "medical", "legacy-doc"),
                f"{base_uri}/acct_45678_medical_summary.doc",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-3001-med-45678",),
                primary_account_id="acct-3001-med-45678",
                requested_prompt_profile_id=PromptProfileId.HEALTHCARE_BILL,
                text_lines=(
                    "Medical Summary",
                    "Patient name: Maria Gonzalez",
                    "Account number: 45678",
                    "January 2024 services include surgery, imaging, and pharmacy.",
                    "Insurance denied portion: $2,281.22",
                    "Self-pay balance remaining: $7,261.44",
                ),
            ),
            make_document(
                "doc-3001-payment-agreement",
                "payment_agreement_offer_12345.pdf",
                "St. Mary Patient Financial Services",
                IssuerCategory.HEALTHCARE_PROVIDER,
                "Provider settlement offer left with the debt-relief office.",
                ("front-door", "medical", "payment-plan"),
                f"{base_uri}/payment_agreement_offer_12345.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-3001-med-45678",),
                primary_account_id="acct-3001-med-45678",
                requested_prompt_profile_id=PromptProfileId.HEALTHCARE_BILL,
                text_lines=(
                    "Payment Agreement Offer",
                    "Account: 12345",
                    "Patient: Maria Gonzalez",
                    "Settlement amount if paid within 60 days: $5,400.00",
                    "Monthly payment option: $225.00 for 24 months",
                ),
            ),
            make_document(
                "doc-3001-late-notice",
                "credit_card_late_notice_9876.png",
                "Northwind Platinum Card Services",
                IssuerCategory.BANK,
                "Late-notice image captured from the client phone.",
                ("front-door", "credit-card", "late-notice"),
                f"{base_uri}/credit_card_late_notice_9876.png",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-3001-cc-987654",),
                primary_account_id="acct-3001-cc-987654",
                requested_prompt_profile_id=PromptProfileId.COLLECTION_NOTICE,
                text_lines=(
                    "Late Payment Notice",
                    "Card ending: 9876",
                    "Customer: Maria Gonzalez",
                    "Late fee assessed: $41.00",
                    "Past due since: 2024-01-12",
                    "Bring the account current immediately to avoid charge-off.",
                ),
            ),
            make_document(
                "doc-3001-bank-statement",
                "bank_stmt_Jan24_Acc#45678.pdf",
                "Northwind Credit Union",
                IssuerCategory.BANK,
                "January checking statement used to validate cash flow.",
                ("front-door", "bank", "cashflow"),
                f"{base_uri}/bank_stmt_Jan24_Acc#45678.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-3001-checking-45678",),
                primary_account_id="acct-3001-checking-45678",
                requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                text_lines=(
                    "Checking Statement",
                    "Account number: 45678",
                    "Statement date: 2024-01-31",
                    "Account holder: Maria Gonzalez",
                    "Ending balance: $1,084.22",
                    "Medical payment drafted: $300.00",
                ),
            ),
            make_document(
                "doc-3001-consolidation-form",
                "debt_consolidation_form_signed.pdf",
                "Contoso Debt Relief Intake",
                IssuerCategory.UNKNOWN,
                "Signed debt-consolidation intake form from the front desk.",
                ("front-door", "intake-form", "signed"),
                f"{base_uri}/debt_consolidation_form_signed.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                text_lines=(
                    "Debt Consolidation Intake Form",
                    "Client: Maria Gonzalez",
                    "Reason: credit-card and medical debt after unexpected surgery.",
                    "Goal: consolidate balances and negotiate with providers.",
                    "Requested monthly budget target: $550.00",
                ),
            ),
            make_document(
                "doc-3001-phone-scan",
                "scan_from_phone_maria_medical.pdf",
                "St. Mary Regional Medical Center",
                IssuerCategory.HEALTHCARE_PROVIDER,
                "Supplemental phone scan of provider itemization.",
                ("front-door", "medical", "phone-scan"),
                f"{base_uri}/scan_from_phone_maria_medical.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-3001-med-45678",),
                primary_account_id="acct-3001-med-45678",
                requested_prompt_profile_id=PromptProfileId.HEALTHCARE_BILL,
                text_lines=(
                    "Provider Itemization",
                    "Patient: Maria Gonzalez",
                    "Account number: 45678",
                    "Charges listed: operating room, anesthesia, lab work, recovery.",
                    "Current balance after insurance: $7,261.44",
                ),
            ),
            make_document(
                "doc-3001-collection-letter",
                "collection_letter_2024-01.pdf",
                "Fabrikam Recovery Services",
                IssuerCategory.COLLECTION_AGENCY,
                "Collection letter included alongside the medical packet.",
                ("front-door", "collection", "medical-debt"),
                f"{base_uri}/collection_letter_2024-01.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-3001-med-45678",),
                primary_account_id="acct-3001-med-45678",
                requested_prompt_profile_id=PromptProfileId.COLLECTION_NOTICE,
                text_lines=(
                    "Collection Letter",
                    "Debtor: Maria Gonzalez",
                    "Original creditor: St. Mary Regional Medical Center",
                    "Account reference: 45678",
                    "Amount referred to collections: $2,281.22",
                    "Response deadline: 2024-01-29",
                ),
            ),
        ),
        entry_point="front_door_walk_in",
        intake_description=(
            "Walk-in debt-relief intake with mixed phone scans, provider letters, "
            "and consumer statements."
        ),
        reason_for_visiting=(
            "$18k credit-card and medical debt after unexpected surgery; needs help "
            "consolidating and negotiating with providers."
        ),
        source=DocumentSource.SCANNED_UPLOAD,
    )


def build_court_packet_case() -> SyntheticCaseSpec:
    """Create a court-entry packet with garnishment and bankruptcy evidence."""
    received_at = datetime(2026, 4, 1, 11, 40, tzinfo=UTC)
    base_uri = "scan://court-packets/case-3002"
    return SyntheticCaseSpec(
        accounts=(
            make_account(
                "acct-3002-student-112233",
                "112233",
                "student loan",
                "Northwind Education Finance",
                "$14,908.66",
            ),
            make_account(
                "acct-3002-judgment-987654321",
                "987654321",
                "court judgment",
                "Maricopa Civil Court",
                "$6,112.40",
            ),
        ),
        case_id="case-3002",
        customer_alias="James Thompson",
        documents=(
            make_document(
                "doc-3002-court-summons",
                "court_summons_2024-02-15_Acc_112233.pdf",
                "Maricopa Civil Court",
                IssuerCategory.COURT,
                "Court summons packet for wage-garnishment litigation.",
                ("court", "summons", "student-loan"),
                f"{base_uri}/court_summons_2024-02-15_Acc_112233.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-3002-student-112233",),
                primary_account_id="acct-3002-student-112233",
                requested_prompt_profile_id=PromptProfileId.COURT_FILING,
                text_lines=(
                    "Civil Summons",
                    "Defendant: James Thompson",
                    "Account number: 112233",
                    "Case filed: 2024-02-15",
                    "Plaintiff: Northwind Education Finance",
                    "Hearing date: 2024-03-12",
                ),
            ),
            make_document(
                "doc-3002-judgment-notice",
                "judgment_notice_studentloan_987654321.pdf",
                "Maricopa Civil Court",
                IssuerCategory.COURT,
                "Judgment notice tied to the student-loan lawsuit.",
                ("court", "judgment", "student-loan"),
                f"{base_uri}/judgment_notice_studentloan_987654321.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=(
                    "acct-3002-student-112233",
                    "acct-3002-judgment-987654321",
                ),
                primary_account_id="acct-3002-judgment-987654321",
                requested_prompt_profile_id=PromptProfileId.COURT_FILING,
                text_lines=(
                    "Judgment Notice",
                    "Case number: CV-2024-7741",
                    "Judgment reference: 987654321",
                    "Debtor: James Thompson",
                    "Judgment amount: $6,112.40",
                    "Judgment entered: 2024-02-22",
                ),
            ),
            make_document(
                "doc-3002-garnishment-order",
                "wage_garnishment_order_scan.jpg",
                "Arizona Department of Labor Compliance",
                IssuerCategory.GOVERNMENT,
                "Phone scan of a wage-garnishment order.",
                ("court", "garnishment", "scan"),
                f"{base_uri}/wage_garnishment_order_scan.jpg",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-3002-judgment-987654321",),
                primary_account_id="acct-3002-judgment-987654321",
                requested_prompt_profile_id=PromptProfileId.GOVERNMENT_NOTICE,
                text_lines=(
                    "Wage Garnishment Order",
                    "Employee: James Thompson",
                    "Employer withholding begins: 2024-03-01",
                    "Amount per pay period: $246.00",
                    "Related judgment reference: 987654321",
                ),
            ),
            make_document(
                "doc-3002-bankruptcy-filing",
                "bankruptcy_filing_docs_Jan24.pdf",
                "United States Bankruptcy Court",
                IssuerCategory.COURT,
                "Bankruptcy packet the client is considering as an alternative.",
                ("court", "bankruptcy", "chapter-review"),
                f"{base_uri}/bankruptcy_filing_docs_Jan24.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                requested_prompt_profile_id=PromptProfileId.COURT_FILING,
                text_lines=(
                    "Bankruptcy Filing Draft",
                    "Debtor: James Thompson",
                    "Prepared January 2024",
                    "Considering Chapter 7 and Chapter 13 options",
                    "Listed unsecured debt: $21,487.00",
                ),
            ),
            make_document(
                "doc-3002-loan-statement",
                "loan_statement_2023_Q4.pdf",
                "Northwind Education Finance",
                IssuerCategory.BANK,
                "Quarterly student-loan statement.",
                ("student-loan", "statement", "quarterly"),
                f"{base_uri}/loan_statement_2023_Q4.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-3002-student-112233",),
                primary_account_id="acct-3002-student-112233",
                requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                text_lines=(
                    "Loan Statement",
                    "Borrower: James Thompson",
                    "Account number: 112233",
                    "Statement date: 2023-12-31",
                    "Outstanding principal: $14,908.66",
                    "Status: delinquent",
                ),
            ),
            make_document(
                "doc-3002-court-transcript",
                "court_transcript_page1-5.png",
                "Maricopa Civil Court Reporter",
                IssuerCategory.COURT,
                "Transcript excerpt image from the contested hearing.",
                ("court", "transcript", "image"),
                f"{base_uri}/court_transcript_page1-5.png",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                requested_prompt_profile_id=PromptProfileId.COURT_FILING,
                text_lines=(
                    "Transcript Excerpt",
                    "Matter: Thompson vs Northwind Education Finance",
                    "Judge notes a default judgment and wage withholding request.",
                    "Debtor reports difficulty paying after reduced work hours.",
                ),
            ),
            make_document(
                "doc-3002-creditor-list",
                "creditor_list_12345.pdf",
                "James Thompson Self-Prepared Filing Packet",
                IssuerCategory.UNKNOWN,
                "Creditor schedule bundled with the bankruptcy intake packet.",
                ("bankruptcy", "creditor-list", "client-prepared"),
                f"{base_uri}/creditor_list_12345.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=(
                    "acct-3002-student-112233",
                    "acct-3002-judgment-987654321",
                ),
                text_lines=(
                    "Creditor List",
                    "Reference: 12345",
                    "Northwind Education Finance - $14,908.66",
                    "Maricopa Civil Court Judgment - $6,112.40",
                    "Additional legal fees estimated at $1,240.00",
                ),
            ),
            make_document(
                "doc-3002-dispute-letter",
                "acct_112233_dispute_letter.pdf",
                "James Thompson",
                IssuerCategory.UNKNOWN,
                "Consumer dispute letter sent regarding the student-loan balance.",
                ("dispute", "student-loan", "client-letter"),
                f"{base_uri}/acct_112233_dispute_letter.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-3002-student-112233",),
                primary_account_id="acct-3002-student-112233",
                text_lines=(
                    "Dispute Letter",
                    "From: James Thompson",
                    "Account number: 112233",
                    (
                        "Requests validation of the claimed balance and "
                        "garnishment amount."
                    ),
                    "Letter dated: 2024-02-18",
                ),
            ),
            make_document(
                "doc-3002-court-seal",
                "official_court_seal_document.pdf",
                "Superior Court Filing Clerk",
                IssuerCategory.COURT,
                "Stamped filing receipt from the court packet.",
                ("court", "seal", "filing-receipt"),
                f"{base_uri}/official_court_seal_document.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                requested_prompt_profile_id=PromptProfileId.COURT_FILING,
                text_lines=(
                    "Official Filing Receipt",
                    "Stamped by Superior Court Clerk",
                    "Received date: 2024-02-15",
                    "Related case: CV-2024-7741",
                    "Party: James Thompson",
                ),
            ),
        ),
        entry_point="court_packet_dropoff",
        intake_description=(
            "Printed legal packet covering student-loan judgment, garnishment, and "
            "bankruptcy exploration."
        ),
        reason_for_visiting=(
            "Facing wage garnishment from old student loans and a recent court "
            "judgment; exploring Chapter 7/13 options."
        ),
        source=DocumentSource.SCANNED_UPLOAD,
    )


def build_bank_referral_case() -> SyntheticCaseSpec:
    """Create a bank-referred intake bundle with loan and overdraft evidence."""
    received_at = datetime(2026, 4, 1, 12, 15, tzinfo=UTC)
    base_uri = "blob://bank-referrals/case-3003"
    return SyntheticCaseSpec(
        accounts=(
            make_account(
                "acct-3003-loan-44556677",
                "44556677",
                "personal loan",
                "Chase Personal Lending",
                "$18,240.13",
            ),
            make_account(
                "acct-3003-overdraft-4455",
                "4455",
                "overdraft fees",
                "Chase Consumer Banking",
                "$3,941.88",
            ),
        ),
        case_id="case-3003",
        customer_alias="Sarah Chen",
        documents=(
            make_document(
                "doc-3003-statement",
                "Chase_Statement_2024-01_Account_44556677.pdf",
                "Chase Consumer Banking",
                IssuerCategory.BANK,
                "Bank-referred statement showing personal-loan stress.",
                ("bank-referral", "statement", "loan"),
                f"{base_uri}/Chase_Statement_2024-01_Account_44556677.pdf",
                DocumentSource.AZURE_BLOB,
                received_at,
                account_candidates=("acct-3003-loan-44556677",),
                primary_account_id="acct-3003-loan-44556677",
                requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                text_lines=(
                    "Monthly Statement",
                    "Customer: Sarah Chen",
                    "Account number: 44556677",
                    "Statement date: 2024-01-31",
                    "Loan balance: $18,240.13",
                    "Past-due amount: $1,188.00",
                ),
            ),
            make_document(
                "doc-3003-loan-balance-notice",
                "loan_balance_notice_2024-02.pdf",
                "Chase Personal Lending",
                IssuerCategory.BANK,
                "Loan balance notice attached to the referral packet.",
                ("bank-referral", "loan", "notice"),
                f"{base_uri}/loan_balance_notice_2024-02.pdf",
                DocumentSource.AZURE_BLOB,
                received_at,
                account_candidates=("acct-3003-loan-44556677",),
                primary_account_id="acct-3003-loan-44556677",
                requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                text_lines=(
                    "Loan Balance Notice",
                    "Borrower: Sarah Chen",
                    "Account number: 44556677",
                    "Notice date: 2024-02-12",
                    "Current payoff amount: $18,240.13",
                ),
            ),
            make_document(
                "doc-3003-overdraft-summary",
                "overdraft_fees_summary_Acc4455.jpg",
                "Chase Consumer Banking",
                IssuerCategory.BANK,
                "Image summary of accumulated overdraft charges.",
                ("bank-referral", "overdraft", "fees"),
                f"{base_uri}/overdraft_fees_summary_Acc4455.jpg",
                DocumentSource.AZURE_BLOB,
                received_at,
                account_candidates=("acct-3003-overdraft-4455",),
                primary_account_id="acct-3003-overdraft-4455",
                requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                text_lines=(
                    "Overdraft Fee Summary",
                    "Customer: Sarah Chen",
                    "Reference account: 4455",
                    "Fees charged in prior 90 days: $392.00",
                    "Returned payment fees: $144.00",
                ),
            ),
            make_document(
                "doc-3003-loan-agreement",
                "personal_loan_agreement_2023_signed.pdf",
                "Chase Personal Lending",
                IssuerCategory.BANK,
                "Signed personal-loan agreement retained by the bank.",
                ("bank-referral", "loan", "agreement"),
                f"{base_uri}/personal_loan_agreement_2023_signed.pdf",
                DocumentSource.AZURE_BLOB,
                received_at,
                account_candidates=("acct-3003-loan-44556677",),
                primary_account_id="acct-3003-loan-44556677",
                requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                text_lines=(
                    "Personal Loan Agreement",
                    "Borrower: Sarah Chen",
                    "Account number: 44556677",
                    "Original principal: $20,000.00",
                    "Signed: 2023-05-18",
                    "Lender: Chase Personal Lending",
                ),
            ),
            make_document(
                "doc-3003-bank-alert",
                "bank_alert_debt_collection.pdf",
                "Chase Collections Outreach",
                IssuerCategory.COLLECTION_AGENCY,
                "Debt-collection alert forwarded by the bank.",
                ("bank-referral", "collection", "alert"),
                f"{base_uri}/bank_alert_debt_collection.pdf",
                DocumentSource.AZURE_BLOB,
                received_at,
                account_candidates=("acct-3003-loan-44556677",),
                primary_account_id="acct-3003-loan-44556677",
                requested_prompt_profile_id=PromptProfileId.COLLECTION_NOTICE,
                text_lines=(
                    "Collection Alert",
                    "Client: Sarah Chen",
                    "Referenced account: 44556677",
                    (
                        "The account is scheduled for external collections "
                        "review on 2024-02-28."
                    ),
                ),
            ),
            make_document(
                "doc-3003-february-statement",
                "monthly_stmt_Feb24_Acc#445566.pdf",
                "Chase Consumer Banking",
                IssuerCategory.BANK,
                "Follow-up monthly statement with overdraft activity.",
                ("bank-referral", "statement", "february"),
                f"{base_uri}/monthly_stmt_Feb24_Acc#445566.pdf",
                DocumentSource.AZURE_BLOB,
                received_at,
                account_candidates=("acct-3003-overdraft-4455",),
                primary_account_id="acct-3003-overdraft-4455",
                requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                text_lines=(
                    "Monthly Statement",
                    "Account number: 445566",
                    "Statement date: 2024-02-29",
                    "Account holder: Sarah Chen",
                    "Overdraft recovery transfer failed twice.",
                    "Ending balance: -$271.44",
                ),
            ),
            make_document(
                "doc-3003-credit-score",
                "credit_score_report_attached.pdf",
                "Northwind Credit Insights",
                IssuerCategory.UNKNOWN,
                "Attached credit summary from the referral email.",
                ("bank-referral", "credit-score", "attachment"),
                f"{base_uri}/credit_score_report_attached.pdf",
                DocumentSource.AZURE_BLOB,
                received_at,
                text_lines=(
                    "Credit Score Summary",
                    "Consumer: Sarah Chen",
                    "Score as of 2024-02-16: 594",
                    (
                        "Primary negatives: personal loan delinquency and "
                        "overdraft activity."
                    ),
                ),
            ),
            make_document(
                "doc-3003-referral-letter",
                "bank_referral_letter_debthelp.pdf",
                "Chase Branch Support",
                IssuerCategory.BANK,
                "Bank referral letter recommending debt-management counseling.",
                ("bank-referral", "referral-letter", "debt-help"),
                f"{base_uri}/bank_referral_letter_debthelp.pdf",
                DocumentSource.AZURE_BLOB,
                received_at,
                text_lines=(
                    "Referral Letter",
                    "Client: Sarah Chen",
                    (
                        "Reason: repeated missed payments on personal loan "
                        "and overdraft fees."
                    ),
                    "Recommended next step: debt-management counseling within 14 days.",
                ),
            ),
            make_document(
                "doc-3003-transaction-history",
                "transaction_history_90days.pdf",
                "Chase Consumer Banking",
                IssuerCategory.BANK,
                "Ninety-day transaction history for underwriting context.",
                ("bank-referral", "transactions", "cashflow"),
                f"{base_uri}/transaction_history_90days.pdf",
                DocumentSource.AZURE_BLOB,
                received_at,
                account_candidates=("acct-3003-overdraft-4455",),
                primary_account_id="acct-3003-overdraft-4455",
                requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                text_lines=(
                    "Transaction History",
                    "Account reference: 4455",
                    "Three ACH returns in the last 90 days.",
                    "Total overdraft charges assessed: $392.00",
                    "Salary deposit reduced after February schedule changes.",
                ),
            ),
        ),
        entry_point="bank_referral_bundle",
        intake_description=(
            "Bank-emailed PDF bundle mixing statements, fee summaries, and a debt-help "
            "referral letter."
        ),
        reason_for_visiting=(
            "Over $22k in personal loans and overdraft fees; bank referred the client "
            "for debt management after missed payments."
        ),
        source=DocumentSource.AZURE_BLOB,
    )


def build_partner_ftp_case() -> SyntheticCaseSpec:
    """Create a cryptic partner FTP batch centered on auto-finance debt."""
    received_at = datetime(2026, 4, 1, 13, 5, tzinfo=UTC)
    base_uri = "sftp://partner-drops/case-3004"
    return SyntheticCaseSpec(
        accounts=(
            make_account(
                "acct-3004-auto-789012",
                "789012",
                "auto finance",
                "Fabrikam Auto Finance",
                "$16,740.55",
            ),
            make_account(
                "acct-3004-coll-00123456",
                "00123456",
                "collection account",
                "Northwind Recovery Group",
                "$8,442.19",
            ),
        ),
        case_id="case-3004",
        customer_alias="Robert Kline",
        documents=(
            make_document(
                "doc-3004-statement",
                "file_00123456_stmt_202401.pdf",
                "Northwind Recovery Group",
                IssuerCategory.COLLECTION_AGENCY,
                "Partner-exported collection statement with a cryptic file name.",
                ("ftp", "collections", "cryptic-name"),
                f"{base_uri}/file_00123456_stmt_202401.pdf",
                DocumentSource.AZURE_SFTP,
                received_at,
                account_candidates=("acct-3004-coll-00123456",),
                primary_account_id="acct-3004-coll-00123456",
                requested_prompt_profile_id=PromptProfileId.COLLECTION_NOTICE,
                text_lines=(
                    "Collection Statement",
                    "Debtor: Robert Kline",
                    "Account number: 00123456",
                    "Statement date: 2024-01-31",
                    "Balance due: $8,442.19",
                ),
            ),
            make_document(
                "doc-3004-auto-loan",
                "AUTO_LOAN_987654321_2023Q4.pdf",
                "Fabrikam Auto Finance",
                IssuerCategory.BANK,
                "Quarterly auto-loan statement from the repo session.",
                ("ftp", "auto-loan", "quarterly"),
                f"{base_uri}/AUTO_LOAN_987654321_2023Q4.pdf",
                DocumentSource.AZURE_SFTP,
                received_at,
                account_candidates=("acct-3004-auto-789012",),
                primary_account_id="acct-3004-auto-789012",
                requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                text_lines=(
                    "Auto Loan Statement",
                    "Borrower: Robert Kline",
                    "Loan reference: 987654321",
                    "Vehicle account number: 789012",
                    "Past-due balance: $16,740.55",
                    "Quarter ending: 2023-12-31",
                ),
            ),
            make_document(
                "doc-3004-repo-notice",
                "repo_notice_Acc_789012.pdf",
                "Fabrikam Auto Finance",
                IssuerCategory.COLLECTION_AGENCY,
                "Repossession notice from the partner FTP batch.",
                ("ftp", "repossession", "notice"),
                f"{base_uri}/repo_notice_Acc_789012.pdf",
                DocumentSource.AZURE_SFTP,
                received_at,
                account_candidates=("acct-3004-auto-789012",),
                primary_account_id="acct-3004-auto-789012",
                requested_prompt_profile_id=PromptProfileId.COLLECTION_NOTICE,
                text_lines=(
                    "Repossession Notice",
                    "Borrower: Robert Kline",
                    "Account number: 789012",
                    "Vehicle recovered on: 2024-01-24",
                    "Deficiency balance projected: $7,880.00",
                ),
            ),
            make_document(
                "doc-3004-collection-batch",
                "COLL_001_2024-02-01.pdf",
                "Northwind Recovery Group",
                IssuerCategory.COLLECTION_AGENCY,
                "Bulk collection notice generated by a partner system.",
                ("ftp", "collection", "partner-export"),
                f"{base_uri}/COLL_001_2024-02-01.pdf",
                DocumentSource.AZURE_SFTP,
                received_at,
                account_candidates=("acct-3004-coll-00123456",),
                primary_account_id="acct-3004-coll-00123456",
                requested_prompt_profile_id=PromptProfileId.COLLECTION_NOTICE,
                text_lines=(
                    "Collection Notice",
                    "Client: Robert Kline",
                    "Reference account: 00123456",
                    "Notice date: 2024-02-01",
                    "Balance transferred for collections: $8,442.19",
                ),
            ),
            make_document(
                "doc-3004-bulk-upload",
                "bulk_upload_batch_4455.pdf",
                "Partner FTP Export Service",
                IssuerCategory.UNKNOWN,
                "Batch cover sheet from the nightly FTP delivery.",
                ("ftp", "batch-cover", "partner"),
                f"{base_uri}/bulk_upload_batch_4455.pdf",
                DocumentSource.AZURE_SFTP,
                received_at,
                text_lines=(
                    "Batch Cover Sheet",
                    "Partner upload batch: 4455",
                    "Customer included: Robert Kline",
                    "Delivery type: nightly FTP export",
                    "Contains auto-finance and collection records.",
                ),
            ),
            make_document(
                "doc-3004-vehicle-loan-scan",
                "vehicle_loan_balance_scan001.jpg",
                "Fabrikam Auto Finance",
                IssuerCategory.BANK,
                "Phone image of the vehicle-loan payoff screen.",
                ("ftp", "auto-loan", "scan"),
                f"{base_uri}/vehicle_loan_balance_scan001.jpg",
                DocumentSource.AZURE_SFTP,
                received_at,
                account_candidates=("acct-3004-auto-789012",),
                primary_account_id="acct-3004-auto-789012",
                requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                text_lines=(
                    "Vehicle Loan Balance",
                    "Borrower: Robert Kline",
                    "Account number: 789012",
                    "Outstanding deficiency: $16,740.55",
                    "Collateral: 2018 Honda Accord",
                ),
            ),
            make_document(
                "doc-3004-account-lookup",
                "acct_lookup_789012_notice.pdf",
                "Northwind Recovery Group",
                IssuerCategory.COLLECTION_AGENCY,
                "Partner notice referencing the auto account in collections.",
                ("ftp", "collections", "account-lookup"),
                f"{base_uri}/acct_lookup_789012_notice.pdf",
                DocumentSource.AZURE_SFTP,
                received_at,
                account_candidates=(
                    "acct-3004-auto-789012",
                    "acct-3004-coll-00123456",
                ),
                requested_prompt_profile_id=PromptProfileId.COLLECTION_NOTICE,
                text_lines=(
                    "Account Lookup Notice",
                    "Customer: Robert Kline",
                    "Referenced account numbers: 789012 and 00123456",
                    (
                        "Partner could not determine whether the debt is "
                        "original or deficiency balance."
                    ),
                ),
            ),
            make_document(
                "doc-3004-partner-export",
                "partner_export_Kline_2024.pdf",
                "Vendor Debt Services",
                IssuerCategory.UNKNOWN,
                "Partner summary export containing client demographics and debt flags.",
                ("ftp", "partner-export", "summary"),
                f"{base_uri}/partner_export_Kline_2024.pdf",
                DocumentSource.AZURE_SFTP,
                received_at,
                text_lines=(
                    "Partner Export Summary",
                    "Client: Robert Kline",
                    "Debt categories: auto finance deficiency, collection account",
                    "Preferred contact status: needs counselor callback",
                ),
            ),
            make_document(
                "doc-3004-unidentified-debt",
                "unidentified_debt_00123456.pdf",
                "Vendor Debt Services",
                IssuerCategory.UNKNOWN,
                "Unclassified debt notice with weak account metadata.",
                ("ftp", "unknown-debt", "review"),
                f"{base_uri}/unidentified_debt_00123456.pdf",
                DocumentSource.AZURE_SFTP,
                received_at,
                account_candidates=(
                    "acct-3004-auto-789012",
                    "acct-3004-coll-00123456",
                ),
                text_lines=(
                    "Unidentified Debt Notice",
                    "Client: Robert Kline",
                    "Reference number: 00123456",
                    "The file does not clearly identify the original creditor.",
                    "Balance estimate: approximately $8,400.00",
                ),
            ),
        ),
        entry_point="partner_ftp_bulk_drop",
        intake_description=(
            "Nightly vendor FTP drop with cryptic filenames spanning repossession and "
            "collection activity."
        ),
        reason_for_visiting=(
            "Auto-finance debt from vehicle repossession and multiple collection "
            "accounts; files dropped nightly via partner FTP."
        ),
        source=DocumentSource.AZURE_SFTP,
    )


def build_mail_scan_case() -> SyntheticCaseSpec:
    """Create a mailed-paperwork case with medical and utility arrears."""
    received_at = datetime(2026, 4, 1, 13, 40, tzinfo=UTC)
    base_uri = "scan://physical-mail/case-3005"
    return SyntheticCaseSpec(
        accounts=(
            make_account(
                "acct-3005-med-334455",
                "334455",
                "medical collection",
                "Fabrikam Medical Collections",
                "$8,404.21",
            ),
            make_account(
                "acct-3005-utility-123456",
                "123456",
                "utility arrears",
                "City Utilities West",
                "$3,711.18",
            ),
        ),
        case_id="case-3005",
        customer_alias="Dorothy Williams",
        documents=(
            make_document(
                "doc-3005-utility-bill",
                "utility_bill_2024_Jan_scan_from_mail.pdf",
                "City Utilities West",
                IssuerCategory.UTILITY_PROVIDER,
                "Mailed utility bill scanned by family members.",
                ("mail-scan", "utility", "jan-bill"),
                f"{base_uri}/utility_bill_2024_Jan_scan_from_mail.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-3005-utility-123456",),
                primary_account_id="acct-3005-utility-123456",
                requested_prompt_profile_id=PromptProfileId.UTILITY_BILL,
                text_lines=(
                    "Utility Bill",
                    "Customer: Dorothy Williams",
                    "Account number: 123456",
                    "Bill date: 2024-01-08",
                    "Amount due: $412.20",
                    "Past-due total: $1,103.44",
                ),
            ),
            make_document(
                "doc-3005-medical-collection",
                "medical_collection_letter_Acc_334455.pdf",
                "Fabrikam Medical Collections",
                IssuerCategory.COLLECTION_AGENCY,
                "Medical collection notice found in the mailed box.",
                ("mail-scan", "medical", "collection"),
                f"{base_uri}/medical_collection_letter_Acc_334455.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-3005-med-334455",),
                primary_account_id="acct-3005-med-334455",
                requested_prompt_profile_id=PromptProfileId.COLLECTION_NOTICE,
                text_lines=(
                    "Medical Collection Letter",
                    "Debtor: Dorothy Williams",
                    "Account reference: 334455",
                    "Current balance: $8,404.21",
                    "Collector: Fabrikam Medical Collections",
                ),
            ),
            make_document(
                "doc-3005-envelope-scan",
                "envelope_scan_front_back.jpg",
                "United States Postal Service",
                IssuerCategory.UNKNOWN,
                "Envelope scan used to reconstruct document provenance.",
                ("mail-scan", "envelope", "provenance"),
                f"{base_uri}/envelope_scan_front_back.jpg",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                text_lines=(
                    "Envelope Front",
                    "Addressee: Dorothy Williams",
                    "Return address: Fabrikam Medical Collections",
                    "Postmark: 2024-01-19",
                    "Envelope Back: utility company insert enclosed.",
                ),
            ),
            make_document(
                "doc-3005-old-card-statement",
                "old_credit_card_stmt_2022.pdf",
                "Northwind Retail Card",
                IssuerCategory.BANK,
                "Older credit-card statement scanned from archived paperwork.",
                ("mail-scan", "credit-card", "archived"),
                f"{base_uri}/old_credit_card_stmt_2022.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                text_lines=(
                    "Archived Credit Card Statement",
                    "Customer: Dorothy Williams",
                    "Statement date: 2022-11-30",
                    "Balance carried: $1,864.00",
                    "Account ending: 4411",
                ),
            ),
            make_document(
                "doc-3005-final-notice",
                "final_notice_utility_123456.pdf",
                "City Utilities West",
                IssuerCategory.UTILITY_PROVIDER,
                "Final shutoff notice from the utility provider.",
                ("mail-scan", "utility", "final-notice"),
                f"{base_uri}/final_notice_utility_123456.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                account_candidates=("acct-3005-utility-123456",),
                primary_account_id="acct-3005-utility-123456",
                requested_prompt_profile_id=PromptProfileId.UTILITY_BILL,
                text_lines=(
                    "Final Notice",
                    "Account number: 123456",
                    "Customer: Dorothy Williams",
                    "Total past due: $3,711.18",
                    "Service interruption date: 2024-02-03",
                ),
            ),
            make_document(
                "doc-3005-handwritten-list",
                "handwritten_note_debt_list.pdf",
                "Dorothy Williams Family Notes",
                IssuerCategory.UNKNOWN,
                "Handwritten debt list rewritten into a clean synthetic document.",
                ("mail-scan", "handwritten", "summary"),
                f"{base_uri}/handwritten_note_debt_list.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                text_lines=(
                    "Handwritten Debt List",
                    "Medical collections about $8,400",
                    "Utility balance about $3,700",
                    "Old credit card maybe $1,800",
                    "Family note says client is on fixed income.",
                ),
            ),
            make_document(
                "doc-3005-medicare-summary",
                "medicare_summary_notice_2024.png",
                "Centers for Medicare & Medicaid Services",
                IssuerCategory.GOVERNMENT,
                "Government benefits summary included with medical paperwork.",
                ("mail-scan", "medicare", "benefits"),
                f"{base_uri}/medicare_summary_notice_2024.png",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                requested_prompt_profile_id=PromptProfileId.GOVERNMENT_NOTICE,
                text_lines=(
                    "Medicare Summary Notice",
                    "Beneficiary: Dorothy Williams",
                    "Claim date: 2024-01-12",
                    "Amount not covered: $1,942.10",
                    "Provider billed more than approved Medicare amount.",
                ),
            ),
            make_document(
                "doc-3005-mail-batch",
                "mail_batch_williams_001.pdf",
                "Family Scan Service",
                IssuerCategory.UNKNOWN,
                "Mail-batch cover page created by family while sorting paperwork.",
                ("mail-scan", "batch-cover", "family"),
                f"{base_uri}/mail_batch_williams_001.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                text_lines=(
                    "Mail Batch Cover",
                    "Family name: Williams",
                    "Batch number: 001",
                    (
                        "Contents include utility bills, medical "
                        "collections, and check stubs."
                    ),
                ),
            ),
            make_document(
                "doc-3005-check-stub",
                "scanned_check_stub_payment.pdf",
                "Northwind Community Bank",
                IssuerCategory.BANK,
                "Check stub showing a recent partial payment.",
                ("mail-scan", "check-stub", "payment-history"),
                f"{base_uri}/scanned_check_stub_payment.pdf",
                DocumentSource.SCANNED_UPLOAD,
                received_at,
                text_lines=(
                    "Check Stub",
                    "Drawer: Dorothy Williams",
                    "Payee: City Utilities West",
                    "Check date: 2024-01-05",
                    "Check amount: $75.00",
                ),
            ),
        ),
        entry_point="physical_mail_scan",
        intake_description=(
            "Family-scanned archive of mailed utility, medical, and handwritten debt "
            "paperwork."
        ),
        reason_for_visiting=(
            "Elderly client with $12k medical and utility debt; family scanning and "
            "mailing in old paperwork boxes."
        ),
        source=DocumentSource.SCANNED_UPLOAD,
    )


def build_portal_submission_case() -> SyntheticCaseSpec:
    """Create a portal and email submission with mixed digital artifacts."""
    received_at = datetime(2026, 4, 1, 14, 10, tzinfo=UTC)
    base_uri = "portal://submissions/case-3006"
    archive_entries = (
        make_archive_entry(
            "payday_lender_itemization.pdf",
            (
                "Payday lender itemization",
                "Borrower: Michael Rodriguez",
                "Account number: PDL-900101",
                "Outstanding amount: $3,120.00",
            ),
        ),
        make_archive_entry(
            "collection_call_log.pdf",
            (
                "Collection call log",
                "Collector called five times between 2024-02-03 and 2024-02-11.",
                "Account reference: 667788",
            ),
        ),
        make_archive_entry(
            "hardship_request.pdf",
            (
                "Hardship request",
                "Client reports job loss and requests a reduced settlement.",
                "Submitted by Michael Rodriguez.",
            ),
        ),
    )
    return SyntheticCaseSpec(
        accounts=(
            make_account(
                "acct-3006-payday-900101",
                "PDL-900101",
                "payday loan",
                "Fabrikam Payday Services",
                "$3,120.00",
            ),
            make_account(
                "acct-3006-cc-667788",
                "667788",
                "credit card",
                "Northwind Card Services",
                "$5,884.22",
            ),
        ),
        case_id="case-3006",
        customer_alias="Michael Rodriguez",
        documents=(
            make_document(
                "doc-3006-payday-agreement",
                "payday_loan_agreement_2024_email.pdf",
                "Fabrikam Payday Services",
                IssuerCategory.COLLECTION_AGENCY,
                "Email-attached payday-loan agreement from the portal intake.",
                ("portal", "email", "payday-loan"),
                f"{base_uri}/payday_loan_agreement_2024_email.pdf",
                DocumentSource.AZURE_BLOB,
                received_at,
                account_candidates=("acct-3006-payday-900101",),
                primary_account_id="acct-3006-payday-900101",
                requested_prompt_profile_id=PromptProfileId.COLLECTION_NOTICE,
                text_lines=(
                    "Payday Loan Agreement",
                    "Borrower: Michael Rodriguez",
                    "Account number: PDL-900101",
                    "Origination date: 2024-01-06",
                    "Current payoff amount: $3,120.00",
                ),
            ),
            make_document(
                "doc-3006-card-statement",
                "credit_card_maxout_statement_Acc_667788.pdf",
                "Northwind Card Services",
                IssuerCategory.BANK,
                "Maxed-out credit-card statement uploaded through the portal.",
                ("portal", "credit-card", "statement"),
                f"{base_uri}/credit_card_maxout_statement_Acc_667788.pdf",
                DocumentSource.AZURE_BLOB,
                received_at,
                account_candidates=("acct-3006-cc-667788",),
                primary_account_id="acct-3006-cc-667788",
                requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                text_lines=(
                    "Credit Card Statement",
                    "Cardholder: Michael Rodriguez",
                    "Account number: 667788",
                    "Statement date: 2024-02-29",
                    "Balance due: $5,884.22",
                    "Credit line available: $0.00",
                ),
            ),
            make_document(
                "doc-3006-unemployment-letter",
                "unemployment_benefit_letter.pdf",
                "Arizona Department of Economic Security",
                IssuerCategory.GOVERNMENT,
                "Unemployment benefit letter included for hardship context.",
                ("portal", "unemployment", "government"),
                f"{base_uri}/unemployment_benefit_letter.pdf",
                DocumentSource.AZURE_BLOB,
                received_at,
                requested_prompt_profile_id=PromptProfileId.GOVERNMENT_NOTICE,
                text_lines=(
                    "Unemployment Benefit Letter",
                    "Claimant: Michael Rodriguez",
                    "Weekly benefit amount: $412.00",
                    "Benefit start date: 2024-02-05",
                ),
            ),
            make_document(
                "doc-3006-portal-batch",
                "portal_upload_batch_rodriguez.zip",
                "Contoso Client Portal",
                IssuerCategory.UNKNOWN,
                "Portal archive that contains three supporting PDFs.",
                ("portal", "archive", "batch-upload"),
                f"{base_uri}/portal_upload_batch_rodriguez.zip",
                DocumentSource.AZURE_BLOB,
                received_at,
                archive_entries=archive_entries,
                account_candidates=(
                    "acct-3006-payday-900101",
                    "acct-3006-cc-667788",
                ),
                text_lines=(
                    "Portal Upload Batch",
                    (
                        "Archive contains three PDF files related to payday "
                        "collections and hardship requests."
                    ),
                    "Client: Michael Rodriguez",
                ),
            ),
            make_document(
                "doc-3006-email-summary",
                "email_attachment_debt_summary.pdf",
                "Michael Rodriguez",
                IssuerCategory.UNKNOWN,
                "Client-authored debt summary sent after the portal upload.",
                ("portal", "email", "client-summary"),
                f"{base_uri}/email_attachment_debt_summary.pdf",
                DocumentSource.AZURE_BLOB,
                received_at,
                account_candidates=(
                    "acct-3006-payday-900101",
                    "acct-3006-cc-667788",
                ),
                text_lines=(
                    "Debt Summary",
                    "Client: Michael Rodriguez",
                    "Payday loans total about $3,120.00",
                    "Credit cards total about $5,884.22",
                    "Client lost job and cannot keep up with minimum payments.",
                ),
            ),
            make_document(
                "doc-3006-paystub-scan",
                "paystub_last3months_scan.jpg",
                "Tailspin Logistics Payroll",
                IssuerCategory.GOVERNMENT,
                "Phone scan of the last stable paystub period before job loss.",
                ("portal", "income", "scan"),
                f"{base_uri}/paystub_last3months_scan.jpg",
                DocumentSource.AZURE_BLOB,
                received_at,
                text_lines=(
                    "Paystub Summary",
                    "Employee: Michael Rodriguez",
                    "Employer: Tailspin Logistics",
                    "Last regular pay date: 2024-01-26",
                    "Net pay: $1,144.66",
                ),
            ),
            make_document(
                "doc-3006-default-notice",
                "loan_default_notice_667788.pdf",
                "Northwind Card Services",
                IssuerCategory.COLLECTION_AGENCY,
                "Default notice tied to the maxed-out credit card.",
                ("portal", "default-notice", "credit-card"),
                f"{base_uri}/loan_default_notice_667788.pdf",
                DocumentSource.AZURE_BLOB,
                received_at,
                account_candidates=("acct-3006-cc-667788",),
                primary_account_id="acct-3006-cc-667788",
                requested_prompt_profile_id=PromptProfileId.COLLECTION_NOTICE,
                text_lines=(
                    "Default Notice",
                    "Borrower: Michael Rodriguez",
                    "Account number: 667788",
                    "Default date: 2024-02-18",
                    "Amount due immediately: $5,884.22",
                ),
            ),
            make_document(
                "doc-3006-self-reported-list",
                "self_reported_debt_list.xlsx",
                "Contoso Client Portal",
                IssuerCategory.UNKNOWN,
                "Portal-exported spreadsheet of self-reported debts.",
                ("portal", "spreadsheet", "self-reported"),
                f"{base_uri}/self_reported_debt_list.xlsx",
                DocumentSource.AZURE_BLOB,
                received_at,
                account_candidates=(
                    "acct-3006-payday-900101",
                    "acct-3006-cc-667788",
                ),
                headers=("debt_type", "issuer_name", "account_number", "balance_due"),
                rows=(
                    (
                        "payday loan",
                        "Fabrikam Payday Services",
                        "PDL-900101",
                        "$3,120.00",
                    ),
                    (
                        "credit card",
                        "Northwind Card Services",
                        "667788",
                        "$5,884.22",
                    ),
                    (
                        "collections fee",
                        "Northwind Recovery Desk",
                        "C-2214",
                        "$410.00",
                    ),
                ),
                worksheet_name="Debt List",
            ),
            make_document(
                "doc-3006-portal-receipt",
                "portal_confirmation_receipt.pdf",
                "Contoso Client Portal",
                IssuerCategory.UNKNOWN,
                "Portal confirmation receipt for the upload session.",
                ("portal", "receipt", "submission"),
                f"{base_uri}/portal_confirmation_receipt.pdf",
                DocumentSource.AZURE_BLOB,
                received_at,
                text_lines=(
                    "Portal Confirmation Receipt",
                    "Client: Michael Rodriguez",
                    "Submission time: 2024-02-20 18:44 UTC",
                    "Files received: 9",
                    "Reference: PORTAL-3006-20240220",
                ),
            ),
        ),
        entry_point="portal_and_email_submission",
        intake_description=(
            "Digital submission via client portal and follow-up email with mixed PDFs, "
            "images, spreadsheet, and a zip archive."
        ),
        reason_for_visiting=(
            "Recent job loss leading to $9k payday loans and maxed-out credit cards; "
            "submitted via client portal and follow-up email."
        ),
        source=DocumentSource.AZURE_BLOB,
    )


def create_default_synthetic_cases() -> tuple[SyntheticCaseSpec, ...]:
    """Create the original lightweight synthetic case bundle."""
    return (build_bankers_box_case(), build_sftp_drop_case())


def create_debt_relief_intake_cases() -> tuple[SyntheticCaseSpec, ...]:
    """Create the six-profile debt-relief intake scenario pack."""
    return (
        build_front_door_case(),
        build_court_packet_case(),
        build_bank_referral_case(),
        build_partner_ftp_case(),
        build_mail_scan_case(),
        build_portal_submission_case(),
    )


def create_synthetic_cases(
    scenario_set: ScenarioSet = "default",
) -> tuple[SyntheticCaseSpec, ...]:
    """Create synthetic cases for the requested scenario set."""
    if scenario_set == "default":
        return create_default_synthetic_cases()
    if scenario_set == "debt-relief-intake":
        return create_debt_relief_intake_cases()
    if scenario_set == "all":
        return (*create_default_synthetic_cases(), *create_debt_relief_intake_cases())
    raise ValueError(f"Unsupported scenario set '{scenario_set}'.")


def sanitize_name(value: str) -> str:
    """Convert a label into a path-safe directory or file component."""
    path_safe = [
        character.lower() if character.isalnum() else "-"
        for character in value
    ]
    return "-".join("".join(path_safe).split("-"))


def build_case_directory_name(case: SyntheticCaseSpec) -> str:
    """Return the folder name used for a generated case."""
    return f"{case.case_id}-{sanitize_name(case.customer_alias)}"


def build_workbook_notes(
    document: SyntheticDocumentSpec,
) -> tuple[tuple[str, str], ...]:
    """Create provenance rows that explain the synthetic document."""
    return (
        ("document_id", document.document_id),
        ("issuer_name", document.issuer_name),
        ("issuer_category", document.issuer_category.value),
        ("source", document.source.value),
        ("source_uri", document.source_uri),
        ("source_summary", document.source_summary),
        ("primary_account_id", document.primary_account_id or ""),
        ("account_candidates", ", ".join(document.account_candidates)),
    )


def build_document_text(document: SyntheticDocumentSpec) -> str:
    """Build a plaintext representation used for fallback extraction."""
    lines = [
        f"file_name: {document.file_name}",
        f"issuer_name: {document.issuer_name}",
        f"issuer_category: {document.issuer_category.value}",
        f"source_summary: {document.source_summary}",
    ]
    if document.primary_account_id:
        lines.append(f"primary_account_id: {document.primary_account_id}")
    if document.account_candidates:
        lines.append(
            "account_candidates: " + ", ".join(document.account_candidates)
        )
    lines.extend(document.text_lines)
    if document.headers and document.rows:
        lines.append("structured_rows:")
        lines.append(" | ".join(document.headers))
        for row in document.rows:
            lines.append(" | ".join(row))
    if document.archive_entries:
        lines.append("archive_entries:")
        for entry in document.archive_entries:
            lines.append(entry.file_name)
            lines.extend(entry.text_lines)
    return "\n".join(lines)


def build_workbook_bytes(document: SyntheticDocumentSpec) -> bytes:
    """Render a workbook-backed synthetic document to bytes."""
    workbook = Workbook()
    data_sheet = workbook.active
    data_sheet.title = document.worksheet_name
    if document.headers:
        data_sheet.append(list(document.headers))
    for row in document.rows:
        data_sheet.append(list(row))
    notes_sheet = workbook.create_sheet("Provenance")
    notes_sheet.append(["field", "value"])
    for row in build_workbook_notes(document):
        notes_sheet.append(list(row))
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def build_pdf_bytes(text_lines: tuple[str, ...]) -> bytes:
    """Render a simple OCR-friendly PDF document."""
    buffer = BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER
    text_object = pdf_canvas.beginText(48, height - 48)
    text_object.setFont("Helvetica", 11)
    for raw_line in text_lines:
        wrapped_lines = wrap(raw_line, width=92) or [""]
        for line in wrapped_lines:
            if text_object.getY() <= 48:
                pdf_canvas.drawText(text_object)
                pdf_canvas.showPage()
                text_object = pdf_canvas.beginText(48, height - 48)
                text_object.setFont("Helvetica", 11)
            text_object.textLine(line)
    pdf_canvas.drawText(text_object)
    pdf_canvas.save()
    return buffer.getvalue()


def build_image_bytes(
    text_lines: tuple[str, ...],
    image_format: Literal["JPEG", "PNG"],
) -> bytes:
    """Render a simple OCR-friendly image document."""
    wrapped_lines: list[str] = []
    for raw_line in text_lines:
        wrapped_lines.extend(wrap(raw_line, width=56) or [""])
    image_height = max(400, 100 + len(wrapped_lines) * 28)
    image = Image.new("RGB", (1400, image_height), "white")
    draw = ImageDraw.Draw(image)
    y_position = 40
    for line in wrapped_lines:
        draw.text((48, y_position), line, fill="black")
        y_position += 26
    buffer = BytesIO()
    if image_format == "JPEG":
        image.save(buffer, format=image_format, quality=95)
    else:
        image.save(buffer, format=image_format)
    return buffer.getvalue()


def build_rtf_bytes(text_lines: tuple[str, ...]) -> bytes:
    """Render a lightweight RTF payload for .doc-style samples."""
    escaped_lines = [
        line.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        for line in text_lines
    ]
    body = "\\par\n".join(escaped_lines)
    return (
        "{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Calibri;}}"
        "\\f0\\fs22\n"
        f"{body}\n"
        "}"
    ).encode()


def build_archive_bytes(document: SyntheticDocumentSpec) -> bytes:
    """Render a zip archive containing embedded PDF artifacts."""
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        for entry in document.archive_entries:
            archive.writestr(entry.file_name, build_pdf_bytes(entry.text_lines))
    return buffer.getvalue()


def render_document_bytes(document: SyntheticDocumentSpec) -> bytes:
    """Render the synthetic document bytes according to its file kind."""
    document_text_lines = tuple(build_document_text(document).splitlines())
    if document.render_kind == "xlsx":
        return build_workbook_bytes(document)
    if document.render_kind == "pdf":
        return build_pdf_bytes(document_text_lines)
    if document.render_kind == "jpg":
        return build_image_bytes(document_text_lines, "JPEG")
    if document.render_kind == "png":
        return build_image_bytes(document_text_lines, "PNG")
    if document.render_kind == "rtf":
        return build_rtf_bytes(document_text_lines)
    if document.render_kind == "zip":
        return build_archive_bytes(document)
    raise ValueError(f"Unsupported render kind '{document.render_kind}'.")


def write_document_file(document: SyntheticDocumentSpec, file_path: Path) -> bytes:
    """Write a rendered synthetic document to disk and return its bytes."""
    document_bytes = render_document_bytes(document)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(document_bytes)
    return document_bytes


def build_request_payload(
    document: SyntheticDocumentSpec,
    document_bytes: bytes,
) -> dict[str, Any]:
    """Create a validated ingestion payload for a generated document."""
    request = DocumentIngestionRequest(
        document_id=document.document_id,
        source=document.source,
        source_uri=document.source_uri,
        issuer_name=document.issuer_name,
        issuer_category=document.issuer_category,
        requested_prompt_profile_id=document.requested_prompt_profile_id,
        source_summary=document.source_summary,
        source_tags=document.source_tags,
        document_content_base64=(
            base64.b64encode(document_bytes).decode("ascii")
            if document.inline_content_mode == "bytes"
            else None
        ),
        document_text=build_document_text(document),
        file_name=document.file_name,
        content_type=document.content_type,
        received_at_utc=document.received_at_utc,
        account_candidates=document.account_candidates,
    )
    return request.model_dump(mode="json")


def prepare_output_directory(output_dir: Path) -> None:
    """Reset the generated sample output directory."""
    if output_dir.exists():
        shutil.rmtree(output_dir)

    (output_dir / "cases").mkdir(parents=True, exist_ok=True)
    (output_dir / "requests").mkdir(parents=True, exist_ok=True)


def write_request_file(
    output_dir: Path,
    document: SyntheticDocumentSpec,
    payload: dict[str, Any],
) -> str:
    """Write a request payload next to the generated documents."""
    request_path = output_dir / "requests" / f"{document.document_id}.json"
    request_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return request_path.relative_to(output_dir).as_posix()


def build_manifest_entry(
    output_dir: Path,
    case: SyntheticCaseSpec,
    document: SyntheticDocumentSpec,
    document_path: Path,
    request_path: str,
) -> dict[str, Any]:
    """Build a manifest entry for a generated document."""
    relative_document_path = document_path.relative_to(output_dir).as_posix()
    return {
        "account_candidates": list(document.account_candidates),
        "case_id": case.case_id,
        "content_type": document.content_type,
        "document_id": document.document_id,
        "document_path": relative_document_path,
        "entry_point": case.entry_point,
        "file_name": document.file_name,
        "issuer_category": document.issuer_category.value,
        "issuer_name": document.issuer_name,
        "primary_account_id": document.primary_account_id,
        "request_path": request_path,
        "source": document.source.value,
        "source_uri": document.source_uri,
        "workbook_path": relative_document_path,
    }


def build_case_manifest_entry(case: SyntheticCaseSpec) -> dict[str, Any]:
    """Build a manifest summary entry for a case bundle."""
    return {
        "account_count": len(case.accounts),
        "accounts": [
            {
                "account_id": account.account_id,
                "account_number": account.account_number,
                "balance_due": account.balance_due,
                "debt_type": account.debt_type,
                "issuer_name": account.issuer_name,
            }
            for account in case.accounts
        ],
        "case_id": case.case_id,
        "customer_alias": case.customer_alias,
        "document_count": len(case.documents),
        "entry_point": case.entry_point,
        "intake_description": case.intake_description,
        "reason_for_visiting": case.reason_for_visiting,
        "source": case.source.value,
    }


def generate_sample_bundle(
    output_dir: Path,
    *,
    scenario_set: ScenarioSet = "default",
) -> dict[str, Any]:
    """Generate the requested synthetic bundle and ingestion payloads."""
    prepare_output_directory(output_dir)
    cases = create_synthetic_cases(scenario_set)
    manifest_documents: list[dict[str, Any]] = []

    for case in cases:
        case_dir = output_dir / "cases" / build_case_directory_name(case)
        for document in case.documents:
            document_path = case_dir / document.file_name
            document_bytes = write_document_file(document, document_path)
            payload = build_request_payload(document, document_bytes)
            request_path = write_request_file(output_dir, document, payload)
            manifest_documents.append(
                build_manifest_entry(
                    output_dir,
                    case,
                    document,
                    document_path,
                    request_path,
                )
            )

    manifest = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "scenario_set": scenario_set,
        "cases": [build_case_manifest_entry(case) for case in cases],
        "documents": manifest_documents,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
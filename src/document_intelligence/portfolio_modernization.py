"""Portfolio modernization helpers for Epic 6 Phase 3."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

RepoClassification = Literal[
    "archive_or_merge",
    "private_operational",
    "private_secret_bearing",
    "public_demo",
    "public_showcase",
]
ShowcaseReadiness = Literal["moderate", "needs_attention", "strong"]

PHASE3_REPO_NAMES: Final[tuple[str, ...]] = (
    "azure-cost-optimizer",
    "kql-incident-response-dashboard",
    "ai-log-anomaly-detector",
    "iac-security-validation",
    "self-healing-aks",
    "zero-trust-cicd-pipeline",
    "multi-region-dr-demo",
    "azure-policy-governance-guardrails",
    "bicep-module-library",
)

DEPENDENCY_FILE_NAMES: Final[tuple[str, ...]] = (
    "package.json",
    "pyproject.toml",
    "requirements.txt",
)
ARCHITECTURE_KEYWORDS: Final[tuple[str, ...]] = (
    "architecture",
    "component",
    "diagram",
    "stack",
    "workflow",
)
BOUNDARY_KEYWORDS: Final[tuple[str, ...]] = (
    "demo-only",
    "private",
    "production",
    "public",
    "public-safe",
    "sanitized",
)
VALIDATION_KEYWORDS: Final[tuple[str, ...]] = (
    "pester",
    "pytest",
    "smoke",
    "test",
    "validate",
    "validation",
    "verify",
)
VALIDATION_COMMAND_HINTS: Final[tuple[str, ...]] = (
    "bicep build",
    "go test",
    "host start",
    "invoke-pester",
    "npm test",
    "pnpm test",
    "pwsh",
    "pytest",
    "python ",
    "terraform validate",
)
VALIDATION_NAME_MARKERS: Final[tuple[str, ...]] = (
    "smoke",
    "test",
    "validate",
    "verify",
)
IGNORED_SCAN_DIRECTORIES: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "bin",
        "build",
        "dist",
        "node_modules",
        "obj",
    }
)
PLACEHOLDER_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "YOUR_* placeholder",
        re.compile(r"\bYOUR_[A-Z0-9_]+\b"),
    ),
    (
        "<your-...> placeholder",
        re.compile(r"<your-[^>]+>", re.IGNORECASE),
    ),
    (
        "<your_...> placeholder",
        re.compile(r"<your_[^>]+>", re.IGNORECASE),
    ),
    ("TODO marker", re.compile(r"\bTODO\b", re.IGNORECASE)),
    ("TBD marker", re.compile(r"\bTBD\b", re.IGNORECASE)),
    ("FIXME marker", re.compile(r"\bFIXME\b", re.IGNORECASE)),
)


@dataclass(frozen=True)
class RepoMatrixEntry:
    """One repo row from the portfolio classification matrix."""

    classification: RepoClassification
    primary_purpose: str
    rationale: str
    recommendation: str
    repo_name: str


@dataclass(frozen=True)
class RepoScanFacts:
    """Observed repo facts used to build the modernization review."""

    architecture_guidance: bool
    boundary_guidance: bool
    dependency_files: tuple[str, ...]
    has_license: bool
    has_readme: bool
    has_tests: bool
    languages: tuple[str, ...]
    placeholder_markers: tuple[str, ...]
    top_level_directories: tuple[str, ...]
    validation_assets: tuple[str, ...]
    validation_guidance: bool
    workflow_files: tuple[str, ...]


@dataclass(frozen=True)
class RepoModernizationReview:
    """Modernization review output for one portfolio repo."""

    classification: RepoClassification
    gaps: tuple[str, ...]
    next_actions: tuple[str, ...]
    primary_purpose: str
    rationalization_note: str
    readiness: ShowcaseReadiness
    readiness_score: int
    repo_name: str
    repo_path: str
    scan_facts: RepoScanFacts
    strengths: tuple[str, ...]


@dataclass(frozen=True)
class PortfolioGapSummary:
    """Cross-repo gap counts used to prioritize the modernization sweep."""

    repos_missing_architecture_guidance: int
    repos_missing_boundary_guidance: int
    repos_missing_tests: int
    repos_missing_validation_guidance: int
    repos_missing_workflows: int
    repos_with_placeholder_markers: int


@dataclass(frozen=True)
class PortfolioModernizationReport:
    """Structured Phase 3 modernization review for the portfolio workspace."""

    flagship_public_demos: tuple[str, ...]
    gap_summary: PortfolioGapSummary
    generated_at_utc: str
    matrix_path: str
    phase3_repo_names: tuple[str, ...]
    rationalization_recommendations: tuple[str, ...]
    repo_reviews: tuple[RepoModernizationReview, ...]
    supporting_public_demos: tuple[str, ...]
    workspace_root: str


def load_repo_classification_matrix(matrix_path: Path) -> tuple[RepoMatrixEntry, ...]:
    """Load the portfolio classification matrix from the wrapper repo."""

    table_lines = _extract_recommended_matrix_lines(
        matrix_path.read_text(encoding="utf-8")
    )
    entries: list[RepoMatrixEntry] = []
    for line in table_lines:
        cells = _parse_markdown_table_row(line)
        if not cells or _is_separator_row(cells):
            continue
        if cells[0] == "Repo":
            continue
        if len(cells) != 5:
            raise ValueError("Repo classification matrix rows must have five columns.")

        repo_name, purpose, classification, recommendation, rationale = cells
        entries.append(
            RepoMatrixEntry(
                classification=_parse_repo_classification(classification),
                primary_purpose=purpose,
                rationale=rationale,
                recommendation=recommendation,
                repo_name=repo_name,
            )
        )
    return tuple(entries)


def scan_repo_for_modernization(repo_path: Path) -> RepoScanFacts:
    """Collect the repo facts needed for the modernization report."""

    readme_text = _readme_text(repo_path)
    top_level_directories = _top_level_directories(repo_path)
    dependency_files = _dependency_files(repo_path)
    workflow_files = _workflow_files(repo_path)
    validation_assets = _validation_assets(repo_path, workflow_files)
    return RepoScanFacts(
        architecture_guidance=_has_architecture_guidance(readme_text),
        boundary_guidance=_has_boundary_guidance(readme_text),
        dependency_files=dependency_files,
        has_license=(repo_path / "LICENSE").is_file(),
        has_readme=readme_text is not None,
        has_tests=_has_test_assets(repo_path),
        languages=_language_hints(repo_path, top_level_directories, dependency_files),
        placeholder_markers=_placeholder_markers(readme_text),
        top_level_directories=top_level_directories,
        validation_assets=validation_assets,
        validation_guidance=_has_validation_guidance(readme_text),
        workflow_files=workflow_files,
    )


def build_repo_modernization_review(
    repo_path: Path,
    matrix_entry: RepoMatrixEntry,
) -> RepoModernizationReview:
    """Build the Phase 3 modernization review for one repo."""

    scan_facts = scan_repo_for_modernization(repo_path)
    readiness_score = _readiness_score(matrix_entry, scan_facts)
    return RepoModernizationReview(
        classification=matrix_entry.classification,
        gaps=_review_gaps(matrix_entry, scan_facts),
        next_actions=_next_actions(matrix_entry, scan_facts),
        primary_purpose=matrix_entry.primary_purpose,
        rationalization_note=matrix_entry.recommendation,
        readiness=_readiness_bucket(readiness_score),
        readiness_score=readiness_score,
        repo_name=matrix_entry.repo_name,
        repo_path=str(repo_path),
        scan_facts=scan_facts,
        strengths=_review_strengths(scan_facts),
    )


def build_portfolio_modernization_report(
    workspace_root: Path,
    matrix_path: Path,
    repo_names: tuple[str, ...] = PHASE3_REPO_NAMES,
) -> PortfolioModernizationReport:
    """Build the structured Phase 3 modernization review."""

    matrix_entries = load_repo_classification_matrix(matrix_path)
    matrix_by_repo = {entry.repo_name: entry for entry in matrix_entries}
    reviews = tuple(
        _review_for_repo_name(workspace_root, repo_name, matrix_by_repo)
        for repo_name in repo_names
    )
    flagship_public_demos = _flagship_public_demos(reviews)
    supporting_public_demos = tuple(
        review.repo_name
        for review in reviews
        if review.classification == "public_demo"
        and review.repo_name not in flagship_public_demos
    )
    return PortfolioModernizationReport(
        flagship_public_demos=flagship_public_demos,
        gap_summary=_portfolio_gap_summary(reviews),
        generated_at_utc=_utc_now(),
        matrix_path=str(matrix_path),
        phase3_repo_names=repo_names,
        rationalization_recommendations=_rationalization_recommendations(
            matrix_by_repo,
            flagship_public_demos,
            supporting_public_demos,
        ),
        repo_reviews=reviews,
        supporting_public_demos=supporting_public_demos,
        workspace_root=str(workspace_root),
    )


def render_portfolio_modernization_report_markdown(
    report: PortfolioModernizationReport,
) -> str:
    """Render the Phase 3 modernization review as Markdown."""

    lines = [
        "# Portfolio Modernization Review",
        "",
        f"Generated: `{report.generated_at_utc}`",
        f"Workspace root: `{report.workspace_root}`",
        f"Classification matrix: `{report.matrix_path}`",
        "",
        "## Rationalization Recommendation",
        "",
    ]
    lines.extend(f"- {item}" for item in report.rationalization_recommendations)
    lines.extend(
        [
            "",
            "## Portfolio Gap Summary",
            "",
            (
                "- Repos missing architecture guidance: "
                f"{report.gap_summary.repos_missing_architecture_guidance}"
            ),
            (
                "- Public demos missing explicit public/private scope guidance: "
                f"{report.gap_summary.repos_missing_boundary_guidance}"
            ),
            f"- Repos missing tests: {report.gap_summary.repos_missing_tests}",
            (
                "- Repos missing validation guidance in the README: "
                f"{report.gap_summary.repos_missing_validation_guidance}"
            ),
            (
                "- Repos missing repo-local GitHub workflows: "
                f"{report.gap_summary.repos_missing_workflows}"
            ),
            (
                "- Repos with README placeholder markers: "
                f"{report.gap_summary.repos_with_placeholder_markers}"
            ),
            "",
            "## Repo Scorecard",
            "",
            (
                "| Repo | Classification | Readiness | README | Tests | "
                "Workflows | Validation assets |"
            ),
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    lines.extend(_scorecard_rows(report.repo_reviews))
    lines.extend(["", "## Repo Reviews", ""])
    lines.extend(_repo_review_sections(report.repo_reviews))
    return "\n".join(lines) + "\n"


def render_portfolio_modernization_report_json(
    report: PortfolioModernizationReport,
) -> str:
    """Render the Phase 3 modernization review as formatted JSON."""

    return json.dumps(asdict(report), indent=2)


def render_portfolio_action_checklist_markdown(
    report: PortfolioModernizationReport,
) -> str:
    """Render the modernization review as an incremental execution checklist."""

    lines = [
        "# Portfolio Modernization Action Checklist",
        "",
        f"Generated: `{report.generated_at_utc}`",
        "",
        "## Execution Order",
        "",
        (
            "- Start with repos that still have placeholder cleanup, missing "
            "validation guidance, and no repo-local validation automation."
        ),
        (
            "- Close README public-scope and validation gaps before deeper code "
            "or workflow hardening so every demo explains its boundary clearly."
        ),
        "- Treat unchecked items as the next incremental Phase 3 work queue.",
        "",
        "## Repo Checklist",
        "",
    ]
    for review in report.repo_reviews:
        lines.extend(_repo_checklist_section(review))
    return "\n".join(lines) + "\n"


def _contains_keywords(text: str | None, keywords: tuple[str, ...]) -> bool:
    if not text:
        return False
    normalized_text = text.lower()
    return any(keyword in normalized_text for keyword in keywords)


def _dependency_files(repo_path: Path) -> tuple[str, ...]:
    return tuple(
        file_name
        for file_name in DEPENDENCY_FILE_NAMES
        if (repo_path / file_name).is_file()
    )


def _extract_recommended_matrix_lines(markdown_text: str) -> tuple[str, ...]:
    lines = markdown_text.splitlines()
    start_index = _section_index(lines, "## Recommended Matrix")
    end_index = _section_index(lines, "## Current Public Surface Recommendation")
    return tuple(
        line
        for line in lines[start_index + 1 : end_index]
        if line.strip().startswith("|")
    )


def _flagship_public_demos(
    reviews: tuple[RepoModernizationReview, ...],
) -> tuple[str, ...]:
    public_reviews = [
        review for review in reviews if review.classification == "public_demo"
    ]
    sorted_reviews = sorted(
        public_reviews,
        key=lambda review: (-review.readiness_score, review.repo_name),
    )
    return tuple(review.repo_name for review in sorted_reviews[:5])


def _has_extension(repo_path: Path, patterns: tuple[str, ...]) -> bool:
    return any(any(repo_path.glob(pattern)) for pattern in patterns)


def _has_architecture_guidance(readme_text: str | None) -> bool:
    return _contains_keywords(readme_text, ARCHITECTURE_KEYWORDS)


def _has_boundary_guidance(readme_text: str | None) -> bool:
    if not readme_text:
        return False

    normalized_text = readme_text.lower()
    if any(
        phrase in normalized_text
        for phrase in ("public-safe", "demo-only", "sanitized", "private")
    ):
        return True
    return "public" in normalized_text and "production" in normalized_text


def _has_test_assets(repo_path: Path) -> bool:
    tests_path = repo_path / "tests"
    if tests_path.is_dir() and any(path.is_file() for path in tests_path.rglob("*")):
        return True
    return _has_extension(
        repo_path,
        (
            "test_*.py",
            "*_test.py",
            "*.test.ts",
            "*.test.tsx",
            "*.spec.ts",
            "*.spec.tsx",
        ),
    )


def _is_separator_row(cells: tuple[str, ...]) -> bool:
    return all(set(cell) <= {"-", ":"} for cell in cells)


def _language_hints(
    repo_path: Path,
    top_level_directories: tuple[str, ...],
    dependency_files: tuple[str, ...],
) -> tuple[str, ...]:
    languages: list[str] = []
    if "pyproject.toml" in dependency_files or "requirements.txt" in dependency_files:
        languages.append("Python")
    if "package.json" in dependency_files:
        languages.append("TypeScript/JavaScript")
    if {"infra", "bicep"} & set(top_level_directories) or _has_extension(
        repo_path,
        ("*.bicep", "**/*.bicep"),
    ):
        languages.append("Bicep")
    if _has_extension(repo_path, ("*.cs", "**/*.cs", "*.csproj", "**/*.csproj")):
        languages.append("C#/.NET")
    if "terraform" in top_level_directories:
        languages.append("Terraform")
    if {"queries", "workbooks"} & set(top_level_directories):
        languages.append("KQL")
    if "k8s" in top_level_directories:
        languages.append("Kubernetes")
    if _has_extension(
        repo_path,
        (
            "*.ps1",
            "scripts/*.ps1",
            "scripts/**/*.ps1",
            "tests/*.ps1",
            "tests/**/*.ps1",
        ),
    ):
        languages.append("PowerShell")
    return tuple(dict.fromkeys(languages))


def _next_actions(
    matrix_entry: RepoMatrixEntry,
    scan_facts: RepoScanFacts,
) -> tuple[str, ...]:
    actions: list[str] = []
    if scan_facts.placeholder_markers:
        actions.append("Remove README placeholder markers and template residue.")
    if not scan_facts.validation_guidance:
        actions.append("Add explicit local validation commands to the README.")
    if not scan_facts.architecture_guidance:
        actions.append("Add a concise architecture section to the README.")
    if (
        matrix_entry.classification == "public_demo"
        and not scan_facts.boundary_guidance
    ):
        actions.append("Document demo-only scope and public-safe boundaries clearly.")
    if not scan_facts.has_tests:
        actions.append("Add tests or validation fixtures for the main executable path.")
    if not scan_facts.workflow_files:
        actions.append("Add a repo-local validation workflow or wrapper command.")
    return tuple(dict.fromkeys(actions))


def _parse_markdown_table_row(line: str) -> tuple[str, ...]:
    raw_cells = [cell.strip() for cell in line.split("|")]
    cells = raw_cells[1:-1]
    return tuple(cell.strip("`").strip() for cell in cells)


def _parse_repo_classification(value: str) -> RepoClassification:
    normalized_value = value.strip()
    if normalized_value == "archive_or_merge":
        return "archive_or_merge"
    if normalized_value == "private_operational":
        return "private_operational"
    if normalized_value == "private_secret_bearing":
        return "private_secret_bearing"
    if normalized_value == "public_demo":
        return "public_demo"
    if normalized_value == "public_showcase":
        return "public_showcase"

    raise ValueError(f"Unsupported repo classification '{value}'.")


def _placeholder_markers(readme_text: str | None) -> tuple[str, ...]:
    if not readme_text:
        return ()

    markers = [
        marker_label
        for marker_label, pattern in PLACEHOLDER_PATTERNS
        if pattern.search(readme_text)
    ]
    return tuple(markers)


def _portfolio_gap_summary(
    reviews: tuple[RepoModernizationReview, ...],
) -> PortfolioGapSummary:
    return PortfolioGapSummary(
        repos_missing_architecture_guidance=sum(
            not review.scan_facts.architecture_guidance for review in reviews
        ),
        repos_missing_boundary_guidance=sum(
            review.classification == "public_demo"
            and not review.scan_facts.boundary_guidance
            for review in reviews
        ),
        repos_missing_tests=sum(not review.scan_facts.has_tests for review in reviews),
        repos_missing_validation_guidance=sum(
            not review.scan_facts.validation_guidance for review in reviews
        ),
        repos_missing_workflows=sum(
            not review.scan_facts.workflow_files for review in reviews
        ),
        repos_with_placeholder_markers=sum(
            bool(review.scan_facts.placeholder_markers) for review in reviews
        ),
    )


def _rationalization_recommendations(
    matrix_by_repo: dict[str, RepoMatrixEntry],
    flagship_public_demos: tuple[str, ...],
    supporting_public_demos: tuple[str, ...],
) -> tuple[str, ...]:
    wrapper_repo = matrix_by_repo.get("portfolio-projects")
    private_repo = matrix_by_repo.get("hybrid-document-intelligence-platform")
    recommendations = [
        (
            "Keep `portfolio-projects` as the only public showcase landing repo and "
            "treat embedded wrapper mirrors as transition-only copies, not permanent "
            "public entry points."
        ),
        (
            "Do not treat embedded wrapper mirrors as the source of truth for "
            "standalone repo tests, workflows, or validation assets; those belong in "
            "the standalone repo or in the private operational source that generates a "
            "curated derivative."
        ),
        (
            "Keep `hybrid-document-intelligence-platform` private operational and "
            "continue publishing only curated public-safe derivatives such as "
            "`security-posture-platform`."
        ),
    ]
    if wrapper_repo is not None:
        recommendations[0] = (
            f"Keep `{wrapper_repo.repo_name}` as the only public showcase landing repo "
            "and treat embedded wrapper mirrors as transition-only copies, not "
            "permanent public entry points."
        )
    if private_repo is not None:
        recommendations[2] = (
            f"Keep `{private_repo.repo_name}` private operational and continue "
            "publishing only curated public-safe derivatives such as "
            "`security-posture-platform`."
        )
    if flagship_public_demos:
        recommendations.append(
            "Treat the strongest first-class public demos as: "
            f"{', '.join(f'`{repo_name}`' for repo_name in flagship_public_demos)}."
        )
    if supporting_public_demos:
        recommendations.append(
            "Keep the remaining demos public but secondary until their README, test, "
            "and validation gaps close: "
            f"{', '.join(f'`{repo_name}`' for repo_name in supporting_public_demos)}."
        )
    recommendations.append(
        "Use the private repo sync automation for future `security-posture-platform` "
        "updates instead of manual clone, amend, or force-push flows."
    )
    return tuple(recommendations)


def _readiness_bucket(score: int) -> ShowcaseReadiness:
    if score >= 6:
        return "strong"
    if score >= 4:
        return "moderate"
    return "needs_attention"


def _readiness_score(
    matrix_entry: RepoMatrixEntry,
    scan_facts: RepoScanFacts,
) -> int:
    score = 0
    score += int(scan_facts.has_readme)
    score += int(scan_facts.validation_guidance)
    score += int(scan_facts.architecture_guidance)
    score += int(scan_facts.has_tests)
    score += int(bool(scan_facts.workflow_files))
    score += int(not scan_facts.placeholder_markers)
    score += int(
        matrix_entry.classification != "public_demo" or scan_facts.boundary_guidance
    )
    return score


def _readme_text(repo_path: Path) -> str | None:
    readme_path = repo_path / "README.md"
    if not readme_path.is_file():
        return None
    return readme_path.read_text(encoding="utf-8")


def _repo_review_sections(
    reviews: tuple[RepoModernizationReview, ...],
) -> list[str]:
    sections: list[str] = []
    for review in reviews:
        languages = ", ".join(review.scan_facts.languages) or "Not detected"
        dependency_files = (
            ", ".join(review.scan_facts.dependency_files) or "None detected"
        )
        validation_assets = (
            ", ".join(review.scan_facts.validation_assets) or "None detected"
        )
        strengths = "; ".join(review.strengths) or "No strengths recorded."
        sections.extend(
            [
                f"### {review.repo_name}",
                "",
                f"- Purpose: {review.primary_purpose}",
                f"- Classification: `{review.classification}`",
                (f"- Readiness: `{review.readiness}` ({review.readiness_score}/7)"),
                f"- Recommendation: {review.rationalization_note}",
                f"- Languages: {languages}",
                f"- Dependency files: {dependency_files}",
                f"- Validation assets: {validation_assets}",
                f"- Strengths: {strengths}",
                f"- Gaps: {'; '.join(review.gaps) or 'No gaps recorded.'}",
                (
                    "- Next actions: "
                    f"{'; '.join(review.next_actions) or 'No next actions recorded.'}"
                ),
                "",
            ]
        )
    return sections


def _review_for_repo_name(
    workspace_root: Path,
    repo_name: str,
    matrix_by_repo: dict[str, RepoMatrixEntry],
) -> RepoModernizationReview:
    if repo_name not in matrix_by_repo:
        raise ValueError(
            f"Repo '{repo_name}' is missing from the classification matrix."
        )

    repo_path = workspace_root / repo_name
    if not repo_path.is_dir():
        raise ValueError(f"Repo '{repo_name}' is missing from the workspace.")
    return build_repo_modernization_review(repo_path, matrix_by_repo[repo_name])


def _review_gaps(
    matrix_entry: RepoMatrixEntry,
    scan_facts: RepoScanFacts,
) -> tuple[str, ...]:
    gaps: list[str] = []
    if not scan_facts.has_readme:
        gaps.append("README.md is missing.")
    if scan_facts.placeholder_markers:
        gaps.append(
            "README contains placeholder markers: "
            f"{', '.join(scan_facts.placeholder_markers)}."
        )
    if not scan_facts.validation_guidance:
        gaps.append("README does not clearly document validation commands.")
    if not scan_facts.architecture_guidance:
        gaps.append("README does not clearly explain architecture or runtime shape.")
    if (
        matrix_entry.classification == "public_demo"
        and not scan_facts.boundary_guidance
    ):
        gaps.append("README does not clearly describe demo-only or public-safe scope.")
    if not scan_facts.has_tests:
        gaps.append("No tests directory or direct test files were detected.")
    if not scan_facts.workflow_files:
        gaps.append("No repo-local GitHub workflow was detected.")
    if not scan_facts.validation_assets:
        gaps.append(
            "No validation wrapper, smoke script, or verification asset was detected."
        )
    return tuple(gaps)


def _review_strengths(scan_facts: RepoScanFacts) -> tuple[str, ...]:
    strengths: list[str] = []
    if scan_facts.has_readme:
        strengths.append("README.md is present.")
    if scan_facts.has_license:
        strengths.append("LICENSE file is present.")
    if scan_facts.has_tests:
        strengths.append("Tests or repo-local test files are present.")
    if scan_facts.workflow_files:
        strengths.append(
            f"{len(scan_facts.workflow_files)} GitHub workflow files are present."
        )
    if scan_facts.validation_assets:
        strengths.append(
            "Validation assets detected: "
            f"{', '.join(scan_facts.validation_assets[:3])}."
        )
    if scan_facts.dependency_files:
        strengths.append(
            "Dependency/tooling files detected: "
            f"{', '.join(scan_facts.dependency_files)}."
        )
    return tuple(strengths)


def _scorecard_rows(reviews: tuple[RepoModernizationReview, ...]) -> list[str]:
    rows: list[str] = []
    for review in reviews:
        rows.append(
            "| "
            f"{review.repo_name} | `{review.classification}` | "
            f"`{review.readiness}` ({review.readiness_score}/7) | "
            f"{'yes' if review.scan_facts.has_readme else 'no'} | "
            f"{'yes' if review.scan_facts.has_tests else 'no'} | "
            f"{len(review.scan_facts.workflow_files)} | "
            f"{len(review.scan_facts.validation_assets)} |"
        )
    return rows


def _repo_checklist_section(review: RepoModernizationReview) -> list[str]:
    checklist_items = list(review.next_actions)
    if not checklist_items and review.gaps:
        checklist_items = list(review.gaps)

    lines = [
        f"### {review.repo_name}",
        "",
        f"- Current readiness: `{review.readiness}` ({review.readiness_score}/7)",
        f"- Classification: `{review.classification}`",
        f"- Recommendation: {review.rationalization_note}",
    ]
    if review.gaps:
        lines.append(f"- Current gaps: {'; '.join(review.gaps)}")
    else:
        lines.append("- Current gaps: None recorded.")
    lines.append("")

    if checklist_items:
        lines.extend(f"- [ ] {item}" for item in checklist_items)
    else:
        lines.append("- [x] No remaining Phase 3 checklist items recorded.")
    lines.append("")
    return lines


def _section_index(lines: list[str], heading: str) -> int:
    for index, line in enumerate(lines):
        if line.strip() == heading:
            return index
    raise ValueError(f"Heading '{heading}' was not found.")


def _top_level_directories(repo_path: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            child.name
            for child in repo_path.iterdir()
            if child.is_dir() and not child.name.startswith(".")
        )
    )


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validation_assets(
    repo_path: Path,
    workflow_files: tuple[str, ...],
) -> tuple[str, ...]:
    asset_paths = set(workflow_files)
    asset_paths.update(_validation_paths_in_directory(repo_path / "scripts", repo_path))
    asset_paths.update(_validation_paths_in_directory(repo_path / "tests", repo_path))
    asset_paths.update(_validation_paths_in_root(repo_path))
    return tuple(sorted(asset_paths))


def _validation_paths_in_directory(directory: Path, repo_path: Path) -> set[str]:
    if not directory.is_dir():
        return set()

    asset_paths = set()
    for path in directory.rglob("*"):
        if not path.is_file() or _has_ignored_parent(path, repo_path):
            continue
        file_name = path.name.lower()
        if any(marker in file_name for marker in VALIDATION_NAME_MARKERS):
            asset_paths.add(path.relative_to(repo_path).as_posix())
    return asset_paths


def _validation_paths_in_root(repo_path: Path) -> set[str]:
    asset_paths = set()
    for path in repo_path.iterdir():
        if not path.is_file():
            continue
        file_name = path.name.lower()
        if any(marker in file_name for marker in VALIDATION_NAME_MARKERS):
            asset_paths.add(path.relative_to(repo_path).as_posix())
    return asset_paths


def _workflow_files(repo_path: Path) -> tuple[str, ...]:
    workflows_root = repo_path / ".github" / "workflows"
    if not workflows_root.is_dir():
        return ()
    return tuple(
        sorted(
            path.relative_to(repo_path).as_posix()
            for path in workflows_root.rglob("*")
            if path.is_file()
        )
    )


def _has_ignored_parent(path: Path, repo_path: Path) -> bool:
    relative_parts = path.relative_to(repo_path).parts[:-1]
    return any(part in IGNORED_SCAN_DIRECTORIES for part in relative_parts)


def _has_validation_guidance(readme_text: str | None) -> bool:
    if not readme_text:
        return False

    normalized_text = readme_text.lower()
    if any(
        command_hint in normalized_text for command_hint in VALIDATION_COMMAND_HINTS
    ):
        return True
    return "## validation" in normalized_text and "```" in normalized_text

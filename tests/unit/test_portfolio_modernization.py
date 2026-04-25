"""Unit tests for the Epic 6 Phase 3 portfolio modernization helpers."""

from __future__ import annotations

from pathlib import Path

from document_intelligence.portfolio_modernization import (
    build_portfolio_modernization_report,
    load_repo_classification_matrix,
    render_portfolio_action_checklist_markdown,
    render_portfolio_modernization_report_markdown,
)


def _write_matrix(matrix_path: Path, repo_rows: list[str]) -> None:
    matrix_path.parent.mkdir(parents=True, exist_ok=True)
    matrix_path.write_text(
        "\n".join(
            [
                "# Portfolio Repo Classification Matrix",
                "",
                "## Recommended Matrix",
                "",
                (
                    "| Repo | Primary purpose | Classification | Recommendation | "
                    "Rationale |"
                ),
                "| --- | --- | --- | --- | --- |",
                *repo_rows,
                "",
                "## Current Public Surface Recommendation",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_load_repo_classification_matrix_reads_expected_row(tmp_path: Path) -> None:
    """The matrix loader should parse the repo rows from the wrapper markdown."""

    matrix_path = tmp_path / "portfolio-projects" / "repo-classification-matrix.md"
    _write_matrix(
        matrix_path,
        [
            (
                "| `azure-cost-optimizer` | Cost reporting demo | `public_demo` | "
                "Keep public | Public-safe cost analysis demo |"
            ),
        ],
    )

    entries = load_repo_classification_matrix(matrix_path)

    assert len(entries) == 1
    assert entries[0].repo_name == "azure-cost-optimizer"
    assert entries[0].classification == "public_demo"
    assert entries[0].recommendation == "Keep public"


def test_build_portfolio_modernization_report_flags_missing_readme_guidance(
    tmp_path: Path,
) -> None:
    """The Phase 3 report should flag README and validation gaps clearly."""

    repo_name = "azure-cost-optimizer"
    repo_path = tmp_path / repo_name
    repo_path.mkdir()
    (repo_path / "README.md").write_text(
        "# Azure Cost Optimizer\n\nTODO: fill in architecture and validation.\n",
        encoding="utf-8",
    )

    matrix_path = tmp_path / "portfolio-projects" / "repo-classification-matrix.md"
    _write_matrix(
        matrix_path,
        [
            (
                "| `azure-cost-optimizer` | Cost reporting demo | `public_demo` | "
                "Keep public for now | Public-safe cost analysis demo |"
            ),
        ],
    )

    report = build_portfolio_modernization_report(
        workspace_root=tmp_path,
        matrix_path=matrix_path,
        repo_names=(repo_name,),
    )

    review = report.repo_reviews[0]
    assert review.readiness == "needs_attention"
    assert "README contains placeholder markers" in review.gaps[0]
    assert any("validation commands" in gap for gap in review.gaps)
    assert any("public-safe scope" in gap for gap in review.gaps)
    assert any("validation workflow" in action for action in review.next_actions)


def test_render_portfolio_modernization_report_markdown_includes_scorecard(
    tmp_path: Path,
) -> None:
    """The rendered markdown should include the summary and scorecard."""

    repo_name = "zero-trust-cicd-pipeline"
    repo_path = tmp_path / repo_name
    (repo_path / ".github" / "workflows").mkdir(parents=True)
    (repo_path / "tests").mkdir(parents=True)
    (repo_path / "README.md").write_text(
        "# Zero Trust CI/CD\n\n"
        "## Architecture\n\n"
        "Workflow and validation details for the public demo.\n\n"
        "## Validation\n\n"
        "Run pytest and verify the pipeline wrappers.\n\n"
        "## Public Scope\n\n"
        "This is a demo-only, public-safe pipeline sample.\n",
        encoding="utf-8",
    )
    (repo_path / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (repo_path / "pyproject.toml").write_text(
        "[project]\nname='demo'\n", encoding="utf-8"
    )
    (repo_path / ".github" / "workflows" / "validate.yml").write_text(
        "name: validate\n",
        encoding="utf-8",
    )
    (repo_path / "tests" / "test_demo.py").write_text(
        "def test_demo():\n    assert True\n",
        encoding="utf-8",
    )

    matrix_path = tmp_path / "portfolio-projects" / "repo-classification-matrix.md"
    _write_matrix(
        matrix_path,
        [
            (
                "| `zero-trust-cicd-pipeline` | Pipeline demo | `public_demo` | "
                "Keep public | Focused security-first pipeline sample |"
            ),
            (
                "| `portfolio-projects` | Wrapper repo | `public_showcase` | "
                "Keep public | Single public landing repo |"
            ),
            (
                "| `hybrid-document-intelligence-platform` | Private platform | "
                "`private_operational` | Keep private | Operational source of truth |"
            ),
            (
                "| `security-posture-platform` | Public derivative | `public_demo` | "
                "Keep public | Curated public-safe derivative |"
            ),
        ],
    )

    report = build_portfolio_modernization_report(
        workspace_root=tmp_path,
        matrix_path=matrix_path,
        repo_names=(repo_name,),
    )
    markdown = render_portfolio_modernization_report_markdown(report)

    assert "# Portfolio Modernization Review" in markdown
    assert "## Rationalization Recommendation" in markdown
    assert "## Repo Scorecard" in markdown
    assert "zero-trust-cicd-pipeline" in markdown
    assert "Use the private repo sync automation" in markdown


def test_render_portfolio_action_checklist_markdown_includes_repo_tasks(
    tmp_path: Path,
) -> None:
    """The action checklist should turn repo findings into incremental tasks."""

    repo_name = "azure-cost-optimizer"
    repo_path = tmp_path / repo_name
    repo_path.mkdir()
    (repo_path / "README.md").write_text(
        "# Azure Cost Optimizer\n\nTODO: validation and public scope.\n",
        encoding="utf-8",
    )

    matrix_path = tmp_path / "portfolio-projects" / "repo-classification-matrix.md"
    _write_matrix(
        matrix_path,
        [
            (
                "| `azure-cost-optimizer` | Cost reporting demo | `public_demo` | "
                "Keep public for now | Public-safe cost analysis demo |"
            ),
        ],
    )

    report = build_portfolio_modernization_report(
        workspace_root=tmp_path,
        matrix_path=matrix_path,
        repo_names=(repo_name,),
    )
    checklist = render_portfolio_action_checklist_markdown(report)

    assert "# Portfolio Modernization Action Checklist" in checklist
    assert "### azure-cost-optimizer" in checklist
    assert "- [ ] Remove README placeholder markers and template residue." in checklist
    assert "- [ ] Add a repo-local validation workflow or wrapper command." in checklist

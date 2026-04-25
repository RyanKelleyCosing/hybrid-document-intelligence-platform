"""Unit tests for Epic 7 gate helper functions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from document_intelligence.epic7_validation import (
    CommandResult,
    resolve_repo_python,
    resolve_venv_python,
    write_summary_file,
)


def test_resolve_repo_python_prefers_repo_local_venv(tmp_path: Path) -> None:
    """The helper should prefer the repo-local virtual environment."""

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    expected_python = repo_root / ".venv" / "Scripts" / "python.exe"
    expected_python.parent.mkdir(parents=True)
    expected_python.write_text("", encoding="utf-8")

    assert resolve_repo_python(repo_root) == expected_python


def test_resolve_repo_python_falls_back_to_current_interpreter(tmp_path: Path) -> None:
    """The helper should fall back to the current interpreter when needed."""

    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    assert resolve_repo_python(repo_root) == Path(sys.executable).resolve()


def test_resolve_venv_python_supports_posix_layout(tmp_path: Path) -> None:
    """The helper should resolve a POSIX virtual-environment interpreter."""

    venv_root = tmp_path / "venv"
    expected_python = venv_root / "bin" / "python"
    expected_python.parent.mkdir(parents=True)
    expected_python.write_text("", encoding="utf-8")

    assert resolve_venv_python(venv_root) == expected_python


def test_write_summary_file_includes_results_and_extra_payload(tmp_path: Path) -> None:
    """The summary writer should preserve command results and metadata."""

    output_path = tmp_path / "outputs" / "summary.json"
    results = [
        CommandResult(
            command=["python", "-m", "pytest"],
            cwd=str(tmp_path),
            returncode=0,
            stdout="passed",
            stderr="",
            step="tests",
        )
    ]

    write_summary_file(
        output_path,
        results,
        extra_payload={"gate": "pack-test", "workspace_root": str(tmp_path)},
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["all_succeeded"] is True
    assert payload["gate"] == "pack-test"
    assert payload["workspace_root"] == str(tmp_path)
    assert payload["results"][0]["step"] == "tests"
    assert payload["results"][0]["succeeded"] is True
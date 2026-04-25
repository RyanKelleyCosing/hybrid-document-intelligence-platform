"""Shared helpers for Epic 7 validation gate runners."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from shutil import which


@dataclass(frozen=True)
class CommandResult:
    """Result of one gate command execution."""

    command: list[str]
    cwd: str
    returncode: int
    stdout: str
    stderr: str
    step: str

    @property
    def succeeded(self) -> bool:
        """Return whether the command succeeded."""

        return self.returncode == 0

    def to_summary_dict(self) -> dict[str, object]:
        """Serialize the command result for JSON output."""

        return {
            "command": self.command,
            "cwd": self.cwd,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "step": self.step,
            "succeeded": self.succeeded,
        }


def resolve_path(repo_root: Path, candidate_path: Path) -> Path:
    """Resolve a possibly relative path from the repo root."""

    if candidate_path.is_absolute():
        return candidate_path
    return repo_root / candidate_path


def resolve_workspace_root(repo_root: Path, candidate_path: Path | None) -> Path:
    """Resolve the workspace root used for sibling-repo checks."""

    if candidate_path is None:
        return repo_root.parent
    return resolve_path(repo_root, candidate_path)


def resolve_repo_python(repo_root: Path) -> Path:
    """Resolve the preferred Python interpreter for gate scripts."""

    for candidate in (
        repo_root / ".venv" / "Scripts" / "python.exe",
        repo_root / ".venv" / "bin" / "python",
    ):
        if candidate.is_file():
            return candidate

    return Path(sys.executable).resolve()


def resolve_venv_python(venv_root: Path) -> Path:
    """Resolve the interpreter path inside a virtual environment."""

    candidates = (
        venv_root / "Scripts" / "python.exe",
        venv_root / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    if os.name == "nt":
        return candidates[0]
    return candidates[1]


def run_command(
    step: str,
    cwd: Path,
    command: list[str],
    *,
    environment_overrides: Mapping[str, str] | None = None,
) -> CommandResult:
    """Run one command and capture the structured result."""

    if not cwd.is_dir():
        return CommandResult(
            command=command,
            cwd=str(cwd),
            returncode=127,
            stdout="",
            stderr=f"Working directory does not exist: {cwd}",
            step=step,
        )

    resolved_command = resolve_command(command)
    environment = dict(os.environ)
    if environment_overrides is not None:
        environment.update(environment_overrides)

    try:
        completed = subprocess.run(
            resolved_command,
            capture_output=True,
            check=False,
            cwd=str(cwd),
            env=environment,
            text=True,
        )
    except FileNotFoundError as error:
        return CommandResult(
            command=resolved_command,
            cwd=str(cwd),
            returncode=127,
            stdout="",
            stderr=str(error),
            step=step,
        )

    return CommandResult(
        command=resolved_command,
        cwd=str(cwd),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        step=step,
    )


def resolve_command(command: list[str]) -> list[str]:
    """Resolve a command executable on the current platform."""

    executable = command[0]
    resolved_executable = which(executable)
    if resolved_executable is None and os.name == "nt":
        resolved_executable = which(f"{executable}.cmd") or which(
            f"{executable}.exe"
        )
    if resolved_executable is None:
        return command

    return [resolved_executable, *command[1:]]


def write_summary_file(
    output_path: Path,
    results: list[CommandResult],
    *,
    extra_payload: Mapping[str, object] | None = None,
) -> None:
    """Write one JSON summary file for a validation gate."""

    summary_payload: dict[str, object] = {
        "all_succeeded": all(result.succeeded for result in results),
        "results": [result.to_summary_dict() for result in results],
    }
    if extra_payload is not None:
        summary_payload.update(dict(extra_payload))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary_payload, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

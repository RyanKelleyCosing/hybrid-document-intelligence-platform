"""Repo-boundary helpers for Epic 6 public/private split work."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Literal

BoundaryExposure = Literal[
    "private_operational",
    "private_secret_bearing",
    "public_derivative_candidate",
]
BoundaryPathKind = Literal["directory", "file", "missing"]


@dataclass(frozen=True)
class RepoBoundaryEntry:
    """One path-level boundary rule for the repo split plan."""

    exposure: BoundaryExposure
    rationale: str
    recommended_action: str
    relative_path: str


@dataclass(frozen=True)
class RepoBoundaryManifest:
    """Structured boundary manifest for the repo split plan."""

    entries: tuple[RepoBoundaryEntry, ...]
    repo_name: str


@dataclass(frozen=True)
class RepoBoundaryReportItem:
    """Resolved boundary status for one manifest path."""

    exists: bool
    exposure: BoundaryExposure
    path_kind: BoundaryPathKind
    rationale: str
    recommended_action: str
    relative_path: str


@dataclass(frozen=True)
class RepoBoundaryReport:
    """Rendered repo-boundary report for the current workspace."""

    items: tuple[RepoBoundaryReportItem, ...]
    manifest_path: str
    repo_name: str


def _parse_boundary_exposure(value: str) -> BoundaryExposure:
    if value == "private_operational":
        return "private_operational"
    if value == "private_secret_bearing":
        return "private_secret_bearing"
    if value == "public_derivative_candidate":
        return "public_derivative_candidate"

    raise ValueError(f"Unsupported repo-boundary exposure '{value}'.")


def _require_non_empty_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Repo-boundary manifest field '{key}' must be a non-empty string.")
    return value.strip()


def _build_repo_boundary_entry(payload: object) -> RepoBoundaryEntry:
    if not isinstance(payload, dict):
        raise ValueError("Repo-boundary manifest entries must be JSON objects.")

    return RepoBoundaryEntry(
        exposure=_parse_boundary_exposure(_require_non_empty_str(payload, "exposure")),
        rationale=_require_non_empty_str(payload, "rationale"),
        recommended_action=_require_non_empty_str(payload, "recommended_action"),
        relative_path=_require_non_empty_str(payload, "relative_path"),
    )


def load_repo_boundary_manifest(manifest_path: Path) -> RepoBoundaryManifest:
    """Load the path-level repo-boundary manifest from disk."""

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Repo-boundary manifest root must be a JSON object.")

    entries_payload = payload.get("entries")
    if not isinstance(entries_payload, list):
        raise ValueError("Repo-boundary manifest must define an 'entries' array.")

    return RepoBoundaryManifest(
        entries=tuple(_build_repo_boundary_entry(item) for item in entries_payload),
        repo_name=_require_non_empty_str(payload, "repo_name"),
    )


def _resolve_path_kind(path: Path) -> BoundaryPathKind:
    if path.is_file():
        return "file"
    if path.is_dir():
        return "directory"
    return "missing"


def _build_repo_boundary_report_item(
    repo_root: Path,
    entry: RepoBoundaryEntry,
) -> RepoBoundaryReportItem:
    resolved_path = repo_root / entry.relative_path
    path_kind = _resolve_path_kind(resolved_path)
    return RepoBoundaryReportItem(
        exists=path_kind != "missing",
        exposure=entry.exposure,
        path_kind=path_kind,
        rationale=entry.rationale,
        recommended_action=entry.recommended_action,
        relative_path=entry.relative_path,
    )


def build_repo_boundary_report(
    repo_root: Path,
    manifest: RepoBoundaryManifest,
    manifest_path: Path,
) -> RepoBoundaryReport:
    """Resolve the repo-boundary manifest against the current workspace."""

    items = tuple(
        _build_repo_boundary_report_item(repo_root, entry)
        for entry in manifest.entries
    )
    return RepoBoundaryReport(
        items=items,
        manifest_path=str(manifest_path),
        repo_name=manifest.repo_name,
    )


def summarize_repo_boundary_report(
    report: RepoBoundaryReport,
) -> dict[BoundaryExposure, int]:
    """Count report items by exposure bucket."""

    summary: dict[BoundaryExposure, int] = {
        "private_operational": 0,
        "private_secret_bearing": 0,
        "public_derivative_candidate": 0,
    }
    for item in report.items:
        summary[item.exposure] += 1
    return summary


def render_repo_boundary_report_markdown(report: RepoBoundaryReport) -> str:
    """Render the repo-boundary report as Markdown."""

    summary = summarize_repo_boundary_report(report)
    lines = [
        "# Repo Boundary Report",
        "",
        f"Repo: `{report.repo_name}`",
        f"Manifest: `{report.manifest_path}`",
        "",
        "## Summary",
        "",
        f"- `private_secret_bearing`: {summary['private_secret_bearing']}",
        f"- `private_operational`: {summary['private_operational']}",
        f"- `public_derivative_candidate`: {summary['public_derivative_candidate']}",
    ]

    for exposure in (
        "private_secret_bearing",
        "private_operational",
        "public_derivative_candidate",
    ):
        lines.extend(["", f"## {exposure}", ""])
        exposure_items = [item for item in report.items if item.exposure == exposure]
        for item in exposure_items:
            existence_label = "present" if item.exists else "missing"
            lines.append(
                f"- `{item.relative_path}` ({item.path_kind}, {existence_label}): "
                f"{item.rationale} Next: {item.recommended_action}"
            )

    return "\n".join(lines) + "\n"


def render_repo_boundary_report_json(report: RepoBoundaryReport) -> str:
    """Render the repo-boundary report as formatted JSON."""

    return json.dumps(asdict(report), indent=2)
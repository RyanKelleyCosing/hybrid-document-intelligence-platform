"""Unit tests for the retained public cost-history publication helper."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit.test_epic7_gate_scripts import load_script_module

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "scripts"

# `scripts/` lives only in the private repo; skip when running against the
# public mirror so CI stays green there.
pytestmark = pytest.mark.skipif(
    not _SCRIPTS_ROOT.is_dir(),
    reason="scripts/ directory is private-only and not present in this checkout",
)


def create_history_fixture(history_directory: Path) -> None:
    """Create a minimal retained-history JSON and CSV fixture."""

    latest_json_path = history_directory / "json" / "latest.json"
    history_csv_path = history_directory / "csv" / "daily-cost-history.csv"
    latest_json_path.parent.mkdir(parents=True, exist_ok=True)
    history_csv_path.parent.mkdir(parents=True, exist_ok=True)
    latest_json_path.write_text('{"costSummary": {"month_to_date_cost": 184.5}}', encoding="utf-8")
    history_csv_path.write_text(
        "generated_at,currency,month_to_date_cost\n2026-04-19T17:16:33Z,USD,184.5\n",
        encoding="utf-8",
    )


def test_find_latest_history_directory_returns_newest_candidate(tmp_path: Path) -> None:
    """The auto-discovery helper should pick the most recently updated history set."""

    module = load_script_module("publish_public_cost_history.py")
    older_history = tmp_path / "older" / "cost-report" / "history"
    newer_history = tmp_path / "newer" / "cost-report" / "history"
    create_history_fixture(older_history)
    create_history_fixture(newer_history)
    latest_json_path = newer_history / "json" / "latest.json"
    latest_json_path.write_text(
        '{"costSummary": {"month_to_date_cost": 185.0}}',
        encoding="utf-8",
    )

    resolved_history = module.find_latest_history_directory(tmp_path)

    assert resolved_history == newer_history


def test_resolve_history_artifacts_requires_csv_history(tmp_path: Path) -> None:
    """The script should fail fast when the retained CSV history file is missing."""

    module = load_script_module("publish_public_cost_history.py")
    history_directory = tmp_path / "cost-report" / "history"
    latest_json_path = history_directory / "json" / "latest.json"
    latest_json_path.parent.mkdir(parents=True, exist_ok=True)
    latest_json_path.write_text("{}", encoding="utf-8")

    try:
        module.resolve_history_artifacts(history_directory)
    except FileNotFoundError as error:
        assert "daily-cost-history.csv" in str(error)
    else:
        raise AssertionError("Expected resolve_history_artifacts to reject missing CSV history.")


def test_main_writes_publication_artifact(monkeypatch, tmp_path: Path) -> None:
    """The publication script should record the uploaded blob metadata to disk."""

    module = load_script_module("publish_public_cost_history.py")
    history_directory = tmp_path / "cost-report" / "history"
    output_file = tmp_path / "published-public-cost-history.json"
    create_history_fixture(history_directory)

    args = SimpleNamespace(
        container_name="cost-optimizer-history",
        function_app_name="func-doc-test-nwigok",
        history_directory=history_directory,
        output_file=output_file,
        outputs_root=tmp_path / "outputs",
        resource_group_name="rg-doc-intel-dev",
        storage_connection_string="UseDevelopmentStorage=true",
    )

    monkeypatch.setattr(module, "parse_args", lambda: args)
    monkeypatch.setattr(module, "ensure_container_exists", lambda *_, **__: None)
    monkeypatch.setattr(
        module,
        "publish_history_artifacts",
        lambda *_, **__: (
            module.BlobAsset(
                blob_name="json/latest.json",
                container_name="cost-optimizer-history",
                content_length_bytes=123,
                storage_uri="https://example.blob.core.windows.net/cost-optimizer-history/json/latest.json",
            ),
            module.BlobAsset(
                blob_name="csv/daily-cost-history.csv",
                container_name="cost-optimizer-history",
                content_length_bytes=456,
                storage_uri="https://example.blob.core.windows.net/cost-optimizer-history/csv/daily-cost-history.csv",
            ),
        ),
    )

    exit_code = module.main()

    assert exit_code == 0
    output_payload = output_file.read_text(encoding="utf-8")
    assert '"ok": true' in output_payload
    assert "json/latest.json" in output_payload
    assert "function_app_setting" not in output_payload
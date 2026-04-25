"""Unit tests for the Pack 3 Azure-backed gate helper scripts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

from document_intelligence.epic7_validation import CommandResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"


def load_script_module(script_name: str) -> ModuleType:
    """Load one script file as an importable module for unit testing."""

    script_path = SCRIPTS_ROOT / script_name
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quick_summary_falls_back_to_child_artifacts(tmp_path: Path) -> None:
    """The quick-summary helper should derive failure details from child artifacts."""

    module = load_script_module("build_epic7_gate_quick_summary.py")
    artifact_dir = tmp_path / "epic7-azure-backed-postdeploy"
    synthetic_bundle_dir = artifact_dir / "synthetic-bundle"
    synthetic_bundle_dir.mkdir(parents=True)
    (synthetic_bundle_dir / "manifest.json").write_text("{}\n", encoding="utf-8")
    (artifact_dir / "storage-backed-bundle-results.json").write_text(
        json.dumps(
            {
                "errorCount": 0,
                "processedCount": 1,
                "requestedCount": 1,
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "packet-pipeline-smoke-results.json").write_text(
        json.dumps({"scenarios": {"nested_archive": {"passed": True}}}),
        encoding="utf-8",
    )
    (artifact_dir / "intake-source-execute-smoke.json").write_text(
        json.dumps({"failedBlobCount": 0, "processedBlobCount": 1}),
        encoding="utf-8",
    )
    (artifact_dir / "public-site-verifier.json").write_text(
        json.dumps({"ok": True}),
        encoding="utf-8",
    )
    cost_report_dir = artifact_dir / "cost-report"
    cost_report_dir.mkdir()
    (cost_report_dir / "azure-cost-report-validation.json").write_text(
        json.dumps(
            {
                "all_succeeded": False,
                "results": [
                    {
                        "stderr": "ERROR:root:Too many requests. Please retry.",
                        "stdout": "",
                        "step": "cost-report-evidence",
                        "succeeded": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    quick_summary = module.build_quick_summary(
        artifact_dir=artifact_dir,
        gate_summary_file=tmp_path / "missing-gate-summary.json",
        tail_characters=4000,
    )

    assert quick_summary["returncode"] == 1
    assert quick_summary["output_file_exists"] is False
    assert quick_summary["source"] == "artifact-fallback"
    assert quick_summary["failing_steps"] == ["azure-cost-report-validation"]
    assert "Too many requests" in str(quick_summary["stderr_tail"])


def test_azure_backed_gate_writes_summary_after_late_exception(
    monkeypatch, tmp_path: Path
) -> None:
    """The gate should still write its summary file after a late-stage exception."""

    module = load_script_module("run_epic7_azure_backed_gate.py")
    output_dir = tmp_path / "outputs"
    output_file = tmp_path / "epic7-azure-backed-postdeploy-gate.validation.json"
    args = SimpleNamespace(
        function_app_name="func-doc-test-nwigok",
        function_base_url="https://func-doc-test-nwigok.azurewebsites.net/api",
        local_settings_file=tmp_path / "local.settings.json",
        output_dir=output_dir,
        output_file=output_file,
        public_site_url="https://www.ryancodes.online",
        resource_group_name="rg-doc-intel-dev",
        review_admin_key="review-key",
        workspace_root=tmp_path,
    )

    monkeypatch.setattr(module, "parse_args", lambda: args)
    monkeypatch.setattr(module, "resolve_repo_python", lambda _: Path("python"))
    monkeypatch.setattr(module, "load_local_values", lambda _: {})
    monkeypatch.setattr(module, "resolve_azure_cli_executable", lambda: "az")
    monkeypatch.setattr(module, "load_function_app_settings", lambda *_, **__: {})
    monkeypatch.setattr(
        module,
        "resolve_function_base_url",
        lambda *_, **__: "https://func-doc-test-nwigok.azurewebsites.net/api",
    )
    monkeypatch.setattr(
        module,
        "resolve_public_site_url",
        lambda *_, **__: "https://www.ryancodes.online",
    )
    monkeypatch.setattr(module, "resolve_review_admin_key", lambda *_, **__: "review-key")
    monkeypatch.setattr(
        module,
        "run_azure_backed_commands",
        lambda *_, **__: [
            CommandResult(
                command=["python", "scripts/run_portfolio_cost_reporting_validation.py"],
                cwd=str(PROJECT_ROOT),
                returncode=1,
                stdout="",
                stderr="RuntimeError: Cost Management summary was unavailable.",
                step="azure-cost-report-validation",
            )
        ],
    )
    monkeypatch.setattr(
        module,
        "compare_live_public_metrics",
        lambda **_: (_ for _ in ()).throw(RuntimeError("public metrics blew up")),
    )
    monkeypatch.setattr(
        module,
        "load_optional_json",
        lambda _: {"all_succeeded": False},
    )

    exit_code = module.main()
    summary_payload = json.loads(output_file.read_text(encoding="utf-8"))
    recorded_steps = [result["step"] for result in summary_payload["results"]]

    assert exit_code == 1
    assert output_file.is_file()
    assert summary_payload["cost_validation"]["all_succeeded"] is False
    assert "public metrics blew up" in str(summary_payload["gate_error"])
    assert "azure-cost-report-validation" in recorded_steps
    assert "azure-backed-gate-internal" in recorded_steps


def test_cost_validation_publishes_public_history_after_evidence(
    monkeypatch, tmp_path: Path
) -> None:
    """The Azure-backed cost validator should publish fresh retained history."""

    module = load_script_module("run_portfolio_cost_reporting_validation.py")
    workspace_root = tmp_path / "workspace"
    portfolio_repo_root = workspace_root / "portfolio-projects" / "azure-cost-optimizer"
    portfolio_repo_root.mkdir(parents=True)
    output_dir = tmp_path / "cost-report"
    summary_file = output_dir / "azure-cost-report-validation.json"
    evidence_file = output_dir / "cost-report-evidence.json"
    publication_file = output_dir / "published-public-cost-history.json"
    args = SimpleNamespace(
        base_backoff_seconds=5.0,
        function_app_name="func-doc-test-nwigok",
        max_backoff_seconds=45.0,
        output_dir=output_dir,
        publish_public_cost_history=True,
        query_attempts=4,
        resource_group_name="rg-doc-intel-dev",
        subscription_id="sub-id",
        summary_attempts=3,
        summary_file=summary_file,
        workspace_root=workspace_root,
    )

    monkeypatch.setattr(module, "parse_args", lambda: args)
    monkeypatch.setattr(module, "resolve_path", lambda _root, path: path)
    monkeypatch.setattr(
        module,
        "resolve_workspace_root",
        lambda _repo_root, _workspace_root: workspace_root,
    )
    monkeypatch.setattr(module, "resolve_repo_python", lambda _: Path("python"))
    monkeypatch.setattr(module, "resolve_subscription_id", lambda _: "sub-id")

    recorded_steps: list[tuple[str, list[str]]] = []

    def fake_run_command(
        step: str,
        cwd: Path,
        command: list[str],
        environment_overrides: dict[str, str] | None = None,
    ) -> CommandResult:
        del cwd, environment_overrides
        recorded_steps.append((step, command))
        if step == "cost-report-evidence":
            history_directory = output_dir / "history"
            evidence_file.parent.mkdir(parents=True, exist_ok=True)
            evidence_file.write_text(
                json.dumps(
                    {
                        "history_directory": str(history_directory),
                        "ok": True,
                    }
                ),
                encoding="utf-8",
            )
        elif step == "cost-report-public-history-publication":
            publication_file.write_text(
                json.dumps(
                    {
                        "container_name": "cost-optimizer-history",
                        "ok": True,
                    }
                ),
                encoding="utf-8",
            )

        return CommandResult(
            command=command,
            cwd=str(portfolio_repo_root),
            returncode=0,
            stdout="",
            stderr="",
            step=step,
        )

    monkeypatch.setattr(module, "run_command", fake_run_command)

    exit_code = module.main()
    summary_payload = json.loads(summary_file.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert [step for step, _ in recorded_steps] == [
        "cost-report-venv",
        "cost-report-install",
        "cost-report-evidence",
        "cost-report-public-history-publication",
    ]
    publication_command = recorded_steps[-1][1]
    assert "scripts/publish_public_cost_history.py" in publication_command
    assert "--history-directory" in publication_command
    assert str(output_dir / "history") in publication_command
    assert "--function-app-name" in publication_command
    assert "func-doc-test-nwigok" in publication_command
    assert "--resource-group-name" in publication_command
    assert "rg-doc-intel-dev" in publication_command
    assert summary_payload["all_succeeded"] is True
    assert summary_payload["publication"]["ok"] is True
    assert summary_payload["artifacts"]["publication_file"] == str(publication_file)


def test_azure_backed_gate_passes_cost_publication_context(
    monkeypatch, tmp_path: Path
) -> None:
    """The Pack 3 gate should pass live publication context into cost validation."""

    module = load_script_module("run_epic7_azure_backed_gate.py")
    recorded_steps: list[tuple[str, list[str]]] = []

    def fake_run_command(
        step: str,
        cwd: Path,
        command: list[str],
        environment_overrides: dict[str, str] | None = None,
    ) -> CommandResult:
        del cwd, environment_overrides
        recorded_steps.append((step, command))
        return CommandResult(
            command=command,
            cwd=str(PROJECT_ROOT),
            returncode=0,
            stdout="",
            stderr="",
            step=step,
        )

    monkeypatch.setattr(module, "run_command", fake_run_command)

    module.run_azure_backed_commands(
        Path("python"),
        tmp_path,
        bundle_dir=tmp_path / "synthetic-bundle",
        cost_validation_summary=tmp_path / "cost-report" / "azure-cost-report-validation.json",
        function_app_name="func-custom",
        function_base_url="https://func-custom.azurewebsites.net/api",
        intake_source_output=tmp_path / "intake-source-execute-smoke.json",
        local_settings_file=tmp_path / "local.settings.json",
        packet_smoke_output=tmp_path / "packet-pipeline-smoke-results.json",
        public_site_url="https://www.ryancodes.online",
        public_verifier_output=tmp_path / "public-site-verifier.json",
        resource_group_name="rg-custom",
        review_admin_key="review-key",
        storage_backed_output=tmp_path / "storage-backed-bundle-results.json",
    )

    cost_command = next(
        command for step, command in recorded_steps if step == "azure-cost-report-validation"
    )

    assert "--function-app-name" in cost_command
    assert "func-custom" in cost_command
    assert "--resource-group-name" in cost_command
    assert "rg-custom" in cost_command
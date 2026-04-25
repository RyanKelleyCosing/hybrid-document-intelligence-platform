"""Unit tests for public-safe cost history readers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from document_intelligence.public_cost_metrics import (
    load_public_cost_history_csv,
    load_public_cost_latest_json,
    load_public_cost_metrics_summary,
)
from document_intelligence.settings import AppSettings

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HAS_BUNDLED_COST_HISTORY = any(
    _REPO_ROOT.glob("outputs/**/cost-report*/history/json/latest.json")
)
requires_bundled_cost_history = pytest.mark.skipif(
    not _HAS_BUNDLED_COST_HISTORY,
    reason="outputs/ retained cost history is gitignored; unavailable in CI",
)


def create_cost_history_fixture(history_directory: Path) -> None:
    """Create a representative cost-history snapshot and CSV payload."""

    latest_json_path = history_directory / "json" / "latest.json"
    history_csv_path = history_directory / "csv" / "daily-cost-history.csv"
    latest_json_path.parent.mkdir(parents=True, exist_ok=True)
    history_csv_path.parent.mkdir(parents=True, exist_ok=True)

    latest_json_path.write_text(
        json.dumps(
            {
                "costSummary": {
                    "currency": "USD",
                    "daily_cost_trend": [
                        {
                            "amount": 14.0,
                            "label": "Apr 17",
                            "period_end": "2026-04-17",
                            "period_start": "2026-04-17",
                        },
                        {
                            "amount": 18.25,
                            "label": "Apr 18",
                            "period_end": "2026-04-18",
                            "period_start": "2026-04-18",
                        },
                        {
                            "amount": 22.5,
                            "label": "Apr 19",
                            "period_end": "2026-04-19",
                            "period_start": "2026-04-19",
                        },
                        {
                            "amount": 24.5,
                            "label": "Apr 20",
                            "period_end": "2026-04-20",
                            "period_start": "2026-04-20",
                        },
                    ],
                    "day_over_day_delta": 4.25,
                    "month_to_date_cost": 184.5,
                    "monthly_cost_trend": [
                        {
                            "amount": 126.0,
                            "label": "Jan 2026",
                            "period_end": "2026-01-31",
                            "period_start": "2026-01-01",
                        },
                        {
                            "amount": 142.25,
                            "label": "Feb 2026",
                            "period_end": "2026-02-28",
                            "period_start": "2026-02-01",
                        },
                        {
                            "amount": 159.5,
                            "label": "Mar 2026",
                            "period_end": "2026-03-31",
                            "period_start": "2026-03-01",
                        },
                        {
                            "amount": 184.5,
                            "label": "Apr 2026",
                            "period_end": "2026-04-20",
                            "period_start": "2026-04-01",
                        },
                    ],
                    "previous_day_cost": 18.25,
                    "recent_daily_costs": [
                        {"amount": 14.0, "usage_date": "2026-04-17"},
                        {"amount": 18.25, "usage_date": "2026-04-18"},
                        {"amount": 22.5, "usage_date": "2026-04-19"},
                    ],
                    "today_cost": 24.5,
                    "top_resource_groups": [
                        {"amount": 82.0, "name": "Current platform environment"}
                    ],
                    "top_resources": [
                        {"amount": 57.5, "name": "Public API application"}
                    ],
                    "top_service_families": [
                        {"amount": 44.0, "name": "Azure AI Services"}
                    ],
                    "week_to_date_cost": 104.75,
                    "weekly_cost_trend": [
                        {
                            "amount": 96.0,
                            "label": "Week of Apr 06",
                            "period_end": "2026-04-12",
                            "period_start": "2026-04-06",
                        },
                        {
                            "amount": 104.75,
                            "label": "Week of Apr 13",
                            "period_end": "2026-04-20",
                            "period_start": "2026-04-13",
                        },
                    ],
                    "year_to_date_cost": 612.25,
                    "yesterday_cost": 22.5,
                },
                "generatedAt": "2026-04-20T17:16:33.262741Z",
                "historyRow": {
                    "currency": "USD",
                    "day_over_day_delta": 4.25,
                    "generated_at": "2026-04-20T17:16:33.262741Z",
                    "month_to_date_cost": 184.5,
                    "previous_day_cost": 18.25,
                    "today_cost": 24.5,
                    "week_to_date_cost": 104.75,
                    "year_to_date_cost": 612.25,
                    "yesterday_cost": 22.5,
                },
            }
        ),
        encoding="utf-8",
    )
    history_csv_path.write_text(
        "generated_at,currency,today_cost,week_to_date_cost,month_to_date_cost,year_to_date_cost,yesterday_cost,previous_day_cost,day_over_day_delta\n"
        "2026-04-17T17:16:33.262741Z,USD,14.0,59.25,144.0,567.0,14.0,10.5,3.5\n"
        "2026-04-18T17:16:33.262741Z,USD,18.25,77.5,162.25,585.25,18.25,14.0,4.25\n"
        "2026-04-19T17:16:33.262741Z,USD,22.5,100.0,184.75,607.75,22.5,18.25,4.25\n"
        "2026-04-20T17:16:33.262741Z,USD,24.5,104.75,184.5,612.25,22.5,18.25,4.25\n",
        encoding="utf-8",
    )


def create_legacy_cost_history_fixture(history_directory: Path) -> None:
    """Create an older retained-history snapshot without the new KPI fields."""

    latest_json_path = history_directory / "json" / "latest.json"
    history_csv_path = history_directory / "csv" / "daily-cost-history.csv"
    latest_json_path.parent.mkdir(parents=True, exist_ok=True)
    history_csv_path.parent.mkdir(parents=True, exist_ok=True)

    latest_json_path.write_text(
        json.dumps(
            {
                "costSummary": {
                    "currency": "USD",
                    "day_over_day_delta": 4.25,
                    "month_to_date_cost": 184.5,
                    "previous_day_cost": 18.25,
                    "recent_daily_costs": [
                        {"amount": 14.0, "usage_date": "2026-04-17"},
                        {"amount": 18.25, "usage_date": "2026-04-18"},
                    ],
                    "top_resource_groups": [
                        {"amount": 82.0, "name": "rg-doc-intel-dev"}
                    ],
                    "top_resources": [
                        {"amount": 57.5, "name": "func-doc-test-nwigok"}
                    ],
                    "top_service_families": [
                        {"amount": 44.0, "name": "Azure AI Services"}
                    ],
                    "yesterday_cost": 22.5,
                },
                "generatedAt": "2026-04-19T17:16:33.262741Z",
                "historyRow": {
                    "currency": "USD",
                    "generated_at": "2026-04-19T17:16:33.262741Z",
                    "top_resource_group_name": "rg-doc-intel-dev",
                    "top_resource_name": "func-doc-test-nwigok",
                },
            }
        ),
        encoding="utf-8",
    )
    history_csv_path.write_text(
        "generated_at,currency,month_to_date_cost,yesterday_cost,previous_day_cost,top_resource_name,top_resource_group_name\n"
        "2026-04-18T17:16:33.262741Z,USD,162.0,18.25,14.0,func-doc-test-nwigok,rg-doc-intel-dev\n"
        "2026-04-19T17:16:33.262741Z,USD,184.5,22.5,18.25,func-doc-test-nwigok,rg-doc-intel-dev\n",
        encoding="utf-8",
    )


def create_anomalous_cost_history_fixture(history_directory: Path) -> None:
    """Create retained history with a clear high-severity daily spike."""

    latest_json_path = history_directory / "json" / "latest.json"
    history_csv_path = history_directory / "csv" / "daily-cost-history.csv"
    latest_json_path.parent.mkdir(parents=True, exist_ok=True)
    history_csv_path.parent.mkdir(parents=True, exist_ok=True)

    latest_json_path.write_text(
        json.dumps(
            {
                "costSummary": {
                    "currency": "USD",
                    "daily_cost_trend": [
                        {
                            "amount": 14.0,
                            "label": "Apr 17",
                            "period_end": "2026-04-17",
                            "period_start": "2026-04-17",
                        },
                        {
                            "amount": 18.25,
                            "label": "Apr 18",
                            "period_end": "2026-04-18",
                            "period_start": "2026-04-18",
                        },
                        {
                            "amount": 22.5,
                            "label": "Apr 19",
                            "period_end": "2026-04-19",
                            "period_start": "2026-04-19",
                        },
                        {
                            "amount": 38.0,
                            "label": "Apr 20",
                            "period_end": "2026-04-20",
                            "period_start": "2026-04-20",
                        },
                    ],
                    "day_over_day_delta": 15.5,
                    "month_to_date_cost": 198.0,
                    "monthly_cost_trend": [
                        {
                            "amount": 126.0,
                            "label": "Jan 2026",
                            "period_end": "2026-01-31",
                            "period_start": "2026-01-01",
                        },
                        {
                            "amount": 142.25,
                            "label": "Feb 2026",
                            "period_end": "2026-02-28",
                            "period_start": "2026-02-01",
                        },
                        {
                            "amount": 159.5,
                            "label": "Mar 2026",
                            "period_end": "2026-03-31",
                            "period_start": "2026-03-01",
                        },
                        {
                            "amount": 198.0,
                            "label": "Apr 2026",
                            "period_end": "2026-04-20",
                            "period_start": "2026-04-01",
                        },
                    ],
                    "previous_day_cost": 18.25,
                    "recent_daily_costs": [
                        {"amount": 14.0, "usage_date": "2026-04-17"},
                        {"amount": 18.25, "usage_date": "2026-04-18"},
                        {"amount": 22.5, "usage_date": "2026-04-19"},
                    ],
                    "today_cost": 38.0,
                    "top_resource_groups": [
                        {"amount": 84.0, "name": "rg-doc-intel-dev"}
                    ],
                    "top_resources": [
                        {"amount": 61.0, "name": "func-doc-test-nwigok"}
                    ],
                    "top_service_families": [
                        {"amount": 49.0, "name": "Azure AI Services"}
                    ],
                    "week_to_date_cost": 118.25,
                    "weekly_cost_trend": [
                        {
                            "amount": 96.0,
                            "label": "Week of Apr 06",
                            "period_end": "2026-04-12",
                            "period_start": "2026-04-06",
                        },
                        {
                            "amount": 118.25,
                            "label": "Week of Apr 13",
                            "period_end": "2026-04-20",
                            "period_start": "2026-04-13",
                        },
                    ],
                    "year_to_date_cost": 625.75,
                    "yesterday_cost": 22.5,
                },
                "generatedAt": "2026-04-20T17:16:33.262741Z",
                "historyRow": {
                    "currency": "USD",
                    "day_over_day_delta": 15.5,
                    "generated_at": "2026-04-20T17:16:33.262741Z",
                    "month_to_date_cost": 198.0,
                    "previous_day_cost": 18.25,
                    "today_cost": 38.0,
                    "week_to_date_cost": 118.25,
                    "year_to_date_cost": 625.75,
                    "yesterday_cost": 22.5,
                },
            }
        ),
        encoding="utf-8",
    )
    history_csv_path.write_text(
        "generated_at,currency,today_cost,week_to_date_cost,month_to_date_cost,year_to_date_cost,yesterday_cost,previous_day_cost,day_over_day_delta\n"
        "2026-04-17T17:16:33.262741Z,USD,14.0,59.25,144.0,567.0,14.0,10.5,3.5\n"
        "2026-04-18T17:16:33.262741Z,USD,18.25,77.5,162.25,585.25,18.25,14.0,4.25\n"
        "2026-04-19T17:16:33.262741Z,USD,22.5,100.0,184.75,607.75,22.5,18.25,4.25\n"
        "2026-04-20T17:16:33.262741Z,USD,38.0,118.25,198.0,625.75,22.5,18.25,15.5\n",
        encoding="utf-8",
    )


def test_load_public_cost_metrics_summary_reads_local_history(tmp_path: Path) -> None:
    """The public cost reader should parse the latest local snapshot."""

    history_directory = tmp_path / "cost-history"
    create_cost_history_fixture(history_directory)
    settings = AppSettings(public_cost_history_directory=history_directory)

    summary = load_public_cost_metrics_summary(settings)

    assert summary is not None
    assert summary.currency == "USD"
    assert summary.today_cost == 24.5
    assert summary.week_to_date_cost == 104.75
    assert summary.month_to_date_cost == 184.5
    assert summary.year_to_date_cost == 612.25
    assert summary.yesterday_cost == 22.5
    assert summary.day_over_day_delta == 4.25
    assert summary.history_row_count == 4
    assert summary.history_source == "Retained public cost history"
    assert summary.daily_cost_trend[-1].label == "Apr 20"
    assert summary.weekly_cost_trend[-1].label == "Week of Apr 13"
    assert summary.monthly_cost_trend[-1].label == "Apr 2026"
    assert summary.forecast is not None
    assert round(summary.forecast.projected_month_end_cost, 2) == 382.62
    assert summary.anomalies == ()
    assert summary.top_resources[0].name == "Public API application"
    assert summary.top_service_families[0].name == "Azure AI Services"
    assert summary.recent_daily_costs[1].usage_date.isoformat() == "2026-04-18"


def test_load_public_cost_latest_json_and_csv_return_sanitized_payloads(
    tmp_path: Path,
) -> None:
    """The JSON and CSV helpers should sanitize retained public contributor labels."""

    history_directory = tmp_path / "cost-history"
    create_legacy_cost_history_fixture(history_directory)
    settings = AppSettings(public_cost_history_directory=history_directory)

    latest_json = load_public_cost_latest_json(settings)
    history_csv = load_public_cost_history_csv(settings)

    assert latest_json is not None
    assert latest_json["costSummary"]["month_to_date_cost"] == 184.5
    assert latest_json["costSummary"]["top_resources"] == [
        {"amount": 57.5, "name": "Public API application"}
    ]
    assert latest_json["costSummary"]["top_resource_groups"] == [
        {"amount": 82.0, "name": "Current platform environment"}
    ]
    assert latest_json["historyRow"]["top_resource_name"] == "Public API application"
    assert latest_json["historyRow"]["top_resource_group_name"] == "Current platform environment"
    assert history_csv is not None
    assert "generated_at,currency,month_to_date_cost,yesterday_cost,previous_day_cost" in history_csv
    assert "Public API application" in history_csv
    assert "Current platform environment" in history_csv


def test_load_public_cost_metrics_summary_derives_richer_fields_from_legacy_history(
    tmp_path: Path,
) -> None:
    """Older retained snapshots should still backfill the richer KPI fields."""

    history_directory = tmp_path / "legacy-cost-history"
    create_legacy_cost_history_fixture(history_directory)
    settings = AppSettings(public_cost_history_directory=history_directory)

    summary = load_public_cost_metrics_summary(settings)

    assert summary is not None
    assert summary.today_cost == 22.5
    assert summary.week_to_date_cost == 63.25
    assert summary.year_to_date_cost == 63.25
    assert summary.daily_cost_trend[-1].amount == 22.5
    assert summary.weekly_cost_trend[-1].amount == 63.25
    assert summary.top_resources[0].name == "Public API application"
    assert summary.top_resource_groups[0].name == "Current platform environment"


@requires_bundled_cost_history
def test_load_public_cost_metrics_summary_falls_back_to_repo_snapshot() -> None:
    """Missing configured history should fall back to the bundled repo snapshot."""

    settings = AppSettings(public_cost_history_directory=Path("missing-history"))

    summary = load_public_cost_metrics_summary(settings)

    assert summary is not None
    assert summary.history_source == "Bundled retained cost history"


def test_load_public_cost_metrics_summary_derives_anomalies_and_forecast(
    tmp_path: Path,
) -> None:
    """Retained daily spikes should surface as public anomaly and forecast signals."""

    history_directory = tmp_path / "anomalous-cost-history"
    create_anomalous_cost_history_fixture(history_directory)
    settings = AppSettings(public_cost_history_directory=history_directory)

    summary = load_public_cost_metrics_summary(settings)

    assert summary is not None
    assert summary.forecast is not None
    assert summary.forecast.based_on_days == 4
    assert round(summary.forecast.projected_month_end_cost, 2) == 429.88
    assert len(summary.anomalies) == 1
    assert summary.anomalies[0].usage_date.isoformat() == "2026-04-20"
    assert summary.anomalies[0].direction == "spike"
    assert summary.anomalies[0].severity == "high"

@requires_bundled_cost_history
def test_load_public_cost_metrics_summary_round_trips_through_json() -> None:
    """The bundled cost summary should survive a JSON model round-trip unchanged."""

    from document_intelligence.public_cost_metrics import PublicCostMetricsSummary

    settings = AppSettings(public_cost_history_directory=Path("missing-history"))
    summary = load_public_cost_metrics_summary(settings)

    assert summary is not None

    payload = summary.model_dump(mode="json")
    serialized = json.dumps(payload)
    rehydrated = PublicCostMetricsSummary.model_validate(json.loads(serialized))

    assert rehydrated.model_dump(mode="json") == payload
    assert rehydrated.history_source == summary.history_source
    assert rehydrated.month_to_date_cost == summary.month_to_date_cost
    assert len(rehydrated.recent_daily_costs) == len(summary.recent_daily_costs)

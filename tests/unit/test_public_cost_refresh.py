"""Unit tests for scheduled public cost refresh."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from document_intelligence.public_cost_refresh import (
    _build_daily_cost_entries,
    _build_ranked_contributors,
    _normalize_existing_history_rows,
    refresh_public_cost_history,
)
from document_intelligence.settings import AppSettings


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz: UTC | None = None) -> "_FixedDateTime":
        del tz
        return cls(2026, 4, 23, 17, 16, 33, 262741, tzinfo=UTC)


def test_refresh_public_cost_history_writes_local_snapshot(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Scheduled refresh should persist a rich local latest.json and CSV row."""

    from document_intelligence import public_cost_refresh as module

    history_directory = tmp_path / "public-cost-history"
    settings = AppSettings(
        public_cost_history_directory=history_directory,
        public_cost_refresh_enabled=True,
        public_cost_subscription_id="sub-id",
    )

    month_to_date_rows = [
        {"Currency": "USD", "UsageDate": 20260401, "totalCost": 105.25},
        {"Currency": "USD", "UsageDate": 20260420, "totalCost": 14.0},
        {"Currency": "USD", "UsageDate": 20260421, "totalCost": 18.25},
        {"Currency": "USD", "UsageDate": 20260422, "totalCost": 22.5},
        {"Currency": "USD", "UsageDate": 20260423, "totalCost": 24.5},
    ]
    year_to_date_rows = [
        {"Currency": "USD", "UsageDate": 20260131, "totalCost": 126.0},
        {"Currency": "USD", "UsageDate": 20260228, "totalCost": 142.25},
        {"Currency": "USD", "UsageDate": 20260331, "totalCost": 159.5},
        *month_to_date_rows,
    ]

    monkeypatch.setattr(module, "datetime", _FixedDateTime)
    monkeypatch.setattr(module, "DefaultAzureCredential", lambda: object())
    monkeypatch.setattr(module, "CostManagementClient", lambda **_: object())

    def fake_query_with_retry(*args, query_name: str, **kwargs):
        del args, kwargs
        if query_name == "month_to_date":
            return month_to_date_rows
        if query_name == "year_to_date":
            return year_to_date_rows
        raise AssertionError(f"Unexpected retry query: {query_name}")

    def fake_query_best_effort(*args, query_name: str, **kwargs):
        del args, kwargs
        if query_name == "top_resources":
            return [{"ResourceId": "/subscriptions/123/resourceGroups/rg/providers/Microsoft.Web/sites/func-doc-test-nwigok", "totalCost": 57.5}]
        if query_name == "top_resource_groups":
            return [{"ResourceGroup": "rg-doc-intel-dev", "totalCost": 82.0}]
        if query_name == "top_service_families":
            return [{"ServiceName": "Azure AI Services", "totalCost": 44.0}]
        raise AssertionError(f"Unexpected best-effort query: {query_name}")

    monkeypatch.setattr(module, "_query_usage_rows_with_retry", fake_query_with_retry)
    monkeypatch.setattr(module, "_query_usage_rows_best_effort", fake_query_best_effort)

    result = refresh_public_cost_history(settings)

    assert result["ok"] is True
    assert result["status"] == "refreshed"
    assert result["history_row_count"] == 1
    assert result["today_cost"] == 24.5
    assert result["week_to_date_cost"] == 79.25
    assert result["year_to_date_cost"] == 612.25

    latest_json_path = history_directory / "json" / "latest.json"
    history_csv_path = history_directory / "csv" / "daily-cost-history.csv"

    payload = json.loads(latest_json_path.read_text(encoding="utf-8"))
    history_csv = history_csv_path.read_text(encoding="utf-8")

    assert payload["costSummary"]["today_cost"] == 24.5
    assert payload["costSummary"]["week_to_date_cost"] == 79.25
    assert payload["costSummary"]["month_to_date_cost"] == 184.5
    assert payload["costSummary"]["year_to_date_cost"] == 612.25
    assert payload["costSummary"]["daily_cost_trend"][-1]["label"] == "Apr 23"
    assert payload["costSummary"]["weekly_cost_trend"][-1]["label"] == "Week of Apr 20"
    assert payload["costSummary"]["monthly_cost_trend"][-1]["label"] == "Apr 2026"
    assert payload["costSummary"]["top_resources"][0]["name"] == "Public API application"
    assert payload["costSummary"]["top_resource_groups"][0]["name"] == "Current platform environment"
    assert "generated_at,currency,today_cost,week_to_date_cost" in history_csv


def test_refresh_public_cost_history_requires_subscription_id(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Scheduled refresh should skip cleanly when no subscription id is configured."""

    monkeypatch.delenv("AZURE_SUBSCRIPTION_ID", raising=False)
    settings = AppSettings(
        public_cost_history_directory=tmp_path / "missing-subscription-history",
        public_cost_refresh_enabled=True,
        public_cost_subscription_id=None,
    )

    result = refresh_public_cost_history(settings)

    assert result["ok"] is False
    assert result["status"] == "configuration_required"


def test_public_cost_refresh_helpers_accept_pretaxcost_columns() -> None:
    """Azure Cost Management query rows should parse real PreTaxCost columns."""

    daily_entries = _build_daily_cost_entries(
        [
            {"Currency": "USD", "UsageDate": 20260420, "PreTaxCost": 0.635318562953198},
            {"Currency": "USD", "UsageDate": 20260421, "PreTaxCost": 0.207399046252108},
        ]
    )
    ranked_resources = _build_ranked_contributors(
        [
            {
                "ResourceId": "/subscriptions/123/resourceGroups/rg-doc-intel-dev/providers/Microsoft.Web/sites/func-doc-test-nwigok",
                "PreTaxCost": 3.79233212042909,
            },
            {
                "ResourceId": "/subscriptions/123/resourceGroups/rg-doc-intel-dev/providers/Microsoft.Storage/storageAccounts/stdoctestnwigok",
                "PreTaxCost": 0.635318562953198,
            },
        ],
        "ResourceId",
    )

    assert [entry.amount for entry in daily_entries] == [0.635318562953198, 0.207399046252108]
    assert [entry.usage_date.isoformat() for entry in daily_entries] == [
        "2026-04-20",
        "2026-04-21",
    ]
    assert ranked_resources[0].name == "Public API application"
    assert ranked_resources[0].amount == 3.79233212042909


def test_public_cost_refresh_helpers_use_public_safe_contributor_labels() -> None:
    """Ranked contributor labels should avoid tenant-specific resource identifiers."""

    ranked_resources = _build_ranked_contributors(
        [
            {
                "ResourceId": "/subscriptions/123/resourceGroups/rg-doc-intel-dev/providers/Microsoft.Storage/storageAccounts/stdoctestnwigok",
                "PreTaxCost": 3.79233212042909,
            },
            {
                "ResourceId": "/subscriptions/123/resourceGroups/rg-doc-intel-dev/providers/Microsoft.CognitiveServices/accounts/aoaidocint-eastus2",
                "PreTaxCost": 0.635318562953198,
            },
            {
                "ResourceId": "/subscriptions/123/resourceGroups/rg-doc-intel-dev/providers/Microsoft.Web/serverfarms/asp-live-test-nwigok",
                "PreTaxCost": 0.207399046252108,
            },
        ],
        "ResourceId",
    )
    ranked_resource_groups = _build_ranked_contributors(
        [
            {"ResourceGroup": "rg-doc-intel-dev", "PreTaxCost": 3.79233212042909},
            {"ResourceGroup": "DefaultResourceGroup-CUS", "PreTaxCost": 0.635318562953198},
        ],
        "ResourceGroup",
    )

    assert [contributor.name for contributor in ranked_resources] == [
        "Platform storage",
        "OpenAI inference",
        "Protected admin compute",
    ]
    assert [contributor.name for contributor in ranked_resource_groups] == [
        "Current platform environment",
        "Shared default environment",
    ]


def test_public_cost_refresh_sanitizes_retained_history_contributor_columns() -> None:
    """Retained CSV history should be rewritten with public-safe contributor labels."""

    normalized_rows = _normalize_existing_history_rows(
        [
            {
                "generated_at": "2026-04-20T17:16:33.262741Z",
                "top_resource_name": "func-doc-test-nwigok",
                "top_resource_group_name": "rg-doc-intel-dev",
            }
        ]
    )

    assert normalized_rows[0]["top_resource_name"] == "Public API application"
    assert normalized_rows[0]["top_resource_group_name"] == "Current platform environment"
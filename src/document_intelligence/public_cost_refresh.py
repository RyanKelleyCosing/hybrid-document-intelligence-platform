"""Refresh durable public-safe Azure cost history on a schedule."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Any

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.storage.blob import BlobServiceClient

from document_intelligence.public_cost_metrics import (
    DEFAULT_COST_HISTORY_CONTAINER,
    DEFAULT_COST_HISTORY_DIRECTORY,
    LATEST_COST_CSV_NAME,
    LATEST_COST_JSON_NAME,
)
from document_intelligence.settings import AppSettings

RETRYABLE_COST_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
PUBLIC_COST_HISTORY_FIELDNAMES = [
    "generated_at",
    "currency",
    "today_cost",
    "week_to_date_cost",
    "month_to_date_cost",
    "year_to_date_cost",
    "yesterday_cost",
    "previous_day_cost",
    "day_over_day_delta",
    "total_estimated_savings",
    "high_priority_count",
    "medium_priority_count",
    "low_priority_count",
    "sql_finding_count",
    "security_finding_count",
    "high_severity_count",
    "medium_severity_count",
    "low_severity_count",
    "top_resource_name",
    "top_resource_cost",
    "top_resource_group_name",
    "top_resource_group_cost",
    "top_service_family_name",
    "top_service_family_cost",
]

PUBLIC_COST_RESOURCE_LABEL_LIMIT = 3


@dataclass(frozen=True)
class CostContributor:
    """Represent one ranked public-safe cost contributor."""

    amount: float
    name: str


@dataclass(frozen=True)
class DailyCostEntry:
    """Represent one day of spend."""

    amount: float
    usage_date: date


@dataclass(frozen=True)
class CostTrendPoint:
    """Represent one aggregated trend period exposed to the UI."""

    amount: float
    label: str
    period_end: date
    period_start: date


@dataclass(frozen=True)
class PublicCostSummaryData:
    """Represent the rich public cost contract persisted in latest.json."""

    currency: str | None
    daily_cost_trend: tuple[CostTrendPoint, ...]
    day_over_day_delta: float
    monthly_cost_trend: tuple[CostTrendPoint, ...]
    month_to_date_cost: float
    previous_day_cost: float
    recent_daily_costs: tuple[DailyCostEntry, ...]
    today_cost: float
    top_resource_groups: tuple[CostContributor, ...]
    top_resources: tuple[CostContributor, ...]
    top_service_families: tuple[CostContributor, ...]
    week_to_date_cost: float
    weekly_cost_trend: tuple[CostTrendPoint, ...]
    year_to_date_cost: float
    yesterday_cost: float


@dataclass(frozen=True)
class PublicCostHistoryRow:
    """Represent one CSV row in the retained public cost history."""

    currency: str | None
    day_over_day_delta: float
    generated_at: datetime
    month_to_date_cost: float
    previous_day_cost: float
    today_cost: float
    top_resource_cost: float
    top_resource_group_cost: float
    top_resource_group_name: str | None
    top_resource_name: str | None
    top_service_family_cost: float
    top_service_family_name: str | None
    week_to_date_cost: float
    year_to_date_cost: float
    yesterday_cost: float
    total_estimated_savings: float = 0.0
    high_priority_count: int = 0
    medium_priority_count: int = 0
    low_priority_count: int = 0
    sql_finding_count: int = 0
    security_finding_count: int = 0
    high_severity_count: int = 0
    medium_severity_count: int = 0
    low_severity_count: int = 0


@dataclass(frozen=True)
class PublicCostSnapshot:
    """Represent the latest JSON payload and matching CSV row."""

    cost_summary: PublicCostSummaryData
    generated_at: datetime
    history_row: PublicCostHistoryRow


@dataclass(frozen=True)
class PersistedHistoryResult:
    """Capture where the refreshed public cost artifacts were written."""

    history_row_count: int
    history_source: str
    outputs: tuple[str, ...]


def refresh_public_cost_history(settings: AppSettings) -> dict[str, Any]:
    """Refresh the retained public-safe cost history from Azure Cost Management."""

    if not settings.public_cost_refresh_enabled:
        return {
            "message": "Public cost refresh is disabled.",
            "ok": False,
            "status": "disabled",
        }

    subscription_id = _resolve_subscription_id(settings)
    if subscription_id is None:
        logging.warning(
            "Skipping public cost refresh because no subscription id is configured."
        )
        return {
            "message": "Set DOCINT_PUBLIC_COST_SUBSCRIPTION_ID or AZURE_SUBSCRIPTION_ID.",
            "ok": False,
            "status": "configuration_required",
        }

    generated_at = datetime.now(UTC)
    try:
        summary = _build_public_cost_summary(
            subscription_id,
            settings,
            today=generated_at.date(),
        )
        snapshot = _build_public_cost_snapshot(generated_at, summary)
        persisted = _persist_public_cost_snapshot(snapshot, settings)
    except Exception as error:
        logging.exception("Scheduled public cost refresh failed: %s", error)
        return {
            "generated_at": generated_at.isoformat(),
            "message": str(error),
            "ok": False,
            "status": "failed",
            "subscription_id": subscription_id,
        }

    return {
        "generated_at": generated_at.isoformat(),
        "history_outputs": list(persisted.outputs),
        "history_row_count": persisted.history_row_count,
        "history_source": persisted.history_source,
        "month_to_date_cost": summary.month_to_date_cost,
        "ok": True,
        "status": "refreshed",
        "subscription_id": subscription_id,
        "today_cost": summary.today_cost,
        "week_to_date_cost": summary.week_to_date_cost,
        "year_to_date_cost": summary.year_to_date_cost,
    }


def _build_public_cost_summary(
    subscription_id: str,
    settings: AppSettings,
    *,
    today: date,
) -> PublicCostSummaryData:
    scope = f"subscriptions/{subscription_id}"
    tomorrow = today + timedelta(days=1)
    year_start = date(today.year, 1, 1)
    week_start = today - timedelta(days=today.weekday())

    credential = DefaultAzureCredential()
    client = CostManagementClient(credential=credential)

    month_to_date_rows = _query_usage_rows_with_retry(
        client,
        scope,
        _build_daily_query("MonthToDate"),
        query_name="month_to_date",
        settings=settings,
    )
    year_to_date_rows = _query_usage_rows_with_retry(
        client,
        scope,
        _build_custom_daily_query(year_start, tomorrow),
        query_name="year_to_date",
        settings=settings,
    )
    top_resource_rows = _query_usage_rows_best_effort(
        client,
        scope,
        _build_grouped_query("ResourceId"),
        query_name="top_resources",
        settings=settings,
    )
    top_resource_group_rows = _query_usage_rows_best_effort(
        client,
        scope,
        _build_grouped_query("ResourceGroup"),
        query_name="top_resource_groups",
        settings=settings,
    )
    top_service_rows = _query_usage_rows_best_effort(
        client,
        scope,
        _build_grouped_query("ServiceName"),
        query_name="top_service_families",
        settings=settings,
    )

    month_to_date_costs = _build_daily_cost_entries(month_to_date_rows)
    year_to_date_costs = _build_daily_cost_entries(year_to_date_rows)
    daily_lookup = {entry.usage_date: entry.amount for entry in year_to_date_costs}
    recent_complete_days = tuple(entry for entry in year_to_date_costs if entry.usage_date < today)
    currency = _resolve_currency(
        month_to_date_rows,
        year_to_date_rows,
        top_resource_rows,
        top_resource_group_rows,
        top_service_rows,
    )
    today_cost = _resolve_today_cost(month_to_date_costs, daily_lookup, today)

    return PublicCostSummaryData(
        currency=currency,
        daily_cost_trend=_build_daily_trend_points(year_to_date_costs),
        day_over_day_delta=daily_lookup.get(today - timedelta(days=1), 0.0)
        - daily_lookup.get(today - timedelta(days=2), 0.0),
        monthly_cost_trend=_build_monthly_trend_points(year_to_date_costs),
        month_to_date_cost=sum(entry.amount for entry in month_to_date_costs),
        previous_day_cost=daily_lookup.get(today - timedelta(days=2), 0.0),
        recent_daily_costs=recent_complete_days[-3:],
        today_cost=today_cost,
        top_resource_groups=tuple(
            _build_ranked_contributors(top_resource_group_rows, "ResourceGroup")
        ),
        top_resources=tuple(
            _build_ranked_contributors(top_resource_rows, "ResourceId")
        ),
        top_service_families=tuple(
            _build_ranked_contributors(top_service_rows, "ServiceName")
        ),
        week_to_date_cost=sum(
            amount for usage_date, amount in daily_lookup.items() if week_start <= usage_date <= today
        ),
        weekly_cost_trend=_build_weekly_trend_points(year_to_date_costs),
        year_to_date_cost=sum(entry.amount for entry in year_to_date_costs),
        yesterday_cost=daily_lookup.get(today - timedelta(days=1), 0.0),
    )


def _query_usage_rows_with_retry(
    client: CostManagementClient,
    scope: str,
    parameters: dict[str, Any],
    *,
    query_name: str,
    settings: AppSettings,
) -> list[dict[str, Any]]:
    for attempt_number in range(1, settings.public_cost_query_max_attempts + 1):
        try:
            return _query_usage_rows(client, scope, parameters)
        except Exception as error:
            should_retry = (
                attempt_number < settings.public_cost_query_max_attempts
                and _is_retryable_cost_error(error)
            )
            if not should_retry:
                raise

            delay_seconds = _resolve_retry_delay_seconds(error, attempt_number, settings)
            logging.warning(
                "Retrying public cost query %s in %.1f seconds (%s/%s): %s",
                query_name,
                delay_seconds,
                attempt_number,
                settings.public_cost_query_max_attempts,
                error,
            )
            time.sleep(delay_seconds)

    return []


def _query_usage_rows_best_effort(
    client: CostManagementClient,
    scope: str,
    parameters: dict[str, Any],
    *,
    query_name: str,
    settings: AppSettings,
) -> list[dict[str, Any]]:
    try:
        return _query_usage_rows_with_retry(
            client,
            scope,
            parameters,
            query_name=query_name,
            settings=settings,
        )
    except Exception as error:
        if not _is_retryable_cost_error(error):
            raise

        logging.warning(
            "Proceeding without optional public cost query %s after retries: %s",
            query_name,
            error,
        )
        return []


def _build_public_cost_snapshot(
    generated_at: datetime,
    summary: PublicCostSummaryData,
) -> PublicCostSnapshot:
    history_row = PublicCostHistoryRow(
        currency=summary.currency,
        day_over_day_delta=summary.day_over_day_delta,
        generated_at=generated_at,
        month_to_date_cost=summary.month_to_date_cost,
        previous_day_cost=summary.previous_day_cost,
        today_cost=summary.today_cost,
        top_resource_cost=summary.top_resources[0].amount if summary.top_resources else 0.0,
        top_resource_group_cost=(
            summary.top_resource_groups[0].amount if summary.top_resource_groups else 0.0
        ),
        top_resource_group_name=(
            summary.top_resource_groups[0].name if summary.top_resource_groups else None
        ),
        top_resource_name=summary.top_resources[0].name if summary.top_resources else None,
        top_service_family_cost=(
            summary.top_service_families[0].amount
            if summary.top_service_families
            else 0.0
        ),
        top_service_family_name=(
            summary.top_service_families[0].name
            if summary.top_service_families
            else None
        ),
        week_to_date_cost=summary.week_to_date_cost,
        year_to_date_cost=summary.year_to_date_cost,
        yesterday_cost=summary.yesterday_cost,
    )
    return PublicCostSnapshot(
        cost_summary=summary,
        generated_at=generated_at,
        history_row=history_row,
    )


def _persist_public_cost_snapshot(
    snapshot: PublicCostSnapshot,
    settings: AppSettings,
) -> PersistedHistoryResult:
    if _prefer_local_cost_history_directory(settings):
        history_directory = _resolve_history_directory(settings)
        return _persist_snapshot_to_local_directory(snapshot, history_directory)

    connection_string = _resolve_storage_connection_string(settings)
    if connection_string:
        container_name = _resolve_container_name(settings)
        return _persist_snapshot_to_blob_storage(snapshot, connection_string, container_name)

    history_directory = _resolve_history_directory(settings)
    return _persist_snapshot_to_local_directory(snapshot, history_directory)


def _persist_snapshot_to_local_directory(
    snapshot: PublicCostSnapshot,
    history_directory: Path,
) -> PersistedHistoryResult:
    archive_path = history_directory / _archive_json_name(snapshot.generated_at)
    latest_path = history_directory / LATEST_COST_JSON_NAME
    csv_path = history_directory / LATEST_COST_CSV_NAME

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    payload_text = _snapshot_json(snapshot)
    archive_path.write_text(payload_text, encoding="utf-8")
    latest_path.write_text(payload_text, encoding="utf-8")

    existing_rows = _read_existing_history_rows(
        csv_path.read_text(encoding="utf-8") if csv_path.exists() else ""
    )
    updated_rows = [*_normalize_existing_history_rows(existing_rows), _history_row_to_dict(snapshot.history_row)]
    csv_path.write_text(_serialize_history_rows(updated_rows), encoding="utf-8")

    return PersistedHistoryResult(
        history_row_count=len(updated_rows),
        history_source="Configured local cost history",
        outputs=(str(archive_path), str(latest_path), str(csv_path)),
    )


def _persist_snapshot_to_blob_storage(
    snapshot: PublicCostSnapshot,
    connection_string: str,
    container_name: str,
) -> PersistedHistoryResult:
    archive_blob_name = _archive_json_name(snapshot.generated_at).as_posix()
    payload_text = _snapshot_json(snapshot)

    with BlobServiceClient.from_connection_string(connection_string) as service_client:
        container_client = service_client.get_container_client(container_name)
        try:
            container_client.create_container()
        except ResourceExistsError:
            pass

        container_client.upload_blob(archive_blob_name, payload_text, overwrite=True)
        container_client.upload_blob(LATEST_COST_JSON_NAME, payload_text, overwrite=True)

        csv_client = container_client.get_blob_client(LATEST_COST_CSV_NAME)
        try:
            existing_csv = csv_client.download_blob().readall().decode("utf-8")
        except ResourceNotFoundError:
            existing_csv = ""

        existing_rows = _read_existing_history_rows(existing_csv)
        updated_rows = [*_normalize_existing_history_rows(existing_rows), _history_row_to_dict(snapshot.history_row)]
        csv_client.upload_blob(_serialize_history_rows(updated_rows), overwrite=True)

    return PersistedHistoryResult(
        history_row_count=len(updated_rows),
        history_source=f"Azure Blob cost history ({container_name})",
        outputs=(
            f"{container_name}/{archive_blob_name}",
            f"{container_name}/{LATEST_COST_JSON_NAME}",
            f"{container_name}/{LATEST_COST_CSV_NAME}",
        ),
    )


def _snapshot_json(snapshot: PublicCostSnapshot) -> str:
    return json.dumps(_snapshot_to_dict(snapshot), indent=2, sort_keys=True)


def _snapshot_to_dict(snapshot: PublicCostSnapshot) -> dict[str, Any]:
    return {
        "costSummary": _summary_to_dict(snapshot.cost_summary),
        "generatedAt": _isoformat(snapshot.generated_at),
        "historyRow": _history_row_to_dict(snapshot.history_row),
    }


def _summary_to_dict(summary: PublicCostSummaryData) -> dict[str, Any]:
    return {
        "currency": summary.currency,
        "daily_cost_trend": [_trend_point_to_dict(point) for point in summary.daily_cost_trend],
        "day_over_day_delta": summary.day_over_day_delta,
        "monthly_cost_trend": [
            _trend_point_to_dict(point) for point in summary.monthly_cost_trend
        ],
        "month_to_date_cost": summary.month_to_date_cost,
        "previous_day_cost": summary.previous_day_cost,
        "recent_daily_costs": [
            _daily_cost_entry_to_dict(entry) for entry in summary.recent_daily_costs
        ],
        "today_cost": summary.today_cost,
        "top_resource_groups": [
            _contributor_to_dict(contributor) for contributor in summary.top_resource_groups
        ],
        "top_resources": [
            _contributor_to_dict(contributor) for contributor in summary.top_resources
        ],
        "top_service_families": [
            _contributor_to_dict(contributor)
            for contributor in summary.top_service_families
        ],
        "week_to_date_cost": summary.week_to_date_cost,
        "weekly_cost_trend": [
            _trend_point_to_dict(point) for point in summary.weekly_cost_trend
        ],
        "year_to_date_cost": summary.year_to_date_cost,
        "yesterday_cost": summary.yesterday_cost,
    }


def _history_row_to_dict(history_row: PublicCostHistoryRow) -> dict[str, Any]:
    return {
        "currency": history_row.currency or "",
        "day_over_day_delta": history_row.day_over_day_delta,
        "generated_at": _isoformat(history_row.generated_at),
        "high_priority_count": history_row.high_priority_count,
        "high_severity_count": history_row.high_severity_count,
        "low_priority_count": history_row.low_priority_count,
        "low_severity_count": history_row.low_severity_count,
        "medium_priority_count": history_row.medium_priority_count,
        "medium_severity_count": history_row.medium_severity_count,
        "month_to_date_cost": history_row.month_to_date_cost,
        "previous_day_cost": history_row.previous_day_cost,
        "security_finding_count": history_row.security_finding_count,
        "sql_finding_count": history_row.sql_finding_count,
        "today_cost": history_row.today_cost,
        "top_resource_cost": history_row.top_resource_cost,
        "top_resource_group_cost": history_row.top_resource_group_cost,
        "top_resource_group_name": history_row.top_resource_group_name or "",
        "top_resource_name": history_row.top_resource_name or "",
        "top_service_family_cost": history_row.top_service_family_cost,
        "top_service_family_name": history_row.top_service_family_name or "",
        "total_estimated_savings": history_row.total_estimated_savings,
        "week_to_date_cost": history_row.week_to_date_cost,
        "year_to_date_cost": history_row.year_to_date_cost,
        "yesterday_cost": history_row.yesterday_cost,
    }


def _daily_cost_entry_to_dict(entry: DailyCostEntry) -> dict[str, Any]:
    return {"amount": entry.amount, "usage_date": entry.usage_date.isoformat()}


def _trend_point_to_dict(point: CostTrendPoint) -> dict[str, Any]:
    return {
        "amount": point.amount,
        "label": point.label,
        "period_end": point.period_end.isoformat(),
        "period_start": point.period_start.isoformat(),
    }


def _contributor_to_dict(contributor: CostContributor) -> dict[str, Any]:
    return {"amount": contributor.amount, "name": contributor.name}


def _build_daily_trend_points(
    daily_entries: list[DailyCostEntry],
) -> tuple[CostTrendPoint, ...]:
    return tuple(
        CostTrendPoint(
            amount=entry.amount,
            label=entry.usage_date.strftime("%b %d"),
            period_end=entry.usage_date,
            period_start=entry.usage_date,
        )
        for entry in daily_entries[-7:]
    )


def _build_weekly_trend_points(
    daily_entries: list[DailyCostEntry],
) -> tuple[CostTrendPoint, ...]:
    grouped_entries = _group_daily_entries(
        daily_entries,
        key_builder=lambda usage_date: usage_date - timedelta(days=usage_date.weekday()),
    )
    return tuple(
        CostTrendPoint(
            amount=amount,
            label=f"Week of {period_start.strftime('%b %d')}",
            period_end=period_end,
            period_start=period_start,
        )
        for period_start, period_end, amount in grouped_entries[-6:]
    )


def _build_monthly_trend_points(
    daily_entries: list[DailyCostEntry],
) -> tuple[CostTrendPoint, ...]:
    grouped_entries = _group_daily_entries(
        daily_entries,
        key_builder=lambda usage_date: date(usage_date.year, usage_date.month, 1),
    )
    return tuple(
        CostTrendPoint(
            amount=amount,
            label=period_start.strftime("%b %Y"),
            period_end=period_end,
            period_start=period_start,
        )
        for period_start, period_end, amount in grouped_entries[-6:]
    )


def _group_daily_entries(
    daily_entries: list[DailyCostEntry],
    *,
    key_builder: Any,
) -> list[tuple[date, date, float]]:
    grouped: dict[date, tuple[date, float]] = {}

    for entry in daily_entries:
        period_start = key_builder(entry.usage_date)
        period_end, current_amount = grouped.get(
            period_start,
            (entry.usage_date, 0.0),
        )
        grouped[period_start] = (
            max(period_end, entry.usage_date),
            current_amount + entry.amount,
        )

    return [
        (period_start, period_end, amount)
        for period_start, (period_end, amount) in sorted(grouped.items())
    ]


def _resolve_today_cost(
    month_to_date_costs: list[DailyCostEntry],
    daily_lookup: dict[date, float],
    today: date,
) -> float:
    if today in daily_lookup:
        return daily_lookup[today]

    month_to_date_total = sum(entry.amount for entry in month_to_date_costs)
    complete_month_total = sum(
        amount
        for usage_date, amount in daily_lookup.items()
        if usage_date.year == today.year
        and usage_date.month == today.month
        and usage_date < today
    )
    return max(0.0, month_to_date_total - complete_month_total)


def _query_usage_rows(
    client: CostManagementClient,
    scope: str,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    result = client.query.usage(scope=scope, parameters=parameters)
    if result is None:
        return []

    properties = getattr(result, "properties", result)
    columns = _read_result_part(properties, "columns")
    rows = _read_result_part(properties, "rows")
    column_names = [
        column.get("name") if isinstance(column, dict) else getattr(column, "name", None)
        for column in columns
    ]

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized_rows.append(
            {
                column_name: value
                for column_name, value in zip(column_names, row)
                if column_name is not None
            }
        )

    return normalized_rows


def _read_result_part(result: Any, attribute: str) -> list[Any]:
    if isinstance(result, dict):
        return list(result.get(attribute, []))

    return list(getattr(result, attribute, []) or [])


def _build_daily_cost_entries(rows: list[dict[str, Any]]) -> list[DailyCostEntry]:
    by_date: dict[date, float] = {}

    for row in rows:
        usage_date = _parse_usage_date(row.get("UsageDate"))
        if usage_date is None:
            continue

        by_date[usage_date] = by_date.get(usage_date, 0.0) + _read_cost_amount(row)

    return [
        DailyCostEntry(amount=amount, usage_date=usage_date)
        for usage_date, amount in sorted(by_date.items())
    ]


def _build_ranked_contributors(
    rows: list[dict[str, Any]],
    dimension_name: str,
) -> list[CostContributor]:
    ranked_rows = sorted(rows, key=_read_cost_amount, reverse=True)
    contributors: list[CostContributor] = []
    label_counts: dict[str, int] = {}

    for row in ranked_rows:
        raw_name = row.get(dimension_name)
        if raw_name in (None, ""):
            continue

        contributor_name = _normalize_contributor_name(str(raw_name), dimension_name)
        if not contributor_name:
            continue

        contributors.append(
            CostContributor(
                amount=_read_cost_amount(row),
                name=_deduplicate_contributor_name(contributor_name, label_counts),
            )
        )
        if len(contributors) == PUBLIC_COST_RESOURCE_LABEL_LIMIT:
            break

    return contributors


def _normalize_contributor_name(raw_name: str, dimension_name: str) -> str:
    normalized_name = raw_name.strip()
    if not normalized_name:
        return ""

    if dimension_name == "ResourceId":
        return _normalize_resource_identifier(normalized_name)

    if dimension_name == "ResourceGroup":
        return _normalize_resource_group_name(normalized_name)

    return normalized_name


def _deduplicate_contributor_name(
    contributor_name: str,
    label_counts: dict[str, int],
) -> str:
    occurrence = label_counts.get(contributor_name, 0) + 1
    label_counts[contributor_name] = occurrence

    if occurrence == 1:
        return contributor_name

    return f"{contributor_name} {occurrence}"


def _normalize_resource_identifier(resource_id: str) -> str:
    if "/" not in resource_id:
        return _normalize_resource_name(resource_id)

    resource_name = resource_id.rstrip("/").split("/")[-1]
    resource_type_path = _extract_resource_type_path(resource_id)
    lowered_name = resource_name.lower()

    match resource_type_path:
        case "microsoft.cognitiveservices/accounts":
            if any(token in lowered_name for token in ("aoai", "openai")):
                return "OpenAI inference"
            if any(token in lowered_name for token in ("docint", "form", "ocr")) or lowered_name.startswith("di"):
                return "Document intelligence inference"
            return "AI service account"
        case "microsoft.communication/communicationservices":
            return "Notification delivery"
        case "microsoft.insights/components":
            return "Application monitoring"
        case "microsoft.keyvault/vaults":
            return "Secrets vault"
        case "microsoft.operationalinsights/workspaces":
            return "Log analytics workspace"
        case "microsoft.sql/servers/databases":
            return "Operational SQL database"
        case "microsoft.storage/storageaccounts":
            return "Platform storage"
        case "microsoft.web/serverfarms":
            if "admin" in lowered_name or lowered_name.startswith("asp"):
                return "Protected admin compute"
            return "Application compute plan"
        case "microsoft.web/sites":
            if "admin" in lowered_name:
                return "Protected admin application"
            if any(token in lowered_name for token in ("func", "api")):
                return "Public API application"
            return "Platform web application"
        case _:
            return _normalize_resource_name(resource_name)


def _extract_resource_type_path(resource_id: str) -> str:
    segments = [segment for segment in resource_id.strip("/").split("/") if segment]
    try:
        provider_index = segments.index("providers")
    except ValueError:
        return ""

    provider_segments = segments[provider_index + 1 :]
    if len(provider_segments) < 2:
        return ""

    namespace = provider_segments[0].lower()
    type_segments = [
        provider_segments[index].lower()
        for index in range(1, len(provider_segments), 2)
    ]
    return "/".join([namespace, *type_segments])


def _normalize_resource_group_name(resource_group_name: str) -> str:
    lowered_name = resource_group_name.lower()
    if "defaultresourcegroup" in lowered_name or lowered_name.startswith("default"):
        return "Shared default environment"
    if any(token in lowered_name for token in ("doc-intel", "docintel")):
        return "Current platform environment"
    if "shared" in lowered_name:
        return "Shared platform environment"
    if any(token in lowered_name for token in ("prod", "production")):
        return "Primary platform environment"
    if any(token in lowered_name for token in ("dev", "test", "stage", "staging")):
        return "Platform environment"
    return "Application environment"


def _normalize_resource_name(resource_name: str) -> str:
    lowered_name = resource_name.lower()
    if any(token in lowered_name for token in ("aoai", "openai")):
        return "OpenAI inference"
    if any(token in lowered_name for token in ("docint", "form", "ocr")) or lowered_name.startswith("di"):
        return "Document intelligence inference"
    if any(token in lowered_name for token in ("func", "api")):
        return "Public API application"
    if "admin" in lowered_name:
        return "Protected admin application"
    if lowered_name.startswith("asp") or "plan" in lowered_name:
        return "Application compute plan"
    if lowered_name.startswith("st") or "storage" in lowered_name:
        return "Platform storage"
    if any(token in lowered_name for token in ("sql", "db", "database")):
        return "Operational SQL database"
    if any(token in lowered_name for token in ("monitor", "insight", "log")):
        return "Platform monitoring"
    return "Platform resource"


def _resolve_subscription_id(settings: AppSettings) -> str | None:
    configured_subscription_id = (settings.public_cost_subscription_id or "").strip()
    if configured_subscription_id:
        return configured_subscription_id

    environment_subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID", "").strip()
    return environment_subscription_id or None


def _resolve_storage_connection_string(settings: AppSettings) -> str | None:
    configured_connection_string = os.getenv(
        "COST_HISTORY_STORAGE_CONNECTION_STRING",
        "",
    ).strip()
    if configured_connection_string:
        return configured_connection_string

    if settings.storage_connection_string:
        return settings.storage_connection_string

    fallback_connection_string = os.getenv("AzureWebJobsStorage", "").strip()
    return fallback_connection_string or None


def _resolve_container_name(settings: AppSettings) -> str:
    configured_container_name = os.getenv("COST_HISTORY_CONTAINER", "").strip()
    if configured_container_name:
        return configured_container_name

    return settings.public_cost_history_container_name or DEFAULT_COST_HISTORY_CONTAINER


def _resolve_history_directory(settings: AppSettings) -> Path:
    if _prefer_local_cost_history_directory(settings):
        return settings.public_cost_history_directory

    configured_directory = os.getenv("COST_HISTORY_DIRECTORY", "").strip()
    if configured_directory:
        return Path(configured_directory)

    return settings.public_cost_history_directory or DEFAULT_COST_HISTORY_DIRECTORY


def _prefer_local_cost_history_directory(settings: AppSettings) -> bool:
    return settings.public_cost_history_directory != DEFAULT_COST_HISTORY_DIRECTORY


def _archive_json_name(timestamp: datetime) -> Path:
    return Path(
        f"json/{timestamp:%Y/%m/%d}/public-cost-{timestamp:%Y%m%dT%H%M%SZ}.json"
    )


def _read_existing_history_rows(existing_csv: str) -> list[dict[str, str]]:
    if not existing_csv.strip():
        return []

    reader = csv.DictReader(io.StringIO(existing_csv))
    return [dict(row) for row in reader]


def _normalize_existing_history_rows(
    rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized_row = {
            field_name: row.get(field_name, "")
            for field_name in PUBLIC_COST_HISTORY_FIELDNAMES
        }
        normalized_row["top_resource_name"] = _sanitize_history_contributor_name(
            normalized_row.get("top_resource_name", ""),
            "ResourceId",
        )
        normalized_row["top_resource_group_name"] = _sanitize_history_contributor_name(
            normalized_row.get("top_resource_group_name", ""),
            "ResourceGroup",
        )
        normalized_rows.append(
            normalized_row
        )
    return normalized_rows


def _sanitize_history_contributor_name(value: Any, dimension_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    if " " in text:
        return text

    return _normalize_contributor_name(text, dimension_name)


def _serialize_history_rows(rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=PUBLIC_COST_HISTORY_FIELDNAMES,
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _build_daily_query(timeframe: str) -> dict[str, Any]:
    return {
        "dataset": {
            "aggregation": {
                "totalCost": {"function": "Sum", "name": "PreTaxCost"}
            },
            "granularity": "Daily",
        },
        "timeframe": timeframe,
        "type": "Usage",
    }


def _build_custom_daily_query(start_date: date, end_date: date) -> dict[str, Any]:
    return {
        "dataset": {
            "aggregation": {
                "totalCost": {"function": "Sum", "name": "PreTaxCost"}
            },
            "granularity": "Daily",
        },
        "timePeriod": {
            "from": _to_query_timestamp(start_date),
            "to": _to_query_timestamp(end_date),
        },
        "timeframe": "Custom",
        "type": "Usage",
    }


def _build_grouped_query(group_name: str) -> dict[str, Any]:
    return {
        "dataset": {
            "aggregation": {
                "totalCost": {"function": "Sum", "name": "PreTaxCost"}
            },
            "granularity": "None",
            "grouping": [{"name": group_name, "type": "Dimension"}],
        },
        "timeframe": "MonthToDate",
        "type": "Usage",
    }


def _resolve_currency(*row_sets: list[dict[str, Any]]) -> str | None:
    for rows in row_sets:
        currency = _extract_currency(rows)
        if currency:
            return currency
    return None


def _extract_currency(rows: list[dict[str, Any]]) -> str | None:
    for row in rows:
        currency = row.get("Currency") or row.get("currency")
        if currency:
            return str(currency)
    return None


def _read_cost_amount(row: dict[str, Any]) -> float:
    return _to_float(
        row.get("PreTaxCost")
        or row.get("totalCost")
        or row.get("costInBillingCurrency")
        or row.get("Cost")
    )


def _parse_usage_date(value: Any) -> date | None:
    if value is None:
        return None

    if isinstance(value, int):
        return datetime.strptime(str(value), "%Y%m%d").date()

    text = str(value)
    if text.isdigit() and len(text) == 8:
        return datetime.strptime(text, "%Y%m%d").date()

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        logging.warning("Could not parse Azure cost usage date value: %s", value)
        return None


def _to_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _to_query_timestamp(query_date: date) -> str:
    return datetime.combine(
        query_date,
        datetime_time.min,
        tzinfo=UTC,
    ).isoformat().replace("+00:00", "Z")


def _is_retryable_cost_error(error: Exception) -> bool:
    status_code = _extract_status_code(error)
    if status_code in RETRYABLE_COST_STATUS_CODES:
        return True

    error_text = str(error).lower()
    retryable_markers = (
        "429",
        "throttl",
        "temporarily unavailable",
        "too many requests",
    )
    return any(marker in error_text for marker in retryable_markers)


def _extract_status_code(error: Exception) -> int | None:
    for candidate in (getattr(error, "status_code", None), getattr(error, "status", None)):
        if isinstance(candidate, int):
            return candidate

    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    return None


def _resolve_retry_delay_seconds(
    error: Exception,
    attempt_number: int,
    settings: AppSettings,
) -> float:
    exponential_delay = min(
        settings.public_cost_query_max_delay_seconds,
        settings.public_cost_query_base_delay_seconds * (2 ** max(attempt_number - 1, 0)),
    )
    retry_after_seconds = _extract_retry_after_seconds(error)
    if retry_after_seconds is None:
        return exponential_delay

    return min(
        settings.public_cost_query_max_delay_seconds,
        max(exponential_delay, retry_after_seconds),
    )


def _extract_retry_after_seconds(error: Exception) -> float | None:
    headers = _extract_response_headers(error)
    if not headers:
        return None

    retry_after_value = (
        headers.get("retry-after")
        or headers.get("retry-after-ms")
        or headers.get("x-ms-retry-after-ms")
        or headers.get("x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after")
    )
    if retry_after_value is None:
        return None

    normalized_value = str(retry_after_value).strip()
    if not normalized_value:
        return None

    if "date" in normalized_value.lower():
        return None

    try:
        delay_value = float(normalized_value)
    except ValueError:
        return None

    if normalized_value.endswith("ms") or "retry-after-ms" in "".join(headers.keys()):
        return max(0.0, delay_value / 1000.0)

    return max(0.0, delay_value)


def _extract_response_headers(error: Exception) -> dict[str, str]:
    response = getattr(error, "response", None)
    raw_headers = getattr(response, "headers", None)
    if raw_headers is None or not hasattr(raw_headers, "items"):
        return {}

    return {str(key).lower(): str(value) for key, value in raw_headers.items()}


def _isoformat(timestamp: datetime) -> str:
    normalized_timestamp = timestamp.astimezone(UTC)
    return normalized_timestamp.isoformat().replace("+00:00", "Z")


__all__ = ["refresh_public_cost_history"]
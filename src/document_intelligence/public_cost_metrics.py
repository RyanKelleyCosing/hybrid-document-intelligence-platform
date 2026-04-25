"""Public-safe cost history readers for the public cost dashboard."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobClient
from pydantic import BaseModel, ConfigDict, Field

from document_intelligence.settings import AppSettings

DEFAULT_COST_HISTORY_CONTAINER = "cost-optimizer-history"
DEFAULT_COST_HISTORY_DIRECTORY = Path("outputs") / "cost-report" / "history"
LATEST_COST_JSON_NAME = "json/latest.json"
LATEST_COST_CSV_NAME = "csv/daily-cost-history.csv"
PUBLIC_COST_COLLECTION_MODE = "Durable public-safe cost history"


class PublicCostContributor(BaseModel):
    """One ranked cost contributor exposed to the public dashboard."""

    model_config = ConfigDict(str_strip_whitespace=True)

    amount: float
    name: str = Field(min_length=1, max_length=160)


class PublicCostDailyPoint(BaseModel):
    """One daily spend point shown in the public dashboard."""

    model_config = ConfigDict(str_strip_whitespace=True)

    amount: float
    usage_date: date


class PublicCostTrendPoint(BaseModel):
    """One aggregated trend period rendered in the public dashboard."""

    model_config = ConfigDict(str_strip_whitespace=True)

    amount: float
    label: str = Field(min_length=1, max_length=64)
    period_end: date
    period_start: date


class PublicCostAnomaly(BaseModel):
    """One unusual retained daily move highlighted on the public dashboard."""

    model_config = ConfigDict(str_strip_whitespace=True)

    amount: float
    baseline_amount: float
    delta_amount: float
    direction: Literal["drop", "spike"]
    severity: Literal["high", "medium"]
    summary: str = Field(min_length=1, max_length=240)
    usage_date: date


class PublicCostForecast(BaseModel):
    """A simple month-end run-rate forecast derived from retained daily history."""

    model_config = ConfigDict(str_strip_whitespace=True)

    based_on_days: int = Field(ge=1, le=31)
    projected_additional_cost: float
    projected_month_end_cost: float
    remaining_days_in_period: int = Field(ge=0, le=31)
    trailing_daily_average: float


class PublicCostMetricsSummary(BaseModel):
    """Sanitized cost summary returned by the public cost API."""

    model_config = ConfigDict(str_strip_whitespace=True)

    anomalies: tuple[PublicCostAnomaly, ...] = ()
    collection_mode: str = Field(min_length=1, max_length=80)
    collection_window: str = Field(min_length=1, max_length=240)
    currency: str | None = Field(default=None, max_length=16)
    daily_cost_trend: tuple[PublicCostTrendPoint, ...] = ()
    day_over_day_delta: float
    forecast: PublicCostForecast | None = None
    generated_at_utc: datetime
    history_row_count: int = Field(ge=0)
    history_source: str = Field(min_length=1, max_length=120)
    month_to_date_cost: float
    monthly_cost_trend: tuple[PublicCostTrendPoint, ...] = ()
    previous_day_cost: float
    recent_daily_costs: tuple[PublicCostDailyPoint, ...] = ()
    today_cost: float
    top_resource_groups: tuple[PublicCostContributor, ...] = ()
    top_resources: tuple[PublicCostContributor, ...] = ()
    top_service_families: tuple[PublicCostContributor, ...] = ()
    week_to_date_cost: float
    weekly_cost_trend: tuple[PublicCostTrendPoint, ...] = ()
    year_to_date_cost: float
    yesterday_cost: float


@dataclass(frozen=True)
class _ResolvedCostHistoryArtifacts:
    """Latest persisted cost snapshot and CSV history payloads."""

    history_csv_text: str
    history_source: str
    latest_snapshot_payload: dict[str, Any]


@dataclass(frozen=True)
class _CostSanitizers:
    """Internal contributor sanitizers shared with the refresh pipeline."""

    deduplicate_name: Callable[[str, dict[str, int]], str]
    normalize_name: Callable[[str, str], str]
    sanitize_history_name: Callable[[Any, str], str]


@dataclass(frozen=True)
class _ParsedHistoryRow:
    """One parsed retained CSV row used for fallback trend derivation."""

    currency: str | None
    day_over_day_delta: float
    generated_at: datetime
    month_to_date_cost: float
    previous_day_cost: float
    today_cost: float | None
    week_to_date_cost: float | None
    year_to_date_cost: float | None
    yesterday_cost: float


def load_public_cost_metrics_summary(
    settings: AppSettings,
) -> PublicCostMetricsSummary | None:
    """Load the latest public-safe cost summary from durable history."""

    artifacts = _load_cost_history_artifacts(settings)
    if artifacts is None:
        return None

    history_rows = _parse_history_rows(artifacts.history_csv_text)
    latest_snapshot = artifacts.latest_snapshot_payload
    cost_summary = _read_mapping(latest_snapshot.get("costSummary"))
    history_row = _read_mapping(latest_snapshot.get("historyRow"))
    generated_at_utc = _parse_datetime(
        _first_present(
            latest_snapshot.get("generatedAt"),
            history_row.get("generated_at"),
        )
    )

    latest_history_rows = _latest_history_rows_by_snapshot_date(history_rows)
    latest_history_row = latest_history_rows[-1] if latest_history_rows else None
    prior_history_row = latest_history_rows[-2] if len(latest_history_rows) >= 2 else None
    snapshot_date = generated_at_utc.date()
    complete_daily_points = _build_complete_daily_points(latest_history_rows)

    month_to_date_cost = _coerce_float(
        _first_present(
            cost_summary.get("month_to_date_cost"),
            history_row.get("month_to_date_cost"),
            latest_history_row.month_to_date_cost if latest_history_row else None,
        )
    )
    today_cost = _resolve_float_value(
        _coerce_optional_float(cost_summary.get("today_cost")),
        latest_history_row.today_cost if latest_history_row else None,
        _derive_today_cost(month_to_date_cost, latest_history_row, prior_history_row),
    )
    all_daily_points = _extend_daily_points_with_today(
        complete_daily_points,
        snapshot_date,
        today_cost,
    )
    daily_cost_trend = (
        _parse_trend_points(cost_summary.get("daily_cost_trend"))
        or _build_daily_trend_points(all_daily_points)
    )
    daily_signal_points = _trend_points_to_daily_points(daily_cost_trend)
    anomalies = _build_cost_anomalies(daily_signal_points)
    forecast = _build_cost_forecast(
        daily_signal_points,
        snapshot_date,
        month_to_date_cost,
    )
    week_to_date_cost = _resolve_float_value(
        _coerce_optional_float(cost_summary.get("week_to_date_cost")),
        latest_history_row.week_to_date_cost if latest_history_row else None,
        _sum_daily_points_in_range(
            all_daily_points,
            snapshot_date - timedelta(days=snapshot_date.weekday()),
            snapshot_date,
        ),
    )
    year_to_date_cost = _resolve_float_value(
        _coerce_optional_float(cost_summary.get("year_to_date_cost")),
        latest_history_row.year_to_date_cost if latest_history_row else None,
        _sum_daily_points_in_range(
            all_daily_points,
            date(snapshot_date.year, 1, 1),
            snapshot_date,
        ),
    )

    return PublicCostMetricsSummary(
        anomalies=anomalies,
        collection_mode=PUBLIC_COST_COLLECTION_MODE,
        collection_window=(
            "Latest retained snapshot plus "
            f"{len(history_rows)} persisted CSV history rows, normalized into daily, "
            "weekly, and monthly trend slices."
        ),
        currency=_normalize_optional_string(
            _first_present(
                cost_summary.get("currency"),
                history_row.get("currency"),
                latest_history_row.currency if latest_history_row else None,
            )
        ),
        daily_cost_trend=daily_cost_trend,
        day_over_day_delta=_coerce_float(
            _first_present(
                cost_summary.get("day_over_day_delta"),
                history_row.get("day_over_day_delta"),
                latest_history_row.day_over_day_delta if latest_history_row else None,
            )
        ),
        forecast=forecast,
        generated_at_utc=generated_at_utc,
        history_row_count=len(history_rows),
        history_source=artifacts.history_source,
        month_to_date_cost=month_to_date_cost,
        monthly_cost_trend=(
            _parse_trend_points(cost_summary.get("monthly_cost_trend"))
            or _build_monthly_trend_points(all_daily_points)
        ),
        previous_day_cost=_coerce_float(
            _first_present(
                cost_summary.get("previous_day_cost"),
                history_row.get("previous_day_cost"),
                latest_history_row.previous_day_cost if latest_history_row else None,
            )
        ),
        recent_daily_costs=(
            _parse_daily_points(cost_summary.get("recent_daily_costs"))
            or tuple(complete_daily_points[-3:])
        ),
        today_cost=today_cost,
        top_resource_groups=_parse_contributors(cost_summary.get("top_resource_groups")),
        top_resources=_parse_contributors(cost_summary.get("top_resources")),
        top_service_families=_parse_contributors(
            cost_summary.get("top_service_families")
        ),
        week_to_date_cost=week_to_date_cost,
        weekly_cost_trend=(
            _parse_trend_points(cost_summary.get("weekly_cost_trend"))
            or _build_weekly_trend_points(all_daily_points)
        ),
        year_to_date_cost=year_to_date_cost,
        yesterday_cost=_coerce_float(
            _first_present(
                cost_summary.get("yesterday_cost"),
                history_row.get("yesterday_cost"),
                latest_history_row.yesterday_cost if latest_history_row else None,
            )
        ),
    )


def load_public_cost_latest_json(settings: AppSettings) -> dict[str, Any] | None:
    """Load the latest public-safe cost snapshot payload."""

    artifacts = _load_cost_history_artifacts(settings)
    if artifacts is None:
        return None
    return artifacts.latest_snapshot_payload


def load_public_cost_history_csv(settings: AppSettings) -> str | None:
    """Load the retained public-safe cost CSV payload."""

    artifacts = _load_cost_history_artifacts(settings)
    if artifacts is None:
        return None
    return artifacts.history_csv_text


def _load_cost_history_artifacts(
    settings: AppSettings,
) -> _ResolvedCostHistoryArtifacts | None:
    if _prefer_local_cost_history_directory(settings):
        local_artifacts = _load_local_cost_history_artifacts(
            _resolve_local_history_directory(settings),
            history_source="Retained public cost history",
        )
        if local_artifacts is not None:
            return local_artifacts
    else:
        blob_artifacts = _load_blob_cost_history_artifacts(settings)
        if blob_artifacts is not None:
            return blob_artifacts

        local_artifacts = _load_local_cost_history_artifacts(
            _resolve_local_history_directory(settings),
            history_source="Retained public cost history",
        )
        if local_artifacts is not None:
            return local_artifacts

    fallback_directory = _find_fallback_history_directory()
    if fallback_directory is None:
        return None

    return _load_local_cost_history_artifacts(
        fallback_directory,
        history_source="Bundled retained cost history",
    )


def _resolve_local_history_directory(settings: AppSettings) -> Path:
    if _prefer_local_cost_history_directory(settings):
        return settings.public_cost_history_directory

    configured_directory = os.getenv("COST_HISTORY_DIRECTORY", "").strip()
    if configured_directory:
        return Path(configured_directory)

    return settings.public_cost_history_directory or DEFAULT_COST_HISTORY_DIRECTORY


def _prefer_local_cost_history_directory(settings: AppSettings) -> bool:
    configured_directory = settings.public_cost_history_directory
    return configured_directory != DEFAULT_COST_HISTORY_DIRECTORY


def _resolve_blob_connection_string(settings: AppSettings) -> str | None:
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


def _resolve_blob_container_name(settings: AppSettings) -> str:
    configured_container_name = os.getenv("COST_HISTORY_CONTAINER", "").strip()
    if configured_container_name:
        return configured_container_name

    return settings.public_cost_history_container_name or DEFAULT_COST_HISTORY_CONTAINER


def _load_local_cost_history_artifacts(
    history_directory: Path,
    *,
    history_source: str,
) -> _ResolvedCostHistoryArtifacts | None:
    latest_json_path = history_directory / LATEST_COST_JSON_NAME
    history_csv_path = history_directory / LATEST_COST_CSV_NAME
    if not latest_json_path.exists() or not history_csv_path.exists():
        return None

    return _ResolvedCostHistoryArtifacts(
        history_csv_text=_sanitize_history_csv_text(
            history_csv_path.read_text(encoding="utf-8")
        ),
        history_source=history_source,
        latest_snapshot_payload=_sanitize_snapshot_payload(_read_snapshot_payload(
            latest_json_path.read_text(encoding="utf-8")
        )),
    )


def _load_blob_cost_history_artifacts(
    settings: AppSettings,
) -> _ResolvedCostHistoryArtifacts | None:
    connection_string = _resolve_blob_connection_string(settings)
    if connection_string is None:
        return None

    container_name = _resolve_blob_container_name(settings)
    latest_snapshot_text = _download_blob_text(
        connection_string,
        container_name,
        LATEST_COST_JSON_NAME,
    )
    history_csv_text = _download_blob_text(
        connection_string,
        container_name,
        LATEST_COST_CSV_NAME,
    )
    if latest_snapshot_text is None or history_csv_text is None:
        return None

    return _ResolvedCostHistoryArtifacts(
        history_csv_text=_sanitize_history_csv_text(history_csv_text),
        history_source="Retained public cost history",
        latest_snapshot_payload=_sanitize_snapshot_payload(
            _read_snapshot_payload(latest_snapshot_text)
        ),
    )


def _download_blob_text(
    connection_string: str,
    container_name: str,
    blob_name: str,
) -> str | None:
    blob_client = BlobClient.from_connection_string(
        conn_str=connection_string,
        container_name=container_name,
        blob_name=blob_name,
    )
    try:
        payload_bytes = blob_client.download_blob().readall()
    except ResourceNotFoundError:
        return None

    return payload_bytes.decode("utf-8")


def _find_fallback_history_directory() -> Path | None:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = sorted(
        repo_root.glob("outputs/**/cost-report*/history/json/latest.json"),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )

    for latest_snapshot_path in candidates:
        history_directory = latest_snapshot_path.parents[1]
        if (history_directory / LATEST_COST_CSV_NAME).exists():
            return history_directory

    return None


def _read_snapshot_payload(payload_text: str) -> dict[str, Any]:
    parsed_payload = json.loads(payload_text)
    if isinstance(parsed_payload, dict):
        return parsed_payload

    logging.warning("Latest public cost snapshot was not a JSON object.")
    return {}


def _load_cost_sanitizers() -> _CostSanitizers:
    from document_intelligence import public_cost_refresh as public_cost_refresh_module

    return _CostSanitizers(
        deduplicate_name=public_cost_refresh_module._deduplicate_contributor_name,
        normalize_name=public_cost_refresh_module._normalize_contributor_name,
        sanitize_history_name=public_cost_refresh_module._sanitize_history_contributor_name,
    )


def _sanitize_snapshot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}

    sanitizers = _load_cost_sanitizers()
    sanitized_payload = dict(payload)
    cost_summary = _read_mapping(payload.get("costSummary"))
    if cost_summary:
        sanitized_cost_summary = dict(cost_summary)
        sanitized_cost_summary["top_resources"] = _sanitize_contributor_collection(
            cost_summary.get("top_resources"),
            dimension_name="ResourceId",
            sanitizers=sanitizers,
        )
        sanitized_cost_summary[
            "top_resource_groups"
        ] = _sanitize_contributor_collection(
            cost_summary.get("top_resource_groups"),
            dimension_name="ResourceGroup",
            sanitizers=sanitizers,
        )
        sanitized_payload["costSummary"] = sanitized_cost_summary

    history_row = _read_mapping(payload.get("historyRow"))
    if history_row:
        sanitized_history_row = dict(history_row)
        if "top_resource_name" in sanitized_history_row:
            sanitized_history_row["top_resource_name"] = (
                sanitizers.sanitize_history_name(
                    sanitized_history_row.get("top_resource_name"),
                    "ResourceId",
                )
            )
        if "top_resource_group_name" in sanitized_history_row:
            sanitized_history_row["top_resource_group_name"] = (
                sanitizers.sanitize_history_name(
                    sanitized_history_row.get("top_resource_group_name"),
                    "ResourceGroup",
                )
            )
        sanitized_payload["historyRow"] = sanitized_history_row

    return sanitized_payload


def _sanitize_contributor_collection(
    value: Any,
    *,
    dimension_name: str,
    sanitizers: _CostSanitizers,
) -> Any:
    if not isinstance(value, list):
        return value

    label_counts: dict[str, int] = {}
    sanitized_items: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        sanitized_item = dict(item)
        contributor_name = _normalize_optional_string(item.get("name"))
        if contributor_name is not None:
            contributor_name = sanitizers.normalize_name(
                contributor_name,
                dimension_name,
            )
            if contributor_name:
                sanitized_item["name"] = sanitizers.deduplicate_name(
                    contributor_name,
                    label_counts,
                )

        sanitized_items.append(sanitized_item)

    return sanitized_items


def _sanitize_history_csv_text(history_csv_text: str) -> str:
    if not history_csv_text.strip():
        return history_csv_text

    reader = csv.DictReader(io.StringIO(history_csv_text))
    fieldnames = list(reader.fieldnames or [])
    if not fieldnames:
        return history_csv_text

    sanitizers = _load_cost_sanitizers()
    sanitized_rows: list[dict[str, Any]] = []
    for row in reader:
        sanitized_row = dict(row)
        if "top_resource_name" in sanitized_row:
            sanitized_row["top_resource_name"] = sanitizers.sanitize_history_name(
                sanitized_row.get("top_resource_name"),
                "ResourceId",
            )
        if "top_resource_group_name" in sanitized_row:
            sanitized_row["top_resource_group_name"] = sanitizers.sanitize_history_name(
                sanitized_row.get("top_resource_group_name"),
                "ResourceGroup",
            )
        sanitized_rows.append(sanitized_row)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(sanitized_rows)
    return buffer.getvalue()


def _read_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _parse_history_rows(history_csv_text: str) -> tuple[_ParsedHistoryRow, ...]:
    reader = csv.DictReader(io.StringIO(history_csv_text))
    parsed_rows: list[_ParsedHistoryRow] = []

    for row in reader:
        parsed_rows.append(
            _ParsedHistoryRow(
                currency=_normalize_optional_string(row.get("currency")),
                day_over_day_delta=_coerce_float(row.get("day_over_day_delta")),
                generated_at=_parse_datetime(row.get("generated_at")),
                month_to_date_cost=_coerce_float(row.get("month_to_date_cost")),
                previous_day_cost=_coerce_float(row.get("previous_day_cost")),
                today_cost=_coerce_optional_float(row.get("today_cost")),
                week_to_date_cost=_coerce_optional_float(row.get("week_to_date_cost")),
                year_to_date_cost=_coerce_optional_float(row.get("year_to_date_cost")),
                yesterday_cost=_coerce_float(row.get("yesterday_cost")),
            )
        )

    return tuple(sorted(parsed_rows, key=lambda item: item.generated_at))


def _parse_contributors(value: Any) -> tuple[PublicCostContributor, ...]:
    if not isinstance(value, list):
        return ()

    parsed_contributors: list[PublicCostContributor] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        name = _normalize_optional_string(item.get("name"))
        if name is None:
            continue

        parsed_contributors.append(
            PublicCostContributor(
                amount=_coerce_float(item.get("amount")),
                name=name,
            )
        )

    return tuple(parsed_contributors)


def _parse_daily_points(value: Any) -> tuple[PublicCostDailyPoint, ...]:
    if not isinstance(value, list):
        return ()

    parsed_points: list[PublicCostDailyPoint] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        usage_date = item.get("usage_date")
        if not isinstance(usage_date, str) or not usage_date.strip():
            continue

        parsed_points.append(
            PublicCostDailyPoint(
                amount=_coerce_float(item.get("amount")),
                usage_date=date.fromisoformat(usage_date),
            )
        )

    return tuple(parsed_points)


def _parse_trend_points(value: Any) -> tuple[PublicCostTrendPoint, ...]:
    if not isinstance(value, list):
        return ()

    parsed_points: list[PublicCostTrendPoint] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        label = _normalize_optional_string(item.get("label"))
        period_start = _normalize_optional_string(item.get("period_start"))
        period_end = _normalize_optional_string(item.get("period_end"))
        if label is None or period_start is None or period_end is None:
            continue

        parsed_points.append(
            PublicCostTrendPoint(
                amount=_coerce_float(item.get("amount")),
                label=label,
                period_end=date.fromisoformat(period_end),
                period_start=date.fromisoformat(period_start),
            )
        )

    return tuple(parsed_points)


def _latest_history_rows_by_snapshot_date(
    history_rows: tuple[_ParsedHistoryRow, ...],
) -> tuple[_ParsedHistoryRow, ...]:
    rows_by_date: dict[date, _ParsedHistoryRow] = {}

    for history_row in history_rows:
        snapshot_date = history_row.generated_at.date()
        existing_row = rows_by_date.get(snapshot_date)
        if existing_row is None or history_row.generated_at > existing_row.generated_at:
            rows_by_date[snapshot_date] = history_row

    return tuple(sorted(rows_by_date.values(), key=lambda item: item.generated_at))


def _build_complete_daily_points(
    history_rows: tuple[_ParsedHistoryRow, ...],
) -> tuple[PublicCostDailyPoint, ...]:
    daily_points: list[PublicCostDailyPoint] = []

    for history_row in history_rows:
        usage_date = history_row.generated_at.date() - timedelta(days=1)
        daily_points.append(
            PublicCostDailyPoint(
                amount=history_row.yesterday_cost,
                usage_date=usage_date,
            )
        )

    return tuple(sorted(daily_points, key=lambda item: item.usage_date))


def _extend_daily_points_with_today(
    daily_points: tuple[PublicCostDailyPoint, ...],
    snapshot_date: date,
    today_cost: float,
) -> tuple[PublicCostDailyPoint, ...]:
    points_by_date = {point.usage_date: point for point in daily_points}
    points_by_date[snapshot_date] = PublicCostDailyPoint(
        amount=today_cost,
        usage_date=snapshot_date,
    )

    return tuple(sorted(points_by_date.values(), key=lambda item: item.usage_date))


def _derive_today_cost(
    month_to_date_cost: float,
    latest_history_row: _ParsedHistoryRow | None,
    prior_history_row: _ParsedHistoryRow | None,
) -> float:
    if latest_history_row is None:
        return 0.0

    latest_date = latest_history_row.generated_at.date()
    if (
        prior_history_row is not None
        and prior_history_row.generated_at.date() < latest_date
        and prior_history_row.generated_at.year == latest_history_row.generated_at.year
        and prior_history_row.generated_at.month == latest_history_row.generated_at.month
    ):
        return max(0.0, month_to_date_cost - prior_history_row.month_to_date_cost)

    if latest_date.day == 1:
        return month_to_date_cost

    return 0.0


def _sum_daily_points_in_range(
    daily_points: tuple[PublicCostDailyPoint, ...],
    range_start: date,
    range_end: date,
) -> float:
    return sum(
        point.amount
        for point in daily_points
        if range_start <= point.usage_date <= range_end
    )


def _build_daily_trend_points(
    daily_points: tuple[PublicCostDailyPoint, ...],
) -> tuple[PublicCostTrendPoint, ...]:
    return tuple(
        PublicCostTrendPoint(
            amount=point.amount,
            label=point.usage_date.strftime("%b %d"),
            period_end=point.usage_date,
            period_start=point.usage_date,
        )
        for point in daily_points[-7:]
    )


def _build_weekly_trend_points(
    daily_points: tuple[PublicCostDailyPoint, ...],
) -> tuple[PublicCostTrendPoint, ...]:
    grouped_points = _group_daily_points(
        daily_points,
        key_builder=lambda usage_date: usage_date - timedelta(days=usage_date.weekday()),
    )
    return tuple(
        PublicCostTrendPoint(
            amount=amount,
            label=f"Week of {period_start.strftime('%b %d')}",
            period_end=period_end,
            period_start=period_start,
        )
        for period_start, period_end, amount in grouped_points[-6:]
    )


def _build_monthly_trend_points(
    daily_points: tuple[PublicCostDailyPoint, ...],
) -> tuple[PublicCostTrendPoint, ...]:
    grouped_points = _group_daily_points(
        daily_points,
        key_builder=lambda usage_date: date(usage_date.year, usage_date.month, 1),
    )
    return tuple(
        PublicCostTrendPoint(
            amount=amount,
            label=period_start.strftime("%b %Y"),
            period_end=period_end,
            period_start=period_start,
        )
        for period_start, period_end, amount in grouped_points[-6:]
    )


def _build_cost_anomalies(
    daily_points: tuple[PublicCostDailyPoint, ...],
) -> tuple[PublicCostAnomaly, ...]:
    anomalies: list[PublicCostAnomaly] = []

    for index in range(3, len(daily_points)):
        trailing_points = daily_points[index - 3 : index]
        baseline_amount = sum(point.amount for point in trailing_points) / len(
            trailing_points
        )
        if baseline_amount <= 0:
            continue

        current_point = daily_points[index]
        delta_amount = current_point.amount - baseline_amount
        absolute_delta = abs(delta_amount)
        medium_threshold = max(5.0, baseline_amount * 0.35)
        high_threshold = max(10.0, baseline_amount * 0.6)
        if absolute_delta < medium_threshold:
            continue

        direction: Literal["drop", "spike"] = (
            "spike" if delta_amount > 0 else "drop"
        )
        severity: Literal["high", "medium"] = (
            "high" if absolute_delta >= high_threshold else "medium"
        )
        delta_percentage = round((absolute_delta / baseline_amount) * 100)
        comparison_label = "above" if direction == "spike" else "below"
        anomalies.append(
            PublicCostAnomaly(
                amount=current_point.amount,
                baseline_amount=baseline_amount,
                delta_amount=delta_amount,
                direction=direction,
                severity=severity,
                summary=(
                    f"{current_point.usage_date.isoformat()} ran {delta_percentage}% "
                    f"{comparison_label} the trailing {len(trailing_points)}-day average."
                ),
                usage_date=current_point.usage_date,
            )
        )

    return tuple(anomalies[-3:])


def _build_cost_forecast(
    daily_points: tuple[PublicCostDailyPoint, ...],
    snapshot_date: date,
    month_to_date_cost: float,
) -> PublicCostForecast | None:
    if not daily_points:
        return None

    trailing_points = daily_points[-min(7, len(daily_points)) :]
    based_on_days = len(trailing_points)
    trailing_daily_average = sum(point.amount for point in trailing_points) / based_on_days
    remaining_days_in_period = max(0, _days_in_month(snapshot_date) - snapshot_date.day)
    projected_additional_cost = trailing_daily_average * remaining_days_in_period

    return PublicCostForecast(
        based_on_days=based_on_days,
        projected_additional_cost=projected_additional_cost,
        projected_month_end_cost=month_to_date_cost + projected_additional_cost,
        remaining_days_in_period=remaining_days_in_period,
        trailing_daily_average=trailing_daily_average,
    )


def _trend_points_to_daily_points(
    trend_points: tuple[PublicCostTrendPoint, ...],
) -> tuple[PublicCostDailyPoint, ...]:
    return tuple(
        PublicCostDailyPoint(
            amount=point.amount,
            usage_date=point.period_end,
        )
        for point in trend_points
        if point.period_start == point.period_end
    )


def _group_daily_points(
    daily_points: tuple[PublicCostDailyPoint, ...],
    *,
    key_builder: Callable[[date], date],
) -> list[tuple[date, date, float]]:
    grouped_points: dict[date, tuple[date, float]] = {}

    for point in daily_points:
        period_start = key_builder(point.usage_date)
        period_end, total_amount = grouped_points.get(
            period_start,
            (point.usage_date, 0.0),
        )
        grouped_points[period_start] = (
            max(period_end, point.usage_date),
            total_amount + point.amount,
        )

    return [
        (period_start, period_end, amount)
        for period_start, (period_end, amount) in sorted(grouped_points.items())
    ]


def _days_in_month(value: date) -> int:
    period_start = date(value.year, value.month, 1)
    if value.month == 12:
        next_period_start = date(value.year + 1, 1, 1)
    else:
        next_period_start = date(value.year, value.month + 1, 1)

    return (next_period_start - period_start).days


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, str) and value.strip():
        normalized_value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized_value).astimezone(UTC)

    return datetime.now(UTC)


def _normalize_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized_value = value.strip()
    return normalized_value or None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _resolve_float_value(*values: float | None) -> float:
    for value in values:
        if value is not None:
            return value
    return 0.0


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


__all__ = [
    "DEFAULT_COST_HISTORY_CONTAINER",
    "DEFAULT_COST_HISTORY_DIRECTORY",
    "LATEST_COST_CSV_NAME",
    "LATEST_COST_JSON_NAME",
    "PublicCostAnomaly",
    "PublicCostContributor",
    "PublicCostDailyPoint",
    "PublicCostForecast",
    "PublicCostMetricsSummary",
    "PublicCostTrendPoint",
    "load_public_cost_history_csv",
    "load_public_cost_latest_json",
    "load_public_cost_metrics_summary",
]
"""Normalized data model shared across all sources and the renderer.

Every source returns (partial) data shaped into these structures so the
orchestrator can merge them with a fixed priority and the dashboard can read a
single, predictable JSON schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string (seconds precision, 'Z')."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class SstReading:
    """A single sea-surface-temperature value with provenance."""
    value_c: float | None = None
    source: str | None = None
    time: str | None = None  # ISO-8601 of the observation/analysis

    def is_present(self) -> bool:
        return self.value_c is not None


@dataclass
class ForecastSeries:
    """Hourly forecast arrays. All lists are parallel to ``time``.

    Missing variables stay as empty lists so the dashboard can feature-detect.
    """
    source: str | None = None
    time: list[str] = field(default_factory=list)
    air_temp_c: list[float | None] = field(default_factory=list)
    wind_speed_kn: list[float | None] = field(default_factory=list)
    wind_gust_kn: list[float | None] = field(default_factory=list)
    wind_dir_deg: list[float | None] = field(default_factory=list)
    weather_code: list[int | None] = field(default_factory=list)
    precip_mm: list[float | None] = field(default_factory=list)
    wave_height_m: list[float | None] = field(default_factory=list)
    wave_period_s: list[float | None] = field(default_factory=list)
    wave_dir_deg: list[float | None] = field(default_factory=list)
    sea_temp_c: list[float | None] = field(default_factory=list)

    def is_present(self) -> bool:
        return len(self.time) > 0


@dataclass
class SourceStatus:
    """Health record for one source on one run."""
    name: str
    ok: bool
    message: str = ""
    fetched_at: str = field(default_factory=utcnow_iso)


@dataclass
class Advisory:
    """A textual marine warning / bulletin (e.g. from HNMS)."""
    source: str
    text: str
    time: str = field(default_factory=utcnow_iso)


@dataclass
class ClimateContext:
    """Basin-wide SST anomaly/trend context (e.g. CEAMed). Not per-island live."""
    source: str | None = None
    anomaly_c: float | None = None
    reference: str | None = None  # description of the baseline
    period: str | None = None     # e.g. "2026-05" (monthly)
    note: str | None = None


@dataclass
class IslandReport:
    """Everything known about one island after merging all sources."""
    name: str
    slug: str
    region: str
    lat: float
    lon: float
    updated_at: str = field(default_factory=utcnow_iso)
    sst: SstReading = field(default_factory=SstReading)
    forecast: ForecastSeries = field(default_factory=ForecastSeries)
    advisories: list[Advisory] = field(default_factory=list)
    climate: ClimateContext = field(default_factory=ClimateContext)
    sources: list[SourceStatus] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

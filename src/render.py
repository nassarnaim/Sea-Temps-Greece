"""Write normalized reports to JSON and maintain rolling history.

Outputs (under data/, all committed for persistence + reuse):
  data/islands/<slug>.json   full per-island report (forecast series included)
  data/history/<slug>.json   rolling SST history for trend sparklines
  data/latest.json           compact summary of all islands + source health

Everything under data/ is also mirrored into site/data/ so the static
dashboard can fetch it locally and on GitHub Pages.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import DATA_DIR, SITE_DIR, Settings
from .model import IslandReport, SourceStatus, utcnow_iso


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _first(seq, default=None):
    for v in seq:
        if v is not None:
            return v
    return default


def _current_conditions(report: IslandReport) -> dict:
    """Pull the first available forecast hour as 'now-ish' conditions."""
    fc = report.forecast
    return {
        "air_temp_c": _first(fc.air_temp_c),
        "wind_speed_kn": _first(fc.wind_speed_kn),
        "wind_gust_kn": _first(fc.wind_gust_kn),
        "wind_dir_deg": _first(fc.wind_dir_deg),
        "weather_code": _first(fc.weather_code),
        "wave_height_m": _first(fc.wave_height_m),
        "wave_period_s": _first(fc.wave_period_s),
    }


def _update_history(slug: str, sst_value, history_days: int) -> None:
    path = DATA_DIR / "history" / f"{slug}.json"
    history = []
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    if sst_value is not None:
        history.append({"time": utcnow_iso(), "sst_c": sst_value})
    cutoff = datetime.now(timezone.utc) - timedelta(days=history_days)
    pruned = []
    for entry in history:
        try:
            t = datetime.fromisoformat(entry["time"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if t >= cutoff:
            pruned.append(entry)
    _write_json(path, pruned)


def write_reports(reports: list[IslandReport], settings: Settings, run_sources: list[SourceStatus] | None = None) -> dict:
    generated_at = utcnow_iso()
    summary_islands = []

    for report in reports:
        _write_json(DATA_DIR / "islands" / f"{report.slug}.json", report.to_dict())
        _update_history(report.slug, report.sst.value_c, settings.history_days)
        summary_islands.append(
            {
                "name": report.name,
                "slug": report.slug,
                "region": report.region,
                "lat": report.lat,
                "lon": report.lon,
                "updated_at": report.updated_at,
                "sst": {
                    "value_c": report.sst.value_c,
                    "source": report.sst.source,
                    "time": report.sst.time,
                },
                "conditions": _current_conditions(report),
                "climate": {
                    "anomaly_c": report.climate.anomaly_c,
                    "source": report.climate.source,
                    "note": report.climate.note,
                },
                "advisories": [a.text for a in report.advisories],
                "sources": [
                    {"name": s.name, "ok": s.ok, "message": s.message} for s in report.sources
                ],
            }
        )

    latest = {
        "generated_at": generated_at,
        "island_count": len(reports),
        "islands": summary_islands,
        "run_sources": [
            {"name": s.name, "ok": s.ok, "message": s.message} for s in (run_sources or [])
        ],
    }
    _write_json(DATA_DIR / "latest.json", latest)

    _mirror_to_site()
    return latest


def _mirror_to_site() -> None:
    """Copy data/ into site/data/ so the static dashboard can fetch it."""
    dest = SITE_DIR / "data"
    if dest.exists():
        shutil.rmtree(dest)
    if DATA_DIR.exists():
        shutil.copytree(DATA_DIR, dest)

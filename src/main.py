"""Orchestrator: fetch every source for every island, merge, render.

Run with:  python -m src.main

Source order matters for the merge:
  1. openmeteo  — backbone forecast + fallback SST (always runs)
  2. cmems      — authoritative SST, overrides backbone (needs secrets)
  3. poseidon   — Greek-regional SST/forecast + advisory (best-effort)
  4. hnms       — marine bulletin advisory (best-effort)
  5. ceamed     — basin-wide SST anomaly context (best-effort)

Every source is wrapped so one failure never aborts the run.
"""
from __future__ import annotations

import sys

from .config import Island, load_settings
from .model import IslandReport, SourceStatus
from .render import write_reports
from .sources.base import Source
from .sources.ceamed import CeamedSource
from .sources.cmems import CmemsSource
from .sources.hnms import HnmsSource
from .sources.openmeteo import OpenMeteoSource
from .sources.poseidon import PoseidonSource


def build_sources(forecast_days: int) -> list[Source]:
    return [
        OpenMeteoSource(forecast_days=forecast_days),
        CmemsSource(),
        PoseidonSource(),
        HnmsSource(),
        CeamedSource(),
    ]


def process_island(island: Island, sources: list[Source]) -> IslandReport:
    report = IslandReport(
        name=island.name,
        slug=island.slug,
        region=island.region,
        lat=island.land_lat,
        lon=island.land_lon,
    )
    for source in sources:
        status = source.run(island, report)
        report.sources.append(status)
        flag = "ok " if status.ok else "FAIL"
        print(f"  [{flag}] {source.name}: {status.message}")
    return report


def main() -> int:
    settings = load_settings()
    sources = build_sources(settings.forecast_days)

    enabled = [s.name for s in sources if s.is_enabled()]
    print(f"Sources enabled: {', '.join(enabled)}")
    if "cmems" not in enabled:
        print("Note: CMEMS not enabled (missing credentials or toolbox) — using backbone SST.")

    reports: list[IslandReport] = []
    for island in settings.islands:
        print(f"\n== {island.name} ({island.region}) ==")
        reports.append(process_island(island, sources))

    # Aggregate per-source health across the whole run.
    run_status: dict[str, SourceStatus] = {}
    for report in reports:
        for s in report.sources:
            cur = run_status.get(s.name)
            # A source is "ok for the run" if it succeeded for at least one island.
            if cur is None or (s.ok and not cur.ok):
                run_status[s.name] = s

    latest = write_reports(reports, settings, list(run_status.values()))
    ok_sources = sum(1 for s in run_status.values() if s.ok)
    print(
        f"\nWrote {latest['island_count']} islands at {latest['generated_at']} "
        f"({ok_sources}/{len(run_status)} sources ok)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

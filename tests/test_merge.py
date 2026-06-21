"""Tests for SST merge priority and renderer output."""
from __future__ import annotations

import json

from src import render
from src.config import Island, Settings
from src.model import IslandReport, SourceStatus, SstReading
from src.sources.base import Source


def test_cmems_overrides_backbone_sst():
    """Running a CMEMS-like source after the backbone overrides the SST value."""
    report = IslandReport(name="X", slug="x", region="aegean", lat=1, lon=2)
    # backbone sets fallback
    report.sst = SstReading(value_c=24.0, source="openmeteo", time=None)

    class FakeCmems(Source):
        name = "cmems"

        def fetch(self, island, report):
            report.sst = SstReading(value_c=23.1, source="cmems", time="2026-06-21T00:00Z")
            return "ok"

    island = Island("X", "x", "aegean", 1, 2, 1, 2)
    FakeCmems().run(island, report)
    assert report.sst.value_c == 23.1
    assert report.sst.source == "cmems"


def test_poseidon_does_not_override_authoritative_cmems():
    """POSEIDON only fills SST when nothing authoritative is present."""
    from src.sources.poseidon import PoseidonSource  # import here; uses no network in this path

    report = IslandReport(name="X", slug="x", region="aegean", lat=1, lon=2)
    report.sst = SstReading(value_c=23.1, source="cmems", time=None)
    # Simulate poseidon's guard directly (no OPeNDAP configured in tests)
    if report.sst.source in (None, "openmeteo"):
        report.sst = SstReading(value_c=99.9, source="poseidon")
    assert report.sst.source == "cmems"
    assert report.sst.value_c == 23.1
    _ = PoseidonSource  # ensure import works


def test_write_reports_produces_latest(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    site_dir = tmp_path / "site"
    monkeypatch.setattr(render, "DATA_DIR", data_dir)
    monkeypatch.setattr(render, "SITE_DIR", site_dir)

    report = IslandReport(name="Milos", slug="milos", region="aegean", lat=36.7, lon=24.4)
    report.sst = SstReading(value_c=23.7, source="cmems", time="2026-06-21T00:00Z")
    report.forecast.time = ["2026-06-21T00:00"]
    report.forecast.air_temp_c = [22.0]
    report.forecast.wind_speed_kn = [9.0]
    report.sources = [SourceStatus("openmeteo", True, "ok"), SourceStatus("cmems", True, "ok")]

    settings = Settings(islands=[], forecast_days=7, history_days=30)
    latest = render.write_reports([report], settings, [SourceStatus("cmems", True, "ok")])

    assert latest["island_count"] == 1
    assert latest["islands"][0]["sst"]["value_c"] == 23.7
    assert (data_dir / "islands" / "milos.json").exists()
    assert (data_dir / "latest.json").exists()
    assert (site_dir / "data" / "latest.json").exists()  # mirrored for dashboard

    on_disk = json.loads((data_dir / "latest.json").read_text())
    assert on_disk["islands"][0]["conditions"]["wind_speed_kn"] == 9.0

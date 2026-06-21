"""Tests for source parsing and run-level resilience (mocked HTTP)."""
from __future__ import annotations

import json

import pytest

from src.config import Island
from src.model import IslandReport, SstReading
from src.sources import openmeteo
from src.sources.base import Source


ISLAND = Island(
    name="Testos", slug="testos", region="aegean",
    land_lat=37.0, land_lon=25.0, sea_lat=36.9, sea_lon=25.0,
)


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _new_report():
    return IslandReport(name="Testos", slug="testos", region="aegean", lat=37.0, lon=25.0)


def test_openmeteo_parses_and_aligns(monkeypatch):
    weather = {
        "hourly": {
            "time": ["2026-06-21T00:00", "2026-06-21T01:00"],
            "temperature_2m": [22.5, 23.0],
            "wind_speed_10m": [10.0, 12.0],
            "wind_gusts_10m": [15.0, 18.0],
            "wind_direction_10m": [180, 190],
            "weather_code": [1, 2],
            "precipitation": [0.0, 0.1],
        }
    }
    marine = {
        "hourly": {
            # marine axis intentionally offset/partial to test alignment
            "time": ["2026-06-21T01:00", "2026-06-21T00:00"],
            "wave_height": [0.5, 0.4],
            "wave_period": [4.0, 3.8],
            "wave_direction": [200, 210],
            "sea_surface_temperature": [24.1, 23.9],
        }
    }

    def fake_get(url, params, timeout):
        return FakeResp(weather if "marine" not in url else marine)

    monkeypatch.setattr(openmeteo.requests, "get", fake_get)
    report = _new_report()
    src = openmeteo.OpenMeteoSource(forecast_days=1)
    status = src.run(ISLAND, report)

    assert status.ok
    fc = report.forecast
    assert fc.time == ["2026-06-21T00:00", "2026-06-21T01:00"]
    assert fc.air_temp_c == [22.5, 23.0]
    # alignment: marine value for 00:00 is 23.9, for 01:00 is 24.1
    assert fc.sea_temp_c == [23.9, 24.1]
    assert fc.wave_height_m == [0.4, 0.5]
    # fallback current SST = first present marine SST on its own axis (24.1 @ 01:00)
    assert report.sst.value_c == 24.1
    assert report.sst.source == "openmeteo"


def test_failing_source_never_aborts():
    class Boom(Source):
        name = "boom"

        def fetch(self, island, report):
            raise RuntimeError("kaboom")

    report = _new_report()
    status = Boom().run(ISLAND, report)
    assert status.ok is False
    assert "kaboom" in status.message
    assert status.name == "boom"


def test_disabled_source_reports_disabled():
    class Off(Source):
        name = "off"

        def is_enabled(self):
            return False

        def fetch(self, island, report):
            raise AssertionError("should not be called")

    status = Off().run(ISLAND, _new_report())
    assert status.ok is False
    assert "disabled" in status.message


def test_per_island_json_roundtrips():
    report = _new_report()
    report.sst = SstReading(value_c=23.4, source="cmems", time="2026-06-21T00:00Z")
    blob = json.dumps(report.to_dict())
    back = json.loads(blob)
    assert back["sst"]["value_c"] == 23.4
    assert back["sst"]["source"] == "cmems"

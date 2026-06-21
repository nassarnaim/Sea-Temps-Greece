"""Open-Meteo backbone source (free, no API key).

Combines two endpoints:
  * Weather forecast  -> air temp, wind (knots), gusts, direction, weather code, precip
  * Marine forecast   -> wave height/period/direction, sea surface temperature

This is the reliable backbone that guarantees the system always produces data.
It also supplies a fallback SST when CMEMS is unavailable.
"""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import Island
from ..model import ForecastSeries, IslandReport, SstReading
from .base import Source

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
# (connect, read) timeouts — bounded so retries can't compound into a long run.
TIMEOUT = (10, 30)


def _build_session() -> requests.Session:
    """Session that retries transient failures (incl. read timeouts) with backoff."""
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=2,
        read=2,
        backoff_factor=1.0,  # 0s, 1s, 2s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_SESSION = _build_session()


def _get(url: str, params: dict) -> dict:
    resp = _SESSION.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _floats(seq) -> list:
    return [None if v is None else float(v) for v in (seq or [])]


def _ints(seq) -> list:
    return [None if v is None else int(v) for v in (seq or [])]


class OpenMeteoSource(Source):
    name = "openmeteo"
    label = "Open-Meteo (backbone)"

    def __init__(self, forecast_days: int = 7):
        self.forecast_days = forecast_days

    def fetch(self, island: Island, report: IslandReport) -> str:
        weather = _get(
            WEATHER_URL,
            {
                "latitude": island.land_lat,
                "longitude": island.land_lon,
                "hourly": ",".join(
                    [
                        "temperature_2m",
                        "wind_speed_10m",
                        "wind_gusts_10m",
                        "wind_direction_10m",
                        "weather_code",
                        "precipitation",
                    ]
                ),
                "wind_speed_unit": "kn",
                "timezone": "UTC",
                "forecast_days": self.forecast_days,
            },
        )
        marine = _get(
            MARINE_URL,
            {
                "latitude": island.sea_lat,
                "longitude": island.sea_lon,
                "hourly": ",".join(
                    [
                        "wave_height",
                        "wave_period",
                        "wave_direction",
                        "sea_surface_temperature",
                    ]
                ),
                "timezone": "UTC",
                "forecast_days": self.forecast_days,
            },
        )

        wh = weather.get("hourly", {})
        mh = marine.get("hourly", {})
        series = ForecastSeries(
            source=self.name,
            time=list(wh.get("time", [])),
            air_temp_c=_floats(wh.get("temperature_2m")),
            wind_speed_kn=_floats(wh.get("wind_speed_10m")),
            wind_gust_kn=_floats(wh.get("wind_gusts_10m")),
            wind_dir_deg=_floats(wh.get("wind_direction_10m")),
            weather_code=_ints(wh.get("weather_code")),
            precip_mm=_floats(wh.get("precipitation")),
        )

        # Marine grid is on its own time axis; align by timestamp to the weather axis.
        marine_time = list(mh.get("time", []))
        idx = {t: i for i, t in enumerate(marine_time)}
        wave_h = _floats(mh.get("wave_height"))
        wave_p = _floats(mh.get("wave_period"))
        wave_d = _floats(mh.get("wave_direction"))
        sea_t = _floats(mh.get("sea_surface_temperature"))

        def aligned(values):
            return [values[idx[t]] if t in idx and idx[t] < len(values) else None for t in series.time]

        series.wave_height_m = aligned(wave_h)
        series.wave_period_s = aligned(wave_p)
        series.wave_dir_deg = aligned(wave_d)
        series.sea_temp_c = aligned(sea_t)
        report.forecast = series

        # Fallback "current" SST = first available marine SST value.
        current_sst, current_time = _first_present(sea_t, marine_time)
        if current_sst is not None:
            report.sst = SstReading(value_c=current_sst, source=self.name, time=current_time)

        return f"{len(series.time)}h forecast, sst={current_sst}"


def _first_present(values: list, times: list) -> tuple[float | None, str | None]:
    for i, v in enumerate(values):
        if v is not None:
            return v, (times[i] if i < len(times) else None)
    return None, None

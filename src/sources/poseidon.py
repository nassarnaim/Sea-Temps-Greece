"""POSEIDON (HCMR) Aegean/Ionian forecast — best-effort.

POSEIDON exposes model output via THREDDS/OPeNDAP, but the dataset URLs are
undocumented and change between model runs. Rather than hard-code a brittle
path, this source:

  * confirms the POSEIDON forecast service is reachable and attaches a
    reference link for the relevant basin (Aegean vs Ionian), and
  * if a POSEIDON_OPENDAP_URL is configured AND xarray is available, attempts
    to read surface sea temperature for the island's sea point.

Either way it degrades gracefully so the backbone keeps the system live.
"""
from __future__ import annotations

import os

import requests

from ..config import Island
from ..model import Advisory, IslandReport, SstReading
from .base import Source

FORECAST_PAGE = "https://poseidon.hcmr.gr/services/forecast"
OPENDAP_URL = os.environ.get("POSEIDON_OPENDAP_URL")  # optional, model-run specific
TIMEOUT = 30


def _xarray_available() -> bool:
    try:
        import xarray  # noqa: F401
        return True
    except Exception:
        return False


class PoseidonSource(Source):
    name = "poseidon"
    label = "POSEIDON / HCMR"

    def fetch(self, island: Island, report: IslandReport) -> str:
        messages: list[str] = []

        # 1) Optional OPeNDAP read of surface sea temperature.
        if OPENDAP_URL and _xarray_available():
            import xarray as xr

            ds = xr.open_dataset(OPENDAP_URL)
            var = next(
                (v for v in ("thetao", "temperature", "sst", "votemper") if v in ds.variables),
                None,
            )
            if var is not None:
                da = ds[var]
                if "time" in da.dims:
                    da = da.isel(time=-1)
                for level in ("depth", "lev"):
                    if level in da.dims:
                        da = da.isel({level: 0})
                lat_name = "latitude" if "latitude" in da.coords else "lat"
                lon_name = "longitude" if "longitude" in da.coords else "lon"
                point = da.sel(
                    {lat_name: island.sea_lat, lon_name: island.sea_lon}, method="nearest"
                )
                value = float(point.values)
                value_c = round(value - 273.15 if value > 100 else value, 2)
                # Only override SST if CMEMS hasn't already set an authoritative value.
                if report.sst.source in (None, "openmeteo"):
                    report.sst = SstReading(value_c=value_c, source=self.name, time=None)
                messages.append(f"opendap sst={value_c}C")

        # 2) Reachability + reference link for the basin.
        resp = requests.get(FORECAST_PAGE, timeout=TIMEOUT)
        resp.raise_for_status()
        basin = "Aegean" if island.region == "aegean" else "Ionian"
        report.advisories.append(
            Advisory(
                source=self.name,
                text=f"POSEIDON {basin} Sea forecast available — see official bulletin.",
            )
        )
        messages.append(f"{basin} forecast reachable")
        return "; ".join(messages)

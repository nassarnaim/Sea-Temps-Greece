"""Copernicus Marine (CMEMS) authoritative SST via the copernicusmarine toolbox.

Requires a free Copernicus Marine account; credentials are read from the
CMEMS_USERNAME / CMEMS_PASSWORD environment variables (GitHub secrets in CI).

The toolbox and its heavy deps (xarray/netCDF4) are optional: if they are not
installed, or credentials are missing, this source disables itself cleanly and
the Open-Meteo backbone SST is used instead.

Dataset id defaults to the NRT Mediterranean high-resolution L4 SST analysis.
Confirm/override with `copernicusmarine describe` and the CMEMS_DATASET_ID env
var if the catalogue id changes.
"""
from __future__ import annotations

import os

from ..config import Island, cmems_credentials
from ..model import IslandReport, SstReading
from .base import Source

DEFAULT_DATASET_ID = os.environ.get(
    "CMEMS_DATASET_ID", "cmems_obs-sst_med_phy_nrt_l4_P1D-m"
)
# Candidate SST variable names across CMEMS L4 products, tried in order.
SST_VARS = ("analysed_sst", "sea_surface_temperature", "thetao", "sst")


def _toolbox_available() -> bool:
    try:
        import copernicusmarine  # noqa: F401
        return True
    except Exception:
        return False


def _to_celsius(value: float) -> float:
    # CMEMS L4 SST is typically in Kelvin; convert if it looks like Kelvin.
    return value - 273.15 if value > 100 else value


class CmemsSource(Source):
    name = "cmems"
    label = "Copernicus Marine (CMEMS)"

    def __init__(self, dataset_id: str = DEFAULT_DATASET_ID):
        self.dataset_id = dataset_id
        self._user, self._pwd = cmems_credentials()

    def is_enabled(self) -> bool:
        return bool(self._user and self._pwd) and _toolbox_available()

    def fetch(self, island: Island, report: IslandReport) -> str:
        import copernicusmarine

        ds = copernicusmarine.open_dataset(
            dataset_id=self.dataset_id,
            username=self._user,
            password=self._pwd,
            minimum_longitude=island.sea_lon - 0.1,
            maximum_longitude=island.sea_lon + 0.1,
            minimum_latitude=island.sea_lat - 0.1,
            maximum_latitude=island.sea_lat + 0.1,
        )

        var = next((v for v in SST_VARS if v in ds.variables), None)
        if var is None:
            raise ValueError(f"no SST variable found in {self.dataset_id}: {list(ds.variables)}")

        da = ds[var]
        # Latest time, nearest grid point, surface level if present.
        if "time" in da.dims:
            da = da.isel(time=-1)
        for level in ("depth", "elevation"):
            if level in da.dims:
                da = da.isel({level: 0})
        point = da.sel(
            latitude=island.sea_lat, longitude=island.sea_lon, method="nearest"
        )
        value = float(point.values)
        value_c = round(_to_celsius(value), 2)

        time_val = None
        if "time" in ds.coords:
            try:
                time_val = str(ds["time"].isel(time=-1).values)[:19] + "Z"
            except Exception:
                time_val = None

        report.sst = SstReading(value_c=value_c, source=self.name, time=time_val)
        return f"sst={value_c}C from {self.dataset_id}"

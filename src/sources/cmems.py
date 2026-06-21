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

# Candidate dataset ids tried in order until one opens. The exact CMEMS
# catalogue id can change; an explicit CMEMS_DATASET_ID env var (confirm with
# `copernicusmarine describe`) always takes precedence. The global L4 OSTIA
# product is included as a reliable fallback that also covers Greek waters.
CANDIDATE_DATASET_IDS = [
    "cmems_obs-sst_med_phy_nrt_l4_P1D-m",       # Med high-res L4 NRT
    "cmems_obs-sst_med_phy_subskin_nrt_P1D-m",  # Med diurnal subskin L4 NRT
    "cmems_obs-sst_glo_phy_nrt_l4_P1D-m",       # Global L4 OSTIA NRT (covers Med)
    "METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2",      # legacy global OSTIA id
]
_ENV_DATASET_ID = os.environ.get("CMEMS_DATASET_ID")
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

    def __init__(self):
        self._user, self._pwd = cmems_credentials()
        # Candidates to try, env override first.
        self._candidates = ([_ENV_DATASET_ID] if _ENV_DATASET_ID else []) + CANDIDATE_DATASET_IDS
        self._dataset_id: str | None = None  # resolved working id
        self._resolution_failed = False      # set once if no candidate opens

    def is_enabled(self) -> bool:
        return bool(self._user and self._pwd) and _toolbox_available()

    def _open(self, dataset_id: str, island: Island):
        import copernicusmarine

        return copernicusmarine.open_dataset(
            dataset_id=dataset_id,
            username=self._user,
            password=self._pwd,
            minimum_longitude=island.sea_lon - 0.1,
            maximum_longitude=island.sea_lon + 0.1,
            minimum_latitude=island.sea_lat - 0.1,
            maximum_latitude=island.sea_lat + 0.1,
        )

    def _resolve(self, island: Island):
        """Probe candidate dataset ids ONCE per run; cache the winner or give up.

        Returns the opened dataset for ``island`` using the resolved id, or
        raises if resolution has already failed (so we never re-probe all
        candidates for every island — that made the run pathologically slow).
        """
        if self._dataset_id:
            return self._open(self._dataset_id, island)
        if self._resolution_failed:
            raise RuntimeError("CMEMS dataset id unresolved (skipped after first failure)")
        errors = []
        for dataset_id in self._candidates:
            try:
                ds = self._open(dataset_id, island)
                self._dataset_id = dataset_id  # cache the first that works
                return ds
            except Exception as exc:  # noqa: BLE001 - try the next candidate
                errors.append(f"{dataset_id}: {type(exc).__name__}")
        self._resolution_failed = True  # don't retry candidates for later islands
        raise RuntimeError("no CMEMS dataset id resolved (" + "; ".join(errors) + ")")

    def fetch(self, island: Island, report: IslandReport) -> str:
        ds = self._resolve(island)

        var = next((v for v in SST_VARS if v in ds.variables), None)
        if var is None:
            raise ValueError(f"no SST variable found in {self._dataset_id}: {list(ds.variables)}")

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
        return f"sst={value_c}C from {self._dataset_id}"

"""Copernicus Marine (CMEMS) authoritative SST via the copernicusmarine toolbox.

Requires a free Copernicus Marine account; credentials are read from the
CMEMS_USERNAME / CMEMS_PASSWORD environment variables (GitHub secrets in CI).

The toolbox and its heavy deps (xarray/netCDF4) are optional: if they are not
installed, or credentials are missing, this source disables itself cleanly and
the Open-Meteo backbone SST is used instead.

Performance: opening a CMEMS dataset is expensive, so we open ONE field for a
Greek-wide bounding box, load that small latest-time SST grid into memory once,
and then sample every island's nearest point locally. The dataset id is also
resolved only once per run (env CMEMS_DATASET_ID first, else candidates).
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

# Bounding box covering all nine islands (Ionian + Aegean) with margin.
GREEK_BBOX = dict(min_lon=18.5, max_lon=29.5, min_lat=35.0, max_lat=40.5)


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
        self._candidates = ([_ENV_DATASET_ID] if _ENV_DATASET_ID else []) + CANDIDATE_DATASET_IDS
        self._dataset_id: str | None = None  # resolved working id
        self._resolution_failed = False      # set once if no candidate opens
        self._field = None                   # in-memory 2D SST DataArray (lat/lon)
        self._field_time: str | None = None  # ISO time of the loaded analysis

    def is_enabled(self) -> bool:
        return bool(self._user and self._pwd) and _toolbox_available()

    def _open(self, dataset_id: str):
        import copernicusmarine

        return copernicusmarine.open_dataset(
            dataset_id=dataset_id,
            username=self._user,
            password=self._pwd,
            minimum_longitude=GREEK_BBOX["min_lon"],
            maximum_longitude=GREEK_BBOX["max_lon"],
            minimum_latitude=GREEK_BBOX["min_lat"],
            maximum_latitude=GREEK_BBOX["max_lat"],
        )

    def _prepare_field(self, ds) -> None:
        """Reduce an opened dataset to a single latest-time 2D SST grid in memory."""
        var = next((v for v in SST_VARS if v in ds.variables), None)
        if var is None:
            raise ValueError(f"no SST variable in {self._dataset_id}: {list(ds.variables)}")
        da = ds[var]
        if "time" in da.dims:
            self._field_time = str(da["time"].isel(time=-1).values)[:19] + "Z"
            da = da.isel(time=-1)
        for level in ("depth", "elevation"):
            if level in da.dims:
                da = da.isel({level: 0})
        # Pull the (small) Greek-box grid into memory once; sampling is then local.
        self._field = da.load()

    def _ensure_field(self) -> None:
        """Resolve the dataset id and load the SST field ONCE per run."""
        if self._field is not None:
            return
        if self._resolution_failed:
            raise RuntimeError("CMEMS dataset id unresolved (skipped after first failure)")
        errors = []
        for dataset_id in self._candidates:
            try:
                ds = self._open(dataset_id)
                self._dataset_id = dataset_id
                self._prepare_field(ds)
                return
            except Exception as exc:  # noqa: BLE001 - try the next candidate
                errors.append(f"{dataset_id}: {type(exc).__name__}")
        self._resolution_failed = True
        raise RuntimeError("no CMEMS dataset id resolved (" + "; ".join(errors) + ")")

    def fetch(self, island: Island, report: IslandReport) -> str:
        self._ensure_field()
        lat_name = "latitude" if "latitude" in self._field.coords else "lat"
        lon_name = "longitude" if "longitude" in self._field.coords else "lon"
        point = self._field.sel(
            {lat_name: island.sea_lat, lon_name: island.sea_lon}, method="nearest"
        )
        value_c = round(_to_celsius(float(point.values)), 2)
        report.sst = SstReading(value_c=value_c, source=self.name, time=self._field_time)
        return f"sst={value_c}C from {self._dataset_id}"

"""Load island definitions and run settings from config/islands.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "islands.yaml"
DATA_DIR = REPO_ROOT / "data"
SITE_DIR = REPO_ROOT / "site"


@dataclass(frozen=True)
class Island:
    name: str
    slug: str
    region: str
    land_lat: float
    land_lon: float
    sea_lat: float
    sea_lon: float


@dataclass(frozen=True)
class Settings:
    islands: list[Island]
    forecast_days: int
    history_days: int


def load_settings(path: Path | None = None) -> Settings:
    path = path or CONFIG_PATH
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    defaults = raw.get("defaults", {})
    settings = raw.get("settings", {})
    islands: list[Island] = []
    for it in raw["islands"]:
        islands.append(
            Island(
                name=it["name"],
                slug=it["slug"],
                region=it["region"],
                land_lat=float(it["land"]["lat"]),
                land_lon=float(it["land"]["lon"]),
                sea_lat=float(it["sea"]["lat"]),
                sea_lon=float(it["sea"]["lon"]),
            )
        )
    return Settings(
        islands=islands,
        forecast_days=int(defaults.get("forecast_days", 7)),
        history_days=int(settings.get("history_days", 30)),
    )


def cmems_credentials() -> tuple[str | None, str | None]:
    """Read CMEMS credentials from the environment (set via GitHub secrets)."""
    return os.environ.get("CMEMS_USERNAME"), os.environ.get("CMEMS_PASSWORD")

"""Hellenic National Meteorological Service (HNMS / EMY) — best-effort.

HNMS has no clean public forecast API; marine forecasts are published as web
pages. This source confirms the marine bulletin page is reachable and attaches
it as an advisory link so users can consult official Greek marine warnings.
If the page is unreachable it records a failure and the run continues.
"""
from __future__ import annotations

import requests

from ..config import Island
from ..model import Advisory, IslandReport
from .base import Source

MARINE_PAGE = "https://emy.gr/en/marine"
TIMEOUT = 30


class HnmsSource(Source):
    name = "hnms"
    label = "HNMS / EMY"

    def fetch(self, island: Island, report: IslandReport) -> str:
        # TLS verification stays on. emy.gr currently serves an incomplete
        # certificate chain, so this probe may fail — that's fine, HNMS is a
        # best-effort advisory and the run continues without it.
        resp = requests.get(MARINE_PAGE, timeout=TIMEOUT, headers={"User-Agent": "Sea-Temps-Greece/1.0"})
        resp.raise_for_status()
        sea = "Aegean Sea" if island.region == "aegean" else "Ionian Sea"
        report.advisories.append(
            Advisory(
                source=self.name,
                text=f"HNMS marine forecast & warnings for the {sea} — consult the official EMY bulletin.",
            )
        )
        return f"marine bulletin reachable ({len(resp.content)} bytes)"

"""CEAMed (CEAM, Valencia) Mediterranean SST trend/anomaly — best-effort context.

CEAMed publishes a *basin-wide*, *monthly* Mediterranean SST trend, not a live
per-island feed. We attach it as shared climate context (the same anomaly value
applies to every island). This source attempts to read the latest anomaly value
from the CEAMet SST page; if parsing fails it still records the reference.
"""
from __future__ import annotations

import re

import requests

from ..config import Island
from ..model import ClimateContext, IslandReport
from .base import Source

SST_PAGE = "https://www.ceam.es/ceamet/SST/SST-trend.html"
TIMEOUT = 30
# Look for an anomaly value like "+1.23" / "-0.4" near the word anomaly.
_ANOMALY_RE = re.compile(r"anomal\w*[^0-9+-]{0,40}([+-]?\d+(?:[.,]\d+)?)\s*(?:°|deg|C)", re.IGNORECASE)


class CeamedSource(Source):
    name = "ceamed"
    label = "CEAMed (Med-wide SST trend)"

    def fetch(self, island: Island, report: IslandReport) -> str:
        resp = requests.get(SST_PAGE, timeout=TIMEOUT, headers={"User-Agent": "Sea-Temps-Greece/1.0"})
        resp.raise_for_status()
        text = resp.text

        anomaly = None
        m = _ANOMALY_RE.search(text)
        if m:
            try:
                anomaly = float(m.group(1).replace(",", "."))
            except ValueError:
                anomaly = None

        report.climate = ClimateContext(
            source=self.name,
            anomaly_c=anomaly,
            reference="Mediterranean basin-wide SST trend (CEAMet)",
            period="monthly",
            note="Basin-wide monthly context, not a per-island live value.",
        )
        return f"anomaly={anomaly}" if anomaly is not None else "reference attached (no value parsed)"

"""Source abstraction.

A Source fetches data for one island and mutates the given IslandReport in
place (filling whatever it can). The orchestrator wraps every call so a single
source raising never aborts the run; the failure is recorded as a SourceStatus.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import Island
from ..model import IslandReport, SourceStatus


class Source(ABC):
    #: stable identifier used in SourceStatus and merge-priority logic
    name: str = "source"
    #: human label for the dashboard
    label: str = "Source"

    def is_enabled(self) -> bool:
        """Whether this source should run (e.g. credentials present)."""
        return True

    @abstractmethod
    def fetch(self, island: Island, report: IslandReport) -> str:
        """Fill ``report`` for ``island``. Return a short status message.

        Raise on failure; the orchestrator converts it into a failed
        SourceStatus so other sources still run.
        """
        raise NotImplementedError

    def run(self, island: Island, report: IslandReport) -> SourceStatus:
        """Execute :meth:`fetch` defensively and return a health record."""
        if not self.is_enabled():
            return SourceStatus(self.name, ok=False, message="disabled (not configured)")
        try:
            message = self.fetch(island, report) or "ok"
            return SourceStatus(self.name, ok=True, message=message)
        except Exception as exc:  # noqa: BLE001 - resilience is the whole point
            return SourceStatus(self.name, ok=False, message=f"{type(exc).__name__}: {exc}")

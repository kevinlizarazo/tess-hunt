"""Slim multi-sector light curve: the only form kept after fetch."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class LightCurve:
    tic: int
    time: np.ndarray  # BTJD
    flux: np.ndarray
    flux_err: np.ndarray
    sector: np.ndarray
    sources: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        n = len(self.time)
        if not (len(self.flux) == len(self.flux_err) == len(self.sector) == n):
            raise ValueError("time, flux, flux_err and sector must have equal length")

    def select(self, mask: np.ndarray) -> "LightCurve":
        return LightCurve(
            self.tic,
            self.time[mask],
            self.flux[mask],
            self.flux_err[mask],
            self.sector[mask],
            self.sources,
        )

    def exposure_days(self) -> np.ndarray:
        out = np.full(len(self.time), np.nan)
        for sector in np.unique(self.sector):
            out[self.sector == sector] = self.sources[str(int(sector))]["cadence_s"] / 86400.0
        return out

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp.npz")
        np.savez_compressed(
            tmp,
            tic=self.tic,
            time=self.time,
            flux=self.flux,
            flux_err=self.flux_err,
            sector=self.sector,
            sources=json.dumps(self.sources),
        )
        # Rename last so a crash mid-write never leaves a file that loads as a complete light curve.
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "LightCurve":
        with np.load(path) as z:
            return cls(
                int(z["tic"]),
                z["time"],
                z["flux"],
                z["flux_err"],
                z["sector"],
                json.loads(str(z["sources"])),
            )

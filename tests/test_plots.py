from pathlib import Path

import numpy as np
from synthetic import make_lc, with_products

from tess_hunt import plots
from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris

ROOT = Path(__file__).resolve().parents[1]
VET3 = load_criteria(ROOT / "criteria" / "vet-v3.toml")
EPH = Ephemeris(5.0, 1326.1, 0.13, 0.0017)
PNG = b"\x89PNG\r\n\x1a\n"
MODSHIFT = {
    "sig_pri": 15.2,
    "sig_sec": 3.1,
    "sig_ter": 3.0,
    "sig_pos": 5.2,
    "phs_pri": 0.0001,
    "phs_sec": 0.759,
    "phs_ter": 0.513,
    "phs_pos": 0.533,
    "dep_sec": 0.00016,
    "err_sec": 0.00005,
    "Fred": 1.12,
}
PIXELS = {
    "sectors": [
        {"sector": 2, "offset_arcsec": 10.9, "quality": 0.92},
        {"sector": 15, "offset_arcsec": 21.6, "quality": 0.61},
    ]
}
NEIGHBOURS = {
    "check": "neighbours",
    "outcome": "pass",
    "reason": "1 of 2 neighbours could host the signal",
    "evidence": {"possible_hosts": [{"source_id": 7, "sep_arcsec": 12.0, "required_depth": 0.02}]},
}


def planet_lc():
    # Two seasons, PDCSAP and QLP in each, so the fold grid has four panels.
    lc = make_lc(sectors=(1, 2, 14, 15), noise_ppm=300.0, signals=[(5.0, 1326.1, 0.13, 0.0017)])
    return with_products(lc, {1: "SPOC", 2: "QLP", 14: "TESS-SPOC", 15: "QLP"})


def draw_all(lc, tmp_path, modshift, pixels, neighbours) -> list[Path]:
    return [
        plots.transits(lc, EPH, tmp_path / "transits.png"),
        plots.folds(
            lc, EPH, VET3["families"], tmp_path / "folds.png", VET3["holdout"]["season_gap_days"]
        ),
        plots.odd_even(lc, EPH, tmp_path / "odd_even.png"),
        plots.phase(lc, EPH, modshift, tmp_path / "phase.png"),
        plots.centroids(pixels, neighbours, tmp_path / "centroids.png", 15.0),
    ]


def test_each_plot_writes_a_png(tmp_path, monkeypatch):
    blank = []
    monkeypatch.setattr(plots, "no_data", lambda path, *a: blank.append(path.name) or path)
    paths = draw_all(planet_lc(), tmp_path / "plots", MODSHIFT, PIXELS, NEIGHBOURS)
    assert blank == []
    for path in paths:
        assert path.read_bytes()[:8] == PNG, path.name
    assert sorted(p.name for p in (tmp_path / "plots").iterdir()) == sorted(p.name for p in paths)


def test_a_plot_with_nothing_to_show_says_no_data(tmp_path, monkeypatch):
    lc = planet_lc()
    empty = lc.select(np.zeros(len(lc.time), dtype=bool))
    nan = planet_lc()
    nan.flux[:] = np.nan
    said = []
    no_data = plots.no_data

    def spy(path, *args):
        said.append(path.name)
        return no_data(path, *args)

    monkeypatch.setattr(plots, "no_data", spy)
    for name, light_curve in (("empty", empty), ("nan", nan)):
        said.clear()
        empty_pixels = {"sectors": [{"sector": 2, "offset_arcsec": float("nan"), "quality": 0.9}]}
        paths = draw_all(light_curve, tmp_path / name, None, empty_pixels, None)
        assert sorted(said) == sorted(p.name for p in paths), name
        for path in paths:
            assert path.read_bytes()[:8] == PNG, (name, path.name)
    said.clear()
    plots.centroids(None, None, tmp_path / "none.png", None)
    assert said == ["none.png"]

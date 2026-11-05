from pathlib import Path

import numpy as np
import pytest
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


def test_each_plot_is_drawn_for_print(tmp_path, monkeypatch):
    # The figure each plot saves, kept for inspection.
    drawn = {}
    save = plots._save

    def keep(fig, path):
        drawn[path.name] = fig
        return save(fig, path)

    monkeypatch.setattr(plots, "_save", keep)
    draw_all(planet_lc(), tmp_path / "plots", MODSHIFT, PIXELS, NEIGHBOURS)
    for name, fig in drawn.items():
        # At the preprint's text width, so its text prints at one size, with no title above the plot: the caption
        # says what each shows. Grids keep their panel titles.
        assert fig.get_figwidth() == plots.WIDTH_IN, name
        assert fig._suptitle is None, name
        if name in ("phase.png", "centroids.png"):
            assert all(not ax.get_title() for ax in fig.axes), name
    for name in ("transits.png", "folds.png", "odd_even.png"):
        assert (
            drawn[name]
            ._supxlabel.get_text()
            .startswith(("Time from mid-transit (h)", "Time from predicted"))
        )
        assert drawn[name]._supylabel.get_text() == "Relative flux (ppm)"
        assert drawn[name]._supxlabel.get_fontsize() == plots.FONT_PT
    [ax] = drawn["phase.png"].axes
    assert ax.get_xlim() == (-0.25, 0.75)
    assert (ax.get_xlabel(), ax.get_ylabel()) == ("Orbital phase", "Relative flux (ppm)")
    # The ModShift secondary at 0.759 is drawn an orbit earlier, labelled with the phase the record gives.
    lines = {
        line.get_label(): line.get_xdata()[0]
        for line in ax.get_lines()
        if line.get_label().startswith("Mod")
    }
    assert lines == {"ModShift secondary, phase 0.759, 3.1σ": pytest.approx(0.759 - 1.0)}
    assert all(t.get_fontsize() == plots.FONT_PT for t in ax.get_xticklabels())
    # Sharp in print and small enough to commit.
    for path in (tmp_path / "plots").iterdir():
        assert path.stat().st_size < 300_000, path.name
    # A plot with nothing to show carries no title either, and names the plot it stands in for in its text.
    plots.no_data(tmp_path / "blank.png", "TIC 1: phase", "no finite cadences")
    [ax] = drawn["blank.png"].axes
    assert ax.get_title() == "" and drawn["blank.png"]._suptitle is None
    assert [t.get_text() for t in ax.texts] == ["TIC 1: phase: no data (no finite cadences)"]


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

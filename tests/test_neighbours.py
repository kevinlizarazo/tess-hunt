import io
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import requests

from tess_hunt import neighbours
from tess_hunt.catalogs import TOI_URL
from tess_hunt.checks import Outcome
from tess_hunt.config import load_criteria

ROOT = Path(__file__).resolve().parents[1]
CFG = load_criteria(ROOT / "criteria" / "vet-v3.toml")["neighbours"]
DEPTH = 233e-6
T_TARGET = 9.0


def cone(*rows):
    return pd.DataFrame(rows, columns=neighbours.COLUMNS)


def star(source_id, sep, g, bp_rp=1.0):
    return (source_id, 10.0, -20.0, g, bp_rp, sep)


def g_for(tmag, bp_rp=1.0):
    return tmag - neighbours.tess_mag(0.0, bp_rp)


def test_tess_mag_at_a_solar_colour_matches_eq_2():
    # Stassun et al. 2019's eq. 2 is eq. 1 at BP-RP 0.82: T = G - 0.430.
    assert neighbours.tess_mag(10.0, 0.82) == pytest.approx(10.0 - 0.430, abs=1e-3)


def test_required_depth_and_possible():
    table = cone(
        star(1, 0.3, g_for(T_TARGET)),
        star(2, 12.0, g_for(T_TARGET + 5.0)),
        star(3, 40.0, g_for(T_TARGET + 10.0)),
    )
    out = neighbours.required_depths(table, DEPTH, T_TARGET, 1, CFG).set_index("source_id")
    assert list(out.index) == [2, 3]
    assert out.loc[2, "required_depth"] == pytest.approx(0.0233)
    assert out.loc[3, "required_depth"] == pytest.approx(2.33)
    assert bool(out.loc[2, "possible"]) and not bool(out.loc[3, "possible"])
    assert set(out["tmag_from"]) == {"colour"}

    result = neighbours.neighbour_check(out.reset_index(), None)
    assert result.check == "neighbours" and result.outcome is Outcome.PASS
    [host] = result.evidence["possible_hosts"]
    assert host["source_id"] == 2 and host["sep_arcsec"] == 12.0
    assert host["required_depth"] == pytest.approx(0.0233)
    assert [row["source_id"] for row in result.evidence["table"]] == [2, 3]


def test_target_is_not_its_own_neighbour():
    table = cone(star(7, 0.2, 12.0), star(1, 0.4, 9.0), star(8, 1.5, 13.0))

    by_id = neighbours.required_depths(table, DEPTH, T_TARGET, 1, CFG)
    assert list(by_id["source_id"]) == [7, 8]

    nearest = neighbours.required_depths(table, DEPTH, T_TARGET, None, CFG)
    assert list(nearest["source_id"]) == [1, 8]

    nothing_close = neighbours.required_depths(table.iloc[2:], DEPTH, T_TARGET, None, CFG)
    assert list(nothing_close["source_id"]) == [8]


def test_g_only_takes_the_brightest_magnitude(monkeypatch):
    lo, hi = CFG["bp_rp_range"]
    grid = min(neighbours.tess_mag(12.0, c) for c in np.linspace(lo, hi, 3001))
    assert neighbours.tess_mag_bright(12.0, CFG["bp_rp_range"]) == pytest.approx(grid, abs=1e-9)
    assert grid == pytest.approx(neighbours.tess_mag(12.0, hi), abs=1e-9)

    table = cone(star(1, 0.1, 9.0), star(2, 20.0, 12.0, np.nan), star(3, 30.0, 12.0, 0.82))
    out = neighbours.required_depths(table, DEPTH, T_TARGET, 1, CFG).set_index("source_id")
    assert out.loc[2, "tmag"] == pytest.approx(grid, abs=1e-9)
    assert out.loc[2, "tmag"] < out.loc[3, "tmag"]
    assert out.loc[2, "tmag_from"] == "g_only" and out.loc[3, "tmag_from"] == "colour"

    # A relation with a turning point inside the range is searched there, not only at the ends.
    monkeypatch.setattr(neighbours, "TESS_COLOUR_TERM", np.polynomial.Polynomial([0.0, -2.0, 1.0]))
    assert neighbours.tess_mag_bright(12.0, [0.0, 3.0]) == pytest.approx(11.0)


def test_star_without_g_is_inconclusive():
    table = cone(star(1, 0.1, 9.0), star(2, 10.0, g_for(14.0)), star(3, 50.0, np.nan, np.nan))
    out = neighbours.required_depths(table, DEPTH, T_TARGET, 1, CFG)
    no_g = out.set_index("source_id").loc[3]
    assert np.isnan(no_g["tmag"]) and no_g["tmag_from"] == "none" and not no_g["possible"]
    result = neighbours.neighbour_check(out, None)
    assert result.outcome is Outcome.INCONCLUSIVE
    assert result.evidence["no_g"] == [3]
    assert [h["source_id"] for h in result.evidence["possible_hosts"]] == [2]


def test_missing_target_magnitude_is_inconclusive():
    table = cone(star(1, 0.1, 9.0), star(2, 10.0, g_for(14.0)))
    out = neighbours.required_depths(table, DEPTH, np.nan, 1, CFG)
    assert neighbours.neighbour_check(out, None).outcome is Outcome.INCONCLUSIVE


def test_gaia_failure_is_inconclusive():
    calls = []

    def launch(query, ids):
        calls.append(query)
        raise OSError("archive unavailable")

    with pytest.raises(neighbours.NeighbourError) as caught:
        neighbours.gaia_cone(10.0, -20.0, CFG["radius_arcmin"], launch=launch, backoff=0.0)
    assert len(calls) == 3

    result = neighbours.neighbour_check(None, str(caught.value))
    assert result.outcome is Outcome.INCONCLUSIVE
    assert "archive unavailable" in result.evidence["error"]


def test_gaia_cone_asks_for_the_radius_and_sorts_by_separation():
    queries = []

    def launch(query, ids):
        queries.append(query)
        # The archive names some gaia_source columns in upper case.
        return pd.DataFrame(
            {
                "SOURCE_ID": [5, 4],
                "ra": [10.0, 10.0],
                "dec": [-20.0, -20.0],
                "phot_g_mean_mag": [12.0, 11.0],
                "bp_rp": [1.0, 1.0],
                "sep_arcsec": [30.0, 0.2],
            }
        )

    out = neighbours.gaia_cone(10.0, -20.0, 1.0, launch=launch)
    assert list(out.columns) == neighbours.COLUMNS
    assert list(out["source_id"]) == [4, 5]
    assert "CIRCLE('ICRS', 10.0000000000, -20.0000000000, 0.0166666667)" in queries[0]


@pytest.fixture(scope="module")
def toi_table():
    response = requests.get(TOI_URL, timeout=120)
    response.raise_for_status()
    return pd.read_csv(io.StringIO(response.text), dtype={"TOI": str})


@pytest.mark.network
# Each control with the Gaia source of the eclipsing binary it was retired to, TIC 31553886 and TIC 30329564
# (benchmarks/README.md); the TIC's DR2 ids are their DR3 ids too.
@pytest.mark.parametrize(
    "toi, eb", [("1058.01", 6757952648798471040), ("1175.01", 2039904204830247296)]
)
def test_nearby_eb_controls_show_a_possible_host(toi, eb, toi_table):
    row = (
        pd.read_csv(ROOT / "benchmarks" / "pixel_controls.csv", dtype={"toi": str})
        .set_index("toi")
        .loc[toi]
    )
    toi_row = toi_table.set_index("TOI").loc[toi]
    depth, tmag = toi_row["Depth (ppm)"] * 1e-6, toi_row["TESS Mag"]
    table = neighbours.required_depths(
        neighbours.gaia_cone(row.ra, row.dec, CFG["radius_arcmin"]), depth, tmag, None, CFG
    )
    result = neighbours.neighbour_check(table, None)
    hosts = result.evidence["possible_hosts"]
    print(f"TOI-{toi} (TIC {int(row.tic)}): depth {depth * 1e6:.0f} ppm, Tmag {tmag}")
    print(f"{result.outcome.value}: {result.reason}")
    for h in hosts:
        print(
            f'  {h["source_id"]}: {h["sep_arcsec"]:.2f}", required depth {h["required_depth"]:.4f}'
        )
    assert eb in [h["source_id"] for h in hosts]

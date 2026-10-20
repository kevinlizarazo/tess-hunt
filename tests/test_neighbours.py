import io
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import requests
from astropy.coordinates import SkyCoord

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


def star(source_id, sep, g, bp_rp=1.0, pmra=np.nan, pmdec=np.nan):
    return (source_id, 10.0, -20.0, g, bp_rp, sep, pmra, pmdec, 2016.0)


def g_for(tmag, bp_rp=1.0):
    return tmag - neighbours.tess_mag(0.0, bp_rp)


def test_tess_mag_at_a_solar_colour_matches_eq_2():
    # Stassun et al. 2019's eq. 2 is eq. 1 at BP-RP 0.82: T = G - 0.430.
    assert neighbours.tess_mag(10.0, 0.82) == pytest.approx(10.0 - 0.430, abs=1e-3)


def test_required_depth_and_possible():
    table = cone(
        star(1, 0.3, g_for(T_TARGET)),
        star(2, 12.0, g_for(T_TARGET + 5.0), pmra=-164.0, pmdec=-53.0),
        star(3, 40.0, g_for(T_TARGET + 10.0)),
    )
    out = neighbours.required_depths(table, DEPTH, T_TARGET, 1, CFG).set_index("source_id")
    assert list(out.index) == [2, 3]
    # TRICERATOPS's match moves each star to the TIC's epoch with these (decision 0026).
    assert out.loc[2, "pmra"] == -164.0 and out.loc[2, "pmdec"] == -53.0
    assert out.loc[2, "ref_epoch"] == 2016.0
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

    only_close = neighbours.required_depths(table.iloc[1:], DEPTH, T_TARGET, None, CFG)
    assert list(only_close["source_id"]) == [8]

    # A target the cone does not identify would otherwise stay in the table as its own possible host.
    big = 4623036865373793408
    rounded = int(float(big))  # the float parse gaia.dr3_join guards against
    unidentified = [
        (cone(star(big, 0.2, 9.0), star(8, 1.5, 13.0)), rounded),
        (table.iloc[2:], None),
        (cone(), 1),
        (cone(), None),
    ]
    for cone_rows, source_id in unidentified:
        with pytest.raises(neighbours.NeighbourError):
            neighbours.required_depths(cone_rows, DEPTH, T_TARGET, source_id, CFG)


def test_close_companion_without_an_id_is_inconclusive():
    # Without an id, the nearer of two stars within 1" need not be the target: dropping it could hide the
    # companion and leave the target listed as its own host.
    table = cone(star(7, 0.2, 12.0), star(1, 0.4, 9.0), star(8, 1.5, 13.0))
    with pytest.raises(neighbours.NeighbourError) as caught:
        neighbours.required_depths(table, DEPTH, T_TARGET, None, CFG)
    result = neighbours.neighbour_check(None, str(caught.value))
    assert result.outcome is Outcome.INCONCLUSIVE and "2 Gaia DR3 stars" in result.reason


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
                # A two-parameter solution has no proper motion.
                "pmra": [np.nan, -164.0],
                "pmdec": [np.nan, -53.0],
                "REF_EPOCH": [2016.0, 2016.0],
            }
        )

    out = neighbours.gaia_cone(10.0, -20.0, 1.0, launch=launch)
    assert list(out.columns) == neighbours.COLUMNS
    assert {"pmra", "pmdec", "ref_epoch"} <= set(neighbours.COLUMNS)
    assert list(out["source_id"]) == [4, 5]
    assert out["pmra"].tolist()[0] == -164.0 and np.isnan(out["pmdec"].tolist()[1])
    assert "CIRCLE('ICRS', 10.0000000000, -20.0000000000, 0.0166666667)" in queries[0]
    assert "pmra, pmdec, ref_epoch" in queries[0]


# TIC 44926986 (decision 0034): its TIC position, at J2000, and four Gaia DR3 rows, at J2016.0: the target, which
# moved 2.75" between the two epochs, its bound companion TIC 44926982, a field star and one near the cone's edge.
TIC_44926986 = (146.852182941572, -39.8797286285282)
TARGET, COMPANION, FIELD, EDGE = (
    5431607545961330560,
    5431607545963652864,
    5431607610382753536,
    5431607644742487424,
)
# Positions to 10 decimals, 3.6e-7".
DR3_44926986 = pd.DataFrame(
    [
        (TARGET, 146.8512349542, -39.8799633192, 9.969851, 0.8970566, -163.63, -52.65, 2016.0),
        (COMPANION, 146.8483459688, -39.8815709756, 11.201227, 1.143877, -165.81, -52.51, 2016.0),
        (FIELD, 146.8459195820, -39.8795135394, 17.862907, 1.0609055, -6.57, 4.10, 2016.0),
        (EDGE, 146.8673306792, -39.8681610837, 17.649206, 1.0582619, -7.96, 4.33, 2016.0),
    ],
    columns=[c for c in neighbours.COLUMNS if c != "sep_arcsec"],
)


def archive(stars: pd.DataFrame):
    """The Gaia archive over `stars`, for `gaia_cone`'s two queries: a row by source id, and a cone whose centre and
    the point each separation runs from are read from the query and measured as the archive measures them."""

    def launch(query, ids):
        lookup = re.search(r"WHERE source_id = (\d+)", query)
        if lookup:
            return stars.loc[stars["source_id"] == int(lookup[1]), ["ra", "dec"]]
        number = r"(-?[\d.]+)"
        circle = re.search(rf"CIRCLE\('ICRS', {number}, {number}, {number}\)", query)
        distance = re.search(rf"POINT\('ICRS', {number}, {number}\)\) \* 3600", query)
        positions = SkyCoord(stars["ra"], stars["dec"], unit="deg")
        centre = SkyCoord(float(circle[1]), float(circle[2]), unit="deg")
        inside = positions.separation(centre).deg <= float(circle[3])
        point = SkyCoord(float(distance[1]), float(distance[2]), unit="deg")
        out = stars[inside].assign(sep_arcsec=positions[inside].separation(point).arcsec)
        return out.rename(columns={"source_id": "SOURCE_ID"})

    return launch


def test_the_cone_centres_on_the_targets_own_dr3_row():
    # With the source id, every separation runs from the target's DR3 position, and the star's motion since the TIC's
    # epoch no longer moves them or the cone's edge.
    launch = archive(DR3_44926986)
    out = neighbours.gaia_cone(*TIC_44926986, CFG["radius_arcmin"], source_id=TARGET, launch=launch)
    sep = out.set_index("source_id")["sep_arcsec"]
    assert list(out["source_id"]) == [TARGET, COMPANION, FIELD]
    assert sep[TARGET] == pytest.approx(0.0, abs=1e-6)
    assert sep[COMPANION] == pytest.approx(9.859, abs=1e-3)
    assert sep[FIELD] == pytest.approx(14.77, abs=0.01)
    # 61.50" from the target, past the 1' radius.
    assert EDGE not in sep.index

    # At 44926986-1's depth and TESS magnitude, the companion is a possible host at its true separation.
    table = neighbours.required_depths(out, 0.0007763817834557, 9.4929, TARGET, CFG)
    [host] = neighbours.neighbour_check(table, None).evidence["possible_hosts"]
    assert host["source_id"] == COMPANION and host["sep_arcsec"] == pytest.approx(9.859, abs=1e-3)


def test_without_an_id_the_cone_stays_on_the_tic_position():
    launch = archive(DR3_44926986)
    out = neighbours.gaia_cone(*TIC_44926986, CFG["radius_arcmin"], launch=launch)
    sep = out.set_index("source_id")["sep_arcsec"]
    # As the archive measured them from the TIC position (decision 0034's evidence).
    assert sep[TARGET] == pytest.approx(2.752, abs=1e-3)
    assert sep[COMPANION] == pytest.approx(12.504, abs=1e-3)
    assert sep[EDGE] == pytest.approx(59.039, abs=1e-3)
    # A target that moved more than 1" isn't found at its TIC position, so the table is inconclusive, not measured
    # from the wrong place.
    with pytest.raises(neighbours.NeighbourError, match="0 Gaia DR3 stars within"):
        neighbours.required_depths(out, DEPTH, T_TARGET, None, CFG)


@pytest.mark.parametrize(
    "down, source_id, asked, reason",
    [
        ("lookup", TARGET, ["lookup"] * 3, r"Gaia archive \(the target's DR3 row\) failed 3 times"),
        ("cone", TARGET, ["lookup"] + ["cone"] * 3, "Gaia archive failed 3 times"),
        (None, 1, ["lookup"], "the target's Gaia DR3 source 1 is not in gaia_source"),
    ],
    ids=["lookup fails", "cone fails", "no DR3 row"],
)
def test_a_cone_is_never_centred_on_a_guess(down, source_id, asked, reason):
    found, calls = archive(DR3_44926986), []

    def launch(query, ids):
        kind = "cone" if "CIRCLE" in query else "lookup"
        calls.append(kind)
        if kind == down:
            raise OSError("archive unavailable")
        return found(query, ids)

    with pytest.raises(neighbours.NeighbourError, match=reason) as caught:
        neighbours.gaia_cone(
            *TIC_44926986, CFG["radius_arcmin"], source_id=source_id, launch=launch, backoff=0.0
        )
    # Without the target's DR3 row there is no cone at all, not one on the TIC position.
    assert calls == asked
    result = neighbours.neighbour_check(None, str(caught.value))
    assert result.outcome is Outcome.INCONCLUSIVE and str(caught.value) in result.reason


@pytest.fixture(scope="module")
def toi_table():
    response = requests.get(TOI_URL, timeout=120)
    response.raise_for_status()
    return pd.read_csv(io.StringIO(response.text), dtype={"TOI": str})


@pytest.mark.network
# Each control with its target's Gaia DR3 source, as `vetting run` joins it (Ruling N, decision 0025), and the source
# of the eclipsing binary it was retired to, TIC 31553886 and TIC 30329564 (benchmarks/README.md); the TIC's DR2 ids
# are their DR3 ids too.
@pytest.mark.parametrize(
    "toi, target, eb",
    [
        ("1058.01", 6757952644494426624, 6757952648798471040),
        ("1175.01", 2039904204830244096, 2039904204830247296),
    ],
)
def test_nearby_eb_controls_show_a_possible_host(toi, target, eb, toi_table):
    row = (
        pd.read_csv(ROOT / "benchmarks" / "pixel_controls.csv", dtype={"toi": str})
        .set_index("toi")
        .loc[toi]
    )
    toi_row = toi_table.set_index("TOI").loc[toi]
    depth, tmag = toi_row["Depth (ppm)"] * 1e-6, toi_row["TESS Mag"]
    # Centred on the target's own DR3 row, as production centres it (decision 0034).
    cone = neighbours.gaia_cone(row.ra, row.dec, CFG["radius_arcmin"], source_id=target)
    table = neighbours.required_depths(cone, depth, tmag, target, CFG)
    result = neighbours.neighbour_check(table, None)
    hosts = result.evidence["possible_hosts"]
    print(f"TOI-{toi} (TIC {int(row.tic)}): depth {depth * 1e6:.0f} ppm, Tmag {tmag}")
    print(f"{result.outcome.value}: {result.reason}")
    for h in hosts:
        print(
            f'  {h["source_id"]}: {h["sep_arcsec"]:.2f}", required depth {h["required_depth"]:.4f}'
        )
    assert eb in [h["source_id"] for h in hosts]

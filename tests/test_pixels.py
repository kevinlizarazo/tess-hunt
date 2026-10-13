import hashlib
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tess_hunt import pixels
from tess_hunt.checks import Outcome
from tess_hunt.config import load_criteria

ROOT = Path(__file__).resolve().parents[1]
TRIAGE = load_criteria(ROOT / "criteria" / "triage-v1.toml")
CFG = TRIAGE["pixels"]
STAR = {"tic": 7, "ra": 10.0, "dec": -60.0}


class StubTLC:
    def __init__(self):
        self.metrics = {"tic": 7, "planetno": 1, "per": 3.0, "epo": 1326.0, "dur": 0.1}


def save_image(tdi_dir, sector, period=3.0, epoch=1326.0, hours=0.1 * 24):
    """A difference-image file as transit-diffImage saves it, the planet's ephemeris at index 6."""
    path = Path(tdi_dir) / "tic7" / f"imageData_7.1_sector{sector}.pickle"
    path.parent.mkdir(exist_ok=True)
    planet = {"period": period, "epoch": epoch, "durationHours": hours}
    path.write_bytes(pickle.dumps([None] * 6 + [planet]))
    return path


def stub_vetting(offsets, raises=None, no_image=()):
    """LEO-Vetter's pixel_vetting: an image file for every sector but those in `no_image`, and `offsets`
    for the first sectors with one."""

    def run(tlc, star, sectors, quality_flags=None, tdi_dir=".", n_bad=0, max_sectors=np.inf):
        if raises:
            raise raises
        m = tlc.metrics
        imaged = [s for s in sectors if s not in no_image]
        for s in imaged:
            save_image(tdi_dir, s, m["per"], m["epo"], m["dur"] * 24)
        good = imaged[: len(offsets)]
        centroids = [{"offset_arc": o, "offset_pix": o / 21.0, "quality": 0.9} for o in offsets]
        m["offset_qual"] = offsets[0] if offsets else np.nan
        m["offset_mean"] = float(np.mean(offsets)) if offsets else np.nan
        return None, good, [], centroids

    return run


class Calls:
    """pixel_vetting that runs each stub in turn, repeating the last, and counts its calls."""

    def __init__(self, *stubs):
        self.stubs, self.calls = stubs, 0

    def __call__(self, tlc, star, sectors, **kw):
        self.calls += 1
        return self.stubs[min(self.calls, len(self.stubs)) - 1](tlc, star, sectors, **kw)


@pytest.fixture
def on_silicon(monkeypatch):
    monkeypatch.setattr(pixels, "observable_sectors", lambda tic, ra, dec, sectors: list(sectors))
    monkeypatch.setattr(pixels.shutil, "which", lambda name: f"/usr/bin/{name}")


def check(tmp_path, monkeypatch, offsets, raises=None, sectors=(13, 96, 67)):
    monkeypatch.setattr(pixels, "pixel_vetting", stub_vetting(offsets, raises))
    return pixels.pixel_check(StubTLC(), STAR, list(sectors), CFG, tmp_path, backoff=0)


def calls_check(tmp_path, monkeypatch, calls, cfg=CFG):
    monkeypatch.setattr(pixels, "pixel_vetting", calls)
    return pixels.pixel_check(StubTLC(), STAR, [13, 96, 67], cfg, tmp_path, backoff=0)


def test_offset_over_the_limit_fails(tmp_path, monkeypatch, on_silicon):
    result = check(tmp_path, monkeypatch, [16.0])
    assert result.outcome is Outcome.FAIL and result.evidence["offset_qual_arcsec"] == 16.0


def test_offset_under_the_limit_passes(tmp_path, monkeypatch, on_silicon):
    assert check(tmp_path, monkeypatch, [9.0, 7.5]).outcome is Outcome.PASS


def test_nan_offset_is_inconclusive_not_a_pass(tmp_path, monkeypatch, on_silicon):
    assert check(tmp_path, monkeypatch, []).outcome is Outcome.INCONCLUSIVE


def test_pixel_exception_is_inconclusive(tmp_path, monkeypatch, on_silicon):
    result = check(tmp_path, monkeypatch, [9.0], raises=OSError("DNS failure"))
    assert result.outcome is Outcome.INCONCLUSIVE and "OSError" in result.reason


def test_network_error_is_retried(tmp_path, monkeypatch, on_silicon):
    calls = Calls(stub_vetting([], raises=OSError("DNS failure")), stub_vetting([9.0]))
    assert calls_check(tmp_path, monkeypatch, calls).outcome is Outcome.PASS
    assert calls.calls == 2


def test_missing_image_is_retried(tmp_path, monkeypatch, on_silicon):
    # transit-diffImage runs curl through os.system, so a failed TESScut download raises nothing: the
    # sector just has no image, and LEO-Vetter judges on older sectors instead.
    calls = Calls(stub_vetting([9.0], no_image={96}), stub_vetting([16.0]))
    result = calls_check(tmp_path, monkeypatch, calls)
    assert result.outcome is Outcome.FAIL and calls.calls == 2
    assert result.evidence["no_image"] == []


def test_image_still_missing_is_judged_without_it_and_recorded(tmp_path, monkeypatch, on_silicon):
    calls = Calls(stub_vetting([9.0], no_image={96}))
    result = calls_check(tmp_path, monkeypatch, calls)
    assert result.outcome is Outcome.PASS and calls.calls == 3
    assert result.evidence["no_image"] == [96]
    assert [s["sector"] for s in result.evidence["sectors"]] == [67]


def test_nan_with_every_image_saved_is_not_retried(tmp_path, monkeypatch, on_silicon):
    calls = Calls(stub_vetting([]))
    result = calls_check(tmp_path, monkeypatch, calls)
    assert result.outcome is Outcome.INCONCLUSIVE and calls.calls == 1
    assert result.reason == "no sector gave a usable difference image"


def test_nan_best_quality_offset_is_inconclusive(tmp_path, monkeypatch, on_silicon):
    result = check(tmp_path, monkeypatch, [np.nan, 9.0])
    assert result.outcome is Outcome.INCONCLUSIVE
    assert result.reason == "the best-quality sector's offset is NaN"


def test_sectors_after_the_last_good_one_are_not_retried(tmp_path, monkeypatch, on_silicon):
    calls = Calls(stub_vetting([9.0], no_image={13}))
    result = calls_check(tmp_path, monkeypatch, calls, cfg=CFG | {"max_sectors": 1})
    assert result.outcome is Outcome.PASS and calls.calls == 1
    assert result.evidence["no_image"] == []


def test_pixels_give_up_after_three_attempts(tmp_path, monkeypatch, on_silicon):
    calls = Calls(stub_vetting([], raises=OSError("DNS failure")))
    result = calls_check(tmp_path, monkeypatch, calls)
    assert result.outcome is Outcome.INCONCLUSIVE and calls.calls == 3


def test_sectors_are_tried_latest_first(tmp_path, monkeypatch, on_silicon):
    seen = []

    def spy(tlc, star, sectors, **kw):
        seen.extend(sectors)
        return stub_vetting([9.0])(tlc, star, sectors, **kw)

    monkeypatch.setattr(pixels, "pixel_vetting", spy)
    pixels.pixel_check(StubTLC(), STAR, [13, 96, 67], CFG, tmp_path)
    assert seen == [96, 67, 13]


def test_criteria_reach_pixel_vetting(tmp_path, monkeypatch, on_silicon):
    seen = {}

    def spy(tlc, star, sectors, **kw):
        seen.update(kw)
        return stub_vetting([9.0])(tlc, star, sectors, **kw)

    monkeypatch.setattr(pixels, "pixel_vetting", spy)
    pixels.pixel_check(StubTLC(), STAR, [96], CFG | {"max_sectors": 2, "n_bad": 1}, tmp_path)
    assert (seen["max_sectors"], seen["n_bad"], seen["tdi_dir"]) == (2, 1, str(tmp_path))


def test_missing_criteria_key_raises_instead_of_retrying(tmp_path, monkeypatch, on_silicon):
    monkeypatch.setattr(pixels, "pixel_vetting", stub_vetting([9.0]))
    with pytest.raises(KeyError):
        pixels.pixel_check(StubTLC(), STAR, [96], {"max_offset_arcsec": 15.0}, tmp_path)


def test_images_for_another_ephemeris_are_removed_first(tmp_path, monkeypatch, on_silicon):
    save_image(tmp_path, 96, period=5.0)
    save_image(tmp_path, 67)
    save_image(tmp_path, 13).write_bytes(b"truncated")
    present = []

    def spy(tlc, star, sectors, **kw):
        present.extend(sorted(p.name for p in (tmp_path / "tic7").iterdir()))
        return stub_vetting([9.0])(tlc, star, sectors, **kw)

    monkeypatch.setattr(pixels, "pixel_vetting", spy)
    result = pixels.pixel_check(StubTLC(), STAR, [13, 96, 67], CFG, tmp_path)
    assert present == ["imageData_7.1_sector67.pickle"]
    assert result.evidence["stale_removed"] == [
        "imageData_7.1_sector13.pickle",
        "imageData_7.1_sector96.pickle",
    ]


def test_asked_ephemeris_takes_the_transit_fit_then_the_trapezoid_then_the_search():
    search = {"per": 3.0, "epo": 1326.0, "dur": 0.1}
    trap = {"trap_aic": -40.0, "trap_per": 3.1, "trap_epo": 1326.1, "trap_dur": 0.2}
    transit = {"transit_aic": -50.0, "transit_per": 3.2, "transit_epo": 1326.2, "transit_dur": 0.3}
    assert pixels.asked_ephemeris(search) == (3.0, 1326.0, 0.1 * 24)
    assert pixels.asked_ephemeris(search | trap | {"transit_aic": np.nan}) == (
        3.1,
        1326.1,
        0.2 * 24,
    )
    assert pixels.asked_ephemeris(search | trap | transit) == (3.2, 1326.2, 0.3 * 24)


def test_files_transit_diffimage_leaves_are_hashed(tmp_path, monkeypatch, on_silicon):
    monkeypatch.setattr(pixels, "pixel_vetting", stub_vetting([9.0]))
    result = pixels.pixel_check(StubTLC(), STAR, [96], CFG, tmp_path)
    image = tmp_path / "tic7" / "imageData_7.1_sector96.pickle"
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    assert result.evidence["files"] == {"tic7/imageData_7.1_sector96.pickle": digest}


def test_missing_unzip_is_inconclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(
        pixels.shutil, "which", lambda name: None if name == "unzip" else "/usr/bin/curl"
    )
    assert pixels.pixel_check(StubTLC(), STAR, [13], CFG, tmp_path).outcome is Outcome.INCONCLUSIVE


def test_no_sector_on_silicon_is_inconclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(pixels.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(pixels, "observable_sectors", lambda tic, ra, dec, sectors: [])
    assert pixels.pixel_check(StubTLC(), STAR, [13], CFG, tmp_path).outcome is Outcome.INCONCLUSIVE


def test_observable_sectors_keeps_order_and_drops_sectors_off_silicon():
    assert pixels.observable_sectors(7, 10.0, -60.0, [96, 13, 2, 200]) == [96, 2]


def test_offset_limit_matches_the_leo_section():
    # triage-v1 states the 15" rule in [leo] and [pixels]; pixel_check reads [pixels].
    assert CFG["max_offset_arcsec"] == TRIAGE["leo"]["offset"]


CONTROLS = pd.read_csv(ROOT / "benchmarks" / "pixel_controls.csv", dtype={"toi": str})


@pytest.mark.network
@pytest.mark.slow
@pytest.mark.parametrize("toi", list(CONTROLS["toi"]))
def test_real_nearby_eb_controls(toi, tmp_path):
    row = CONTROLS.set_index("toi").loc[toi]
    tlc = StubTLC()
    tlc.metrics.update({"tic": int(row.tic), "per": row.period, "epo": row.t0, "dur": row.duration})
    star = {"tic": int(row.tic), "ra": row.ra, "dec": row.dec}
    sectors = [int(s) for s in str(row.sectors).split(";")]
    result = pixels.pixel_check(tlc, star, sectors, CFG, tmp_path)
    assert result.outcome.value == row.expected, result.evidence

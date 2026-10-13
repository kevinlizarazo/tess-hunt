import hashlib
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


def stub_vetting(offsets, raises=None):
    def run(tlc, star, sectors, quality_flags=None, tdi_dir=".", n_bad=0, max_sectors=np.inf):
        if raises:
            raise raises
        good = sectors[: len(offsets)]
        centroids = [{"offset_arc": o, "offset_pix": o / 21.0, "quality": 0.9} for o in offsets]
        tlc.metrics["offset_qual"] = offsets[0] if offsets else np.nan
        tlc.metrics["offset_mean"] = float(np.mean(offsets)) if offsets else np.nan
        return None, good, [], centroids

    return run


class Flaky:
    """pixel_vetting that comes back empty (or raises) on its first `failures` calls, then finds 9"."""

    def __init__(self, failures, raises=None):
        self.failures, self.raises, self.calls = failures, raises, 0

    def __call__(self, tlc, star, sectors, **kw):
        self.calls += 1
        offsets, raises = ([], self.raises) if self.calls <= self.failures else ([9.0], None)
        return stub_vetting(offsets, raises)(tlc, star, sectors, **kw)


@pytest.fixture
def on_silicon(monkeypatch):
    monkeypatch.setattr(pixels, "observable_sectors", lambda tic, ra, dec, sectors: list(sectors))
    monkeypatch.setattr(pixels.shutil, "which", lambda name: f"/usr/bin/{name}")


def check(tmp_path, monkeypatch, offsets, raises=None, sectors=(13, 96, 67)):
    monkeypatch.setattr(pixels, "pixel_vetting", stub_vetting(offsets, raises))
    return pixels.pixel_check(StubTLC(), STAR, list(sectors), CFG, tmp_path, backoff=0)


def flaky_check(tmp_path, monkeypatch, flaky):
    monkeypatch.setattr(pixels, "pixel_vetting", flaky)
    return pixels.pixel_check(StubTLC(), STAR, [13], CFG, tmp_path, backoff=0)


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
    flaky = Flaky(1, raises=OSError("DNS failure"))
    assert flaky_check(tmp_path, monkeypatch, flaky).outcome is Outcome.PASS
    assert flaky.calls == 2


def test_empty_cutouts_are_retried(tmp_path, monkeypatch, on_silicon):
    # transit-diffImage runs curl through os.system, so a failed TESScut download raises nothing.
    flaky = Flaky(1)
    assert flaky_check(tmp_path, monkeypatch, flaky).outcome is Outcome.PASS
    assert flaky.calls == 2


def test_pixels_give_up_after_three_attempts(tmp_path, monkeypatch, on_silicon):
    flaky = Flaky(99, raises=OSError("DNS failure"))
    result = flaky_check(tmp_path, monkeypatch, flaky)
    assert result.outcome is Outcome.INCONCLUSIVE and flaky.calls == 3


def test_sectors_are_tried_latest_first(tmp_path, monkeypatch, on_silicon):
    seen = []

    def spy(tlc, star, sectors, **kw):
        seen.extend(sectors)
        return stub_vetting([9.0])(tlc, star, sectors, **kw)

    monkeypatch.setattr(pixels, "pixel_vetting", spy)
    pixels.pixel_check(StubTLC(), STAR, [13, 96, 67], CFG, tmp_path)
    assert seen == [96, 67, 13]


def test_files_transit_diffimage_leaves_are_hashed(tmp_path, monkeypatch, on_silicon):
    def writes(tlc, star, sectors, **kw):
        out = Path(kw["tdi_dir"]) / "tic7" / "imageData_7.1_sector96.pickle"
        out.parent.mkdir()
        out.write_bytes(b"difference image")
        return stub_vetting([9.0])(tlc, star, sectors, **kw)

    monkeypatch.setattr(pixels, "pixel_vetting", writes)
    result = pixels.pixel_check(StubTLC(), STAR, [96], CFG, tmp_path)
    digest = hashlib.sha256(b"difference image").hexdigest()
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

import pandas as pd
import pytest
import requests
from fakes import FakeResponse, FakeSession

from tess_hunt import mast

URIS = {
    "mast:HLSP/qlp/s0001/0000/0002/6113/6679/hlsp_qlp_tess_ffi_s0001-0000000261136679_tess_v01_llc.fits": "mast/hlsp/qlp/s0001/0000/0002/6113/6679/hlsp_qlp_tess_ffi_s0001-0000000261136679_tess_v01_llc.fits",
    "mast:HLSP/tess-spoc/s0001/target/0000/0002/6113/6679/hlsp_tess-spoc_tess_phot_0000000261136679-s0001_tess_v1_lc.fits": "mast/hlsp/tess-spoc/s0001/target/0000/0002/6113/6679/hlsp_tess-spoc_tess_phot_0000000261136679-s0001_tess_v1_lc.fits",
    "mast:TESS/product/tess2018206045859-s0001-0000000261136679-0120-s_lc.fits": "tess/public/tid/s0001/0000/0002/6113/6679/tess2018206045859-s0001-0000000261136679-0120-s_lc.fits",
    "mast:TESS/product/tess2023096110322-s0064-0000000261136679-0257-s_lc.fits": "tess/public/tid/s0064/0000/0002/6113/6679/tess2023096110322-s0064-0000000261136679-0257-s_lc.fits",
}


@pytest.mark.parametrize("uri,key", URIS.items())
def test_s3_key(uri, key):
    assert mast.s3_key(uri) == key


def test_s3_key_rejects_unknown():
    with pytest.raises(ValueError):
        mast.s3_key("mast:JWST/product/x.fits")


def test_is_light_curve():
    assert mast.is_light_curve("QLP", "hlsp_qlp_x_llc.fits")
    assert not mast.is_light_curve("QLP", "hlsp_qlp_x_lc.fits")
    assert mast.is_light_curve("SPOC", "tess-s0064-x-s_lc.fits")
    assert not mast.is_light_curve("SPOC", "tess-s0064-x-a_fast-lc.fits")
    assert not mast.is_light_curve("TESS-SPOC", "hlsp_tess-spoc_x_tp.fits")


def test_rank_prefers_spoc_then_tess_spoc_then_qlp():
    products = pd.DataFrame(
        [
            {"tic": 1, "sector": 5, "provenance": "QLP", "cadence_s": 200.0},
            {"tic": 1, "sector": 5, "provenance": "SPOC", "cadence_s": 120.0},
            {"tic": 1, "sector": 5, "provenance": "TESS-SPOC", "cadence_s": 200.0},
            {"tic": 1, "sector": 6, "provenance": "QLP", "cadence_s": 200.0},
        ]
    )
    assert list(mast.rank(products)["provenance"]) == ["SPOC", "TESS-SPOC", "QLP", "QLP"]
    assert list(mast.best(products)["provenance"]) == ["SPOC", "QLP"]


def test_download_retries_server_errors():
    session = FakeSession(sequence=[FakeResponse(500), FakeResponse(200, b"abc")])
    assert mast.download("k", 3, session, backoff=0) == b"abc"


def test_download_retries_short_body():
    session = FakeSession(sequence=[FakeResponse(200, b"ab"), FakeResponse(200, b"abc")])
    assert mast.download("k", 3, session, backoff=0) == b"abc"


def test_download_retries_connection_errors():
    session = FakeSession(sequence=[requests.ConnectionError("reset"), FakeResponse(200, b"abc")])
    assert mast.download("k", 3, session, backoff=0) == b"abc"


def test_download_gives_up_after_attempts():
    session = FakeSession(sequence=[FakeResponse(503)] * 3)
    with pytest.raises(mast.DownloadError) as exc:
        mast.download("k", 3, session, backoff=0)
    assert not isinstance(exc.value, mast.MissingProduct)
    assert len(session.urls) == 3


def test_missing_product_does_not_retry():
    session = FakeSession()
    with pytest.raises(mast.MissingProduct):
        mast.download("k", 3, session, backoff=0)
    assert session.urls == [mast.S3_BASE + "k"]


@pytest.mark.network
def test_discover_and_download_pi_men():
    products = mast.discover([261136679])
    s1 = products[products["sector"] == 1]
    assert set(s1["provenance"]) == {"SPOC", "TESS-SPOC", "QLP"}
    assert not products["filename"].str.contains("fast").any()
    qlp = s1[s1["provenance"] == "QLP"].iloc[0]
    assert qlp["s3_key"] == list(URIS.values())[0]
    blob = mast.download(qlp["s3_key"], int(qlp["size"]), requests.Session())
    assert len(blob) == 80640

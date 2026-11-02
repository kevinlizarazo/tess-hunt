import pandas as pd
import pytest
import requests
from astropy.table import Table
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


def qlp_name(sector: int, version: int, tic: int = 1) -> str:
    return f"hlsp_qlp_tess_ffi_s{sector:04d}-{tic:016d}_tess_v{version:02d}_llc.fits"


def spoc_name(sector: int, tic: int = 1) -> str:
    return f"tess2023096110322-s{sector:04d}-{tic:016d}-0257-s_lc.fits"


def tess_spoc_name(sector: int, tic: int = 1) -> str:
    return f"hlsp_tess-spoc_tess_phot_{tic:016d}-s{sector:04d}_tess_v1_lc.fits"


def product(tic: int, sector: int, provenance: str, cadence_s: float, filename: str) -> dict:
    return {
        "tic": tic,
        "sector": sector,
        "provenance": provenance,
        "cadence_s": cadence_s,
        "filename": filename,
        "data_uri": f"u/{filename}",
        "size": 1,
        "s3_key": f"k/{filename}",
    }


def test_rank_prefers_spoc_then_tess_spoc_then_qlp():
    products = pd.DataFrame(
        [
            {"tic": 1, "sector": 5, "provenance": "QLP", "cadence_s": 200.0},
            {"tic": 1, "sector": 5, "provenance": "SPOC", "cadence_s": 120.0},
            {"tic": 1, "sector": 5, "provenance": "TESS-SPOC", "cadence_s": 200.0},
            {"tic": 1, "sector": 6, "provenance": "QLP", "cadence_s": 200.0},
        ]
    )
    products["filename"] = [qlp_name(5, 1), spoc_name(5), tess_spoc_name(5), qlp_name(6, 1)]
    assert list(mast.rank(products)["provenance"]) == ["SPOC", "TESS-SPOC", "QLP", "QLP"]
    assert list(mast.best(products)["provenance"]) == ["SPOC", "QLP"]


@pytest.mark.parametrize("order", [[0, 1, 2, 3], [1, 0, 3, 2]])
def test_rank_takes_the_later_qlp_version(order):
    # QLP redelivers a sector as v02 of the same file. The later version comes first even at a longer cadence label,
    # and a TESS-SPOC file still comes before it.
    rows = [
        product(241522065, 99, "QLP", 200.0, qlp_name(99, 1, 241522065)),
        product(241522065, 99, "QLP", 600.0, qlp_name(99, 2, 241522065)),
        product(241522065, 100, "QLP", 200.0, qlp_name(100, 2, 241522065)),
        product(241522065, 100, "TESS-SPOC", 200.0, tess_spoc_name(100, 241522065)),
    ]
    products = pd.DataFrame([rows[i] for i in order], columns=mast.PRODUCT_COLUMNS)
    assert list(mast.rank(products)["filename"]) == [
        qlp_name(99, 2, 241522065),
        qlp_name(99, 1, 241522065),
        tess_spoc_name(100, 241522065),
        qlp_name(100, 2, 241522065),
    ]
    assert list(mast.best(products)["filename"]) == [
        qlp_name(99, 2, 241522065),
        tess_spoc_name(100, 241522065),
    ]


def test_rank_is_unchanged_with_one_version():
    # One file per product in each star and sector, as in every listing M2 and M3 fetched from: the order as before.
    products = pd.DataFrame(
        [
            product(7, 5, "QLP", 1800.0, qlp_name(5, 1, 7)),
            product(3, 64, "QLP", 200.0, qlp_name(64, 1, 3)),
            product(3, 64, "SPOC", 120.0, spoc_name(64, 3)),
            product(7, 5, "TESS-SPOC", 1800.0, tess_spoc_name(5, 7)),
            product(3, 38, "QLP", 600.0, qlp_name(38, 1, 3)),
            product(3, 64, "TESS-SPOC", 200.0, tess_spoc_name(64, 3)),
            product(7, 4, "QLP", 1800.0, qlp_name(4, 1, 7)),
        ],
        columns=mast.PRODUCT_COLUMNS,
    )
    pd.testing.assert_frame_equal(
        mast.rank(products), products.iloc[[4, 2, 5, 1, 6, 3, 0]].reset_index(drop=True)
    )


def test_download_retries_server_errors():
    session = FakeSession(sequence=[FakeResponse(500), FakeResponse(200, b"abc")])
    assert mast.download("k", 3, session, backoff=0) == (b"abc", "s3")


def test_download_retries_short_body():
    session = FakeSession(sequence=[FakeResponse(200, b"ab"), FakeResponse(200, b"abc")])
    assert mast.download("k", 3, session, backoff=0) == (b"abc", "s3")


def test_download_retries_connection_errors():
    session = FakeSession(sequence=[requests.ConnectionError("reset"), FakeResponse(200, b"abc")])
    assert mast.download("k", 3, session, backoff=0) == (b"abc", "s3")


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


URI = "mast:HLSP/qlp/s0100/0000/0001/6850/6068/hlsp_qlp_tess_ffi_s0100-0000000168506068_tess_v01_llc.fits"


def test_bucket_404_falls_through_to_the_mast_api():
    session = FakeSession(routes={mast.MAST_API + URI: b"abc"})
    assert mast.download("k", 3, session, backoff=0, data_uri=URI) == (b"abc", "mast_api")
    assert session.urls == [mast.S3_BASE + "k", mast.MAST_API + URI]


def test_missing_everywhere_is_a_missing_product():
    session = FakeSession()
    with pytest.raises(mast.MissingProduct):
        mast.download("k", 3, session, backoff=0, data_uri=URI)
    assert session.urls == [mast.S3_BASE + "k", mast.MAST_API + URI]


@pytest.mark.network
def test_mast_api_serves_a_qlp_file_missing_from_the_bucket():
    blob, route = mast.download(
        "mast/hlsp/qlp/s0100/0000/0001/6850/6068/hlsp_qlp_tess_ffi_s0100-0000000168506068_tess_v01_llc.fits",
        679680,
        requests.Session(),
        data_uri=URI,
    )
    assert route == "mast_api" and len(blob) == 679680


@pytest.mark.network
def test_discover_and_download_pi_men():
    products = mast.discover([261136679])
    s1 = products[products["sector"] == 1]
    assert set(s1["provenance"]) == {"SPOC", "TESS-SPOC", "QLP"}
    assert not products["filename"].str.contains("fast").any()
    qlp = s1[s1["provenance"] == "QLP"].iloc[0]
    assert qlp["s3_key"] == list(URIS.values())[0]
    blob = mast.download(qlp["s3_key"], int(qlp["size"]), requests.Session())[0]
    assert len(blob) == 80640


class FakeObservations:
    """query_criteria fails `failures` times, then returns one SPOC observation per TIC."""

    def __init__(self, failures=0):
        self.failures = failures

    def query_criteria(self, target_name, **kw):
        if self.failures:
            self.failures -= 1
            raise ConnectionError("MAST 503")
        return Table(
            {
                "target_name": target_name,
                "provenance_name": ["QLP"] * len(target_name),
                "t_exptime": [200.0] * len(target_name),
                "obs_id": [f"o{t}" for t in target_name],
                "sequence_number": [98] * len(target_name),
            }
        )

    def get_product_list(self, obs):
        return Table(
            {
                "obs_id": list(obs["obs_id"]),
                "productFilename": [
                    f"hlsp_qlp_tess_ffi_s0098-{int(t):016d}_tess_v01_llc.fits"
                    for t in obs["target_name"]
                ],
                "dataURI": [
                    f"mast:HLSP/qlp/s0098/x/hlsp_qlp_tess_ffi_s0098-{int(t):016d}_tess_v01_llc.fits"
                    for t in obs["target_name"]
                ],
                "size": [100] * len(obs),
            }
        )


def test_discover_retries_a_failed_batch():
    out = mast.discover([1, 2], observations=FakeObservations(failures=2), backoff=0.0)
    assert sorted(out["tic"]) == [1, 2]


def test_discover_records_failed_batches_when_asked():
    failed = []
    out = mast.discover(
        [1, 2, 3], batch=2, observations=FakeObservations(failures=3), backoff=0.0, failed=failed
    )
    assert failed == [1, 2] and list(out["tic"]) == [3]


def test_discover_reports_why_a_batch_failed(capsys):
    class UnknownProducts(FakeObservations):
        def get_product_list(self, obs):
            return Table(
                {
                    "obs_id": list(obs["obs_id"]),
                    "productFilename": [f"x{t}_llc.fits" for t in obs["target_name"]],
                    "dataURI": [f"mast:JWST/product/x{t}_llc.fits" for t in obs["target_name"]],
                    "size": [100] * len(obs),
                }
            )

    failed = []
    mast.discover([1], observations=UnknownProducts(), backoff=0.0, failed=failed)
    assert failed == [1]
    assert (
        "ValueError: unrecognised data URI: mast:JWST/product/x1_llc.fits"
        in capsys.readouterr().err
    )


def test_discover_raises_without_a_failed_list():
    with pytest.raises(mast.DiscoverError):
        mast.discover([1], observations=FakeObservations(failures=3), backoff=0.0)

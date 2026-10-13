import numpy as np
import pandas as pd
import pytest
from astropy.table import Table

from tess_hunt.gaia import COLUMNS, QUERY, GaiaError, dr3_join, launch_gaia, logg_flame


def stars(n=2):
    return pd.DataFrame({"tic": range(1, n + 1), "gaia": [str(1000 + i) for i in range(1, n + 1)]})


def fake_launch(rows_by_call):
    calls = []

    def launch(query, ids):
        calls.append(list(ids["tic"]))
        return pd.DataFrame(rows_by_call.pop(0))

    return launch, calls


def row(tic, dist, logg_mass=1.0, radius=1.0, eb=np.nan):
    return {
        "tic": tic,
        "dr3_source_id": 10 * tic + int(dist * 10),
        "angular_distance": dist,
        "ruwe": 1.0,
        "logg_gspphot": 4.4,
        "mass_flame": logg_mass,
        "radius_flame": radius,
        "eb_frequency": eb,
        "eb_reference_time": np.nan if np.isnan(eb) else 100.0,
    }


def test_logg_flame_is_solar_for_one_solar_mass_and_radius():
    assert logg_flame([1.0], [1.0])[0] == pytest.approx(4.438)
    assert np.isnan(logg_flame([np.nan], [1.0])[0])


def test_dr3_join_keeps_the_nearest_neighbour():
    launch, _ = fake_launch([[row(1, 0.9, radius=3.0), row(1, 0.1), row(2, 0.2, eb=0.5)]])
    out = dr3_join(stars(), launch=launch).set_index("tic")
    assert list(out.reset_index().columns) == COLUMNS
    assert out.loc[1, "angular_distance"] == 0.1 and out.loc[1, "logg_flame"] == pytest.approx(
        4.438
    )
    assert out.loc[2, "eb_frequency"] == 0.5


def test_dr3_join_uploads_in_chunks():
    launch, calls = fake_launch([[row(1, 0.1)], [row(2, 0.1)], [row(3, 0.1)]])
    dr3_join(stars(3), launch=launch, chunk=1)
    assert calls == [[1], [2], [3]]


def test_dr3_join_skips_stars_without_a_dr2_id():
    launch, calls = fake_launch([[row(2, 0.1)]])
    out = dr3_join(pd.DataFrame({"tic": [1, 2], "gaia": ["", "1002"]}), launch=launch)
    assert calls == [[2]] and list(out["tic"]) == [2]


def test_dr3_join_uploads_dr2_ids_exactly():
    # Real DR2 ids pass 2**53; beside a blank id, a float parse would round this one to ...280.
    uploaded = []

    def launch(query, ids):
        uploaded.extend(int(v) for v in ids["dr2"])
        return pd.DataFrame([row(2, 0.1)])

    dr3_join(pd.DataFrame({"tic": [1, 2], "gaia": ["", "4623036865373793408"]}), launch=launch)
    assert uploaded == [4623036865373793408]


def test_dr3_join_retries_then_fails():
    attempts = []

    def failing(query, ids):
        attempts.append(1)
        raise ConnectionError("archive down")

    with pytest.raises(GaiaError, match="archive down"):
        dr3_join(stars(), launch=failing, attempts=3, backoff=0.0)
    assert len(attempts) == 3


class FakeArchive:
    """Runs every job; refuses to delete it."""

    def __init__(self):
        self.removed = []

    def launch_job_async(self, query, upload_resource, **kw):
        class Job:
            jobid = "job-1"

            def get_results(self):
                return Table({"tic": upload_resource["tic"]})

        return Job()

    def remove_jobs(self, jobs):
        self.removed.append(jobs)
        raise ConnectionError("archive busy")


def test_launch_keeps_the_result_when_cleanup_fails(capsys):
    archive = FakeArchive()
    out = launch_gaia(QUERY, Table({"tic": [7], "dr2": [1007]}), gaia=archive)
    assert list(out["tic"]) == [7] and archive.removed == [["job-1"]]
    err = capsys.readouterr().err
    assert "job-1" in err and "ConnectionError: archive busy" in err

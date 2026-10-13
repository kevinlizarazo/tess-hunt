import os

from tess_hunt.pool import process_pool, run_jobs


def test_pool_spawns_and_passes_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path))
    with process_pool(1) as pool:
        assert pool._mp_context.get_start_method() == "spawn"
        assert pool.submit(os.getenv, "TESS_HUNT_DATA").result() == str(tmp_path)


def test_run_jobs_in_process_for_one_worker():
    seen = []
    assert run_jobs(lambda x: seen.append(x) or x * 2, [1, 2], 1) == [2, 4] and seen == [1, 2]


def test_run_jobs_in_a_pool_otherwise():
    assert run_jobs(abs, [-1, -2, 3], 2) == [1, 2, 3]

import os

from tess_hunt.pool import process_pool


def test_pool_spawns_and_passes_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path))
    with process_pool(1) as pool:
        assert pool._mp_context.get_start_method() == "spawn"
        assert pool.submit(os.getenv, "TESS_HUNT_DATA").result() == str(tmp_path)

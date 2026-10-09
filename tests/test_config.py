import hashlib
from pathlib import Path

from tess_hunt.config import data_dir, load_criteria

ROOT = Path(__file__).resolve().parents[1]


def test_data_dir_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "d"))
    assert data_dir() == tmp_path / "d"
    assert (tmp_path / "d").is_dir()


def test_data_dir_default_is_outside_repo(tmp_path, monkeypatch):
    monkeypatch.delenv("TESS_HUNT_DATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert data_dir() == tmp_path / ".cache" / "tess-hunt"


def test_criteria_hash_is_of_file_bytes(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("[a]\nx = 1\n")
    criteria = load_criteria(path)
    assert criteria["a"]["x"] == 1
    assert criteria.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_repo_criteria_files_parse():
    assert load_criteria(ROOT / "criteria" / "search-v1.toml")["sample"]["teff_min"] == 5300.0
    assert load_criteria(ROOT / "criteria" / "vet-v1.toml")["novelty"]["neighbour_arcmin"] == 2.5

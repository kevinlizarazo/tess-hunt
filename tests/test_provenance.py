import json
import os
import subprocess

import pytest

from tess_hunt.config import load_criteria
from tess_hunt.provenance import DirtyTreeError, ResumeError, resume_run, start_run


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "criteria").mkdir()
    (root / "src" / "a.py").write_text("x = 1\n")
    (root / "criteria" / "c.toml").write_text("[a]\nx = 1\n")
    (root / "pyproject.toml").write_text("[project]\nname = 't'\n")
    (root / "uv.lock").write_text("lock\n")
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "add", ".")
    git(root, "commit", "-m", "init")
    return root


def start(repo, tmp_path, production, criteria="criteria/c.toml", argv=("tess-hunt", "test")):
    return start_run(
        "test",
        [load_criteria(repo / criteria)],
        production,
        list(argv),
        root=repo,
        runs=tmp_path / "runs",
    )


def test_production_clean_tree_records_commit_and_criteria(repo, tmp_path):
    run = start(repo, tmp_path, production=True)
    prov = json.loads((run.path / "provenance.json").read_text())
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert prov["git"]["commit"] == head.strip()
    assert prov["criteria"][0]["file"] == "criteria/c.toml"
    assert prov["git"]["dirty_paths"] == []


def test_production_refuses_modified_criteria(repo, tmp_path):
    (repo / "criteria" / "c.toml").write_text("[a]\nx = 2\n")
    with pytest.raises(DirtyTreeError, match="criteria/c.toml"):
        start(repo, tmp_path, production=True)


def test_production_refuses_untracked_source(repo, tmp_path):
    (repo / "src" / "new.py").write_text("")
    with pytest.raises(DirtyTreeError, match="src/new.py"):
        start(repo, tmp_path, production=True)


def test_production_refuses_criteria_outside_criteria_dir(repo, tmp_path):
    (repo / "other.toml").write_text("[a]\nx = 1\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "other")
    with pytest.raises(DirtyTreeError, match="criteria/"):
        start(repo, tmp_path, production=True, criteria="other.toml")


def test_exploratory_run_allows_dirty_tree_and_records_it(repo, tmp_path):
    (repo / "src" / "a.py").write_text("x = 2\n")
    run = start(repo, tmp_path, production=False)
    assert run.provenance["git"]["dirty_paths"] == ["src/a.py"]


def test_record_input_and_argv_carry_no_machine_paths(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    target = tmp_path / "data" / "runs" / "x" / "targets.parquet"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"abc")
    run = start(
        repo, tmp_path, production=False, argv=("tess-hunt", "fetch", "--targets", str(target))
    )
    run.record_input("targets", target)
    text = (run.path / "provenance.json").read_text()
    assert str(tmp_path) not in text
    assert "$TESS_HUNT_DATA/runs/x/targets.parquet" in text
    assert run.provenance["inputs"]["targets"]["file"] == "targets.parquet"


def test_argv_records_the_program_by_name_only(repo, tmp_path):
    run = start(repo, tmp_path, production=False, argv=("/opt/checkout/.venv/bin/tess-hunt", "vet"))
    assert run.provenance["argv"] == ["tess-hunt", "vet"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_finish_freezes_the_run(repo, tmp_path):
    run = start(repo, tmp_path, production=False)
    run.write_json("result.json", {"n": 1})
    run.finish(stars=3)
    prov = json.loads((run.path / "provenance.json").read_text())
    assert prov["ended_at"] and prov["summary"] == {"stars": 3}
    with pytest.raises(PermissionError):
        (run.path / "result.json").write_text("{}")
    with pytest.raises(PermissionError):
        run.write_json("added.json", {"n": 2})
    with pytest.raises(PermissionError):
        (run.path / "provenance.json").unlink()


def resume(repo, tmp_path, run):
    return resume_run(
        run.path.name,
        [load_criteria(repo / "criteria" / "c.toml")],
        root=repo,
        runs=tmp_path / "runs",
    )


def test_resume_reopens_an_unfinished_run(repo, tmp_path):
    run = start(repo, tmp_path, production=False)
    again = resume(repo, tmp_path, run)
    assert again.path == run.path and len(again.provenance["resumed_at"]) == 1


def test_resume_refuses_changed_criteria_or_code(repo, tmp_path):
    run = start(repo, tmp_path, production=False)
    (repo / "criteria" / "c.toml").write_text("[a]\nx = 2\n")
    with pytest.raises(ResumeError, match="criteria"):
        resume(repo, tmp_path, run)
    (repo / "criteria" / "c.toml").write_text("[a]\nx = 1\n")
    (repo / "src" / "a.py").write_text("x = 2\n")
    with pytest.raises(ResumeError, match="tree"):
        resume(repo, tmp_path, run)


def test_resume_refuses_a_finished_run(repo, tmp_path):
    run = start(repo, tmp_path, production=False)
    run.finish()
    with pytest.raises(ResumeError, match="finished"):
        resume(repo, tmp_path, run)

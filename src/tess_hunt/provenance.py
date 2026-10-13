"""Run directories: every stage writes into one, stamped with what produced it."""

import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tess_hunt.config import Criteria, data_dir, runs_dir
from tess_hunt.serialize import jsonable

# A production run must be reproducible from its commit, so these may not differ from it.
GUARDED_PATHS = ("src", "criteria", "pyproject.toml", "uv.lock")


class DirtyTreeError(RuntimeError):
    pass


def repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path(__file__).resolve().parent,
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(out.stdout.strip())


def git_state(root: Path) -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True
        ).stdout

    # Porcelain lines are "XY path"; stripping the output would eat the first line's leading space.
    dirty = git("status", "--porcelain", "--untracked-files=all", "--", *GUARDED_PATHS)
    return {
        "commit": git("rev-parse", "HEAD").strip(),
        "dirty_paths": [line[3:] for line in dirty.splitlines() if line.strip()],
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def scrub(arg: str) -> str:
    # Provenance and run outputs may be published under results/; they must not carry this machine's paths.
    return arg.replace(str(data_dir()), "$TESS_HUNT_DATA").replace(str(Path.home()), "~")


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return path.name


@dataclass
class Run:
    path: Path
    provenance: dict[str, Any]

    def write_json(self, name: str, obj: Any) -> Path:
        target = self.path / name
        target.write_text(json.dumps(jsonable(obj), indent=2, sort_keys=True) + "\n")
        return target

    def record_input(self, name: str, path: Path) -> None:
        self.provenance["inputs"][name] = {
            "file": Path(path).name,
            "sha256": sha256_file(Path(path)),
        }
        self._save()

    def record(self, key: str, value: Any) -> None:
        self.provenance[key] = value
        self._save()

    def finish(self, **summary: Any) -> None:
        self.provenance["ended_at"] = _now().isoformat()
        self.provenance["summary"] = summary
        self._save()
        # A finished run is evidence; later edits must fail loudly.
        entries = list(self.path.rglob("*"))
        for p in entries:
            if p.is_file():
                p.chmod(0o444)
        # A writable directory still lets files be added, unlinked or renamed over, whatever their mode.
        dirs = [p for p in entries if p.is_dir()] + [self.path]
        for d in sorted(dirs, key=lambda d: len(d.parts), reverse=True):
            d.chmod(0o555)

    def _save(self) -> None:
        (self.path / "provenance.json").write_text(
            json.dumps(jsonable(self.provenance), indent=2, sort_keys=True) + "\n"
        )


def start_run(
    stage: str,
    criteria: list[Criteria],
    production: bool,
    argv: list[str],
    root: Path | None = None,
    runs: Path | None = None,
) -> Run:
    root = root or repo_root()
    state = git_state(root)
    files = [_relative(c.path, root) for c in criteria]
    if production:
        if state["dirty_paths"]:
            raise DirtyTreeError(
                "production runs need these committed first: " + ", ".join(state["dirty_paths"])
            )
        outside = [f for f in files if not f.startswith("criteria/")]
        if outside:
            raise DirtyTreeError(
                "production criteria must live under criteria/: " + ", ".join(outside)
            )
    started = _now()
    run_id = f"{started:%Y%m%dT%H%M%SZ}-{stage}-{state['commit'][:7]}-{uuid.uuid4().hex[:4]}"
    path = (runs or runs_dir()) / run_id
    path.mkdir(parents=True)
    run = Run(
        path,
        {
            "run_id": run_id,
            "stage": stage,
            "production": production,
            "started_at": started.isoformat(),
            "ended_at": None,
            "git": state,
            "uv_lock_sha256": sha256_file(root / "uv.lock"),
            "criteria": [
                {"file": f, "sha256": c.sha256} for f, c in zip(files, criteria, strict=True)
            ],
            # argv[0] is wherever the checkout's venv put the script; only its name is reproducible.
            "argv": [Path(argv[0]).name, *(scrub(a) for a in argv[1:])],
            "python": sys.version.split()[0],
            "inputs": {},
            "summary": None,
        },
    )
    run._save()
    return run


def publish_run(run_id: str, root: Path, kind: str, files: Callable[[Path], list[Path]]) -> Path:
    """Copy a finished run's `files(run directory)` into results/<kind>/<run id> under `root`."""
    source = runs_dir() / run_id
    provenance = source / "provenance.json"
    if not provenance.exists():
        raise SystemExit(f"no run {run_id} under the data directory")
    if json.loads(provenance.read_text())["ended_at"] is None:
        raise SystemExit(f"run {run_id} has not finished; only finished runs are evidence")
    dest = root / "results" / kind / run_id
    if dest.exists():
        raise SystemExit(f"{dest} exists; published results are never overwritten")
    paths = files(source)
    # Checked before the copy starts, so a refusal leaves no partial publication behind.
    missing = [p.name for p in paths if not p.is_file()]
    if missing:
        raise SystemExit(f"run {run_id} has no {', '.join(missing)}")
    dest.mkdir(parents=True)
    for path in paths:
        shutil.copy(path, dest / path.name)
        (dest / path.name).chmod(0o644)
    print(f"published {run_id} -> {dest.relative_to(root)}")
    return dest


class ResumeError(RuntimeError):
    pass


def resume_run(
    run_id: str, criteria: list[Criteria], root: Path | None = None, runs: Path | None = None
) -> Run:
    """Reopen an unfinished run. Only the same commit, tree state and criteria may continue it, so a resumed
    run never mixes two versions of the code."""
    root = root or repo_root()
    path = (runs or runs_dir()) / run_id
    provenance = json.loads((path / "provenance.json").read_text())
    if provenance["ended_at"] is not None:
        raise ResumeError(f"run {run_id} has finished; finished runs are immutable")
    # Criteria first: an edited criteria file also dirties the tree, and this message says more.
    if [c.sha256 for c in criteria] != [c["sha256"] for c in provenance["criteria"]]:
        raise ResumeError(f"run {run_id} was started with different criteria")
    state = git_state(root)
    if state != provenance["git"]:
        raise ResumeError(
            f"run {run_id} was started at {provenance['git']}, the tree is now {state}"
        )
    provenance.setdefault("resumed_at", []).append(_now().isoformat())
    run = Run(path, provenance)
    run._save()
    return run

"""Where data lives and how pass/fail criteria are loaded."""

import hashlib
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def data_dir() -> Path:
    configured = os.environ.get("TESS_HUNT_DATA")
    root = Path(configured).expanduser() if configured else Path.home() / ".cache" / "tess-hunt"
    root.mkdir(parents=True, exist_ok=True)
    return root


def lc_dir() -> Path:
    return data_dir() / "lc"


def runs_dir() -> Path:
    return data_dir() / "runs"


def catalogs_dir() -> Path:
    return data_dir() / "catalogs"


@dataclass(frozen=True)
class Criteria:
    path: Path
    sha256: str
    values: dict[str, Any]

    def __getitem__(self, section: str) -> dict[str, Any]:
        return self.values[section]


def load_criteria(path: str | Path) -> Criteria:
    path = Path(path)
    raw = path.read_bytes()
    return Criteria(path, hashlib.sha256(raw).hexdigest(), tomllib.loads(raw.decode("utf-8")))

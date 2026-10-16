import subprocess
from importlib.metadata import version
from pathlib import Path

import numpy as np


def test_results_changing_pins():
    # TLS 2.0 and triceratops 1.1.0 both change results; a silent fallback would change ours.
    assert version("transitleastsquares") == "2.0"
    assert version("triceratops") == "1.1.0"


def test_stack_imports():
    import batman  # noqa: F401
    import emcee  # noqa: F401
    import leo_vetter  # noqa: F401
    import lightkurve  # noqa: F401
    import wotan  # noqa: F401
    from triceratops import triceratops  # noqa: F401

    assert int(np.__version__.split(".")[0]) == 1


def test_criteria_and_data_files_have_fixed_line_endings():
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        ["git", "check-attr", "eol", "binary", "--", "criteria/search-v1.toml", "x.fits", "x.npz"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "criteria/search-v1.toml: eol: lf" in out
    assert "x.fits: binary: set" in out and "x.npz: binary: set" in out

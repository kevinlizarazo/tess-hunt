from importlib.metadata import version

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

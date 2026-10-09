import json

import numpy as np

from tess_hunt.checks import Outcome, failed, inconclusive, passed


def test_to_dict_is_plain_json():
    result = failed(
        "odd_even", "differ", sigma=np.float64(4.2), n=np.int64(7), depths=np.array([1.0, np.nan])
    )
    assert result.to_dict() == {
        "check": "odd_even",
        "outcome": "fail",
        "reason": "differ",
        "evidence": {"sigma": 4.2, "n": 7, "depths": [1.0, None]},
    }
    json.dumps(result.to_dict(), allow_nan=False)


def test_outcomes():
    assert passed("x", "ok").outcome is Outcome.PASS
    assert inconclusive("x", "no data").outcome is Outcome.INCONCLUSIVE

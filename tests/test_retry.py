import pytest

from tess_hunt.retry import retry


class Flaky:
    """Raises ConnectionError for the first `failures` calls, then returns "ok"."""

    def __init__(self, failures):
        self.failures = failures
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError(f"down {self.calls}")
        return "ok"


def call_retry(call, sleeps, **kw):
    options = {
        "attempts": 3,
        "backoff": 5.0,
        "retry_on": ConnectionError,
        "error": LookupError,
        "what": "probe",
    }
    return retry(call, sleep=sleeps.append, **(options | kw))


def test_retry_returns_once_the_call_succeeds():
    call, sleeps = Flaky(failures=2), []
    assert call_retry(call, sleeps) == "ok"
    assert call.calls == 3 and sleeps == [5.0, 10.0]


def test_retry_raises_the_callers_error_after_its_attempts():
    call, sleeps = Flaky(failures=99), []
    with pytest.raises(LookupError, match="probe failed 3 times: ConnectionError: down 3"):
        call_retry(call, sleeps)
    assert call.calls == 3 and sleeps == [5.0, 10.0]


def test_retry_passes_other_exceptions_straight_through():
    def broken():
        raise ValueError("bad input")

    sleeps = []
    with pytest.raises(ValueError, match="bad input"):
        call_retry(broken, sleeps)
    assert sleeps == []

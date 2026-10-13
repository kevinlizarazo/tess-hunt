"""Retries for calls to archives that fail now and then."""

import time
from collections.abc import Callable


def retry[T](
    call: Callable[[], T],
    *,
    attempts: int,
    backoff: float,
    retry_on: type[BaseException] | tuple[type[BaseException], ...],
    error: type[Exception],
    what: str,
    sleep: Callable[[float], object] = time.sleep,
) -> T:
    """Call until it returns, waiting `backoff` seconds times the attempt number between tries. If every
    try raises one of `retry_on`, raise `error` naming `what` and the last problem."""
    problem: BaseException | None = None
    for attempt in range(attempts):
        if attempt:
            sleep(backoff * attempt)
        try:
            return call()
        except retry_on as exc:
            problem = exc
    raise error(f"{what} failed {attempts} times: {type(problem).__name__}: {problem}") from problem

"""Every vetting check returns one of three outcomes with the evidence it used."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from tess_hunt.serialize import jsonable


class Outcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class CheckResult:
    check: str
    outcome: Outcome
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "outcome": str(self.outcome),
            "reason": self.reason,
            "evidence": jsonable(self.evidence),
        }


def passed(check: str, reason: str, **evidence: Any) -> CheckResult:
    return CheckResult(check, Outcome.PASS, reason, evidence)


def failed(check: str, reason: str, **evidence: Any) -> CheckResult:
    return CheckResult(check, Outcome.FAIL, reason, evidence)


def inconclusive(check: str, reason: str, **evidence: Any) -> CheckResult:
    return CheckResult(check, Outcome.INCONCLUSIVE, reason, evidence)

import pytest
from pydantic import ValidationError

from agent.handoffs import ApprovalDecision, FitReport, PriceQuote, RiskReport


def test_risk_score_is_bounded():
    report = RiskReport(score=0.5, flags=[], explanation="sample")
    assert 0 <= report.score <= 1
    with pytest.raises(ValidationError):
        RiskReport(score=1.5, explanation="x")


def test_fit_score_is_bounded():
    assert FitReport(score=0.8).score == 0.8
    with pytest.raises(ValidationError):
        FitReport(score=-0.1)


def test_approval_actions_are_closed_set():
    with pytest.raises(ValidationError):
        ApprovalDecision(action="send_anyway")


def test_price_cannot_be_negative():
    with pytest.raises(ValidationError):
        PriceQuote(amount=-1)

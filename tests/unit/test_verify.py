from rag.verify import is_claim, verify_claims

EV = [{"evidence_id": "e1", "title": "Churn model", "text": "Built a churn classifier for 120k customers. "
       "Reached 0.71 PR-AUC with gradient boosting.", "skills": ["scikit-learn"]}]


def test_price_and_plans_are_not_claims():
    assert not is_claim("My proposed price is $900 fixed for the scope above.")
    assert not is_claim("I would start by benchmarking both models.")
    assert not is_claim("Your churn data has 8% positives.")
    assert is_claim("I built a churn classifier for 120k customers.")


def test_supported_claim_kept_and_fabrication_removed():
    draft = ("I built a churn classifier for 120k customers. I have 10 years of experience at Google. "
             "Would a call help?")
    report, cleaned = verify_claims(draft, EV)
    labels = {c.claim: c.label for c in report.checks}
    assert labels["I built a churn classifier for 120k customers."] == "supported"
    assert labels["I have 10 years of experience at Google."] == "unsupported"
    assert "Google" not in cleaned and report.unsupported_before == 1 and report.unsupported_after == 0


def test_invented_number_never_supported():
    report, _ = verify_claims("I built a churn classifier for 500k customers.", EV)
    assert report.checks[0].label != "supported"

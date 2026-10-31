"""Tests for F6: Explainable AI (XAI) and Risk-Score Validation.

Covers the 12 required test conditions:
1. Logistic Regression contributions match w_j * x_j.
2. Contributions + intercept reconcile with decision_function within 1e-4.
3. Multiclass and binary class-specific contributions.
4. Feature names after preprocessing/vectorization correctly mapped.
5. SHAP explanations for supported estimators only.
6. Explanation failures returning honest unavailable state.
7. Rule-engine warnings not mislabeled as model contributions.
8. Stable API response schemas and frontend rendering contract.
9. Risk category thresholds matching documented implementation.
10. Calibration and held-out evaluation zero-leakage verification.
11. Provisional status when validation evidence is insufficient (<10 words).
12. Missing features and malformed inputs handled safely.
"""

import json
import os
import sys
import numpy as np
import pytest
from scipy.sparse import csr_matrix
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import ComplementNB
from starlette.testclient import TestClient

# Ensure backend directory is in sys.path
backend_path = os.path.abspath("backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.schemas.analysis import JobTextAnalysisResponse, MLAnalysisResult
from app.services.ml_explainer import (
    explain_linear_prediction,
    explain_prediction,
    explain_with_shap,
)
from app.services.ml_inference import get_ml_service
from app.services.risk_engine import (
    RiskEngine,
    classify_risk_score,
    count_informative_words,
    get_risk_engine,
)


@pytest.fixture
def test_client(db_session):
    """Provides a TestClient with get_db overridden to use the isolated test db_session."""
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 1: Logistic Regression contributions match w_j * x_j
# ---------------------------------------------------------------------------
def test_logistic_regression_contributions_match_weights_times_features():
    """Verify that every feature contribution strictly equals w_j * x_j."""
    ml_svc = get_ml_service()
    text = (
        "Urgent job opening. Please wire transfer registration fees and bank deposit "
        "to secure your interview slot and work from home package."
    )
    res = ml_svc.analyze_text(text, explanation_method="linear_coefficients")
    assert res.explanation_available is True

    # Vectorize manually to inspect exact x_j and w_j
    X_vec = ml_svc.vectorizer.transform([text])
    feature_names = ml_svc.vectorizer.get_feature_names_out()
    coef = ml_svc.primary_classifier.coef_[0]

    for item in res.top_positive_features + res.top_negative_features:
        # Locate feature in vocabulary
        feature_idx = np.where(feature_names == item.feature)[0]
        assert len(feature_idx) == 1, f"Feature '{item.feature}' not found in vocabulary"
        idx = feature_idx[0]
        expected_x = float(X_vec[0, idx])
        expected_w = float(coef[idx])
        expected_phi = expected_x * expected_w

        assert abs(item.feature_value - expected_x) < 1e-4
        assert abs(item.coefficient - expected_w) < 1e-4
        assert abs(item.contribution - expected_phi) < 1e-4
        if expected_phi >= 0:
            assert item.direction_label == "increases model score"
        else:
            assert item.direction_label == "decreases model score"


# ---------------------------------------------------------------------------
# Test 2: Contributions + intercept reconcile with decision_function within 1e-4
# ---------------------------------------------------------------------------
def test_contributions_and_intercept_reconcile_with_decision_function():
    """Verify exact additivity identity: sum(phi_j) + b = z within 1e-4."""
    ml_svc = get_ml_service()
    test_cases = [
        "Software Engineer with 5 years experience in Python, AWS, Docker, and PostgreSQL.",
        "Kindly transfer registration fee via Western Union to proceed with the hiring process immediately.",
    ]

    for text in test_cases:
        res = ml_svc.analyze_text(text, explanation_method="linear_coefficients")
        assert res.explanation_available is True
        assert res.decision_score is not None
        assert res.intercept is not None
        assert res.reconciled_score is not None
        assert res.is_reconciled is True

        # Check numerical reconciliation tolerance
        diff = abs(res.decision_score - res.reconciled_score)
        assert diff < 1e-4, f"Reconciliation error {diff} exceeds 1e-4 tolerance"


# ---------------------------------------------------------------------------
# Test 3: Multiclass class-specific contributions
# ---------------------------------------------------------------------------
def test_multiclass_and_binary_class_specific_contributions():
    """Verify multiclass class-specific contribution extraction."""
    # Synthetic multiclass logistic regression
    rng = np.random.RandomState(42)
    X_train = csr_matrix(rng.uniform(0, 1, size=(30, 20)))
    y_train = np.array([0, 1, 2] * 10)
    clf = LogisticRegression(solver="lbfgs", random_state=42)
    clf.fit(X_train, y_train)

    feature_names = np.array([f"token_{i}" for i in range(20)])
    X_sample = csr_matrix(rng.uniform(0, 1, size=(1, 20)))

    # Explain for class 1
    exp_class1 = explain_linear_prediction(
        clf, X_sample, feature_names, target_class=1, top_k=5
    )
    assert exp_class1["explanation_available"] is True
    assert exp_class1["is_reconciled"] is True
    assert exp_class1["target_class"] == "1"

    # Verify decision score matches decision_function for class 1
    expected_z = clf.decision_function(X_sample)[0, 1]
    assert abs(exp_class1["decision_score"] - expected_z) < 1e-4

    # Explain for class 2
    exp_class2 = explain_linear_prediction(
        clf, X_sample, feature_names, target_class=2, top_k=5
    )
    assert exp_class2["target_class"] == "2"
    expected_z2 = clf.decision_function(X_sample)[0, 2]
    assert abs(exp_class2["decision_score"] - expected_z2) < 1e-4


# ---------------------------------------------------------------------------
# Test 4: Feature names after preprocessing/vectorization correctly mapped
# ---------------------------------------------------------------------------
def test_feature_names_mapping_after_preprocessing():
    """Verify vocabulary tokens are cleanly stripped, lowercased, and mapped."""
    ml_svc = get_ml_service()
    text = "<p>Looking for a Senior Python Developer with Docker and AWS experience.</p>"
    res = ml_svc.analyze_text(text)

    vocab = set(ml_svc.vectorizer.get_feature_names_out())
    all_features = res.top_positive_features + res.top_negative_features
    for f in all_features:
        assert f.feature in vocab
        # Ensure no HTML markup remains in tokens
        assert "<" not in f.feature
        assert ">" not in f.feature


# ---------------------------------------------------------------------------
# Test 5: SHAP explanations for supported estimators only
# ---------------------------------------------------------------------------
def test_shap_explanations_for_supported_estimators():
    """Verify SHAP LinearExplainer runs on supported Logistic Regression model."""
    ml_svc = get_ml_service()
    text = "Please deposit fee for training kit and laptop insurance."

    res = explain_with_shap(
        classifier=ml_svc.primary_classifier,
        vectorizer=ml_svc.vectorizer,
        cleaned_text=text,
        top_k=5,
    )
    assert res["explanation_available"] is True
    assert "SHAP" in res["explanation_method"].upper()
    assert len(res["top_positive_features"]) > 0
    for item in res["top_positive_features"]:
        assert item["direction_label"] == "increases model score"
        assert item["contribution"] >= 0


# ---------------------------------------------------------------------------
# Test 6: Explanation failures returning honest unavailable state
# ---------------------------------------------------------------------------
def test_unsupported_estimator_returns_honest_unavailable_state():
    """Verify unsupported estimators return honest unavailable state without fabricating numbers."""
    # ComplementNB does not have linear decision function weights like LR for SHAP LinearExplainer
    X_toy = csr_matrix([[1, 0, 1], [0, 1, 0]])
    y_toy = np.array([1, 0])
    nb = ComplementNB()
    nb.fit(X_toy, y_toy)

    feature_names = np.array(["a", "b", "c"])
    res = explain_with_shap(nb, csr_matrix([[1, 1, 0]]), feature_names)

    assert res["explanation_available"] is False
    assert res["explanation_unavailable_reason"] is not None
    assert (
        "not supported" in res["explanation_unavailable_reason"]
        or "linear and tree-based" in res["explanation_unavailable_reason"]
        or "practical" in res["explanation_unavailable_reason"]
    )
    assert len(res["top_positive_features"]) == 0
    assert len(res["top_negative_features"]) == 0


# ---------------------------------------------------------------------------
# Test 7: Rule-engine warnings not mislabeled as model contributions
# ---------------------------------------------------------------------------
def test_rules_heuristics_not_mislabeled_as_model_contributions():
    """Verify rule indicators remain distinct from ML feature contributions."""
    engine = get_risk_engine()
    text = (
        "Position: Administrative Assistant. We require a $100 upfront application fee "
        "sent via Western Union to our recruiter at hr-manager@gmail.com. Immediate opening."
    )
    response = engine.analyze_job_text(text)

    # Rule signals must be in evidence
    rule_evidence = [e for e in response.evidence if e.evidence_type == "rule_signal"]
    assert len(rule_evidence) > 0
    rule_names = {e.source_name for e in rule_evidence}
    assert any("Upfront Fees" in r for r in rule_names)

    # ML features must only contain individual linguistic vocabulary tokens
    ml_res = response.ml_analysis
    assert ml_res is not None
    assert ml_res.explanation_available is True

    for feature_item in ml_res.top_positive_features + ml_res.top_negative_features:
        # None of the features should be a rule category name
        assert feature_item.feature not in [
            "Upfront Fees",
            "Suspicious Contact",
            "Sensitive Information",
            "Urgency Indicators",
        ]


# ---------------------------------------------------------------------------
# Test 8: Stable API response schemas and frontend rendering contract
# ---------------------------------------------------------------------------
def test_stable_api_response_schemas_and_fields(test_client):
    """Verify API POST /api/v1/analyze/job-text returns all required F6 XAI fields."""
    payload = {
        "text": (
            "Job Title: Senior Cloud Architect. Requirements: 8+ years designing AWS and Azure "
            "infrastructure, Terraform automation, Kubernetes clusters, and Python microservices."
        ),
        "explanation_method": "auto",
    }
    resp = test_client.post("/api/v1/analyze/job-text", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    assert "ml_analysis" in data
    ml = data["ml_analysis"]

    required_fields = [
        "model_version",
        "model_name",
        "score_type",
        "target_class",
        "primary_prediction",
        "primary_threshold",
        "calibrated_prediction",
        "calibrated_probability",
        "calibrated_threshold",
        "decision_threshold",
        "decision_score",
        "intercept",
        "reconciled_score",
        "is_reconciled",
        "explanation_method",
        "explanation_available",
        "top_positive_features",
        "top_negative_features",
        "active_feature_count",
        "total_feature_contribution",
        "explanation_disclaimer",
    ]
    for field in required_fields:
        assert field in ml, f"Missing required field in ml_analysis: {field}"

    assert ml["score_type"] == "log_odds_decision_score"
    assert ml["target_class"] == "FRAUDULENT"
    assert isinstance(ml["is_reconciled"], bool)
    assert ml["active_feature_count"] is not None
    assert "intent" in ml["explanation_disclaimer"].lower()


# ---------------------------------------------------------------------------
# Test 9: Risk category thresholds matching documented implementation
# ---------------------------------------------------------------------------
def test_risk_category_thresholds_match_documented_implementation():
    """Verify risk categories conform to provisional settings boundaries."""
    assert classify_risk_score(0.0) == "LOW"
    assert classify_risk_score(29.9) == "LOW"
    assert classify_risk_score(30.0) == "MODERATE"
    assert classify_risk_score(59.9) == "MODERATE"
    assert classify_risk_score(60.0) == "HIGH"
    assert classify_risk_score(79.9) == "HIGH"
    assert classify_risk_score(80.0) == "CRITICAL"
    assert classify_risk_score(100.0) == "CRITICAL"


# ---------------------------------------------------------------------------
# Test 10: Calibration and held-out evaluation zero-leakage verification
# ---------------------------------------------------------------------------
def test_calibration_and_held_out_evaluation_zero_leakage():
    """Verify that metadata confirms zero cluster overlap and calibration on validation."""
    meta_path = os.path.join("ml", "artifacts", "metadata_v1.1.0.json")
    assert os.path.exists(meta_path), "metadata_v1.1.0.json missing"

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # 1. Leakage check
    leakage = meta["audit"]["split_leakage_check"]
    assert leakage["leakage_free"] is True
    assert leakage["train_val_overlap"] == 0
    assert leakage["train_test_overlap"] == 0
    assert leakage["val_test_overlap"] == 0

    # 2. Calibration methodology
    calib = meta["calibration_details"]
    assert "Platt" in calib["method"]
    assert "Validation split strictly" in calib["fitting_split"]
    assert calib["ece_improvement"]["calibrated_standard_lr"] < 0.02


# ---------------------------------------------------------------------------
# Test 11: Provisional status when validation evidence is insufficient (<10 words)
# ---------------------------------------------------------------------------
def test_provisional_status_when_evidence_insufficient():
    """Verify text with fewer than 10 informative words returns INSUFFICIENT_EVIDENCE."""
    engine = get_risk_engine()
    # 5 informative words
    short_text = "Hiring looking work apply now job"
    assert count_informative_words(short_text) < settings.MIN_INFORMATIVE_WORDS

    res = engine.analyze_job_text(short_text)
    assert res.risk_category == "INSUFFICIENT_EVIDENCE"
    assert res.risk_score is None
    assert res.ml_analysis is None
    assert "insufficient" in res.warning.lower()


# ---------------------------------------------------------------------------
# Test 12: Missing features and malformed inputs handled safely
# ---------------------------------------------------------------------------
def test_missing_features_and_malformed_inputs_handled_safely():
    """Verify that out-of-vocabulary and strange characters are handled gracefully."""
    ml_svc = get_ml_service()
    # Out of vocabulary words only
    oov_text = "xyzabc12345 qwerty98765 zzzqqqmmm 🦄 🌈 ⚡"
    res = ml_svc.analyze_text(oov_text)

    assert res.explanation_available is True
    # In an all-OOV text, all features x_j = 0, so sum(phi_j) = 0 and z = intercept
    assert res.is_reconciled is True
    assert abs(res.decision_score - res.intercept) < 1e-4
    assert len(res.top_positive_features) == 0
    assert len(res.top_negative_features) == 0


def test_high_severity_rule_safety_override_floor_behavior():
    """Verify that high-severity upfront fee rules enforce documented 65.0 and 85.0 floors."""
    engine = get_risk_engine()

    # Case 1: Compound fee + contact channel -> floor 85.0
    text_compound = (
        "Google is seeking a Senior Software Engineer with 10+ years experience in distributed systems, "
        "C++, Python, and cloud infrastructure. Generous 401k, health benefits, equity, and flexible PTO provided. "
        "Candidates must submit a $100 registration fee. Please contact hr on WhatsApp: +1234567890."
    )
    res_compound = engine.analyze_job_text(text_compound)
    assert res_compound.risk_score >= 85.0
    assert res_compound.risk_category == "CRITICAL"
    assert res_compound.override_floor_applied == "CRITICAL_COMPOUND_FEE_OVERRIDE_85"
    assert res_compound.override_floor_reason is not None
    assert "85.0" in res_compound.override_floor_reason

    # Case 2: Upfront fee alone -> floor 65.0
    text_fee_alone = (
        "We are hiring a warehouse assistant for evening shifts. Candidates must pay a $50 "
        "uniform and equipment fee before attending orientation."
    )
    res_fee_alone = engine.analyze_job_text(text_fee_alone)
    assert res_fee_alone.risk_score >= 65.0
    assert res_fee_alone.risk_category in ("HIGH", "CRITICAL")
    assert res_fee_alone.override_floor_applied == "HIGH_UPFRONT_FEE_OVERRIDE_65"
    assert "65.0" in res_fee_alone.override_floor_reason

    # Case 3: Legitimate text -> no floor applied
    text_legit = (
        "Senior Frontend Engineer wanted at high-growth tech company. 5+ years experience in React, "
        "TypeScript, Next.js, and automated testing. Competitive salary and healthcare benefits."
    )
    res_legit = engine.analyze_job_text(text_legit)
    assert res_legit.override_floor_applied is None
    assert res_legit.override_floor_reason is None


def test_reconciliation_sums_complete_feature_set():
    """Verify that total_feature_contribution reflects the complete vocabulary set."""
    ml_svc = get_ml_service()
    text = (
        "Senior Cloud Architect needed for enterprise migration. Must have deep experience in "
        "Kubernetes, AWS, Terraform, Docker, Python, microservices, and CI/CD pipelines."
    )
    res = ml_svc.analyze_text(text)
    assert res.explanation_available is True
    assert res.active_feature_count is not None
    assert res.active_feature_count > 0
    assert res.total_feature_contribution is not None

    # Check exact mathematical identity: intercept + total_feature_contribution == reconciled_score == decision_score
    reconciled = res.intercept + res.total_feature_contribution
    assert abs(reconciled - res.reconciled_score) < 1e-3
    assert abs(res.reconciled_score - res.decision_score) < 1e-4

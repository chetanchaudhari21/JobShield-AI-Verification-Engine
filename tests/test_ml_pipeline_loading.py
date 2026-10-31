"""ML Pipeline Loading and Preprocessing Acceptance Tests.

Verifies:
- Model bundle v1.1.0 integrity, component instances, and vocabulary dimensions.
- Text preprocessing parity between training and inference pipelines.
- Calibrated and primary prediction probability ranges and validation-tuned thresholds.
- Feature weight explainability structure.
- Strict isolation: failure on missing/corrupt artifacts without silent fallback to legacy v1.0.0.
"""

import os
import sys
import joblib
import pytest
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

# Ensure backend directory is in sys.path
backend_path = os.path.abspath("backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.config import settings
from app.services.ml_inference import (
    MLArtifactCorruptedError,
    MLInferenceService,
    MLInferenceUnavailableError,
    clean_text_for_inference,
    get_ml_service,
)


def test_ml_bundle_integrity_and_version():
    """Verify that the versioned v1.1.0 artifact exists and contains all required components."""
    artifact_path = os.path.abspath(settings.ML_MODEL_ARTIFACT_PATH)
    assert os.path.exists(artifact_path), f"Artifact missing at {artifact_path}"

    bundle = joblib.load(artifact_path)
    assert isinstance(bundle, dict), "Bundle must be a dictionary"
    assert bundle.get("version") == "v1.1.0", f"Unexpected version: {bundle.get('version')}"

    for required_key in ["vectorizer", "primary_classifier", "calibrated_classifier", "metadata"]:
        assert required_key in bundle, f"Bundle missing required key '{required_key}'"


def test_ml_components_instances_and_parameters():
    """Verify that bundle components match the approved architecture."""
    svc = get_ml_service()
    assert svc.is_available() is True
    assert svc.version == "v1.1.0"

    # 1. Vectorizer
    assert isinstance(svc.vectorizer, TfidfVectorizer)
    assert svc.vectorizer.sublinear_tf is True
    assert svc.vectorizer.max_features == 10000
    assert len(svc.vectorizer.get_feature_names_out()) <= 10000

    # 2. Primary Classifier (Balanced LR)
    assert isinstance(svc.primary_classifier, LogisticRegression)
    assert svc.primary_classifier.class_weight == "balanced"
    assert hasattr(svc.primary_classifier, "coef_")

    # 3. Calibrated Classifier (Platt-scaled Sigmoid)
    assert isinstance(svc.calibrated_classifier, CalibratedClassifierCV)
    assert svc.calibrated_classifier.method == "sigmoid"


def test_preprocessing_parity_with_training():
    """Verify that clean_text_for_inference matches training-time normalization."""
    # 1. HTML stripping
    html_sample = "<div><h1>Lead <b>Python</b> Engineer</h1><p>Join us &amp; code!</p></div>"
    cleaned = clean_text_for_inference(html_sample)
    assert "<" not in cleaned
    assert ">" not in cleaned
    assert "lead python engineer join us &amp; code!" == cleaned

    # 2. Whitespace collapsing
    messy_spaces = "Senior    Data    Scientist \n\n\t  Remote   "
    cleaned_spaces = clean_text_for_inference(messy_spaces)
    assert cleaned_spaces == "senior data scientist remote"

    # 3. Empty input handling
    assert clean_text_for_inference("") == ""
    assert clean_text_for_inference(None) == ""


def test_inference_probability_ranges_and_thresholds():
    """Verify inference probabilities are bounded in [0, 1] and thresholds match validation tuning."""
    svc = get_ml_service()
    text = """
    Senior Infrastructure Engineer. Deploying Terraform, Kubernetes, and Docker containers.
    Competitive salary 140,000 USD per year. Apply at https://careers.example.com.
    """
    result = svc.analyze_text(text)
    assert result is not None
    assert result.model_version == "v1.1.0"

    # Calibrated probability
    assert result.calibrated_probability is not None
    assert 0.0 <= result.calibrated_probability <= 1.0

    # Uncalibrated probability
    assert result.uncalibrated_probability is not None
    assert 0.0 <= result.uncalibrated_probability <= 1.0

    # Model thresholds
    assert result.primary_threshold == 0.62
    assert result.calibrated_threshold == 0.40
    assert result.decision_threshold == 0.40

    # Predictions
    assert result.primary_prediction in ("LEGITIMATE", "FRAUDULENT")
    assert result.calibrated_prediction in ("LEGITIMATE", "FRAUDULENT")


def test_explainable_top_features_structure():
    """Verify top feature explanations contain expected directions and numeric weights."""
    svc = get_ml_service()
    text = "Immediate urgent hiring! Earn $5000 daily from home. Pay registration fee deposit."
    result = svc.analyze_text(text, top_k_features=5)

    assert len(result.top_features) > 0
    assert len(result.top_features) <= 5

    for item in result.top_features:
        assert isinstance(item.feature, str)
        assert len(item.feature) > 0
        assert isinstance(item.weight, float)
        assert item.direction in ("fraud_indicative", "legitimate_indicative")


def test_strict_no_legacy_fallback_on_missing_artifact():
    """Verify that pointing to a missing path raises MLInferenceUnavailableError and never loads v1.0.0."""
    missing_svc = MLInferenceService(artifact_path="ml/artifacts/non_existent_bundle.joblib")
    assert missing_svc.is_available() is False
    assert missing_svc.version != "v1.0.0"

    with pytest.raises(MLInferenceUnavailableError):
        missing_svc.analyze_text("Senior Developer needed for active project.")


def test_corrupted_bundle_missing_keys_rejected(tmp_path):
    """Verify that a bundle missing required components is flagged and rejected."""
    corrupted_file = tmp_path / "corrupted_bundle.joblib"
    joblib.dump({"version": "v1.1.0", "vectorizer": None}, corrupted_file)

    broken_svc = MLInferenceService(artifact_path=str(corrupted_file))
    assert broken_svc.is_available() is False

    with pytest.raises(MLInferenceUnavailableError):
        broken_svc.analyze_text("Senior Developer needed for active project.")

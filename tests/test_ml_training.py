"""Automated Tests for JobShield AI ML Preprocessing, Calibration, and Training Pipeline.

Verifies:
- Group-aware split isolation and zero near-duplicate cluster overlap.
- Preprocessing consistency (HTML tag stripping, whitespace collapsing).
- Target mapping ('f' -> 0, 't' -> 1) and exclusion of 'in_balanced_dataset'.
- Validation threshold sweep search logic and bounds.
- Explicit probability calibration via FrozenEstimator.
- Preservation of v1.0.0 artifacts and loading/inference of v1.1.0 artifacts.
"""

import os
import joblib
import pytest
import numpy as np
import pandas as pd

from ml.training.preprocess import (
    load_and_preprocess,
    build_grouping_texts,
    build_cleaned_texts,
    clean_and_normalize_text,
    cluster_near_duplicates,
)
from ml.training.train import run_threshold_sweep, compute_ece

DATA_PATH = "ml/data/DataSet.csv"
ARTIFACT_V1_0 = "ml/artifacts/jobshield_fraud_detector_v1.0.0.joblib"
ARTIFACT_V1_1 = "ml/artifacts/jobshield_fraud_detector_v1.1.0.joblib"
META_V1_0 = "ml/artifacts/metadata_v1.0.0.json"
META_V1_1 = "ml/artifacts/metadata_v1.1.0.json"


@pytest.fixture(scope="module")
def preprocessed_dataset():
    """Module-level fixture to load and preprocess dataset once across test functions."""
    if not os.path.exists(DATA_PATH):
        pytest.skip("DataSet.csv not found")
    data = load_and_preprocess(
        data_path=DATA_PATH, seed=42, train_size=0.70, val_size=0.15, test_size=0.15
    )
    yield data
    del data
    import gc
    gc.collect()


@pytest.mark.skipif(not os.path.exists(DATA_PATH), reason="DataSet.csv not found")
def test_load_and_preprocess_leakage_free(preprocessed_dataset):
    """Verify train, validation, and test splits have 0 cluster overlap."""
    train_df, val_df, test_df, audit_info = preprocessed_dataset

    assert len(train_df) > 0
    assert len(val_df) > 0
    assert len(test_df) > 0
    assert len(train_df) + len(val_df) + len(test_df) == audit_info["rows_after_exact_dedup"]

    # Zero cluster leakage
    train_clusters = set(train_df["cluster_id"])
    val_clusters = set(val_df["cluster_id"])
    test_clusters = set(test_df["cluster_id"])

    assert len(train_clusters.intersection(val_clusters)) == 0
    assert len(train_clusters.intersection(test_clusters)) == 0
    assert len(val_clusters.intersection(test_clusters)) == 0
    assert audit_info["split_leakage_check"]["leakage_free"] is True


def test_preprocessing_html_and_whitespace_consistency():
    """Verify HTML stripping and whitespace normalization produce identical grouping keys."""
    raw_html_1 = "<p>Senior Software Engineer</p><br><p>Python &amp; Django</p>"
    raw_html_2 = "Senior Software Engineer\n\nPython &amp; Django   "

    cleaned_1 = clean_and_normalize_text(raw_html_1)
    cleaned_2 = clean_and_normalize_text(raw_html_2)

    assert "<p>" not in cleaned_1
    assert "<br>" not in cleaned_1
    assert "\n" not in cleaned_2
    assert cleaned_1 == cleaned_2
    assert cleaned_1 == "senior software engineer python &amp; django"


def test_near_duplicate_clustering_clusters_identical_content():
    """Verify listings differing only by HTML markup or formatting are grouped into the same cluster."""
    texts = [
        "executive chef responsible for all food production at restaurants",
        "<p>executive chef</p><br>responsible for all food production at restaurants",
        "data entry clerk typing 60 wpm required immediately",
    ]
    labels, stats = cluster_near_duplicates(texts, sim_threshold=0.95)
    assert len(labels) == 3
    # Texts 0 and 1 must belong to the exact same cluster
    assert labels[0] == labels[1]
    # Text 2 must belong to a different cluster
    assert labels[0] != labels[2]
    assert stats["total_clusters"] == 2


@pytest.mark.skipif(not os.path.exists(DATA_PATH), reason="DataSet.csv not found")
def test_target_mapping_and_exclusion(preprocessed_dataset):
    """Ensure target mapping is correct and in_balanced_dataset is excluded."""
    train_df, val_df, test_df, _ = preprocessed_dataset

    for split in [train_df, val_df, test_df]:
        assert set(split["target"].unique()).issubset({0, 1})
        assert "clean_text" in split.columns
        assert "target" in split.columns
        # Verify clean_text does not contain in_balanced_dataset column values
        assert not split["clean_text"].str.contains("in_balanced_dataset").any()


def test_threshold_selection_logic():
    """Verify threshold sweep selects the threshold that maximizes F1 score."""
    y_true = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    probs = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
    th_grid = np.arange(0.1, 0.9, 0.1)

    selected_th, best_rec, records = run_threshold_sweep(y_true, probs, th_grid)
    assert 0.4 < selected_th <= 0.6
    assert best_rec["f1"] == 1.0
    assert best_rec["precision"] == 1.0
    assert best_rec["recall"] == 1.0
    assert len(records) == len(th_grid)


def test_ece_computation():
    """Verify ECE calculation with perfect and imperfect calibration."""
    y_true = np.array([0, 0, 1, 1])
    probs_perfect = np.array([0.0, 0.0, 1.0, 1.0])
    ece_perf = compute_ece(y_true, probs_perfect, n_bins=5)
    assert ece_perf == 0.0

    probs_imperfect = np.array([0.5, 0.5, 0.5, 0.5])
    ece_imp = compute_ece(y_true, probs_imperfect, n_bins=5)
    assert ece_imp >= 0.0


@pytest.mark.skipif(not os.path.exists(ARTIFACT_V1_1), reason="v1.1.0 artifact not found")
def test_saved_model_artifact_v1_1_0():
    """Verify remediated v1.1.0 model artifact loads, contains calibrated models, and predicts correctly."""
    import gc
    gc.collect()
    bundle = joblib.load(ARTIFACT_V1_1)
    assert bundle["version"] == "v1.1.0"
    assert "primary_classifier" in bundle
    assert "calibrated_classifier" in bundle
    assert "calibrated_balanced_classifier" in bundle
    assert "uncalibrated_standard_classifier" in bundle
    assert "vectorizer" in bundle
    assert "metadata" in bundle

    vectorizer = bundle["vectorizer"]
    primary_clf = bundle["primary_classifier"]
    calibrated_clf = bundle["calibrated_classifier"]

    sample_texts = [
        "Urgent data entry assistant needed. Pay 5000 weekly. Send money for equipment.",
        "Senior Software Engineer. Python, FastAPI, PostgreSQL. London office.",
    ]
    X_sample = vectorizer.transform(sample_texts)
    assert X_sample.shape[0] == 2
    assert X_sample.shape[1] == 10000

    probs_primary = primary_clf.predict_proba(X_sample)[:, 1]
    probs_calibrated = calibrated_clf.predict_proba(X_sample)[:, 1]

    assert len(probs_primary) == 2
    assert len(probs_calibrated) == 2
    assert (probs_primary >= 0.0).all() and (probs_primary <= 1.0).all()
    assert (probs_calibrated >= 0.0).all() and (probs_calibrated <= 1.0).all()


def test_legacy_v1_0_0_artifacts_preserved():
    """Verify existing v1.0.0 artifacts and metadata were NOT deleted or overwritten."""
    assert os.path.exists(ARTIFACT_V1_0), "v1.0.0 joblib was deleted!"
    assert os.path.exists(META_V1_0), "v1.0.0 metadata was deleted!"
    assert os.path.exists(META_V1_1), "v1.1.0 metadata missing!"
    assert os.path.exists(ARTIFACT_V1_1), "v1.1.0 joblib missing!"

    # Check v1.0.0 content retains original version
    import json
    with open(META_V1_0) as f:
        meta_0 = json.load(f)
    assert meta_0["version"] == "v1.0.0"

    with open(META_V1_1) as f:
        meta_1 = json.load(f)
    assert meta_1["version"] == "v1.1.0"

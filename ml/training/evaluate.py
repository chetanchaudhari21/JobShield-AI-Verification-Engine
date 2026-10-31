"""Evaluation and Verification CLI for JobShield AI ML Artifacts.

Loads saved bundle from ml/artifacts/ (default v1.1.0) and outputs measured evaluation
metrics, confusion matrix, ROC-AUC, PR-AUC, and probability calibration checks.
"""

import os
import sys
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    roc_auc_score,
    average_precision_score,
    brier_score_loss,
)
from sklearn.calibration import calibration_curve

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath("."))

from ml.training.preprocess import load_and_preprocess

DEFAULT_ARTIFACT = os.path.join("ml", "artifacts", "jobshield_fraud_detector_v1.1.0.joblib")
LEGACY_ARTIFACT = os.path.join("ml", "artifacts", "jobshield_fraud_detector_v1.0.0.joblib")


def evaluate_saved_model(artifact_path: str = DEFAULT_ARTIFACT, data_path: str = "ml/data/DataSet.csv"):
    """Load model artifact and evaluate on holdout test set."""
    if not os.path.exists(artifact_path):
        raise FileNotFoundError(f"Artifact not found at {artifact_path}. Run ml/training/train.py first.")

    print(f"Loading artifact from: {artifact_path}")
    bundle = joblib.load(artifact_path)
    version = bundle.get("version", "v1.0.0")
    primary_model = bundle["primary_classifier"]
    calibrated_model = bundle["calibrated_classifier"]
    vectorizer = bundle["vectorizer"]
    metadata = bundle["metadata"]

    print(f"Re-creating test holdout using reproducible seed 42 ({version})...")
    _, _, test_df, _ = load_and_preprocess(data_path=data_path, seed=42)

    X_test = vectorizer.transform(test_df["clean_text"])
    y_test = test_df["target"].values

    print("\n" + "=" * 65)
    print(f"[{version}] PRIMARY MODEL: Balanced Logistic Regression (Fraud Screening)")
    print("=" * 65)
    th_bal = metadata["primary_model_metrics"]["threshold"]
    probs_bal = primary_model.predict_proba(X_test)[:, 1]
    preds_bal = (probs_bal >= th_bal).astype(int)

    p_bal = precision_score(y_test, preds_bal, zero_division=0)
    r_bal = recall_score(y_test, preds_bal, zero_division=0)
    f1_bal = f1_score(y_test, preds_bal, zero_division=0)
    pr_bal = average_precision_score(y_test, probs_bal)
    roc_bal = roc_auc_score(y_test, probs_bal)
    cm_bal = confusion_matrix(y_test, preds_bal)
    brier_bal = brier_score_loss(y_test, probs_bal)

    print(f"Decision Threshold: {th_bal:.2f}")
    print(f"Precision:          {p_bal:.4f} ({p_bal * 100:.2f}%)")
    print(f"Recall:             {r_bal:.4f} ({r_bal * 100:.2f}%)")
    print(f"F1-Score:           {f1_bal:.4f}")
    print(f"PR-AUC (AP):        {pr_bal:.4f}")
    print(f"ROC-AUC:            {roc_bal:.4f}")
    print(f"Brier Score Loss:   {brier_bal:.4f}")
    print(f"Confusion Matrix:\n{cm_bal}")
    print(f"  [TN={cm_bal[0,0]}, FP={cm_bal[0,1]}]")
    print(f"  [FN={cm_bal[1,0]}, TP={cm_bal[1,1]}]")

    print("\n" + "=" * 65)
    print(f"[{version}] CALIBRATED MODEL: Calibrated Classifier (Risk Engine)")
    print("=" * 65)
    th_std = metadata["calibrated_model_metrics"]["threshold"]
    probs_std = calibrated_model.predict_proba(X_test)[:, 1]
    preds_std = (probs_std >= th_std).astype(int)

    p_std = precision_score(y_test, preds_std, zero_division=0)
    r_std = recall_score(y_test, preds_std, zero_division=0)
    f1_std = f1_score(y_test, preds_std, zero_division=0)
    pr_std = average_precision_score(y_test, probs_std)
    roc_std = roc_auc_score(y_test, probs_std)
    cm_std = confusion_matrix(y_test, preds_std)
    brier_std = brier_score_loss(y_test, probs_std)

    print(f"Decision Threshold: {th_std:.2f}")
    print(f"Precision:          {p_std:.4f} ({p_std * 100:.2f}%)")
    print(f"Recall:             {r_std:.4f} ({r_std * 100:.2f}%)")
    print(f"F1-Score:           {f1_std:.4f}")
    print(f"PR-AUC (AP):        {pr_std:.4f}")
    print(f"ROC-AUC:            {roc_std:.4f}")
    print(f"Brier Score Loss:   {brier_std:.4f}")
    print(f"Confusion Matrix:\n{cm_std}")
    print(f"  [TN={cm_std[0,0]}, FP={cm_std[0,1]}]")
    print(f"  [FN={cm_std[1,0]}, TP={cm_std[1,1]}]")

    print(f"\nCalibration Check ({version} Calibrated Model):")
    frac_pos, mean_pred = calibration_curve(y_test, probs_std, n_bins=10, strategy="uniform")
    for cp, fp in zip(mean_pred, frac_pos):
        print(f"  Mean Pred Prob: {cp:.4f} -> Fraction True Positive: {fp:.4f}")

    return {
        "version": version,
        "primary": {"precision": p_bal, "recall": r_bal, "f1": f1_bal, "pr_auc": pr_bal, "roc_auc": roc_bal},
        "calibrated": {"precision": p_std, "recall": r_std, "f1": f1_std, "pr_auc": pr_std, "roc_auc": roc_std},
    }


if __name__ == "__main__":
    target_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ARTIFACT
    evaluate_saved_model(artifact_path=target_path)

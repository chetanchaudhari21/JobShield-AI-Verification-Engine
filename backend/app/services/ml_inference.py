"""Machine Learning Inference Service for JobShield AI.

Loads the versioned baseline model bundle, cleans incoming text without leakage,
evaluates calibrated posterior probabilities and primary screening predictions,
and generates local linear model explanations (feature contributions).
"""

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Union
import joblib
import numpy as np

from app.core.config import settings
from app.schemas.analysis import FeatureContribution, MLAnalysisResult
from app.services.ml_explainer import (
    EXPLANATION_DISCLAIMER,
    explain_prediction,
    explain_linear_prediction,
    explain_with_shap,
)

logger = logging.getLogger("jobshield.ml")

HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def clean_text_for_inference(text: str) -> str:
    """Strips HTML markup and collapses extraneous whitespace matching training preprocessing."""
    if not text:
        return ""
    stripped = HTML_TAG_RE.sub(" ", str(text).lower())
    return WHITESPACE_RE.sub(" ", stripped).strip()


class MLServiceError(Exception):
    """Base exception for ML service failures."""
    pass


class MLArtifactNotFoundError(MLServiceError):
    """Raised when model artifact cannot be found at configured path."""
    pass


class MLArtifactCorruptedError(MLServiceError):
    """Raised when model artifact is corrupted or missing required keys."""
    pass


class MLInferenceUnavailableError(MLServiceError):
    """Raised when inference is called but ML model is not available."""
    pass


class MLInferenceService:
    """Singleton service for loading versioned model artifacts and running predictions."""

    _instance: Optional["MLInferenceService"] = None

    def __init__(self, artifact_path: Optional[str] = None):
        self.artifact_path = artifact_path or settings.ML_MODEL_ARTIFACT_PATH
        self.bundle: Optional[Dict[str, Any]] = None
        self.version: str = "unknown"
        self.vectorizer = None
        self.primary_classifier = None
        self.calibrated_classifier = None
        self.primary_threshold: float = 0.62
        self.calibrated_threshold: float = 0.40
        self._load_error: Optional[str] = None
        self._last_sync_check: float = 0.0
        self.sync_interval_seconds: float = 2.0
        self.load_model()

    @classmethod
    def get_instance(cls) -> "MLInferenceService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Resets the singleton instance (primarily for tests)."""
        cls._instance = None

    def sync_active_model_from_db(self, db: Optional[Any] = None, force: bool = False) -> bool:
        """Synchronizes in-memory model state with the database's currently active ModelVersion.

        Ensures that in a multi-worker API deployment (e.g. Uvicorn with multiple worker processes),
        all worker processes detect atomic deployments and rollbacks without process restarts.
        """
        now = time.time()
        if not force and (now - getattr(self, "_last_sync_check", 0.0) < getattr(self, "sync_interval_seconds", 2.0)):
            return False
        self._last_sync_check = now

        if db is not None:
            return self._sync_with_session(db)
        else:
            try:
                from app.db.session import SessionLocal
                with SessionLocal() as session:
                    return self._sync_with_session(session)
            except Exception as exc:
                logger.debug("Automatic multi-process model sync query bypassed: %s", exc)
                return False

    def _sync_with_session(self, session: Any) -> bool:
        try:
            from app.models.ml import ModelVersion
            active = session.query(ModelVersion).filter(ModelVersion.evaluation_status == "active").first()
            if active and (active.version != self.version or active.artifact_path != self.artifact_path):
                logger.info(
                    "Multi-process sync: active model changed in DB from %s to %s (%s). Reloading...",
                    self.version,
                    active.version,
                    active.artifact_path,
                )
                self.artifact_path = active.artifact_path
                self.load_model()
                return True
        except Exception as exc:
            logger.debug("Failed checking active model from DB: %s", exc)
        return False

    def load_model(self) -> None:
        """Loads configured joblib bundle from disk.

        STRICT VERSION GUARANTEE: Never silently falls back to legacy v1.0.0 artifacts.
        Only loads the explicitly configured path in settings.ML_MODEL_ARTIFACT_PATH.
        """
        resolved_path = os.path.abspath(self.artifact_path)
        if not os.path.exists(resolved_path):
            self._load_error = f"ML model artifact not found at {resolved_path}."
            logger.error(self._load_error)
            self.bundle = None
            return

        try:
            logger.info("Loading ML artifact bundle from %s", resolved_path)
            loaded = joblib.load(resolved_path)
            if not isinstance(loaded, dict):
                raise ValueError("Artifact file does not contain a valid dictionary bundle.")

            required_keys = ["vectorizer", "primary_classifier", "calibrated_classifier"]
            missing = [k for k in required_keys if k not in loaded or loaded[k] is None]
            if missing:
                raise ValueError(f"Artifact bundle is corrupted; missing required components: {missing}")

            self.bundle = loaded
            self.version = (
                self.bundle.get("version")
                or self.bundle.get("metadata", {}).get("version")
                or ("v1.0.0" if "v1.0.0" in self.artifact_path else "v1.1.0")
            )
            self.vectorizer = self.bundle["vectorizer"]
            self.primary_classifier = self.bundle["primary_classifier"]
            self.calibrated_classifier = self.bundle["calibrated_classifier"]

            # Extract validation-tuned thresholds from metadata
            metadata = self.bundle.get("metadata", {})
            if "primary_model_metrics" in metadata:
                self.primary_threshold = float(metadata["primary_model_metrics"].get("threshold", 0.62))
            else:
                self.primary_threshold = 0.62

            if "calibrated_model_metrics" in metadata:
                self.calibrated_threshold = float(metadata["calibrated_model_metrics"].get("threshold", 0.40))
            else:
                self.calibrated_threshold = 0.40

            self._load_error = None
            logger.info(
                "Successfully loaded ML model version %s (primary_th=%.2f, cal_th=%.2f)",
                self.version,
                self.primary_threshold,
                self.calibrated_threshold,
            )
        except Exception as exc:
            self._load_error = f"Failed to load ML artifact bundle: {type(exc).__name__}"
            logger.error(self._load_error)
            self.bundle = None
            self.vectorizer = None
            self.primary_classifier = None
            self.calibrated_classifier = None

    def is_available(self) -> bool:
        return (
            self.bundle is not None
            and self.vectorizer is not None
            and self.primary_classifier is not None
            and self.calibrated_classifier is not None
        )

    def analyze_text(
        self,
        raw_text: str,
        top_k_features: int = 6,
        explanation_method: str = "auto",
        target_class: Union[int, str] = "FRAUDULENT",
    ) -> MLAnalysisResult:
        """Runs vectorization, inference, and explainability on raw job text.

        Raises MLInferenceUnavailableError if the model artifact failed to load or is missing.
        Never silently substitutes legacy models or returns null when inference is requested.
        """
        self.sync_active_model_from_db()

        if not self.is_available():
            self.sync_active_model_from_db(force=True)
            if not self.is_available():
                error_reason = self._load_error or "ML model artifact is not loaded or unavailable."
                raise MLInferenceUnavailableError(error_reason)

        cleaned_text = clean_text_for_inference(raw_text)
        if not cleaned_text:
            raise ValueError("Job text cannot be empty after HTML stripping and whitespace normalization.")

        try:
            X = self.vectorizer.transform([cleaned_text])

            # 1. Primary Model Prediction (Balanced LR, tuned threshold 0.62)
            primary_probs = self.primary_classifier.predict_proba(X)[0]
            primary_prob_fraud = float(primary_probs[1])
            primary_pred = "FRAUDULENT" if primary_prob_fraud >= self.primary_threshold else "LEGITIMATE"

            # 2. Calibrated Model Probability (Platt-scaled Standard LR, tuned threshold 0.40)
            calibrated_probs = self.calibrated_classifier.predict_proba(X)[0]
            calibrated_prob_fraud = float(calibrated_probs[1])
            calibrated_pred = "FRAUDULENT" if calibrated_prob_fraud >= self.calibrated_threshold else "LEGITIMATE"

            # 3. Explainability: Linear Coefficients or SHAP (Feature F6)
            explanation = explain_prediction(
                classifier=self.primary_classifier,
                vectorizer=self.vectorizer,
                cleaned_text=cleaned_text,
                method=explanation_method,
                target_class=target_class,
                top_k=top_k_features,
            )

            top_features = [
                FeatureContribution(**f) for f in explanation.get("top_features", [])
            ]
            top_positive = [
                FeatureContribution(**f) for f in explanation.get("top_positive_features", [])
            ]
            top_negative = [
                FeatureContribution(**f) for f in explanation.get("top_negative_features", [])
            ]

            return MLAnalysisResult(
                model_version=self.version,
                model_name="JobShield AI Text Fraud Classifier Baseline",
                primary_prediction=primary_pred,
                calibrated_prediction=calibrated_pred,
                calibrated_probability=round(calibrated_prob_fraud, 4),
                uncalibrated_probability=round(primary_prob_fraud, 4),
                primary_threshold=self.primary_threshold,
                calibrated_threshold=self.calibrated_threshold,
                decision_threshold=self.calibrated_threshold,
                calibration_method="Platt Scaling (Sigmoid) via FrozenEstimator on Validation Data",
                score_type=explanation.get("score_type", "log_odds_decision_score"),
                target_class=explanation.get("target_class", "FRAUDULENT"),
                intercept=explanation.get("intercept"),
                decision_score=explanation.get("decision_score"),
                reconciled_score=explanation.get("reconciled_score"),
                is_reconciled=explanation.get("is_reconciled", True),
                explanation_method=explanation.get("explanation_method", "LOGISTIC_REGRESSION_COEFFICIENTS"),
                explanation_available=explanation.get("explanation_available", True),
                explanation_unavailable_reason=explanation.get("explanation_unavailable_reason"),
                top_features=top_features,
                top_positive_features=top_positive,
                top_negative_features=top_negative,
                active_feature_count=explanation.get("active_feature_count", len(explanation.get("top_features", []))),
                total_feature_contribution=explanation.get("total_feature_contribution"),
                explanation_disclaimer=explanation.get("explanation_disclaimer", EXPLANATION_DISCLAIMER),
            )
        except Exception as exc:
            if isinstance(exc, MLServiceError):
                raise
            logger.error("ML inference execution failed: %s", type(exc).__name__)
            raise MLServiceError(f"Inference execution failed: {type(exc).__name__}") from exc


def get_ml_service() -> MLInferenceService:
    """Dependency / accessor for singleton MLInferenceService."""
    return MLInferenceService.get_instance()

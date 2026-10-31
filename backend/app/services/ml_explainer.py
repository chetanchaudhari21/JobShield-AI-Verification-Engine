"""Explainable AI (XAI) Engine for JobShield AI (Feature F6).

Provides rigorous, mathematically grounded explanations for model predictions:
1. Exact Linear Model log-odds feature contributions:
   - Evaluates phi_j = w_j * x_j in the transformed TF-IDF feature space.
   - Incorporates model intercept b.
   - Reconciles sum(phi_j) + b == decision_function(X) within numerical tolerance.
   - Supports binary and multiclass estimators with class-specific attribution.
   - Distinguishes log-odds contributions from final calibrated posterior probabilities.
2. SHAP (SHapley Additive exPlanations) for supported estimators:
   - Validates model architecture compatibility before applying SHAP.
   - Strictly rejects unsupported estimators with an honest unavailable state.
3. Separation of Concerns:
   - Purely model-derived; never mislabels heuristic rules as ML contributions.
   - Strictly attaches statutory non-intent / non-proof disclaimers.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import scipy.sparse as sp

logger = logging.getLogger("jobshield.xai")

EXPLANATION_DISCLAIMER = (
    "These contributions describe how input features influenced this model's output. "
    "They do not establish intent, prove fraud, or independently verify the authenticity of a job offer."
)


def explain_linear_prediction(
    classifier: Any,
    vectorizer: Any,
    cleaned_text: str,
    target_class: Union[int, str] = "FRAUDULENT",
    top_k: int = 6,
) -> Dict[str, Any]:
    """Computes exact linear model log-odds feature contributions and validates reconciliation.

    For a linear model:
        decision_score(x) = sum_j (w_j * x_j) + intercept
    Each feature contribution phi_j = w_j * x_j represents the change in log-odds.
    """
    if not hasattr(classifier, "coef_") or not hasattr(classifier, "intercept_"):
        return {
            "explanation_available": False,
            "explanation_unavailable_reason": (
                f"Active model '{type(classifier).__name__}' does not provide linear coefficients."
            ),
            "top_features": [],
            "top_positive_features": [],
            "top_negative_features": [],
            "explanation_method": "UNAVAILABLE",
            "score_type": "decision_score",
            "target_class": str(target_class),
            "intercept": None,
            "decision_score": None,
            "reconciled_score": None,
            "is_reconciled": False,
            "explanation_disclaimer": EXPLANATION_DISCLAIMER,
        }

    # Transform input into feature space
    if sp.issparse(vectorizer) or isinstance(vectorizer, np.ndarray):
        X = vectorizer
        feature_names = np.array(cleaned_text) if isinstance(cleaned_text, (list, np.ndarray)) else np.array([])
    elif hasattr(vectorizer, "transform"):
        if not cleaned_text or (isinstance(cleaned_text, str) and not cleaned_text.strip()):
            return {
                "explanation_available": False,
                "explanation_unavailable_reason": "Explanation unavailable: input text is empty after normalization.",
                "top_features": [],
                "top_positive_features": [],
                "top_negative_features": [],
                "explanation_method": "LOGISTIC_REGRESSION_COEFFICIENTS",
                "score_type": "log_odds_decision_score",
                "target_class": str(target_class),
                "intercept": None,
                "decision_score": None,
                "reconciled_score": None,
                "is_reconciled": False,
                "explanation_disclaimer": EXPLANATION_DISCLAIMER,
            }
        X = vectorizer.transform([cleaned_text])
        feature_names = vectorizer.get_feature_names_out()
    else:
        return {
            "explanation_available": False,
            "explanation_unavailable_reason": "Explanation unavailable: invalid vectorizer or feature input.",
            "top_features": [],
            "top_positive_features": [],
            "top_negative_features": [],
            "explanation_method": "LOGISTIC_REGRESSION_COEFFICIENTS",
            "score_type": "log_odds_decision_score",
            "target_class": str(target_class),
            "intercept": None,
            "decision_score": None,
            "reconciled_score": None,
            "is_reconciled": False,
            "explanation_disclaimer": EXPLANATION_DISCLAIMER,
        }

    # Determine class index and coefficients
    coef_matrix = classifier.coef_
    intercept_vector = classifier.intercept_
    classes = getattr(classifier, "classes_", np.array([0, 1]))
    n_classes = len(classes)

    # Class resolution
    class_idx = 1
    class_name = "FRAUDULENT"
    is_binary = n_classes == 2 and coef_matrix.shape[0] == 1

    if is_binary:
        if isinstance(target_class, str):
            if target_class.upper() in ("LEGITIMATE", "0", "FALSE", "NEG"):
                class_idx = 0
                class_name = "LEGITIMATE"
            else:
                class_idx = 1
                class_name = "FRAUDULENT"
        elif target_class == 0:
            class_idx = 0
            class_name = "LEGITIMATE"
        else:
            class_idx = 1
            class_name = "FRAUDULENT"

        raw_coefs = coef_matrix[0]
        raw_intercept = float(intercept_vector[0])

        if class_idx == 1:
            w = raw_coefs
            b = raw_intercept
            dec_score = float(classifier.decision_function(X)[0])
        else:
            w = -raw_coefs
            b = -raw_intercept
            dec_score = -float(classifier.decision_function(X)[0])
    else:
        # Multiclass model (e.g. 3 or more classes)
        if isinstance(target_class, int) and 0 <= target_class < n_classes:
            class_idx = target_class
            class_name = str(classes[class_idx])
        elif isinstance(target_class, str):
            matched_indices = [i for i, c in enumerate(classes) if str(c).upper() == target_class.upper()]
            if matched_indices:
                class_idx = matched_indices[0]
                class_name = str(classes[class_idx])
            else:
                # Default to predicted class
                class_idx = int(classifier.predict(X)[0])
                class_name = str(classes[class_idx])
        else:
            class_idx = int(classifier.predict(X)[0])
            class_name = str(classes[class_idx])

        w = coef_matrix[class_idx]
        b = float(intercept_vector[class_idx])
        all_dec_scores = classifier.decision_function(X)[0]
        dec_score = float(all_dec_scores[class_idx])

    # Extract non-zero tokens from sparse vector
    coo = X.tocoo()
    contributions: List[Dict[str, Any]] = []
    total_feature_contrib = 0.0

    for col_idx, tfidf_val in zip(coo.col, coo.data):
        token = str(feature_names[col_idx])
        coef_val = float(w[col_idx])
        contrib_val = float(coef_val * tfidf_val)
        total_feature_contrib += contrib_val

        direction = "fraud_indicative" if contrib_val > 0 else "legitimate_indicative"
        direction_label = "increases model score" if contrib_val > 0 else "decreases model score"
        sign = "+" if contrib_val > 0 else "-"

        contributions.append({
            "feature": token,
            "weight": round(contrib_val, 4),
            "direction": direction,
            "feature_value": round(float(tfidf_val), 4),
            "coefficient": round(coef_val, 4),
            "contribution": round(contrib_val, 4),
            "direction_label": direction_label,
            "sign": sign,
        })

    # Exact mathematical reconciliation
    reconciled_score = float(b + total_feature_contrib)
    reconciliation_error = abs(dec_score - reconciled_score)
    is_reconciled = reconciliation_error < 1e-4

    # Top positive (increasing fraud log-odds)
    positives = [c for c in contributions if c["contribution"] > 0]
    positives.sort(key=lambda x: x["contribution"], reverse=True)
    top_positives = positives[:top_k]

    # Top negative (decreasing fraud log-odds, i.e. strongest legitimate influence)
    negatives = [c for c in contributions if c["contribution"] < 0]
    negatives.sort(key=lambda x: x["contribution"])
    top_negatives = negatives[:top_k]

    # Combined top features sorted by absolute magnitude (preserves backward compatibility)
    all_sorted = sorted(contributions, key=lambda x: abs(x["contribution"]), reverse=True)
    top_combined = all_sorted[:top_k]

    return {
        "explanation_available": True,
        "explanation_unavailable_reason": None,
        "explanation_method": "LOGISTIC_REGRESSION_COEFFICIENTS",
        "score_type": "log_odds_decision_score",
        "target_class": class_name,
        "intercept": round(b, 4),
        "decision_score": round(dec_score, 4),
        "reconciled_score": round(reconciled_score, 4),
        "reconciliation_error": round(reconciliation_error, 6),
        "is_reconciled": is_reconciled,
        "top_features": top_combined,
        "top_positive_features": top_positives,
        "top_negative_features": top_negatives,
        "total_active_features": len(contributions),
        "active_feature_count": len(contributions),
        "total_feature_contribution": round(total_feature_contrib, 4),
        "explanation_disclaimer": EXPLANATION_DISCLAIMER,
    }


def explain_with_shap(
    classifier: Any,
    vectorizer: Any,
    cleaned_text: str,
    target_class: Union[int, str] = "FRAUDULENT",
    top_k: int = 6,
) -> Dict[str, Any]:
    """Computes Shapley values using SHAP for supported estimators."""
    try:
        import shap
    except ImportError:
        return {
            "explanation_available": False,
            "explanation_unavailable_reason": "Explanation unavailable: 'shap' library is not installed in the environment.",
            "top_features": [],
            "top_positive_features": [],
            "top_negative_features": [],
            "explanation_method": "SHAP",
            "score_type": "decision_score",
            "target_class": str(target_class),
            "intercept": None,
            "decision_score": None,
            "reconciled_score": None,
            "is_reconciled": False,
            "explanation_disclaimer": EXPLANATION_DISCLAIMER,
        }

    # Verify estimator compatibility
    # SHAP LinearExplainer supports LogisticRegression, Ridge, Lasso, ElasticNet, SGDClassifier
    is_linear = hasattr(classifier, "coef_") and hasattr(classifier, "intercept_")
    is_tree = hasattr(classifier, "tree_") or "Tree" in type(classifier).__name__ or "Forest" in type(classifier).__name__

    if not is_linear and not is_tree:
        return {
            "explanation_available": False,
            "explanation_unavailable_reason": (
                f"Explanation unavailable for estimator '{type(classifier).__name__}': "
                "SHAP explainer is not supported or computationally practical for this model architecture."
            ),
            "top_features": [],
            "top_positive_features": [],
            "top_negative_features": [],
            "explanation_method": "UNAVAILABLE",
            "score_type": "decision_score",
            "target_class": str(target_class),
            "intercept": None,
            "decision_score": None,
            "reconciled_score": None,
            "is_reconciled": False,
            "explanation_disclaimer": EXPLANATION_DISCLAIMER,
        }

    # Transform input into feature space
    if sp.issparse(vectorizer) or isinstance(vectorizer, np.ndarray):
        X = vectorizer
        feature_names = np.array(cleaned_text) if isinstance(cleaned_text, (list, np.ndarray)) else np.array([])
    elif hasattr(vectorizer, "transform"):
        if not cleaned_text or (isinstance(cleaned_text, str) and not cleaned_text.strip()):
            return {
                "explanation_available": False,
                "explanation_unavailable_reason": "Explanation unavailable: input text is empty after normalization.",
                "top_features": [],
                "top_positive_features": [],
                "top_negative_features": [],
                "explanation_method": "SHAP",
                "score_type": "decision_score",
                "target_class": str(target_class),
                "intercept": None,
                "decision_score": None,
                "reconciled_score": None,
                "is_reconciled": False,
                "explanation_disclaimer": EXPLANATION_DISCLAIMER,
            }
        X = vectorizer.transform([cleaned_text])
        feature_names = vectorizer.get_feature_names_out()
    else:
        return {
            "explanation_available": False,
            "explanation_unavailable_reason": "Explanation unavailable: invalid vectorizer or feature input.",
            "top_features": [],
            "top_positive_features": [],
            "top_negative_features": [],
            "explanation_method": "SHAP",
            "score_type": "decision_score",
            "target_class": str(target_class),
            "intercept": None,
            "decision_score": None,
            "reconciled_score": None,
            "is_reconciled": False,
            "explanation_disclaimer": EXPLANATION_DISCLAIMER,
        }

    try:
        n_features = len(feature_names)

        # Use an independent zero-reference background for sparse text bag-of-words
        background = sp.csr_matrix((1, n_features), dtype=np.float64)

        if is_linear:
            explainer = shap.LinearExplainer(classifier, background)
            shap_values = explainer(X)
            # In binary linear explainer: values shape is (1, n_features), base_values is (1,)
            values = shap_values.values[0]
            base_val = float(shap_values.base_values[0])
            dec_score = float(classifier.decision_function(X)[0])
        else:
            explainer = shap.TreeExplainer(classifier)
            shap_values = explainer(X)
            values = shap_values.values[0]
            base_val = float(shap_values.base_values[0])
            dec_score = float(classifier.predict_proba(X)[0, 1])

        coo = X.tocoo()
        contributions: List[Dict[str, Any]] = []
        total_shap = 0.0

        for col_idx in coo.col:
            token = str(feature_names[col_idx])
            s_val = float(values[col_idx])
            total_shap += s_val
            tfidf_val = float(X[0, col_idx])

            direction = "fraud_indicative" if s_val > 0 else "legitimate_indicative"
            direction_label = "increases model score" if s_val > 0 else "decreases model score"
            sign = "+" if s_val > 0 else "-"

            contributions.append({
                "feature": token,
                "weight": round(s_val, 4),
                "direction": direction,
                "feature_value": round(tfidf_val, 4),
                "coefficient": None,
                "contribution": round(s_val, 4),
                "direction_label": direction_label,
                "sign": sign,
            })

        reconciled_score = float(base_val + total_shap)
        reconciliation_error = abs(dec_score - reconciled_score)
        is_reconciled = reconciliation_error < 1e-4

        positives = [c for c in contributions if c["contribution"] > 0]
        positives.sort(key=lambda x: x["contribution"], reverse=True)

        negatives = [c for c in contributions if c["contribution"] < 0]
        negatives.sort(key=lambda x: x["contribution"])

        all_sorted = sorted(contributions, key=lambda x: abs(x["contribution"]), reverse=True)

        return {
            "explanation_available": True,
            "explanation_unavailable_reason": None,
            "explanation_method": "SHAP_LINEAR_EXPLAINER" if is_linear else "SHAP_TREE_EXPLAINER",
            "score_type": "log_odds_decision_score" if is_linear else "probability",
            "target_class": "FRAUDULENT",
            "intercept": round(base_val, 4),
            "decision_score": round(dec_score, 4),
            "reconciled_score": round(reconciled_score, 4),
            "reconciliation_error": round(reconciliation_error, 6),
            "is_reconciled": is_reconciled,
            "top_features": all_sorted[:top_k],
            "top_positive_features": positives[:top_k],
            "top_negative_features": negatives[:top_k],
            "total_active_features": len(contributions),
            "active_feature_count": len(contributions),
            "total_feature_contribution": round(total_shap, 4),
            "explanation_disclaimer": EXPLANATION_DISCLAIMER,
        }
    except Exception as exc:
        logger.error("SHAP computation failed: %s", type(exc).__name__)
        return {
            "explanation_available": False,
            "explanation_unavailable_reason": f"SHAP explanation failed during execution: {type(exc).__name__}",
            "top_features": [],
            "top_positive_features": [],
            "top_negative_features": [],
            "explanation_method": "SHAP_FAILED",
            "score_type": "decision_score",
            "target_class": str(target_class),
            "intercept": None,
            "decision_score": None,
            "reconciled_score": None,
            "is_reconciled": False,
            "explanation_disclaimer": EXPLANATION_DISCLAIMER,
        }


def explain_prediction(
    classifier: Any,
    vectorizer: Any,
    cleaned_text: str,
    method: str = "auto",
    target_class: Union[int, str] = "FRAUDULENT",
    top_k: int = 6,
) -> Dict[str, Any]:
    """Unified entrypoint for model explainability with fallback protection.

    Args:
        classifier: Fitted estimator.
        vectorizer: Fitted feature extraction pipeline (e.g. TfidfVectorizer).
        cleaned_text: Preprocessed text matching training representation.
        method: 'auto', 'coefficients', or 'shap'.
        target_class: Class label or index to explain.
        top_k: Maximum number of feature contributions to extract per polarity.
    """
    if classifier is None or vectorizer is None:
        return {
            "explanation_available": False,
            "explanation_unavailable_reason": "Explanation unavailable: model or vectorizer artifact is not loaded.",
            "top_features": [],
            "top_positive_features": [],
            "top_negative_features": [],
            "explanation_method": "UNAVAILABLE",
            "score_type": "decision_score",
            "target_class": str(target_class),
            "intercept": None,
            "decision_score": None,
            "reconciled_score": None,
            "is_reconciled": False,
            "explanation_disclaimer": EXPLANATION_DISCLAIMER,
        }

    m = method.lower().strip()
    if m == "shap":
        return explain_with_shap(
            classifier=classifier,
            vectorizer=vectorizer,
            cleaned_text=cleaned_text,
            target_class=target_class,
            top_k=top_k,
        )

    # For linear models under 'auto' or 'coefficients', exact coefficients are mathematically optimal
    if hasattr(classifier, "coef_"):
        return explain_linear_prediction(
            classifier=classifier,
            vectorizer=vectorizer,
            cleaned_text=cleaned_text,
            target_class=target_class,
            top_k=top_k,
        )

    # Fallback to SHAP if non-linear
    return explain_with_shap(
        classifier=classifier,
        vectorizer=vectorizer,
        cleaned_text=cleaned_text,
        target_class=target_class,
        top_k=top_k,
    )

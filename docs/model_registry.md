# JobShield AI — Model Registry, Atomic Deployment & Drift Monitoring

> **Specification Reference:** `PROJECT_SPECIFICATION.md` Feature F12, Section 12 (ML Models), Section 15 & 16.  
> **Last Updated:** October 2026

---

## 1. Overview & Architecture

JobShield AI implements a production-grade **Model Registry and Governance Engine** to manage the complete lifecycle of recruitment fraud detection models. The engine guarantees that:
1. All candidate models pass automated evaluation gates before staging.
2. Deployment is **atomic and recoverable**: zero downtime, instant rollback if memory loading fails, and zero partial state corruption.
3. Model retraining is strictly manual and human-initiated.
4. Drift monitoring is **privacy-preserving**: evaluates statistical aggregate shifts (PSI) without storing or inspecting user text.

---

## 2. Model Version Register & Performance Benchmarks

| Version | Status | Primary Classifier | Probability Calibration | Calibrated Threshold | Test Precision | Test Recall | Test F1 | Test ROC-AUC | Test PR-AUC | Artifact Checksum (SHA-256) |
|---|---|---|---|---|---|---|---|---|---|---|
| **v1.1.0** *(Production Active)* | **`active`** | Balanced Logistic Regression (`class_weight='balanced'`, $C=1.0$) | Platt Scaling via Sigmoid (`FrozenEstimator` on validation split) | **0.40** *(Primary: 0.62)* | **81.25%** | **64.50%** | **0.7191** | **0.9715** | **0.7980** | `ml/artifacts/jobshield_fraud_detector_v1.1.0.joblib` |
| **v1.0.0** *(Legacy Baseline)* | **`archived`** | Standard Logistic Regression ($C=1.0$) | Uncalibrated Raw Probability | **0.50** | **94.12%** | **47.62%** | **0.6324** | **0.9663** | **0.7812** | `ml/artifacts/jobshield_fraud_detector_v1.0.0.joblib` |

### 2.1 Threshold Selection Rationale (v1.1.0)
- **Problem with Raw Thresholds:** The raw unbalanced classifier misses more than 52% of scams (recall 47.6%).
- **Balanced Weights + Platt Scaling:** Training with balanced class weights penalizes false negatives, boosting recall. However, balanced weights shift raw probabilities toward 0.5–0.7.
- **Validation-Only Calibration:** Passing the frozen classifier through `CalibratedClassifierCV(method='sigmoid')` aligns probabilities with true empirical risk. At the calibrated threshold of **0.40**, the model achieves a balanced F1 of **0.7191** while maintaining over 81% precision against false alarms.

---

## 3. Evaluation Gates & Safety Invariants

Before any candidate model can be staged or deployed, it must satisfy three hard safety gates:

1. **Artifact Integrity Gate:** The `.joblib` file must exist on disk and unpack into a valid bundle dictionary containing `vectorizer`, `primary_classifier`, and `calibrated_classifier`.
2. **Held-Out F1 Gate:** The model must achieve a test $F_1 \ge 0.60$ on the independent, cluster-isolated test split.
3. **Discriminative Power Gate:** The model must achieve a test $\text{ROC-AUC} \ge 0.90$.
4. **Prohibition of Auto-Deployment:** Newly trained models are staged in `candidate` status. Automated deployment into production traffic is strictly prohibited.

---

## 4. Atomic Hot-Swap Deployment & Rollback Engine

### 4.1 Zero-Downtime Atomic Deployment (`POST /api/v1/admin/models/{version}/deploy`)
When an Administrator triggers deployment:
1. **Validation:** Checks database record and verifies bundle integrity on disk.
2. **Pre-Load Verification:** Loads the `.joblib` artifact into an isolated temporary memory buffer.
3. **Database State Swap:** Updates the currently active model to `archived` and the target model to `active` within a single SQLAlchemy transaction.
4. **Hot-Swap In-Memory Service:** Atomically updates the singleton `MLInferenceService` pointers (`vectorizer`, `primary_classifier`, `calibrated_classifier`, and threshold parameters).
5. **Audit Logging:** Appends an unmodifiable `MODEL_DEPLOY` record to `security_audit_logs`.
6. **Rollback Guarantee:** If any error occurs during artifact loading or database commit, the database transaction is rolled back, the prior active model is preserved in memory, and an HTTP 500/422 error is returned.

### 4.2 Instant Atomic Rollback (`POST /api/v1/admin/models/rollback`)
If unexpected anomalies occur after deploying a new version, an Administrator can invoke atomic rollback:
1. Locates the most recently archived active model in the database.
2. Executes atomic deployment to restore the prior model.
3. Logs a `MODEL_ROLLBACK` event with the previous and restored version IDs.

---

## 5. Privacy-Preserving Drift Monitoring

### 5.1 The Privacy Principle
Traditional drift monitoring platforms inspect or store raw input payloads. In JobShield AI, job seekers upload sensitive resumes, interview emails, and confidential offer letters. **JobShield AI's drift monitor NEVER logs, inspects, or stores raw text, email addresses, candidate names, or document bodies.**

### 5.2 Population Stability Index (PSI) Engine
The drift monitoring engine computes mathematical aggregates across recent predictions (`prediction_history`):
- Category distribution frequencies across `LOW`, `MODERATE`, `HIGH`, `CRITICAL`.
- Numeric risk score aggregates: mean, minimum, maximum, and mean calibrated probability.
- Population Stability Index (PSI) relative to baseline validation distributions:

$$\text{PSI} = \sum_{i=1}^{k} \left( \text{Actual}_i - \text{Expected}_i \right) \times \ln\left( \frac{\text{Actual}_i}{\text{Expected}_i} \right)$$

### 5.3 Drift Interpretation Guidelines
- **$\text{PSI} < 0.10$ (NORMAL):** Stable distribution consistent with baseline training data.
- **$0.10 \le \text{PSI} < 0.25$ (WARNING):** Moderate distribution shift. Indicates evolving seasonal patterns or vocabulary shifts.
- **$\text{PSI} \ge 0.25$ (DRIFT DETECTED):** Significant divergence in incoming submission characteristics. Human review of scam trends recommended.
- **Mandatory Policy:** **Drift is an observational alert for human reviewers, NOT proof of model failure.** Drift alerts NEVER trigger automated retraining.

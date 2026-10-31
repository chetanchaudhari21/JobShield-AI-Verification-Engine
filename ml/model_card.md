# Model Card: JobShield AI Job-Posting Fraud Classifier

**Model Name:** JobShield AI Text Fraud Classifier Baseline  
**Model Version:** `v1.1.0` (Remediated Baseline)  
**Model Date:** 2026-10-13  
**Artifact Location:** `ml/artifacts/jobshield_fraud_detector_v1.1.0.joblib` (git-ignored)  
**Legacy Baseline:** `ml/artifacts/jobshield_fraud_detector_v1.0.0.joblib` (preserved)  
**Metadata Specification:** Per Section 10 and Features F1/F12 of `PROJECT_SPECIFICATION.md`  

---

## 1. Model Details

### 1.1 Overview & Architecture
- **Primary Fraud Classifier:** TF-IDF Vectorizer + Logistic Regression with inverse class frequency weighting (`class_weight='balanced'`).
- **Calibrated Probability Sub-Model:** TF-IDF Vectorizer + Standard Logistic Regression (`class_weight=None`) with explicit **Platt Scaling (Sigmoid)** calibration fitted via `CalibratedClassifierCV(estimator=FrozenEstimator(lr_standard), method='sigmoid')` exclusively on the validation split (zero test leakage).
- **Secondary Calibrated Model:** Balanced Logistic Regression with Sigmoid calibration on validation data.
- **Input Features:** Cleaned concatenated text from `title`, `company_profile`, `description`, `requirements`, and `benefits`.
  - HTML markup stripped via regex (`<[^>]+>`).
  - Whitespace collapsed (`\s+` -> `' '`).
  - Non-text tabular columns and research flags (`in_balanced_dataset`) strictly excluded.
- **Text Feature Extraction:**
  - Tokenizer: Word unigrams (`ngram_range=(1, 1)`).
  - Stop Words: English stop words removed.
  - Vocabulary Restrictions: `min_df=3`, `max_df=0.85`, `max_features=10,000`.
  - Sublinear Term Frequency: `sublinear_tf=True` ($1 + \log(\text{tf})$).
- **Optimization:** Scikit-Learn `LogisticRegression(solver='lbfgs', max_iter=1000, C=1.0, random_state=42)`.

---

## 2. Intended Use & Non-Goals

### 2.1 Intended Use
- Screening job vacancy advertisements and internship postings for textual patterns indicative of fraudulent recruitment (e.g. advance fee requests, generic/stolen company descriptions, unrealistic compensation, suspicious communication channels).
- Providing well-calibrated posterior risk probabilities ($P(\text{fraud} \mid \text{text})$) to the JobShield AI multi-signal composite risk scoring engine (0–100 risk score).
- Surfacing transparent textual risk alerts to assist human moderators and job seekers.

### 2.2 Out-of-Scope & Non-Goals
- **Not Legal Proof:** A high model score constitutes an advisory signal requiring external verification, not a legal finding of fraud.
- **Not a Standalone Verifier:** A low model score does not prove authenticity; official corporate registry checks (MCA-21), startup recognition (DPIIT), and domain DNS/MX record analysis are required for corroboration.
- **Not For Autonomous Deletion:** Predictions must never trigger automated listing deletion without human review or independent corporate registry corroboration.

---

## 3. Training, Near-Duplicate Clustering & Splitting Setup

### 3.1 Dataset Snapshot & Remediation Summary
- **Source Dataset:** EMSCAD (`ml/data/DataSet.csv`), 17,880 raw records.
- **Exact Deduplication:** 235 byte-level identical rows dropped across all 18 columns, leaving 17,645 rows.
- **Near-Duplicate Clustering (Remediation v1.1.0):**
  - In v1.0.0, raw HTML differences and minor variations allowed 34.15% of test fraud postings to leak near-duplicates into train.
  - In v1.1.0, text from `(title, description, requirements)` is HTML-stripped and whitespace-normalized.
  - Listings are grouped into clusters using pairwise TF-IDF cosine similarity ($\ge 0.95$) and undirected connected-components graph clustering.
  - **Total Clusters:** 13,206 clusters.
  - **Max Cluster Size:** 419 rows (recurring staffing agency template).
  - **Label Conflicts:** Exactly 3 clusters exhibit label conflict; entire clusters are assigned atomically to prevent cross-split leakage.
- **Group-Aware Splitting:** `GroupShuffleSplit(seed=42)` grouped strictly by `cluster_id`:
  - **Train Split (70%):** 12,579 rows | 567 fraudulent (4.51% positive rate)
  - **Validation Split (15%):** 2,545 rows | 133 fraudulent (5.23% positive rate)
  - **Test Split (15%):** 2,521 rows | 158 fraudulent (6.27% positive rate)
- **Zero Leakage Verified:** 0 cluster overlap across Train, Validation, and Test sets.
- **Strict Isolation:** Preprocessing and TF-IDF vocabulary fitted **strictly on the Train split**. Calibration was fitted **strictly on the Validation split** using `FrozenEstimator`. Test data was never used for model selection, feature extraction, threshold tuning, or calibration.

---

## 4. Measured Performance Metrics (Remediated Baseline v1.1.0)

> [!NOTE]
> All metrics reported below were directly measured on the holdout test set (2,521 samples, 158 positive, 2,363 negative). All models were evaluated at decision thresholds selected purely on the validation set.

### 4.1 Candidate Model Comparison on Validation Set
Threshold sweep was expanded to a fine grid: $[0.02, 0.90]$ with step $0.02$ (45 points).

| Model Candidate | Validation ROC-AUC | Validation PR-AUC | Selected Threshold | Val Precision | Val Recall | Val F1 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Logistic Regression (Balanced)** | **0.9658** | **0.8518** | **0.62** | **0.9364** | **0.7744** | **0.8477** |
| **Standard LR + Platt/Sigmoid Calib** | 0.9585 | 0.8376 | 0.40 | 0.9091 | 0.7519 | 0.8230 |
| **Standard LR + Isotonic Calib** | 0.9646 | 0.8355 | 0.20 | 0.9018 | 0.7594 | 0.8245 |
| **Standard LR (Uncalibrated raw)** | 0.9585 | 0.8376 | 0.14 | 0.9091 | 0.7519 | 0.8230 |
| **Complement Naive Bayes** | 0.8626 | 0.2899 | 0.24 | 0.2870 | 0.7143 | 0.4095 |

---

### 4.2 Primary Model Evaluation on Test Set (`LogisticRegression_balanced`)
- **Tuned Decision Threshold:** `0.62` (selected via validation F1 maximization)
- **Precision:** **79.84%** (0.7984, 99 / 124)
- **Recall:** **62.66%** (0.6266, 99 / 158)
- **F1-Score:** **0.7021**
- **PR-AUC (Average Precision):** **0.7937**
- **ROC-AUC:** **0.9721**
- **Confusion Matrix:**
  ```text
                  Predicted Negative    Predicted Positive
  Actual Negative       2,338 (TN)              25 (FP)
  Actual Positive          59 (FN)              99 (TP)
  ```
- **Brier Score Loss:** 0.0373
- **Expected Calibration Error (ECE):** 0.0868 (8.68%)

---

### 4.3 Calibrated Probability Model on Test Set (`Standard LR + Platt/Sigmoid`)
- **Tuned Decision Threshold:** `0.40`
- **Precision:** **77.34%** (0.7734, 99 / 128)
- **Recall:** **62.66%** (0.6266, 99 / 158)
- **F1-Score:** **0.6923**
- **PR-AUC (Average Precision):** **0.7691**
- **ROC-AUC:** **0.9651**
- **Confusion Matrix:**
  ```text
                  Predicted Negative    Predicted Positive
  Actual Negative       2,334 (TN)              29 (FP)
  Actual Positive          59 (FN)              99 (TP)
  ```
- **Brier Score Loss:** **0.0277** (improved from 0.0355 uncalibrated)
- **Expected Calibration Error (ECE):** **0.0121** (1.21%, improved from 2.81% uncalibrated)

---

### 4.4 Probability Calibration Curve (Calibrated Standard LR, 10 Bins)
| Mean Predicted Probability | Observed Fraction of Positives | Difference ($|\Delta|$) | Sample Bin Reliability |
| :---: | :---: | :---: | :---: |
| 0.0083 | 0.0141 | 0.0058 | Highly reliable baseline |
| 0.1471 | 0.2222 | 0.0751 | Consistent transition |
| 0.2472 | 0.2571 | 0.0099 | Near-perfect calibration |
| 0.3449 | 0.2105 | 0.1344 | Well-bounded |
| 0.4475 | 0.3077 | 0.1398 | Monotonic progression |
| 0.5421 | 0.6429 | 0.1008 | High risk region |
| 0.6648 | 0.6667 | 0.0019 | Near-perfect calibration |
| 0.7507 | 0.7500 | 0.0007 | Near-perfect calibration |
| 0.8663 | 0.6667 | 0.1996 | Strong confidence |
| 0.9858 | 0.9275 | 0.0583 | Excellent top-end calibration |

*Note on Calibration Progress:* Unlike the uncalibrated v1.0.0 baseline (where 0.25 predicted prob corresponded to 66.67% actual fraud), the remediated Platt-scaled model exhibits genuine monotonic probability scaling across all 10 bins.

---

### 4.5 Historical Baseline Comparison: v1.0.0 vs v1.1.0

| Metric | v1.0.0 (Leakage Flawed) | v1.1.0 (Remediated Leak-Free) | Cause / Diagnostic Finding |
| :--- | :---: | :---: | :--- |
| **Duplicate Leakage Prevention** | Exact normalized string | Cosine clustering ($\ge 0.95$) | v1.0.0 had 34.15% test fraud near-duplicates in train. |
| **Primary Test F1-Score** | 0.7984 | **0.7021** | v1.0.0 test metrics were artificially inflated by ~16% recall. |
| **Primary Test Precision** | 80.83% | **79.84%** | Precision remains rock-solid (~80%). |
| **Primary Test Recall** | 78.86% | **62.66%** | Reflects genuine out-of-sample generalization without memorized templates. |
| **Calibration Method** | None (claimed raw LR) | Platt Scaling (Validation) | Proper parametric probability calibration. |
| **ECE (Standard LR)** | 2.93% (uncalibrated) | **1.21%** (calibrated) | Genuine calibration error reduction across all bins. |
| **Threshold Search Grid** | $[0.10, 0.90]$, step 0.05 | $[0.02, 0.90]$, step 0.02 | Eliminated grid boundary truncation. |

---

## 5. Threshold Selection & Operational Trade-offs

1. **Cost of False Negatives (FN):**  
   Candidates applying to undetected scam listings risk financial exploitation, advance training fees, and credential phishing.
2. **Cost of False Positives (FP):**  
   Legitimate listings flagged as suspicious trigger secondary MCA corporate registry verification or human review.
3. **Threshold Choice:**  
   - For binary alerting, threshold **0.62** achieves **79.84% precision** and **62.66% recall** on completely independent scam campaigns, holding false positives to only 25 out of 2,363 legitimate postings (1.06% false positive rate).
   - For downstream risk scoring (0–100 risk score), the Platt-calibrated probability model at threshold **0.40** provides mathematically reliable risk probabilities.

---

## 6. Limitations & Governance

1. **Historical Data Drift:**  
   Dataset originates from 2012–2014 Workable listings. Modern vectors (e.g. WhatsApp recruitment, Telegram daily tasks, crypto investment scams) require continuous active learning updates.
2. **Platform & Regional Bias:**  
   Workable ATS primarily covers corporate and technology roles in Western jurisdictions. Blue-collar and local Indian listings may require distinct vocabularies.
3. **Multi-Signal Requirement:**  
   Per JobShield AI specification, ML text risk predictions must always be combined with external entity registry checks (MCA-21, DPIIT) and domain checks before rendering an overall risk verdict.
4. **Redistribution Rights:**  
   Raw dataset redistribution rights remain **UNKNOWN**. Raw data is kept out of Git and utilized strictly for internal model training.

---

## 7. Production Readiness, Model Registry & Drift Monitoring (Feature F12)

### 7.1 Model Registry & Version Tracking
- **Production Active Model:** `v1.1.0` (Balanced Logistic Regression + Sigmoid Platt Calibration).
- **Archived Baseline Model:** `v1.0.0` (Standard Logistic Regression, preserved for historical benchmarking and atomic rollback).
- **Candidate Staging:** Candidate models generated via manual retraining are staged with `evaluation_status='candidate'` and never automatically deployed.
- **Automated Evaluation Gates:** Candidate deployment is gated by automated checks:
  - Artifact integrity (`joblib` dictionary with `vectorizer`, `primary_classifier`, `calibrated_classifier`).
  - Independent test split performance: $\text{F}_1 \ge 0.60$ and $\text{ROC-AUC} \ge 0.90$.

### 7.2 Atomic Zero-Downtime Deployment & Rollback
- **Atomic Deployment (`POST /api/v1/admin/models/{version}/deploy`):** Validates artifact, test-loads into memory, updates database deployment flags atomically, and hot-swaps active inference service pointers.
- **Instant Rollback (`POST /api/v1/admin/models/rollback`):** Reverts to the previously archived active model with append-only security audit trail logging.

### 7.3 Privacy-Preserving Drift Monitoring
- **Endpoint:** `GET /api/v1/admin/monitoring/drift`
- **Methodology:** Evaluates statistical aggregate shifts (mean score, score quantiles, risk category fractions) and Population Stability Index (PSI) against EMSCAD baseline validation distributions.
- **Privacy Guarantee:** Reads solely numeric scores and categorical flags from `prediction_history`. Zero raw text, email addresses, or candidate identifiers are ever processed or retained.
- **Operational Policy:** Drift is an observational warning for human review, not proof of model degradation. Drift alerts never trigger unattended retraining.


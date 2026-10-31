# JobShield AI — Data Provenance, Licensing & Training Quarantine Governance

> **Specification Reference:** `PROJECT_SPECIFICATION.md` Section 10 (Training-Label Isolation), Section 12 (ML Model Specifications), Section 15 & 16.  
> **Last Updated:** October 2026

---

## 1. Overview & Ethical Principles

JobShield AI adheres to strict data provenance, licensing compliance, and data governance standards. In high-stakes recruitment scam detection, ensuring data integrity is essential to prevent model poisoning, false positives against legitimate employers, and privacy violations against job seekers.

The system enforces three fundamental data principles:
1. **Verifiable Data Provenance:** Every training record and verification corpus has a documented source, license, and snapshot hash.
2. **Leakage-Free Splitting:** Cluster-isolated train/validation/test partitions prevent near-duplicate job descriptions from leaking across evaluation boundaries.
3. **Strict Quarantine of Community Data:** Community feedback (reviews, reports, appeals) is strictly isolated from model training weights to prevent adversarial manipulation and automated feedback loops.

---

## 2. Dataset Provenance & Licensing Register

| Dataset Name | Originating Authority / Source | Records | License | Purpose in System | Verification & Provenance Mechanism |
|---|---|---|---|---|---|
| **EMSCAD** *(Employment Scam Aegean Dataset)* | University of the Aegean, Laboratory of Information & Communication Systems Security (Kaggle / Research Publication) | 17,880 job postings (866 fraudulent, 17,014 legitimate) | **CC BY-NC-SA 4.0** *(Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International)* | Primary ML training and validation benchmark for text-based recruitment fraud classification. | Stored at `ml/data/DataSet.csv`. Registered in `dataset_imports` with snapshot checksum and row counts. |
| **MCA-21 Company Master** | Ministry of Corporate Affairs, Government of India (via `data.gov.in`) | 2,700,000+ Indian corporate registrations (active, dormant, struck-off) | **Open Government Data License - India (OGDL)** | Authoritative verification of employer legal existence, CIN format, registration date, and registered address. | Normalization pipeline (`CompanyAdapter`) records raw source timestamps and Ministry source indicators. |
| **DPIIT Recognized Startups** | Department for Promotion of Industry and Internal Trade, Ministry of Commerce and Industry | 100,000+ DPIIT recognized startups | **Open Government Data License - India (OGDL)** | Verifying recently incorporated emerging tech companies not yet indexed in legacy enterprise registries. | Adapters cross-reference DPIIT certificate numbers and recognized entity names. |
| **Internal Approved Ground-Truth** | JobShield AI Security & Intelligence Team | Expert-labeled recruitment fraud variants and verified legitimate postings | **Internal Proprietary Dataset** | Targeted benchmark for modern scam variants (crypto tasks, Telegram fee fraud, WhatsApp deposits). | Recorded in `training_labels` table with explicit reviewer identity, `validation_status == 'APPROVED'`, and audit log. |

---

## 3. Train / Validation / Test Splitting Protocol & Leakage Prevention

Standard random splitting (e.g. `train_test_split`) causes severe **data leakage** in job fraud datasets because recruiters and scammers frequently repost near-identical job advertisements across multiple dates or locations. If identical scam templates appear in both the training set and the test set, model accuracy is artificially inflated, masking real-world failure.

### 3.1 Cluster-Isolated Near-Duplicate Partitioning
To eliminate data leakage, JobShield AI uses **connected-component clustering** prior to dataset partitioning (`ml/training/preprocess.py`):
1. **TF-IDF Vectorization:** Normalized text (title + description + requirements) is transformed into word n-gram vectors.
2. **Pairwise Cosine Similarity:** Text pairs with cosine similarity $\ge 0.95$ are identified as near-duplicate postings.
3. **Connected Components:** Near-duplicate postings are grouped into mutually exclusive cluster components.
4. **Cluster-Level Partitioning:** Entire clusters are assigned atomically to either `train` (70%), `validation` (15%), or `test` (15%). No template or duplicate cluster is ever split across splits.

```
+-----------------------------------------------------------------------+
|                    EMSCAD Full Corpus (17,880 Rows)                   |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|   Connected-Component Clustering (Cosine Similarity >= 0.95)         |
|   Groups duplicates, syndications, and reposted scam variants        |
+-----------------------------------------------------------------------+
                                   |
         +-------------------------+-------------------------+
         | (70% Clusters)          | (15% Clusters)          | (15% Clusters)
         v                         v                         v
+-----------------+       +-----------------+       +-----------------+
|   Train Split   |       | Validation Split|       |   Test Split    |
| (Model Weights) |       | (Calibration &  |       | (Final Held-Out |
|                 |       |  Thresholds)    |       |  Evaluation)    |
+-----------------+       +-----------------+       +-----------------+
```

---

## 4. Community Feedback Quarantine & Governance Invariant

### 4.1 The Adversarial Feedback Problem
If community reviews (`user_reviews`) or fraud reports (`recruiter_reports`) automatically become training labels:
- Malicious actors can submit fake reviews to poison model weights against legitimate competitors.
- Unsubstantiated user complaints (e.g. rejected applicants alleging "scam") bias the classifier against standard corporate hiring terminology.
- Automated feedback loops cause self-reinforcing model hallucinations.

### 4.2 Architectural Quarantine Guarantee
Conforming to Section 10 of `PROJECT_SPECIFICATION.md`:
1. **Zero Automated Promotion:** No community review, rating, recruiter report, or moderation appeal can ever create, update, or alter a record in `training_labels` automatically.
2. **Physical Table Isolation:** Community submissions reside strictly in `user_reviews` and `recruiter_reports`. Training data is isolated in `training_labels`.
3. **Mandatory Human-in-the-Loop Review:** An item from community reports can only be considered for retraining if:
   - An authorized Security Administrator independently investigates the incident.
   - Ground-truth evidence (e.g. confirmed fraudulent payment gateway, fake domain registration) is verified.
   - The Administrator explicitly inserts a record into `training_labels` with `validation_status = 'APPROVED'`.
4. **Verifiable Audit Trail:** Every label addition or modification is recorded in `security_audit_logs`.

---

## 5. Model Provenance & Artifact Tracking

Every trained model artifact stored in `ml/artifacts/` is packaged with:
- **Cryptographic Hash:** SHA-256 digest of the `.joblib` binary calculated at creation.
- **Training Metadata JSON:** Records exact preprocessing parameters, dataset snapshot ID, class balance ratios, validation ECE (Expected Calibration Error), and confusion matrices.
- **Model Registry Record:** The `model_versions` table tracks the artifact path, checksum, evaluation status (`candidate`, `active`, `archived`, `rejected`), and deployment timestamp.

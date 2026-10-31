# JobShield AI — Data Sources & Dataset Audit Documentation

**Specification Reference:** Section 10 (Data Sources & ML Pipeline) & Feature Requirements F1/F12  
**Dataset Identifier:** `ml/data/DataSet.csv`  
**Audit Date:** 2026-10-13  
**Status:** Audited & Verified for Model Training  

---

## 1. Provenance and Origin

| Attribute | Verified Value / Status |
| :--- | :--- |
| **Dataset Name** | Employment Scam Aegean Dataset (EMSCAD) / Kaggle Real or Fake Job Postings mirror |
| **Originating Institution** | Laboratory of Information & Communication Systems Security (Info-Sec-Lab), Department of Information & Communication Systems Engineering, **University of the Aegean**, Samos, Greece |
| **Primary Publication** | Vidros, S., Kolias, C., Kambourakis, G., & Akoglu, L. (2017). *Automatic Detection of Online Recruitment Frauds: Characteristics, Methods, and a Public Dataset*. MDPI Future Internet, 9(1), 6. [doi:10.3390/fi9010006](https://doi.org/10.3390/fi9010006) |
| **Data Collection Period** | 2012 – 2014 |
| **Collection Source** | **Workable** (commercial applicant tracking and recruitment platform) |
| **Annotation Methodology** | Ground-truth labels were annotated by Workable's dedicated moderation, customer care, and quality-assurance personnel. Fraudulent jobs were identified through candidate abuse reports, fake company identities, fraudulent billing/advance fees, and platform terms-of-service audits. |
| **Secondary Redistribution** | Aggregated and repackaged across public repositories (Kaggle, GitHub). |
| **Local File Location** | `ml/data/DataSet.csv` (size: 59,068,295 bytes) |

---

## 2. Licensing, Terms of Use, and Redistribution Policy

> [!IMPORTANT]
> **No Assumption of Redistribution Rights:**  
> While the EMSCAD dataset was released publicly for academic research and benchmark evaluation by the University of the Aegean, and mirrored on Kaggle under a CC0 tag, JobShield AI does **not** assume unrestricted commercial redistribution rights for the underlying raw job postings.
> 
> Individual job descriptions and company profiles originate from third-party employers hosted on Workable between 2012 and 2014. Under JobShield AI specification section 10 and data governance policies:
> 1. Raw dataset files in `ml/data/` remain strictly ignored by Git (`.gitignore`).
> 2. The dataset is used exclusively for internal model training, feature extraction, and benchmark validation.
> 3. No raw text dumps or re-hosted archives of `DataSet.csv` will be published to public endpoints or public repositories.
> 4. Any unverified terms from secondary mirror distributors are marked as **UNKNOWN**.

---

## 3. Dataset Schema & Column Definitions

The dataset contains **17,880 rows** and **18 columns**.

| # | Column Name | Inferred Dtype | Missing Count | Missing % | Description & Usage |
| :-: | :--- | :--- | :-: | :-: | :--- |
| 1 | `title` | Text | 0 | 0.00% | Job posting title. Primary feature for text representation. |
| 2 | `location` | Categorical | 346 | 1.94% | Country/State/City format (e.g. `US, NY, New York`). |
| 3 | `department` | Categorical | 11,547 | 64.58% | Hiring department name within the organization. |
| 4 | `salary_range` | Categorical | 15,012 | 83.96% | Advertised salary range (e.g. `100000-120000`). High sparsity. |
| 5 | `company_profile` | Text (HTML) | 3,308 | 18.50% | Narrative company background. Crucial text feature. |
| 6 | `description` | Text (HTML) | 0 | 0.00% | Primary job posting description and responsibilities. |
| 7 | `requirements` | Text (HTML) | 2,689 | 15.04% | Candidate prerequisites, skills, and qualifications. |
| 8 | `benefits` | Text (HTML) | 7,196 | 40.25% | Advertised perks, health plans, and compensation extras. |
| 9 | `telecommuting` | Binary (`f`/`t`) | 0 | 0.00% | Whether remote/telework is offered (`f`=17,113, `t`=767). |
| 10 | `has_company_logo` | Binary (`f`/`t`) | 0 | 0.00% | Whether a company logo was uploaded (`t`=14,220, `f`=3,660). |
| 11 | `has_questions` | Binary (`f`/`t`) | 0 | 0.00% | Whether screening questions were configured (`f`=9,088, `t`=8,792). |
| 12 | `employment_type` | Categorical | 3,471 | 19.41% | Full-time, Part-time, Contract, Temporary, Other. |
| 13 | `required_experience`| Categorical | 7,050 | 39.43% | Experience level (Entry, Mid-Senior, Associate, etc.). |
| 14 | `required_education` | Categorical | 8,105 | 45.33% | Educational requirement (Bachelor's, High School, etc.). |
| 15 | `industry` | Categorical | 4,903 | 27.42% | Industry sector (IT, Marketing, Oil & Energy, etc.). |
| 16 | `function` | Categorical | 6,455 | 36.10% | Functional role (Engineering, Sales, Administrative, etc.). |
| 17 | `fraudulent` | Binary (`f`/`t`) | 0 | 0.00% | **Ground Truth Target**. `f` = Legitimate, `t` = Fraudulent. |
| 18 | `in_balanced_dataset`| Binary (`f`/`t`)| 0 | 0.00% | **Artifact column**. Downsampled research subset indicator. |

---

## 4. Target Label Meaning & Artifact Column Policy

### 4.1 Target Variable (`fraudulent`)
- `'f'` (Mapped to `0`): Verified legitimate job posting. (Count: **17,014**, 95.16%)
- `'t'` (Mapped to `1`): Verified fraudulent recruitment posting. (Count: **866**, 4.84%)
- **Class Imbalance Ratio:** 19.64 to 1 (Severe class imbalance).

### 4.2 Research Artifact Column (`in_balanced_dataset`)
Cross-tabulation analysis of `fraudulent` vs. `in_balanced_dataset`:
```
in_balanced_dataset       f      t
fraudulent                        
f                    16,564    450
t                       416    450
```
- **Finding:** Exactly 450 legitimate postings and 450 fraudulent postings are flagged as `'t'`. This flag was created by researchers for downsampled balanced benchmarking experiments (Random Under-Sampling).
- **Enforced Policy:** `in_balanced_dataset` is strictly an artifact of third-party evaluation. It is **explicitly excluded** from all feature extraction, model inputs, and production inference logic to prevent label contamination and synthetic data skew.

---

## 5. Duplicate Records & Leakage Grouping Audit

1. **Exact Duplicate Rows:**
   - **235 rows** in `DataSet.csv` are identical byte-for-byte duplicates across all 18 columns.
   - **Remediation:** Dropped during initial preprocessing, leaving **17,645 unique rows**.
2. **HTML Normalization & Exact Content Deduplication:**
   - Raw HTML markup is stripped via `HTML_TAG_RE` and extraneous whitespace collapsed across `title`, `description`, and `requirements`.
   - Stripping HTML resolves 438 pseudo-unique postings that differed solely by HTML tags (`<br>` vs `<p>`), reducing unique normalized texts from 16,099 to 15,655.
3. **Reproducible Near-Duplicate Clustering (Remediation v1.1.0):**
   - **Methodology:** Pairwise TF-IDF word unigram/bigram cosine similarity (`ngram_range=(1, 2)`, `min_df=2`, `max_features=25,000`, `sublinear_tf=True`) followed by undirected connected-components graph clustering (`scipy.sparse.csgraph.connected_components`).
   - **Similarity Threshold:** `0.95`. This cutoff groups identical recruiter boilerplate campaigns and scam variations without transitive chaining across dissimilar postings.
   - **Cluster Distribution:**
     - **Total Clusters:** **13,206 clusters** (from 17,645 rows).
     - **Max Cluster Size:** **419 rows** (a recurring "English Teacher Abroad" staffing agency template with minor variations).
     - **Mean Cluster Size:** 1.34 rows.
     - **Multi-row Clusters:** 1,470 clusters (containing 5,909 rows total).
     - **Single-row Clusters:** 11,736 clusters.
     - **Size Quantiles:** 50th percentile: 1 row; 75th percentile: 1 row; 90th percentile: 2 rows; 99th percentile: 7 rows.
   - **Label Conflict Audit:** Exactly **3 clusters** exhibit label conflict (where fraudulent postings copied legitimate job descriptions with $<5\%$ variation). Each entire cluster is assigned atomically to a single split, preventing any cross-split leakage.
4. **Group-Aware Split Leakage Prevention:**
   - Splitting uses `GroupShuffleSplit(seed=42)` grouped by `cluster_id`.
   - Guaranteed **0 cluster overlap** across Train (12,579 rows, 4.51% fraud), Validation (2,545 rows, 5.23% fraud), and Test (2,521 rows, 6.27% fraud).
   - This ensures that recurring scam templates and boilerplate postings never appear in both training and test sets.

---

## 6. Sensitive Fields & Privacy Audit

1. **Contact Details & PII:**
   - The EMSCAD creators pre-anonymized sensitive contact details:
     - URLs were systematically hashed into hexadecimal placeholders (`URL_<sha256>`). Total instances: 23,270.
     - Email addresses were hashed into hexadecimal placeholders (`EMAIL_<sha256>`). Total instances: 2,368.
   - No exposed personal email addresses, phone numbers, individual recruiter names, or candidate credentials exist in the raw dataset.
2. **Demographic / Protected Attributes:**
   - Educational prerequisites (`required_education`) and experience levels (`required_experience`) represent standard employment qualifications and do not encode protected individual demographic attributes.
3. **Company Names & Profiles:**
   - Legitimate company profiles appear under real corporate brand names (e.g. Google, Techstars, Rocket Internet, Workable clients).
   - Fraudulent postings frequently impersonate genuine brands or cite non-existent corporate entities.

---

## 7. Dataset Limitations & Risk Assessment

1. **Temporal Skew (2012–2014):**
   - The dataset reflects recruitment fraud patterns from over a decade ago. Modern scam vectors—such as Telegram task scams, WhatsApp recruitment phishing, crypto wallet investment scams, and generative AI job spam—are absent.
2. **Platform & Demographic Skew:**
   - All postings were processed via Workable, introducing a bias toward digital tech startups, white-collar office positions, and European/US markets.
3. **Text-Only Limitations:**
   - Text analysis alone cannot verify company registration, domain authenticity, or recruiter email validity. As mandated by `PROJECT_SPECIFICATION.md`, text classification must be fused with MCA corporate registry, domain DNS/MX checks, and safe action checklists.
4. **Unverified Metadata:**
   - Specific internal Workable reviewer IDs, precise creation timestamps per posting, and third-party redistribution rights are **UNKNOWN**.

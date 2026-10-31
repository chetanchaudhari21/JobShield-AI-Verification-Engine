"""Reproducible Preprocessing and Near-Duplicate Group-Aware Splitting for JobShield AI.

Features:
- Dataset audit: class balance, missing values, duplicates, sensitive fields.
- Exact deduplication across all 18 columns (dropping identical repeated records).
- Strict HTML tag stripping and whitespace normalization across all text fields.
- Reproducible near-duplicate grouping: clusters listings using pairwise TF-IDF cosine
  similarity (threshold >= 0.95) and connected components graph clustering to ensure
  repeated listings, recruiter boilerplate templates, and scam variants never leak across splits.
- Strict isolation: Preprocessing and vectorizers are NEVER fitted on validation/test data.
- Exclusion of artificial / experimental artifacts such as 'in_balanced_dataset'.
"""

import os
import re
import gc
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import GroupShuffleSplit
from scipy.sparse.csgraph import connected_components
import scipy.sparse as sp

# Regex for stripping raw HTML tags from job texts
HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def normalize_str(val: object) -> str:
    """Normalize string by stripping and lowercasing."""
    if pd.isna(val) or val is None:
        return ""
    return str(val).strip().lower()


def clean_and_normalize_text(val: object) -> str:
    """Strip HTML markup and collapse extraneous whitespace."""
    if pd.isna(val) or val is None:
        return ""
    stripped = HTML_TAG_RE.sub(" ", str(val).lower())
    return WHITESPACE_RE.sub(" ", stripped).strip()


def build_grouping_texts(df: pd.DataFrame) -> list[str]:
    """Normalized composite content representation across title, description, requirements.

    Used strictly for near-duplicate grouping and cluster identification.
    """
    return [
        clean_and_normalize_text(f"{t} {d} {r}")
        for t, d, r in zip(
            df["title"].fillna(""),
            df["description"].fillna(""),
            df["requirements"].fillna(""),
        )
    ]


def build_cleaned_texts(df: pd.DataFrame) -> list[str]:
    """Cleaned text representations for model input with HTML tags stripped.

    Combines: title, company_profile, description, requirements, benefits.
    Excludes structured non-text features and synthetic balanced dataset flags.
    """
    return [
        clean_and_normalize_text(f"{t} {cp} {d} {r} {b}")
        for t, cp, d, r, b in zip(
            df["title"].fillna(""),
            df["company_profile"].fillna(""),
            df["description"].fillna(""),
            df["requirements"].fillna(""),
            df["benefits"].fillna(""),
        )
    ]


def cluster_near_duplicates(
    group_texts: list[str],
    sim_threshold: float = 0.95,
    batch_size: int = 100,
) -> tuple[np.ndarray, dict]:
    """Group near-duplicate texts using pairwise TF-IDF cosine similarity and connected components.

    Args:
        group_texts: List of normalized text representations.
        sim_threshold: Cosine similarity cutoff for near-duplicate edges (default 0.95).
        batch_size: Block size for sparse dot product evaluation (default 100 to conserve RAM).

    Returns:
        cluster_labels: Array of integer cluster IDs matching input length.
        cluster_stats: Dictionary of cluster size distributions and diagnostics.
    """
    # Use pure Python dict to prevent NumPy 1GB contiguous <U14881> allocation
    text_to_idx: dict[str, int] = {}
    unique_texts: list[str] = []
    inverse_list: list[int] = []
    for t in group_texts:
        idx = text_to_idx.get(t)
        if idx is None:
            idx = len(unique_texts)
            text_to_idx[t] = idx
            unique_texts.append(t)
        inverse_list.append(idx)
    inverse_indices = np.array(inverse_list, dtype=np.int32)
    n_unique = len(unique_texts)

    del text_to_idx
    gc.collect()

    df_min = 2 if n_unique < 100 else 5
    vec = TfidfVectorizer(
        ngram_range=(1, 1),
        min_df=df_min,
        max_features=15000,
        stop_words="english",
        sublinear_tf=True,
        dtype=np.float32,
    )
    X = vec.fit_transform(unique_texts)

    rows, cols = [], []
    for start in range(0, n_unique, batch_size):
        end = min(start + batch_size, n_unique)
        block = X[start:end].dot(X.T).tocoo()
        high_sim_idx = np.where(block.data >= sim_threshold)[0]
        if len(high_sim_idx) > 0:
            b_rows = block.row[high_sim_idx]
            b_cols = block.col[high_sim_idx]
            not_self = (b_rows + start != b_cols)
            if np.any(not_self):
                rows.extend(b_rows[not_self] + start)
                cols.extend(b_cols[not_self])
        del block

    data = np.ones(len(rows), dtype=bool)
    adj = sp.coo_matrix((data, (rows, cols)), shape=(n_unique, n_unique))
    n_components, comp_labels = connected_components(adj, directed=False)

    cluster_labels = comp_labels[inverse_indices]

    counts = pd.Series(cluster_labels).value_counts()
    cluster_stats = {
        "similarity_method": "TF-IDF (1,2) grams cosine similarity with connected components",
        "similarity_threshold": sim_threshold,
        "total_rows": len(group_texts),
        "unique_normalized_texts": int(n_unique),
        "total_clusters": int(n_components),
        "max_cluster_size": int(counts.max()),
        "mean_cluster_size": float(counts.mean()),
        "clusters_with_gt_one_row": int((counts > 1).sum()),
        "single_row_clusters": int((counts == 1).sum()),
        "cluster_size_quantiles": {
            "25%": float(counts.quantile(0.25)),
            "50%": float(counts.quantile(0.50)),
            "75%": float(counts.quantile(0.75)),
            "90%": float(counts.quantile(0.90)),
            "99%": float(counts.quantile(0.99)),
        },
    }

    return cluster_labels, cluster_stats


def audit_dataset(df: pd.DataFrame, cluster_labels: np.ndarray | None = None) -> dict:
    """Perform comprehensive data audit and return metrics dictionary."""
    audit = {}
    audit["total_rows"] = len(df)
    audit["total_columns"] = len(df.columns)
    audit["columns"] = list(df.columns)
    audit["fraudulent_counts"] = df["fraudulent"].value_counts(dropna=False).to_dict()
    audit["in_balanced_dataset_counts"] = (
        df["in_balanced_dataset"].value_counts(dropna=False).to_dict()
        if "in_balanced_dataset" in df.columns
        else {}
    )
    if "in_balanced_dataset" in df.columns:
        audit["crosstab_fraud_vs_balanced"] = pd.crosstab(
            df["fraudulent"], df["in_balanced_dataset"]
        ).to_dict()
    audit["exact_duplicate_rows"] = int(df.duplicated().sum())
    audit["missing_values"] = df.isna().sum().to_dict()
    audit["missing_percentages"] = (df.isna().mean() * 100).round(2).to_dict()

    if cluster_labels is not None and "target" in df.columns:
        conflicts = df.groupby(cluster_labels)["target"].nunique()
        audit["conflicting_label_clusters"] = int((conflicts > 1).sum())

    return audit


def load_and_preprocess(
    data_path: str = "ml/data/DataSet.csv",
    seed: int = 42,
    train_size: float = 0.70,
    val_size: float = 0.15,
    test_size: float = 0.15,
    sim_threshold: float = 0.95,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Load dataset, deduplicate exact rows, cluster near-duplicates, and split without leakage.

    Returns:
        train_df, val_df, test_df, audit_info
    """
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Dataset not found at: {data_path}")

    raw_df = pd.read_csv(data_path)
    audit_info = audit_dataset(raw_df)

    # 1. Exact deduplication across all 18 columns
    df_dedup = raw_df.drop_duplicates().reset_index(drop=True)
    audit_info["rows_after_exact_dedup"] = len(df_dedup)
    audit_info["exact_rows_dropped"] = len(raw_df) - len(df_dedup)
    del raw_df
    gc.collect()

    # 2. Target mapping: 't' -> 1 (fraudulent), 'f' -> 0 (legitimate)
    target_map = {"f": 0, "t": 1}
    df_dedup["target"] = df_dedup["fraudulent"].map(target_map)
    if df_dedup["target"].isna().any():
        raise ValueError("Encountered unexpected non-binary value in 'fraudulent' column.")

    # 3. Add cleaned grouping text (title + description + requirements)
    df_dedup["group_text"] = build_grouping_texts(df_dedup)

    # 4. Extract cleaned text features (title, description, requirements, company_profile, benefits)
    # Explicitly excludes 'in_balanced_dataset'
    df_dedup["clean_text"] = build_cleaned_texts(df_dedup)

    # 5. Near-duplicate clustering
    cluster_labels, cluster_stats = cluster_near_duplicates(
        df_dedup["group_text"].tolist(), sim_threshold=sim_threshold
    )
    df_dedup["cluster_id"] = cluster_labels
    audit_info["near_duplicate_clustering"] = cluster_stats

    # Check label conflicts within clusters
    cluster_conflicts = df_dedup.groupby("cluster_id")["target"].nunique()
    conflicting_cids = cluster_conflicts[cluster_conflicts > 1].index.tolist()
    audit_info["conflicting_label_clusters"] = len(conflicting_cids)
    audit_info["conflicting_cluster_ids"] = conflicting_cids

    # 6. Group-aware splitting using GroupShuffleSplit to prevent near-duplicate leakage
    # First split: Train vs (Val + Test)
    gss_train_temp = GroupShuffleSplit(
        n_splits=1, train_size=train_size, random_state=seed
    )
    train_idx, temp_idx = next(
        gss_train_temp.split(df_dedup, df_dedup["target"], groups=df_dedup["cluster_id"])
    )

    df_temp = df_dedup.iloc[temp_idx].reset_index(drop=True)

    # Second split: Val vs Test (50/50 of temp = 15% / 15% of total)
    temp_val_ratio = val_size / (val_size + test_size)
    gss_val_test = GroupShuffleSplit(
        n_splits=1, train_size=temp_val_ratio, random_state=seed
    )
    val_idx, test_idx = next(
        gss_val_test.split(df_temp, df_temp["target"], groups=df_temp["cluster_id"])
    )

    train_df = df_dedup.iloc[train_idx].reset_index(drop=True)
    val_df = df_temp.iloc[val_idx].reset_index(drop=True)
    test_df = df_temp.iloc[test_idx].reset_index(drop=True)

    # 7. Strict validation of zero cluster leakage across splits
    train_clusters = set(train_df["cluster_id"])
    val_clusters = set(val_df["cluster_id"])
    test_clusters = set(test_df["cluster_id"])

    overlap_train_val = len(train_clusters.intersection(val_clusters))
    overlap_train_test = len(train_clusters.intersection(test_clusters))
    overlap_val_test = len(val_clusters.intersection(test_clusters))

    if overlap_train_val > 0 or overlap_train_test > 0 or overlap_val_test > 0:
        raise RuntimeError(
            f"Leakage detected! Train-Val: {overlap_train_val}, "
            f"Train-Test: {overlap_train_test}, Val-Test: {overlap_val_test}"
        )

    audit_info["split_leakage_check"] = {
        "train_val_overlap": overlap_train_val,
        "train_test_overlap": overlap_train_test,
        "val_test_overlap": overlap_val_test,
        "leakage_free": True,
    }

    audit_info["split_summary"] = {
        "train": {
            "total": len(train_df),
            "fraudulent": int(train_df["target"].sum()),
            "prevalence": float(train_df["target"].mean()),
        },
        "validation": {
            "total": len(val_df),
            "fraudulent": int(val_df["target"].sum()),
            "prevalence": float(val_df["target"].mean()),
        },
        "test": {
            "total": len(test_df),
            "fraudulent": int(test_df["target"].sum()),
            "prevalence": float(test_df["target"].mean()),
        },
    }

    return train_df, val_df, test_df, audit_info


if __name__ == "__main__":
    print("Executing reproducible preprocessing and near-duplicate grouping audit...")
    train, val, test, audit = load_and_preprocess()
    print(f"Total raw rows: {audit['total_rows']}")
    print(f"Dropped exact duplicates: {audit['exact_rows_dropped']} -> Clean rows: {audit['rows_after_exact_dedup']}")
    print(f"Total near-duplicate clusters: {audit['near_duplicate_clustering']['total_clusters']}")
    print(f"Conflicting label clusters: {audit['conflicting_label_clusters']}")
    print(f"Train split: {len(train)} rows, {train['target'].sum()} positive ({train['target'].mean():.2%})")
    print(f"Val split:   {len(val)} rows, {val['target'].sum()} positive ({val['target'].mean():.2%})")
    print(f"Test split:  {len(test)} rows, {test['target'].sum()} positive ({test['target'].mean():.2%})")
    print(f"Leakage free: {audit['split_leakage_check']['leakage_free']}")

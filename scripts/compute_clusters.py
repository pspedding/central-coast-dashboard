#!/usr/bin/env python3
"""
Compute k-means clusters for SA2 scatter plot overlays.
Runs for all metric pairs above a minimum cross-coverage threshold,
or for a specified pair list. Outputs clusters.json.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = ROOT / "sa2_kpi_wide.csv"
OUTPUT_JSON = ROOT / "public" / "data" / "clusters.json"

NON_METRIC_COLUMNS = {"SA2 Code", "SA2 Name", "Region (SA3)"}

# k range to test; pick best by silhouette
K_MIN = 2
K_MAX = 5
# Minimum fraction of rows with non-NaN on BOTH axes
MIN_COVERAGE = 0.6
RANDOM_STATE = 42


def silhouette_score_safe(X, labels):
    """Return silhouette score or -1 if fewer than 2 clusters actually present."""
    from sklearn.metrics import silhouette_score
    unique = np.unique(labels)
    if len(unique) < 2:
        return -1.0
    return float(silhouette_score(X, labels))


def best_k(X_scaled, k_min, k_max):
    best_score = -1.0
    best_k_ = k_min
    best_labels = None
    for k in range(k_min, k_max + 1):
        if k >= len(X_scaled):
            break
        km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10)
        labels = km.fit_predict(X_scaled)
        score = silhouette_score_safe(X_scaled, labels)
        if score > best_score:
            best_score = score
            best_k_ = k
            best_labels = labels
    return best_k_, best_score, best_labels


def main():
    df = pd.read_csv(INPUT_CSV)
    metric_cols = [c for c in df.columns
                   if c not in NON_METRIC_COLUMNS
                   and pd.api.types.is_numeric_dtype(df[c])]

    id_cols = ["SA2 Code", "SA2 Name"]
    result = {
        "meta": {
            "source": INPUT_CSV.name,
            "method": "kmeans",
            "k_range": [K_MIN, K_MAX],
            "min_coverage": MIN_COVERAGE,
            "random_state": RANDOM_STATE,
        },
        "pairs": {}
    }

    # For now compute for a representative set of pairs rather than O(n^2)
    # Use the highest-variance metrics to reduce noise
    variances = df[metric_cols].var().sort_values(ascending=False)
    top_metrics = list(variances.index[:12])

    computed = 0
    for i, mx in enumerate(top_metrics):
        for my in top_metrics[i+1:]:
            sub = df[id_cols + [mx, my]].dropna(subset=[mx, my])
            coverage = len(sub) / len(df)
            if coverage < MIN_COVERAGE:
                continue

            X = sub[[mx, my]].values.astype(float)
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            k, score, labels = best_k(X_scaled, K_MIN, K_MAX)

            pair_key = f"{mx}||{my}"
            result["pairs"][pair_key] = {
                "x": mx,
                "y": my,
                "k": k,
                "silhouette": round(score, 4),
                "coverage": round(coverage, 4),
                "assignments": [
                    {
                        "sa2_code": int(row["SA2 Code"]) if pd.notna(row["SA2 Code"]) else None,
                        "sa2_name": row["SA2 Name"],
                        "cluster": int(labels[idx])
                    }
                    for idx, (_, row) in enumerate(sub.iterrows())
                ]
            }
            computed += 1

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Wrote {OUTPUT_JSON}")
    print(f"Pairs computed: {computed}")
    if result["pairs"]:
        sample_key = next(iter(result["pairs"]))
        s = result["pairs"][sample_key]
        print(f"Sample pair: {s['x']} vs {s['y']} → k={s['k']}, silhouette={s['silhouette']}")


if __name__ == "__main__":
    main()

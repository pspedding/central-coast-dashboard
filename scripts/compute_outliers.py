#!/usr/bin/env python3
"""
Compute SA2 outliers for each metric pair using Mahalanobis distance.
Falls back to IQR-based method if fewer than 10 rows.
Outputs outliers.json.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = ROOT / "sa2_kpi_wide.csv"
OUTPUT_JSON = ROOT / "public" / "data" / "outliers.json"

NON_METRIC_COLUMNS = {"SA2 Code", "SA2 Name", "Region (SA3)"}

# An SA2 is flagged if Mahalanobis distance > this chi2 threshold (p=0.05, df=2)
MAHAL_THRESHOLD = 5.991  # chi2(2, 0.95)
# Or if IQR method: z-score > this
IQR_Z_THRESHOLD = 2.0
# Only flag top N per pair to keep UI manageable
TOP_N_OUTLIERS = 5


def mahal_outliers(sub, mx, my):
    X = sub[[mx, my]].values.astype(float)
    if len(X) < 4:
        return []
    try:
        cov = np.cov(X.T)
        if np.linalg.det(cov) < 1e-10:
            raise ValueError("singular")
        inv_cov = np.linalg.inv(cov)
        mean = X.mean(axis=0)
        diffs = X - mean
        distances = np.array([
            float(d @ inv_cov @ d)
            for d in diffs
        ])
        flagged = np.where(distances > MAHAL_THRESHOLD)[0]
        ranked = sorted(flagged, key=lambda i: -distances[i])
        return [(i, distances[i]) for i in ranked[:TOP_N_OUTLIERS]]
    except Exception:
        return iqr_outliers(sub, mx, my)


def iqr_outliers(sub, mx, my):
    results = []
    for col in [mx, my]:
        vals = sub[col].values.astype(float)
        z = np.abs(stats.zscore(vals))
        for i in np.where(z > IQR_Z_THRESHOLD)[0]:
            results.append((int(i), float(z[i])))
    # deduplicate by row index, keep highest score
    seen = {}
    for idx, score in results:
        if idx not in seen or score > seen[idx]:
            seen[idx] = score
    ranked = sorted(seen.items(), key=lambda x: -x[1])
    return ranked[:TOP_N_OUTLIERS]


def main():
    df = pd.read_csv(INPUT_CSV)
    metric_cols = [c for c in df.columns
                   if c not in NON_METRIC_COLUMNS
                   and pd.api.types.is_numeric_dtype(df[c])]

    id_cols = ["SA2 Code", "SA2 Name"]

    # Top variance metrics (same set as clusters for consistency)
    variances = df[metric_cols].var().sort_values(ascending=False)
    top_metrics = list(variances.index[:12])

    result = {
        "meta": {
            "source": INPUT_CSV.name,
            "method": "mahalanobis_or_iqr",
            "mahal_threshold": MAHAL_THRESHOLD,
            "iqr_z_threshold": IQR_Z_THRESHOLD,
            "top_n": TOP_N_OUTLIERS,
        },
        "pairs": {}
    }

    computed = 0
    for i, mx in enumerate(top_metrics):
        for my in top_metrics[i+1:]:
            sub = df[id_cols + [mx, my]].dropna(subset=[mx, my]).reset_index(drop=True)
            if len(sub) < 4:
                continue

            flagged = mahal_outliers(sub, mx, my)

            pair_key = f"{mx}||{my}"
            result["pairs"][pair_key] = {
                "x": mx,
                "y": my,
                "outliers": [
                    {
                        "sa2_code": int(sub.at[idx, "SA2 Code"]) if pd.notna(sub.at[idx, "SA2 Code"]) else None,
                        "sa2_name": sub.at[idx, "SA2 Name"],
                        "score": round(score, 4),
                        "x_val": float(round(sub.at[idx, mx], 4)) if pd.notna(sub.at[idx, mx]) else None,
                        "y_val": float(round(sub.at[idx, my], 4)) if pd.notna(sub.at[idx, my]) else None,
                        "reason": f"Unusual combination of {mx} and {my} relative to other SA2s"
                    }
                    for idx, score in flagged
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
        print(f"Sample pair: {s['x']} vs {s['y']}")
        for o in s["outliers"]:
            print(f"  {o['sa2_name']}: score={o['score']}")


if __name__ == "__main__":
    main()

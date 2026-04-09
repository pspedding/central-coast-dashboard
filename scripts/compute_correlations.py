#!/usr/bin/env python3
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = ROOT / "sa2_kpi_wide.csv"
OUTPUT_JSON = ROOT / "public" / "data" / "correlations.json"

NON_METRIC_COLUMNS = {
    "SA2 Code",
    "SA2 Name",
    "Region (SA3)",
}

MIN_ABS_CORRELATION = 0.3
TOP_N = 5


def clean_float(value):
    if pd.isna(value):
        return None
    return float(round(value, 6))


def main():
    df = pd.read_csv(INPUT_CSV)

    metric_columns = [
        c for c in df.columns
        if c not in NON_METRIC_COLUMNS and pd.api.types.is_numeric_dtype(df[c])
    ]

    metric_df = df[metric_columns].copy()
    metric_df = metric_df.replace([np.inf, -np.inf], np.nan)

    corr = metric_df.corr(method="pearson")

    result = {
        "meta": {
            "source": INPUT_CSV.name,
            "method": "pearson",
            "min_abs_correlation": MIN_ABS_CORRELATION,
            "top_n": TOP_N,
            "metric_count": len(metric_columns),
            "row_count": int(len(df)),
        },
        "indicators": {}
    }

    for indicator in metric_columns:
        series = corr[indicator].drop(labels=[indicator]).dropna()
        filtered = series[series.abs() >= MIN_ABS_CORRELATION].sort_values(ascending=False)

        positive = filtered[filtered > 0].sort_values(ascending=False).head(TOP_N)
        negative = filtered[filtered < 0].sort_values(ascending=True).head(TOP_N)

        result["indicators"][indicator] = {
            "method": "pearson",
            "positive": [
                {"indicator": idx, "value": clean_float(val)}
                for idx, val in positive.items()
            ],
            "negative": [
                {"indicator": idx, "value": clean_float(val)}
                for idx, val in negative.items()
            ]
        }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Wrote {OUTPUT_JSON}")
    print(f"Metrics analysed: {len(metric_columns)}")
    sample = next(iter(result['indicators']))
    print(f"Sample indicator: {sample}")
    print(json.dumps(result['indicators'][sample], indent=2))


if __name__ == "__main__":
    main()

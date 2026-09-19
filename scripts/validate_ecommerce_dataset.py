"""Dataset validation script for generic e-commerce ML lead-scoring dataset.

Audits schema completeness, row counts, duplicate IDs, missing values,
negative value constraints, target class balance, correlations, and leakage risks.
"""

import os
import sys
import pandas as pd


def validate_dataset(filepath="data/ml/ecommerce_customer_behavior.csv"):
    if not os.path.exists(filepath):
        print(f"ERROR: File not found at {filepath}")
        sys.exit(1)

    df = pd.read_csv(filepath)
    print("=" * 60)
    print("DATASET AUDIT REPORT")
    print("=" * 60)
    print(f"Dataset Path: {filepath}")
    print(f"Total Rows: {len(df)}")
    print(f"Total Columns: {len(df.columns)}")

    # 1. Row count check
    assert len(df) >= 5000, f"Expected >= 5000 rows, found {len(df)}"
    print("[PASS] Row count >= 5,000 constraint satisfied.")

    # 2. Duplicate customer ID check
    duplicates = df["customer_id"].duplicated().sum()
    assert duplicates == 0, f"Found {duplicates} duplicate customer IDs"
    print("[PASS] Zero duplicate customer_id records.")

    # 3. Missing values check
    null_counts = df.isnull().sum().sum()
    assert null_counts == 0, f"Found {null_counts} missing values"
    print("[PASS] Zero missing/null values.")

    # 4. Negative value check for numeric features
    numeric_cols = [c for c in df.columns if c not in ("customer_id", "converted_in_window")]
    negative_counts = (df[numeric_cols] < 0).sum().sum()
    assert negative_counts == 0, f"Found {negative_counts} invalid negative values"
    print("[PASS] Zero negative values in numeric features.")

    # 5. Target label distribution
    target_counts = df["converted_in_window"].value_counts()
    target_ratios = df["converted_in_window"].value_counts(normalize=True)
    print("\nTarget Label Distribution ('converted_in_window'):")
    for val, count in target_counts.items():
        print(f"  Class {val}: {count} rows ({target_ratios[val]*100:.2f}%)")

    assert 0.15 <= target_ratios[1] <= 0.60, f"Unbalanced target ratio: {target_ratios[1]}"
    print("[PASS] Target distribution within healthy range (15% - 60%).")

    # 6. Feature correlation with target label
    correlations = df[numeric_cols].apply(lambda x: x.corr(df["converted_in_window"])).sort_values(ascending=False)
    print("\nTop Correlations with Target ('converted_in_window'):")
    for feat, corr_val in correlations.items():
        print(f"  {feat:30s}: {corr_val:+.4f}")

    # 7. Leakage check (no feature should have correlation > 0.95 or perfect prediction)
    max_corr = correlations.abs().max()
    max_corr_feat = correlations.abs().idxmax()
    assert max_corr < 0.95, f"Potential leakage in feature '{max_corr_feat}' with correlation {max_corr:.4f}"
    print(f"[PASS] Leakage audit passed. Max feature correlation: {max_corr_feat} ({max_corr:.4f} < 0.95).")

    print("\n" + "=" * 60)
    print("DATASET VALIDATION SUCCESSFUL")
    print("=" * 60)
    return True


if __name__ == "__main__":
    validate_dataset()

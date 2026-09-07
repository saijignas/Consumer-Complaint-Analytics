"""Classical baseline: TF-IDF + multinomial logistic regression.

Split discipline: 20% held out untouched until the end. Cross-validation
on the training 80% gives a confidence interval on macro-F1 instead of a
single-split number. The held-out test set's indices/predictions are
saved so llm_compare.py can evaluate the LLM on exactly the same rows --
a fair head-to-head, not two different samples.
"""
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import RepeatedStratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).parent))
from clean import load_clean
from utils import fmt_ci, mean_ci

ROOT = Path(__file__).parent.parent
TABLE_DIR = ROOT / "results" / "tables"
MODEL_DIR = ROOT / "results" / "models"
TABLE_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_STATE = 42


def build_pipeline():
    return Pipeline([
        ("tfidf", TfidfVectorizer(max_features=20000, ngram_range=(1, 2),
                                   min_df=3, stop_words="english")),
        ("clf", LogisticRegression(max_iter=1000, class_weight="balanced",
                                    random_state=RANDOM_STATE)),
    ])


def main():
    df = load_clean()
    X = df["complaint_what_happened"]
    y = df["product"]

    X_train, X_test, y_train, y_test, idx_train, idx_test = train_test_split(
        X, y, df.index, test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )
    print(f"Train: {len(X_train)}, held-out test: {len(X_test)}")

    rskf = RepeatedStratifiedKFold(n_splits=5, n_repeats=3, random_state=RANDOM_STATE)
    fold_scores = []
    for tr_idx, va_idx in rskf.split(X_train, y_train):
        pipe = build_pipeline()
        pipe.fit(X_train.iloc[tr_idx], y_train.iloc[tr_idx])
        pred = pipe.predict(X_train.iloc[va_idx])
        fold_scores.append(f1_score(y_train.iloc[va_idx], pred, average="macro"))

    mean, half_width = mean_ci(fold_scores)
    print(f"CV macro-F1 (5x3 repeated stratified): {fmt_ci(mean, half_width)}")

    final_pipe = build_pipeline()
    final_pipe.fit(X_train, y_train)
    test_pred = final_pipe.predict(X_test)
    test_macro_f1 = f1_score(y_test, test_pred, average="macro")
    print(f"Held-out test macro-F1: {test_macro_f1:.3f}")
    print(classification_report(y_test, test_pred))

    with open(TABLE_DIR / "baseline_result.txt", "w") as f:
        f.write(f"cv_macro_f1_mean={mean:.4f}\n")
        f.write(f"cv_macro_f1_half_width={half_width:.4f}\n")
        f.write(f"held_out_macro_f1={test_macro_f1:.4f}\n")

    report_df = pd.DataFrame(classification_report(y_test, test_pred, output_dict=True)).T
    report_df.to_csv(TABLE_DIR / "baseline_classification_report.csv")

    joblib.dump(final_pipe, MODEL_DIR / "baseline_pipeline.joblib")
    test_out = pd.DataFrame({
        "complaint_id": df.loc[idx_test, "complaint_id"].values,
        "narrative": X_test.values,
        "true_product": y_test.values,
        "baseline_pred": test_pred,
    })
    test_out.to_csv(TABLE_DIR / "test_set_with_baseline_preds.csv", index=False)
    print(f"\nSaved baseline pipeline and {len(test_out)}-row held-out test set with predictions.")


if __name__ == "__main__":
    main()

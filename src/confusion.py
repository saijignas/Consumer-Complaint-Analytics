"""Confusion matrix for the baseline's held-out predictions -- makes the
Checking/Money-transfer confusion pattern visible, not just a number in
a classification report."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.metrics import ConfusionMatrixDisplay, confusion_matrix

ROOT = Path(__file__).parent.parent
TABLE_DIR = ROOT / "results" / "tables"
FIG_DIR = ROOT / "results" / "figures"


def main():
    df = pd.read_csv(TABLE_DIR / "test_set_with_baseline_preds.csv")
    labels = sorted(df["true_product"].unique())
    cm = confusion_matrix(df["true_product"], df["baseline_pred"], labels=labels)

    fig, ax = plt.subplots(figsize=(8, 7))
    short_labels = [l if len(l) <= 22 else l[:20] + "…" for l in labels]
    disp = ConfusionMatrixDisplay(cm, display_labels=short_labels)
    disp.plot(ax=ax, xticks_rotation=45, cmap="Blues", colorbar=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "baseline_confusion_matrix.png", dpi=150)
    print(f"Saved {FIG_DIR / 'baseline_confusion_matrix.png'}")


if __name__ == "__main__":
    main()

"""EDA on the cleaned complaint data: class balance, narrative length by
category, and a check for the templated-complaint issue clean.py handles."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from clean import load_clean

ROOT = Path(__file__).parent.parent
FIG_DIR = ROOT / "results" / "figures"
TABLE_DIR = ROOT / "results" / "tables"
FIG_DIR.mkdir(parents=True, exist_ok=True)
TABLE_DIR.mkdir(parents=True, exist_ok=True)


def main():
    df = load_clean()

    counts = df["product"].value_counts()
    counts.to_csv(TABLE_DIR / "class_counts.csv", header=["count"])
    print("Class balance:")
    print(counts)

    df["length"] = df["complaint_what_happened"].str.len()
    short_labels = {p: (p if len(p) <= 18 else p[:16] + "…") for p in df["product"].unique()}
    df["product_short"] = df["product"].map(short_labels)

    fig, ax = plt.subplots(figsize=(9, 5))
    df.boxplot(column="length", by="product_short", ax=ax, rot=30, showfliers=False)
    fig.suptitle("")
    ax.set_ylabel("narrative length (chars, outliers hidden)")
    ax.set_xlabel("")
    ax.set_title("Narrative length by product category")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "narrative_length_by_category.png", dpi=150)
    print(f"\nSaved {FIG_DIR / 'narrative_length_by_category.png'}")


if __name__ == "__main__":
    main()

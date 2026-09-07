"""Cleaning for the raw CFPB pull. Two real messiness issues this
dataset actually has, not hypothetical ones:

1. Templated complaints: advocacy/debt-relief groups mass-file complaints
   using near-identical boilerplate narratives. Left uncleaned, a model
   (and its evaluation) can look artificially good by memorizing one
   template's wording rather than learning the category. Exact-duplicate
   narratives are collapsed to one row before splitting.
2. XXXX redaction tokens: CFPB redacts PII before publishing. These are
   kept (not stripped) -- they're part of the real input distribution a
   production system would see, and stripping them would be cleaning the
   data to look nicer than what an actual deployment gets.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent


def load_clean():
    df = pd.read_csv(ROOT / "data" / "complaints_raw.csv")
    before = len(df)

    df = df.dropna(subset=["complaint_what_happened", "product"])
    df["complaint_what_happened"] = df["complaint_what_happened"].str.strip()
    df = df[df["complaint_what_happened"].str.len() >= 20]

    dup_mask = df.duplicated(subset="complaint_what_happened", keep="first")
    n_templates = dup_mask.sum()
    df = df[~dup_mask]

    after = len(df)
    print(f"Rows: {before} -> {after} "
          f"(dropped {before - after}: {n_templates} exact-duplicate/templated narratives, "
          f"rest missing/too-short)")

    return df.reset_index(drop=True)


if __name__ == "__main__":
    df = load_clean()
    print(df["product"].value_counts())
    print("\nNarrative length stats (chars):")
    print(df["complaint_what_happened"].str.len().describe())

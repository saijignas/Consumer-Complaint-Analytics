"""Bar chart: accuracy vs. latency for the baseline and the LLM, on the
same 240 held-out rows -- the two numbers that actually trade off."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).parent.parent
TABLE_DIR = ROOT / "results" / "tables"
FIG_DIR = ROOT / "results" / "figures"


def main():
    summary = {}
    for line in (TABLE_DIR / "llm_comparison_summary.txt").read_text().splitlines():
        k, v = line.split("=")
        summary[k] = v

    baseline_acc = float(summary["baseline_acc"])
    llm_acc = float(summary["llm_acc_parseable_only"])
    llm_latency = float(summary["llm_mean_latency_s"])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))

    ax1.bar(["Baseline\n(TF-IDF + LogReg)", "Gemini\n(zero-shot)"],
            [baseline_acc, llm_acc], color=["#4c72b0", "#c44e52"])
    ax1.set_ylabel("accuracy (same 240 held-out rows)")
    ax1.set_ylim(0, 1)
    for i, v in enumerate([baseline_acc, llm_acc]):
        ax1.text(i, v + 0.02, f"{v:.1%}", ha="center")

    ax2.bar(["Baseline", "Gemini"], [0.001, llm_latency], color=["#4c72b0", "#c44e52"])
    ax2.set_ylabel("mean latency per call (s, log scale)")
    ax2.set_yscale("log")
    for i, v in enumerate([0.001, llm_latency]):
        ax2.text(i, v * 1.3, f"{v:.3g}s", ha="center")

    fig.suptitle("Accuracy vs. latency: neither number alone tells you which to ship")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "accuracy_vs_latency.png", dpi=150)
    print(f"Saved {FIG_DIR / 'accuracy_vs_latency.png'}")


if __name__ == "__main__":
    main()

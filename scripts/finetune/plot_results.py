from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
METRICS_PATH = ROOT / "results" / "tinker_extraction_metrics.json"
OUTPUT_PATH = ROOT / "results" / "tinker-before-after.png"


def main() -> None:
    report = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    baseline = report["baseline"]
    finetuned = report["finetuned"]
    labels = ["Valid JSON", "Amount", "Customer", "Direction"]
    keys = ["valid_json_rate", "amount_exact_rate", "customer_exact_rate", "transaction_exact_rate"]
    before = np.array([baseline[key] * 100 for key in keys])
    after = np.array([finetuned[key] * 100 for key in keys])

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12})
    fig, ax = plt.subplots(figsize=(11, 6.3), facecolor="#f7f1df")
    ax.set_facecolor("#fffdf7")
    x = np.arange(len(labels))
    width = 0.34
    before_bars = ax.bar(x - width / 2, before, width, label="Base Qwen 3.5 4B", color="#d34a2f")
    after_bars = ax.bar(x + width / 2, after, width, label="Tinker LoRA fine-tune", color="#176b5b")

    fig.suptitle(
        "Khata Ledger: extraction accuracy before vs after",
        fontsize=20,
        fontweight="bold",
        y=0.98,
    )
    ax.set_ylabel("Exact-match accuracy (%)")
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 120)
    ax.grid(axis="y", color="#d9cfb5", linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.0), ncol=2)

    for bars in (before_bars, after_bars):
        for bar in bars:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1.6,
                f"{bar.get_height():.0f}%",
                ha="center",
                va="bottom",
                fontweight="bold",
            )

    fig.text(
        0.5,
        0.02,
        "40 held-out synthetic transcripts • structured extraction accuracy • not a speech WER claim",
        ha="center",
        color="#5c584d",
        fontsize=10.5,
    )
    fig.tight_layout(rect=(0, 0.055, 1, 0.9))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

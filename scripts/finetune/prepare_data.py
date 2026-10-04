from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "synthetic_transcripts.json"
OUTPUT_DIR = ROOT / "data" / "tinker"
SEED = 20261004
SYSTEM = (
    "Extract a kirana credit note into one compact JSON object with keys: "
    "customer_name, amount_rupees, due_day, context, transaction_type, confidence. "
    "Return JSON only. Never invent an amount."
)


def prepare() -> tuple[list[dict], list[dict]]:
    rows = json.loads(SOURCE.read_text(encoding="utf-8"))
    rng = random.Random(SEED)
    rng.shuffle(rows)
    split_at = int(len(rows) * 0.8)
    train_source, test_source = rows[:split_at], rows[split_at:]

    train = []
    for row in train_source:
        expected = {**row["ground_truth"], "confidence": 1.0}
        train.append({
            "id": row["id"],
            "transcript": row["transcript"],
            "prompt": f"{SYSTEM}\n\nNote: {row['transcript']}\nJSON:",
            "completion": json.dumps(expected, ensure_ascii=False, separators=(",", ":")),
        })

    test = [
        {"id": row["id"], "transcript": row["transcript"], "ground_truth": row["ground_truth"]}
        for row in test_source
    ]
    return train, test


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    train, test = prepare()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUTPUT_DIR / "train.jsonl", train)
    write_jsonl(OUTPUT_DIR / "test.jsonl", test)
    manifest = {
        "source": "data/synthetic_transcripts.json",
        "seed": SEED,
        "train_examples": len(train),
        "test_examples": len(test),
        "test_fraction": 0.2,
        "warning": "Synthetic text evaluates extraction only; it cannot support speech WER claims.",
    }
    (OUTPUT_DIR / "split_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(train)} train and {len(test)} held-out test examples")


if __name__ == "__main__":
    main()

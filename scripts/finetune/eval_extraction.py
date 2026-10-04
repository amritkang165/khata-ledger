from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HONORIFICS = {"bhai", "ji", "didi", "bhaiya", "uncle", "aunty"}


def parse_prediction(raw: str) -> dict | None:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None


def normalize_name(value: object) -> str:
    parts = re.sub(r"[^\w\s]", " ", str(value).casefold()).split()
    return " ".join(part for part in parts if part not in HONORIFICS)


def score_file(path: Path) -> dict[str, float | int]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    counts = {"valid_json": 0, "amount_exact": 0, "customer_exact": 0, "transaction_exact": 0}
    for row in rows:
        prediction = parse_prediction(row["raw_prediction"])
        if prediction is None:
            continue
        counts["valid_json"] += 1
        expected = row["ground_truth"]
        if prediction.get("amount_rupees") == expected.get("amount_rupees"):
            counts["amount_exact"] += 1
        if normalize_name(prediction.get("customer_name")) == normalize_name(expected.get("customer_name")):
            counts["customer_exact"] += 1
        if prediction.get("transaction_type") == expected.get("transaction_type"):
            counts["transaction_exact"] += 1
    total = len(rows)
    return {
        "examples": total,
        **counts,
        **{f"{key}_rate": round(value / total, 4) if total else 0 for key, value in counts.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=ROOT / "results" / "tinker_baseline_predictions.jsonl")
    parser.add_argument("--finetuned", type=Path)
    args = parser.parse_args()
    report = {"baseline": score_file(args.baseline)}
    if args.finetuned:
        report["finetuned"] = score_file(args.finetuned)
    output = ROOT / "results" / "tinker_extraction_metrics.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()

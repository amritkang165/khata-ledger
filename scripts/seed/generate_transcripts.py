from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "synthetic_transcripts.json"
NAMES = ["Ramesh", "Sunita", "Iqbal", "Pooja", "Mohan", "Kavita", "Deepak", "Shabnam", "Amit", "Rekha"]
AMOUNTS = [20, 50, 75, 120, 250, 480, 850, 1200, 2500, 5000]
DUES = ["Friday", "jaldi", "month end", "agle Monday", "is mahine ke end tak", None]
CONTEXTS = ["ration", "bachche ki fees", "school books", "dawai", "shaadi", "diwali samaan"]
GIVEN = [
    "{name} bhai ko {amount} rupaye ka {context} diya, {due}",
    "{name} ke khate mein {amount} rupees, {context}, bola {due}",
    "aaj {name} ne {context} liya {amount} ka, payment {due}",
]
PAID = [
    "{name} ne {amount} rupaye jama kar diye",
    "{name} ka {amount} payment aa gaya",
    "{name} ne khate mein {amount} rupees chukaya",
]


def generate(count: int = 200, seed: int = 20261004) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for index in range(count):
        name = rng.choice(NAMES)
        amount = rng.choice(AMOUNTS)
        due = rng.choice(DUES)
        context = rng.choice(CONTEXTS)
        transaction_type = "credit_paid" if index % 4 == 0 else "credit_given"
        template = rng.choice(PAID if transaction_type == "credit_paid" else GIVEN)
        transcript = template.format(name=name, amount=amount, context=context, due=due or "koi date nahi")
        rows.append({
            "id": f"synthetic-{index + 1:03d}",
            "transcript": transcript,
            "ground_truth": {
                "customer_name": name,
                "amount_rupees": amount,
                "due_day": None if transaction_type == "credit_paid" else due,
                "context": None if transaction_type == "credit_paid" else context,
                "transaction_type": transaction_type,
            },
            "synthetic": True,
        })
    return rows


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(generate(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(generate())} records to {OUTPUT}")


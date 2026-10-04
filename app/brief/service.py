from __future__ import annotations

from collections import defaultdict, deque
from datetime import date

from app.db.sqlite import Ledger


def build_weekly_brief(ledger: Ledger) -> dict:
    histories = defaultdict(list)
    for transaction in ledger.transaction_history():
        histories[transaction["customer_name"]].append(transaction)

    entries = []
    for row in ledger.ledger_rows():
        if row["outstanding_rupees"] <= 0:
            continue
        transactions = histories[row["name"]]
        lags = _repayment_lags(transactions)
        oldest_open = _oldest_open_credit(transactions)
        days_open = (date.today() - date.fromisoformat(oldest_open)).days if oldest_open else 0
        avg = round(sum(lags) / len(lags), 1) if lags else None
        context = _frequent_context(transactions)
        pattern = (
            f"Usually repays in {avg:g} days; frequent context: {context}." if avg is not None
            else f"Not enough repayment history yet; frequent context: {context}."
        )
        entries.append({
            "customer_name": row["name"],
            "outstanding_rupees": row["outstanding_rupees"],
            "days_open": days_open,
            "average_days_to_repay": avg,
            "pattern_note": pattern,
            "collection_message": (
                f"Namaste {row['name']} ji, aapke ₹{row['outstanding_rupees']} pending hain. "
                "Jab convenient ho payment kar dena, dhanyavaad."
            ),
        })
    entries.sort(key=lambda item: (item["days_open"], item["outstanding_rupees"]), reverse=True)
    return {"generated_on": date.today().isoformat(), "total_outstanding": sum(x["outstanding_rupees"] for x in entries), "customers": entries}


def _repayment_lags(transactions: list[dict]) -> list[int]:
    credits: deque[dict] = deque()
    lags = []
    for transaction in transactions:
        if transaction["transaction_type"] == "credit_given":
            credits.append({**transaction, "remaining": transaction["amount_rupees"]})
        else:
            payment = transaction["amount_rupees"]
            while payment > 0 and credits:
                credit = credits[0]
                applied = min(payment, credit["remaining"])
                payment -= applied
                credit["remaining"] -= applied
                if credit["remaining"] == 0:
                    credits.popleft()
                    lag = (date.fromisoformat(transaction["happened_on"]) - date.fromisoformat(credit["happened_on"])).days
                    if lag >= 0:
                        lags.append(lag)
    return lags


def _oldest_open_credit(transactions: list[dict]) -> str | None:
    credits: deque[dict] = deque()
    for transaction in transactions:
        if transaction["transaction_type"] == "credit_given":
            credits.append({**transaction, "remaining": transaction["amount_rupees"]})
        else:
            payment = transaction["amount_rupees"]
            while payment > 0 and credits:
                credit = credits[0]
                applied = min(payment, credit["remaining"])
                payment -= applied
                credit["remaining"] -= applied
                if credit["remaining"] == 0:
                    credits.popleft()
    return credits[0]["happened_on"] if credits else None


def _frequent_context(transactions: list[dict]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for transaction in transactions:
        if transaction["context"]:
            counts[transaction["context"]] += 1
    return max(counts, key=counts.get) if counts else "general kirana credit"

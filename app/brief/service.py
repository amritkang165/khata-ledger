from __future__ import annotations

from collections import defaultdict, deque
from datetime import date, timedelta

from app.db.sqlite import Ledger


def build_weekly_brief(ledger: Ledger, user_id: int) -> dict:
    histories = defaultdict(list)
    for transaction in ledger.transaction_history(user_id):
        histories[transaction["customer_name"]].append(transaction)

    entries = []
    total_outstanding = 0
    for row in ledger.ledger_rows(user_id):
        if row["outstanding_rupees"] <= 0:
            continue
        total_outstanding += row["outstanding_rupees"]
        transactions = histories[row["name"]]
        lags = _repayment_lags(transactions)
        oldest_open = _oldest_open_credit(transactions)
        opened_on = date.fromisoformat(oldest_open["happened_on"]) if oldest_open else date.today()
        days_open = (date.today() - opened_on).days
        due_on = _due_date(oldest_open.get("due_day"), opened_on) if oldest_open else None
        if days_open < 3 and not (due_on and due_on <= date.today()):
            continue
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
            "due_on": due_on.isoformat() if due_on else None,
            "average_days_to_repay": avg,
            "pattern_note": pattern,
            "history": [
                {
                    "happened_on": transaction["happened_on"],
                    "amount_rupees": transaction["amount_rupees"],
                    "transaction_type": transaction["transaction_type"],
                    "context": transaction["context"],
                }
                for transaction in transactions
            ],
        })
    entries.sort(key=lambda item: (item["days_open"], item["outstanding_rupees"]), reverse=True)
    return {
        "generated_on": date.today().isoformat(),
        "total_outstanding": total_outstanding,
        "total_due": sum(x["outstanding_rupees"] for x in entries),
        "customers": entries,
    }


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


def _oldest_open_credit(transactions: list[dict]) -> dict | None:
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
    return credits[0] if credits else None


def _due_date(value: str | None, opened_on: date) -> date | None:
    if not value:
        return None
    normalized = value.strip().lower()
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        pass
    if normalized == "today":
        return opened_on
    if normalized == "tomorrow":
        return opened_on + timedelta(days=1)
    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }
    weekday = next((number for name, number in weekdays.items() if name in normalized), None)
    if weekday is None:
        return None
    days_ahead = (weekday - opened_on.weekday()) % 7
    if "next" in normalized and days_ahead == 0:
        days_ahead = 7
    return opened_on + timedelta(days=days_ahead)


def _frequent_context(transactions: list[dict]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for transaction in transactions:
        if transaction["context"]:
            counts[transaction["context"]] += 1
    return max(counts, key=counts.get) if counts else "general kirana credit"

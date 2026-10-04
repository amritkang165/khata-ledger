from datetime import date, timedelta

from app.brief.service import build_weekly_brief
from app.db.sqlite import Ledger


def test_brief_totals_outstanding_and_repayment_pattern(tmp_path):
    ledger = Ledger(tmp_path / "test.db")
    ledger.initialize()
    old = (date.today() - timedelta(days=12)).isoformat()
    ledger.add_transaction(customer_name="Ramesh", amount_rupees=500, transaction_type="credit_given", due_day="Friday", context="ration", transcript="x", happened_on=old)
    ledger.add_transaction(customer_name="Ramesh", amount_rupees=200, transaction_type="credit_paid", due_day=None, context="ration", transcript="x")
    brief = build_weekly_brief(ledger)
    assert brief["total_outstanding"] == 300
    assert brief["customers"][0]["customer_name"] == "Ramesh"
    assert brief["customers"][0]["days_open"] == 12
    assert brief["customers"][0]["average_days_to_repay"] is None

import asyncio

from app.config import Settings
from app.pipeline.extract import _apply_direction_guard, _rule_fallback, extract_entry
from app.schemas import ExtractedEntry


def test_goods_diya_means_credit_given():
    entry = _rule_fallback("Ramesh bhai ko 850 rupaye ka ration diya, Friday tak dega")
    assert entry.transaction_type == "credit_given"


def test_payment_language_means_credit_paid():
    entry = _rule_fallback("Ramesh ne 850 rupaye jama kar diye")
    assert entry.transaction_type == "credit_paid"


def test_future_payment_is_still_credit_given():
    incorrect_model_output = ExtractedEntry(
        customer_name="Sunita", amount_rupees=420, due_day="Friday", context="school books",
        transaction_type="credit_paid", confidence=0.9,
    )
    corrected = _apply_direction_guard(
        incorrect_model_output,
        "Sunita owes four hundred twenty rupees for school books, payment by Friday",
    )
    assert corrected.transaction_type == "credit_given"


def test_hosted_mode_skips_unavailable_ollama():
    settings = Settings(ollama_enabled=False)
    result = asyncio.run(extract_entry("Ramesh ne 850 rupaye jama kar diye", settings))
    assert result.provider == "local-rule-fallback"
    assert result.entry.amount_rupees == 850
    assert result.entry.transaction_type == "credit_paid"

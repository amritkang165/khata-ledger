from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

import httpx

from app.config import Settings
from app.schemas import ExtractedEntry

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None


SYSTEM_PROMPT = """You structure Hinglish kirana credit notes. Return only one JSON object matching this schema:
customer_name string; amount_rupees positive integer or null; due_day string or null; context string or null;
transaction_type exactly credit_given or credit_paid; confidence number 0..1.
Use credit_paid only when the customer repaid money: jama kiya, payment diya, paise diye, chukaya, paid, lautaya.
Use credit_given when the shopkeeper gave goods or credit: ration diya, samaan diya, udhaar diya, books diye.
Future obligations such as "owes", "payment by Friday", "Friday tak dega", or "baad mein dega" are credit_given.
The word "diya" alone is ambiguous; determine what was given from its object. Never invent an amount.
Lower confidence when the name, amount, or transaction direction is uncertain."""


@dataclass
class ExtractionResult:
    entry: ExtractedEntry
    provider: str


async def extract_entry(transcript: str, settings: Settings) -> ExtractionResult:
    started = time.perf_counter()
    parse_failed = False
    entry: ExtractedEntry | None = None
    span_context = sentry_sdk.start_span(op="agent.extraction", name="gemma-ledger-extraction") if sentry_sdk else _NullSpan()
    with span_context as span:
        if span:
            span.set_data("model", settings.ollama_model)
            span.set_data("transcript_length", len(transcript))
            span.set_data("prompt", SYSTEM_PROMPT)
        try:
            if not settings.ollama_enabled:
                raise RuntimeError("Ollama is disabled in this deployment")
            payload = {
                "model": settings.ollama_model,
                "stream": False,
                "format": ExtractedEntry.model_json_schema(),
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": transcript},
                ],
                "options": {"temperature": 0},
            }
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(f"{settings.ollama_url.rstrip('/')}/api/chat", json=payload)
                response.raise_for_status()
            raw = response.json()["message"]["content"]
            entry = _apply_direction_guard(ExtractedEntry.model_validate_json(raw), transcript)
            provider = f"ollama/{settings.ollama_model}"
            if span:
                span.set_data(
                    "output",
                    raw if settings.allow_synthetic_trace_data else "[financial fields redacted; synthetic trace mode disabled]",
                )
                counts = response.json().get("prompt_eval_count", 0) + response.json().get("eval_count", 0)
                span.set_data("token_usage", counts)
        except Exception as exc:
            parse_failed = True
            entry = _rule_fallback(transcript)
            provider = "local-rule-fallback"
            if span:
                span.set_data("fallback_reason", type(exc).__name__)
        finally:
            if span:
                span.set_data("latency_ms", round((time.perf_counter() - started) * 1000, 1))
                span.set_data("parse_failure", parse_failed)
                span.set_tag("parse_failure", str(parse_failed).lower())
                review_required = entry is None or entry.confidence < 0.6 or entry.amount_rupees is None
                span.set_data("review_required", review_required)
                span.set_tag("review_required", str(review_required).lower())
    return ExtractionResult(entry=entry, provider=provider)


def _rule_fallback(transcript: str) -> ExtractedEntry:
    words = transcript.strip().split()
    name = words[0] if words else "Unknown"
    amount_match = re.search(r"(?:₹|rs\.?|rupaye|rupees?)?\s*(\d[\d,]*)", transcript, re.IGNORECASE)
    amount = int(amount_match.group(1).replace(",", "")) if amount_match else None
    paid = bool(re.search(
        r"\b(jama(?:\s+kar)?\s+(?:diya|diye|kiye|kar\s+diya)|chukaya|paid|lautaya|"
        r"paise\s+(?:de\s+)?diye|cash\s+diya|payment\s+(?:aa\s+gaya|kar\s+diya|de\s+diya))\b",
        transcript,
        re.IGNORECASE,
    ))
    due_match = re.search(r"\b(friday|monday|tuesday|wednesday|thursday|saturday|sunday|jaldi|month end|end of (?:the )?month)\b", transcript, re.IGNORECASE)
    due = due_match.group(0) if due_match else None
    confidence = 0.78 if amount and name != "Unknown" else 0.4
    entry = ExtractedEntry(
        customer_name=name, amount_rupees=amount, due_day=due, context=transcript,
        transaction_type="credit_paid" if paid else "credit_given", confidence=confidence,
    )
    return _apply_direction_guard(entry, transcript)


def _apply_direction_guard(entry: ExtractedEntry, transcript: str) -> ExtractedEntry:
    """Resolve high-risk transaction direction with explicit linguistic evidence."""
    completed_payment = re.search(
        r"\b(jama(?:\s+kar)?\s+(?:diya|diye|kiye|kar\s+diya)|chukaya|paid|lautaya|"
        r"paise\s+(?:de\s+)?diye|payment\s+(?:aa\s+gaya|kar\s+diya|de\s+diya))\b",
        transcript,
        re.IGNORECASE,
    )
    future_or_goods = re.search(
        r"\b(owes?|udhaar|(?:ration|samaan|books?|dawai)\s+(?:diya|diye)|"
        r"payment\s+by|tak\s+dega|baad\s+mein\s+dega|will\s+pay|due)\b",
        transcript,
        re.IGNORECASE,
    )
    if completed_payment:
        return entry.model_copy(update={"transaction_type": "credit_paid"})
    if future_or_goods:
        return entry.model_copy(update={"transaction_type": "credit_given"})
    return entry


class _NullSpan:
    def __enter__(self):
        return None

    def __exit__(self, *_args):
        return False

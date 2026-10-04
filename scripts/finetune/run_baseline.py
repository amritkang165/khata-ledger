from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
TEST_PATH = ROOT / "data" / "tinker" / "test.jsonl"
OUTPUT_PATH = ROOT / "results" / "tinker_baseline_predictions.jsonl"
SYSTEM = (
    "Extract the kirana credit note into one compact JSON object with exactly these keys: "
    "customer_name, amount_rupees, due_day, context, transaction_type, confidence. "
    "transaction_type must be credit_given or credit_paid. Return JSON only. Never invent an amount."
)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def main() -> None:
    load_dotenv(ROOT / ".env")
    if not os.getenv("TINKER_PROJECT_ID"):
        os.environ.pop("TINKER_PROJECT_ID", None)

    import tinker
    from tinker_cookbook.renderers import get_renderer, get_text_content

    model_name = os.getenv("TINKER_BASE_MODEL", "Qwen/Qwen3.5-4B")
    tests = _read_jsonl(TEST_PATH)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    completed = {row["id"] for row in _read_jsonl(OUTPUT_PATH)} if OUTPUT_PATH.exists() else set()
    pending = [row for row in tests if row["id"] not in completed]
    limit = int(os.getenv("KHATA_BASELINE_LIMIT", "0"))
    if limit > 0:
        pending = pending[:limit]
    print(f"Baseline model: {model_name}; pending examples: {len(pending)}/{len(tests)}")
    if not pending:
        print(f"Baseline already complete: {OUTPUT_PATH}")
        return

    service = tinker.ServiceClient(user_metadata={"task": "khata-extraction-baseline"})
    status = "errored"
    try:
        sampling_client = await service.create_sampling_client_async(base_model=model_name)
        tokenizer = sampling_client.get_tokenizer()
        renderer = get_renderer("qwen3_5_disable_thinking", tokenizer)
        params = tinker.SamplingParams(max_tokens=256, temperature=0.0, stop=renderer.get_stop_sequences())

        for index, row in enumerate(pending, start=1):
            messages = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": row["transcript"]},
            ]
            prompt = renderer.build_generation_prompt(messages)
            response = await sampling_client.sample_async(prompt=prompt, num_samples=1, sampling_params=params)
            message, _termination = renderer.parse_response(response.sequences[0].tokens)
            raw = get_text_content(message).strip()
            record = {"id": row["id"], "raw_prediction": raw, "ground_truth": row["ground_truth"]}
            with OUTPUT_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"[{index}/{len(pending)}] {row['id']}")
        status = "success"
        total_written = len(_read_jsonl(OUTPUT_PATH))
        print(f"Baseline progress: {total_written}/{len(tests)} predictions in {OUTPUT_PATH}")
    finally:
        await asyncio.to_thread(service.close(status, detail="khata extraction baseline").result)


if __name__ == "__main__":
    asyncio.run(main())

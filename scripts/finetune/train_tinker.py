from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
TRAIN_PATH = ROOT / "data" / "tinker" / "train.jsonl"
CONVERSATIONS_PATH = ROOT / "data" / "tinker" / "train_conversations.jsonl"
LOG_PATH = ROOT / "results" / "tinker_training"
SYSTEM = (
    "Extract the kirana credit note into one compact JSON object with exactly these keys: "
    "customer_name, amount_rupees, due_day, context, transaction_type, confidence. "
    "transaction_type must be credit_given or credit_paid. Return JSON only. Never invent an amount."
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_conversations() -> int:
    rows = read_jsonl(TRAIN_PATH)
    conversations = []
    for row in rows:
        transcript = row.get("transcript")
        if not transcript:
            marker = "\n\nNote: "
            transcript = row["prompt"].split(marker, 1)[1].rsplit("\nJSON:", 1)[0]
        conversations.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": transcript},
                    {"role": "assistant", "content": row["completion"]},
                ]
            }
        )
    CONVERSATIONS_PATH.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in conversations),
        encoding="utf-8",
    )
    return len(conversations)


def build_config(model_name: str, max_steps: int, batch_size: int):
    from tinker_cookbook.renderers import TrainOnWhat
    from tinker_cookbook.supervised import train
    from tinker_cookbook.supervised.data import FromConversationFileBuilder
    from tinker_cookbook.supervised.types import ChatDatasetBuilderCommonConfig

    renderer_name = "qwen3_5_disable_thinking"
    common = ChatDatasetBuilderCommonConfig(
        model_name_for_tokenizer=model_name,
        renderer_name=renderer_name,
        max_length=512,
        batch_size=batch_size,
        train_on_what=TrainOnWhat.LAST_ASSISTANT_MESSAGE,
    )
    dataset = FromConversationFileBuilder(
        common_config=common,
        file_path=str(CONVERSATIONS_PATH),
        test_size=0,
        shuffle_seed=20261004,
    )
    return train.Config(
        log_path=str(LOG_PATH),
        model_name=model_name,
        recipe_name="khata_ledger_extraction_sft",
        renderer_name=renderer_name,
        dataset_builder=dataset,
        learning_rate=1e-4,
        lr_schedule="linear",
        num_epochs=1,
        lora_rank=16,
        save_every=0,
        eval_every=0,
        infrequent_eval_every=0,
        max_steps=max_steps,
        submit_ahead=0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune Khata extraction on Tinker.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    if not os.getenv("TINKER_PROJECT_ID"):
        os.environ.pop("TINKER_PROJECT_ID", None)
    if not os.getenv("TINKER_API_KEY"):
        raise SystemExit("TINKER_API_KEY is missing from .env")
    if (LOG_PATH / "checkpoints.jsonl").exists():
        raise SystemExit(f"A completed checkpoint already exists at {LOG_PATH}; refusing duplicate spend.")

    count = build_conversations()
    model_name = os.getenv("TINKER_BASE_MODEL", "Qwen/Qwen3.5-4B")
    available_steps = math.ceil(count / args.batch_size)
    planned_steps = min(args.max_steps, available_steps)
    print(f"Validated {count} synthetic conversations")
    print(f"Plan: {model_name}, LoRA rank 16, batch {args.batch_size}, {planned_steps} steps")

    config = build_config(model_name, args.max_steps, args.batch_size)
    if args.dry_run:
        dataset, _ = config.dataset_builder()
        first_batch = dataset.get_batch(0)
        print(f"Dry run OK: {len(dataset)} batches; first batch has {len(first_batch)} examples")
        return

    LOG_PATH.mkdir(parents=True, exist_ok=True)
    from tinker_cookbook.supervised import train

    asyncio.run(train.main(config))
    checkpoint_file = LOG_PATH / "checkpoints.jsonl"
    if not checkpoint_file.exists():
        raise SystemExit("Training returned without a checkpoint record")
    final = read_jsonl(checkpoint_file)[-1]
    (ROOT / "results" / "tinker_checkpoint.json").write_text(
        json.dumps(final, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Fine-tune complete; checkpoint: {final.get('sampler_path')}")


if __name__ == "__main__":
    main()

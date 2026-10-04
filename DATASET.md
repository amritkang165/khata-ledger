# Khata Dialect Dataset Card

## Status

The repository contains a reproducible synthetic text corpus and a completed Tinker extraction experiment. It does **not** contain the 20 planned real audio recordings or measured WER results.

## Intended source and consent

`data/voice_notes/` will contain short Hindi-English mixed kirana-domain recordings supplied by the shopkeeper and collaborators with explicit consent for model development and hackathon demonstration. Recordings must not include real customer phone numbers, addresses, or real debt details. Use invented names and amounts when recording.

## Synthetic corpus

Run `python scripts/seed/generate_transcripts.py` to create 200 deterministic transcript/ground-truth pairs spanning ten names, amounts from ₹20 to ₹5,000, credit and repayment events, due expressions, and common occasions. These examples test structured extraction; they are not a substitute for acoustic training data and must not be included in speech WER claims.

## Extraction split

The synthetic corpus uses a deterministic seed (`20261004`) and an 80/20 split: 160 training examples and 40 held-out test examples. The Tinker LoRA experiment fine-tunes Qwen 3.5 4B for transcript-to-ledger JSON extraction.

Baseline versus fine-tuned exact-match accuracy on the 40 held-out transcripts:

- Valid JSON: 100% → 100%
- Amount: 100% → 100%
- Customer: 100% → 100%
- Transaction direction: 80% → 100%

These results measure structured text extraction only and are not speech-recognition WER.

## Planned audio split

Recordings will be grouped by speaker before splitting to avoid the same speaker leaking across train and test sets. The intended split is 80% train and 20% held-out test, with the exact item IDs and random seed documented after assets arrive.

## Evaluation

Report overall WER plus three targeted slices: amounts/numbers, customer names, and general speech. Amount errors are the primary product risk and will be reported separately. Baseline and fine-tuned predictions, normalization rules, substitutions/deletions/insertions, and confidence intervals will be retained with the report.

## Known limitations

- A small convenience sample cannot represent India's Hindi-English dialect diversity.
- Synthetic phrasing overstates lexical coverage and cannot measure acoustic robustness.
- Names and number words are deliberately constrained.
- Shop noise, device microphones, age, gender, code-switching rate, and speaking style may cause large distribution shifts.
- The reported extraction result uses synthetic templates and may overestimate performance on natural shopkeeper speech.

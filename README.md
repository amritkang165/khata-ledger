# Khata Ledger

A voice-first credit ledger for a kirana shopkeeper who will speak a note but will not type one. A note is transcribed by ElevenLabs Scribe, structured by Gemma running through local Ollama, matched to a customer, and written to local SQLite. A Monday brief turns the ledger into a practical collection list.

> **Transcription is cloud for dialect accuracy; every rupee of data stays on this machine.**

This is a runnable vertical slice with local ledger storage, synthetic-only Atlas pattern retrieval, Sentry tracing, and a measured Tinker extraction fine-tune.

## What works now

- `POST /api/note` accepts an audio upload or a development-only transcript.
- The browser can record a voice note directly from the device microphone.
- Audio is sent directly to ElevenLabs Scribe v2 and is not persisted by this app.
- Gemma 3 produces schema-constrained JSON through Ollama.
- A deterministic local parser keeps the demo usable when Ollama is unavailable and reports that fallback in the response.
- Entries below `0.6` confidence, or with no amount, go to `pending_reviews` and never touch the ledger.
- Customer names are fuzzy-matched, including common honorifics such as “bhai” and “ji”.
- SQLite starts empty and records only notes entered by the shopkeeper.
- Local accounts use PBKDF2 password hashing and server-side, expiring sessions; every ledger query is scoped to the signed-in owner.
- `GET /api/brief` returns outstanding totals, repayment patterns, age, and Hinglish collection messages.
- The single-page UI shows note processing, the ledger, and the collection brief.
- Low-confidence notes appear in an owner-only correction queue; transaction history can be inspected and incorrect entries deleted.
- Sentry spans record the model, system prompt, latency, token usage, and a `parse_failure` tag when configured. Parsed financial output is redacted by default.
- Atlas Vector Search retrieves only explicitly synthetic repayment profiles; no real ledger row is uploaded.
- A 10-step Tinker LoRA fine-tune on Qwen 3.5 4B improved held-out synthetic transaction-direction extraction from 80% to 100% (40 examples). Amount, customer, and valid-JSON accuracy remained 100%.

## Run locally

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/), and Ollama.

```bash
cp .env.example .env
ollama pull gemma3:4b
uv sync --extra dev --extra experiment
./start.sh
```

Open <http://localhost:8000>. Environment variables are read from the shell; either export `.env` values or use your preferred dotenv runner. Without an ElevenLabs key, the manual transcript box still exercises extraction, matching, review gating, SQLite, and the brief.

Create the first account in the browser. On an installation upgraded from the earlier single-user build, that first account safely claims the existing local ledger entries. Later accounts always start with an empty, isolated ledger.

Try:

```text
Ramesh bhai ko 850 rupaye ka ration diya, Friday tak dega
```

Tests:

```bash
uv run pytest -q
```

Docker is also available. Ollama stays on the host, outside the Compose stack:

```bash
docker compose up --build
```

## Deploy the synthetic demo on Render

`render.yaml` defines a paid 512 MB Docker web service in Singapore with a 1 GB persistent disk mounted at `/var/data`. Render's filesystem is otherwise ephemeral, so `KHATA_DB_PATH` points to that disk. Secret values are intentionally omitted and must be entered in Render's dashboard.

The public hosted demo sets `OLLAMA_ENABLED=false` and uses the deterministic extraction fallback because it cannot reach the shopkeeper's local Ollama process. The complete Gemma/Ollama flow remains a local-only privacy feature. Use only synthetic demonstration notes on the public deployment.

The Docker build context excludes `.env`, local SQLite data, voice notes, results, tests, and the virtual environment.

## Architecture and privacy boundary

```text
voice note ──temporary upload──> ElevenLabs Scribe ──transcript──┐
                                                               v
browser <──API response── FastAPI ──> local Gemma/Ollama ──> SQLite
                              └────> Sentry trace (no PII by default)
```

The financial system of record is SQLite. The app does not store uploaded audio. Manual transcript input exists only for development and judging resilience. Sentry is disabled unless `SENTRY_DSN` is set, and financial output is redacted from traces by default. `ALLOW_SYNTHETIC_TRACE_DATA=true` may be used only with the repository's synthetic demo notes to capture judging evidence. Atlas contains synthetic pattern documents only—never the real ledger or customer PII.

## API

- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
- `POST /api/note`: multipart form with either `audio` or `transcript`
- `GET /api/ledger`: current per-customer balances
- `GET /api/transactions`, `DELETE /api/transactions/{id}`: owner-scoped history and correction
- `GET /api/reviews`, `POST /api/reviews/{id}/approve`, `DELETE /api/reviews/{id}`
- `GET /api/brief`: weekly collection brief
- `GET /api/health`: service and model configuration

## Training and evaluation assets

Synthetic data is never inserted into the real ledger. Generate the reproducible 200-example extraction corpus with:

```bash
python scripts/seed/generate_transcripts.py
```

Real voice notes belong in `data/voice_notes/` and remain gitignored. `TODO(ASSET)`: add the owner's 20 consented recordings and a manifest before Tinker evaluation.

## Built with Copilot

Placeholder for the two required build-session screenshots and an honest assessment. Do not fabricate this evidence; add it from the actual Copilot sessions before submission.

## Tinker evaluation

Tinker's live model catalog did not expose Whisper/audio fine-tuning, so the measured Tinker experiment fine-tunes transcript-to-ledger JSON extraction instead. The deterministic 80/20 split contains 160 synthetic training transcripts and 40 held-out synthetic transcripts. Results are stored in `results/tinker_extraction_metrics.json`; the comparison chart is `results/tinker-before-after.png`.

These are text-extraction exact-match results, not speech WER. No acoustic improvement is claimed.

## Current gaps

- Measured speech WER is not available because Tinker did not expose a trainable Whisper/audio model. Do not present extraction accuracy as WER.
- Atlas retrieval remains isolated to eight explicitly synthetic profiles. The SQLite ledger and real customer data are never synchronized to Atlas.
- Collection-message generation currently uses a safe local template; Gemma-generated tone will follow after evaluation.
- Due phrases are retained as spoken; calendar normalization and true “days overdue” are still pending.
- ElevenLabs, Ollama, Sentry, Tinker, and Atlas were smoke-tested locally; deployment still requires environment-specific credentials and services.

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.brief.service import build_weekly_brief
from app.config import settings
from app.db.sqlite import Ledger
from app.pipeline.extract import extract_entry
from app.pipeline.match import match_customer
from app.pipeline.transcribe import TranscriptionError, transcribe_audio
from app.schemas import NoteResponse

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None


ledger = Ledger(settings.db_path)
UI_DIR = Path(__file__).parent / "ui"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ledger.initialize()
    ledger.seed_demo()
    yield


if settings.sentry_dsn and sentry_sdk:
    sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=1.0, send_default_pii=False)

app = FastAPI(title="Khata Ledger", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=UI_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(UI_DIR / "index.html")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "privacy": "ledger-local",
        "ollama_model": settings.ollama_model,
        "ollama_enabled": settings.ollama_enabled,
    }


@app.get("/api/ledger")
def get_ledger():
    return {"customers": ledger.ledger_rows()}


@app.get("/api/brief")
def get_brief():
    return build_weekly_brief(ledger)


@app.get("/api/similar")
def get_similar(profile_id: str = "SYN-001"):
    """Retrieve neighbors for a synthetic demo profile; never accepts real ledger data."""
    try:
        from app.db.atlas import AtlasPatternStore

        return AtlasPatternStore(settings).similar_to_profile(profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Synthetic profile not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Atlas pattern store unavailable: {type(exc).__name__}") from exc


@app.post("/api/note", response_model=NoteResponse)
async def post_note(
    audio: UploadFile | None = File(default=None),
    transcript: str | None = Form(default=None),
):
    if transcript and transcript.strip():
        text = transcript.strip()
        transcription_provider = "manual-demo-input"
    elif audio:
        try:
            text = await transcribe_audio(
                audio.filename or "note.webm", await audio.read(), audio.content_type or "audio/webm", settings
            )
        except TranscriptionError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        transcription_provider = "elevenlabs-scribe"
    else:
        raise HTTPException(status_code=422, detail="Provide an audio file or a transcript")

    result = await extract_entry(text, settings)
    entry = result.entry
    if entry.confidence < 0.6 or entry.amount_rupees is None:
        ledger.add_review(text, entry.model_dump_json(), "low confidence or missing amount")
        return NoteResponse(
            transcript=text, extracted=entry, status="review_required",
            transcription_provider=transcription_provider, extraction_provider=result.provider,
        )

    matched_name, _score = match_customer(entry.customer_name, ledger.customer_names())
    transaction = ledger.add_transaction(
        customer_name=matched_name, amount_rupees=entry.amount_rupees,
        transaction_type=entry.transaction_type, due_day=entry.due_day,
        context=entry.context, transcript=text,
    )
    return NoteResponse(
        transcript=text, extracted=entry, status="inserted", transaction=transaction,
        matched_customer=matched_name, transcription_provider=transcription_provider,
        extraction_provider=result.provider,
    )

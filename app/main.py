from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.brief.service import build_weekly_brief
from app.auth import (
    AuthValidationError,
    hash_password,
    new_session_token,
    normalize_email,
    session_token_hash,
    verify_password,
)
from app.config import settings
from app.db.sqlite import Ledger
from app.pipeline.extract import extract_entry
from app.pipeline.match import match_customer
from app.pipeline.transcribe import TranscriptionError, transcribe_audio
from app.schemas import LoginRequest, NoteResponse, RegisterRequest, UserResponse

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None


ledger = Ledger(settings.db_path)
UI_DIR = Path(__file__).parent / "ui"
SESSION_COOKIE = "khata_session"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ledger.initialize()
    yield


if settings.sentry_dsn and sentry_sdk:
    sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=1.0, send_default_pii=False)

app = FastAPI(title="Khata Ledger", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=UI_DIR), name="static")


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )


def current_user(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    user = ledger.account_for_session(session_token_hash(token)) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to access your ledger")
    return user


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


@app.post("/api/auth/register", response_model=UserResponse, status_code=201)
def register(payload: RegisterRequest, response: Response):
    try:
        email = normalize_email(payload.email)
        password_hash = hash_password(payload.password)
    except AuthValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user = ledger.create_account(payload.display_name, email, password_hash)
    if not user:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    ledger.claim_legacy_data_for_first_account(user["id"])
    token = new_session_token()
    ledger.create_session(user["id"], session_token_hash(token))
    _set_session_cookie(response, token)
    return user


@app.post("/api/auth/login", response_model=UserResponse)
def login(payload: LoginRequest, response: Response):
    try:
        email = normalize_email(payload.email)
    except AuthValidationError as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password") from exc
    account = ledger.account_by_email(email)
    if not account or not verify_password(payload.password, account["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = new_session_token()
    ledger.create_session(account["id"], session_token_hash(token))
    _set_session_cookie(response, token)
    return {key: account[key] for key in ("id", "display_name", "email")}


@app.post("/api/auth/logout", status_code=204)
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        ledger.delete_session(session_token_hash(token))
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")


@app.get("/api/auth/me", response_model=UserResponse)
def auth_me(user: dict = Depends(current_user)):
    return user


@app.get("/api/ledger")
def get_ledger(user: dict = Depends(current_user)):
    return {"customers": ledger.ledger_rows(user["id"])}


@app.get("/api/brief")
def get_brief(user: dict = Depends(current_user)):
    return build_weekly_brief(ledger, user["id"])


@app.get("/api/similar")
def get_similar(profile_id: str = "SYN-001", _user: dict = Depends(current_user)):
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
    user: dict = Depends(current_user),
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
        ledger.add_review(user["id"], text, entry.model_dump_json(), "low confidence or missing amount")
        return NoteResponse(
            transcript=text, extracted=entry, status="review_required",
            transcription_provider=transcription_provider, extraction_provider=result.provider,
        )

    matched_name, _score = match_customer(entry.customer_name, ledger.customer_names(user["id"]))
    transaction = ledger.add_transaction(
        user_id=user["id"], customer_name=matched_name, amount_rupees=entry.amount_rupees,
        transaction_type=entry.transaction_type, due_day=entry.due_day,
        context=entry.context, transcript=text,
    )
    return NoteResponse(
        transcript=text, extracted=entry, status="inserted", transaction=transaction,
        matched_customer=matched_name, transcription_provider=transcription_provider,
        extraction_provider=result.provider,
    )

from __future__ import annotations

import httpx

from app.config import Settings


class TranscriptionError(RuntimeError):
    pass


async def transcribe_audio(filename: str, content: bytes, content_type: str, settings: Settings) -> str:
    if not settings.elevenlabs_api_key:
        raise TranscriptionError("ELEVENLABS_API_KEY is not configured")
    files = {"file": (filename, content, content_type or "application/octet-stream")}
    data = {"model_id": settings.elevenlabs_model_id, "language_code": "hin"}
    headers = {"xi-api-key": settings.elevenlabs_api_key}
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            "https://api.elevenlabs.io/v1/speech-to-text", headers=headers, data=data, files=files
        )
    if response.is_error:
        raise TranscriptionError(f"ElevenLabs returned HTTP {response.status_code}: {response.text[:240]}")
    transcript = response.json().get("text", "").strip()
    if not transcript:
        raise TranscriptionError("ElevenLabs returned an empty transcript")
    return transcript


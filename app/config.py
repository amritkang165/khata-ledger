from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path(os.getenv("KHATA_DB_PATH", ROOT / "data" / "khata.db"))
    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    elevenlabs_model_id: str = os.getenv("ELEVENLABS_MODEL_ID", "scribe_v2")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma3:4b")
    ollama_enabled: bool = os.getenv("OLLAMA_ENABLED", "true").lower() == "true"
    sentry_dsn: str = os.getenv("SENTRY_DSN", "")
    allow_synthetic_trace_data: bool = os.getenv("ALLOW_SYNTHETIC_TRACE_DATA", "false").lower() == "true"
    mongodb_uri: str = os.getenv("MONGODB_URI", "")
    atlas_database: str = os.getenv("ATLAS_DATABASE", "khata_patterns")
    atlas_collection: str = os.getenv("ATLAS_COLLECTION", "synthetic_customer_patterns")
    atlas_vector_index: str = os.getenv("ATLAS_VECTOR_INDEX", "pattern_vector_index")


settings = Settings()

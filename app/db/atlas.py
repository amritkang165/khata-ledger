from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.config import Settings


SYNTHETIC_PATTERNS = [
    {"profile_id": "SYN-001", "display_name": "Asha (synthetic)", "pattern_text": "School fees and books. Usually repays within 6 days, reliably before Friday.", "average_days_to_repay": 6, "risk_band": "low"},
    {"profile_id": "SYN-002", "display_name": "Bharat (synthetic)", "pattern_text": "Routine ration purchases. Pays in small installments over 18 days.", "average_days_to_repay": 18, "risk_band": "medium"},
    {"profile_id": "SYN-003", "display_name": "Chanda (synthetic)", "pattern_text": "School books and child fees. Repays quickly after salary day, about 7 days.", "average_days_to_repay": 7, "risk_band": "low"},
    {"profile_id": "SYN-004", "display_name": "Danish (synthetic)", "pattern_text": "Festival and wedding purchases. Frequently delays repayment beyond 35 days.", "average_days_to_repay": 38, "risk_band": "high"},
    {"profile_id": "SYN-005", "display_name": "Ekta (synthetic)", "pattern_text": "Medicine purchases. Clears the full balance within 4 days without reminders.", "average_days_to_repay": 4, "risk_band": "low"},
    {"profile_id": "SYN-006", "display_name": "Farhan (synthetic)", "pattern_text": "Diwali goods and non-essential items. Needs two reminders and pays after 28 days.", "average_days_to_repay": 28, "risk_band": "high"},
    {"profile_id": "SYN-007", "display_name": "Geeta (synthetic)", "pattern_text": "Monthly ration. Settles the account on salary day in about 14 days.", "average_days_to_repay": 14, "risk_band": "medium"},
    {"profile_id": "SYN-008", "display_name": "Harish (synthetic)", "pattern_text": "Wedding and luxury goods. Makes partial payments and stretches debt to 45 days.", "average_days_to_repay": 45, "risk_band": "high"},
]


@dataclass
class AtlasPatternStore:
    settings: Settings

    def __post_init__(self) -> None:
        if not self.settings.mongodb_uri:
            raise RuntimeError("MONGODB_URI is not configured")
        from pymongo import MongoClient

        self.client = MongoClient(self.settings.mongodb_uri, serverSelectionTimeoutMS=8_000)
        self.collection = self.client[self.settings.atlas_database][self.settings.atlas_collection]

    def ping(self) -> None:
        self.client.admin.command("ping")

    def seed(self) -> int:
        model = embedding_model()
        for pattern in SYNTHETIC_PATTERNS:
            document = {
                **pattern,
                "embedding": model.encode(pattern["pattern_text"], normalize_embeddings=True).tolist(),
                "synthetic": True,
            }
            self.collection.replace_one({"profile_id": pattern["profile_id"]}, document, upsert=True)
        return len(SYNTHETIC_PATTERNS)

    def create_vector_index(self) -> str:
        from pymongo.operations import SearchIndexModel

        if any(True for _ in self.collection.list_search_indexes(self.settings.atlas_vector_index)):
            return self.settings.atlas_vector_index
        definition = {
            "fields": [
                {"type": "vector", "path": "embedding", "numDimensions": 384, "similarity": "cosine"},
                {"type": "filter", "path": "synthetic"},
            ]
        }
        model = SearchIndexModel(definition=definition, name=self.settings.atlas_vector_index, type="vectorSearch")
        return self.collection.create_search_index(model=model)

    def similar_to_profile(self, profile_id: str, limit: int = 3) -> dict[str, Any]:
        source = self.collection.find_one({"profile_id": profile_id, "synthetic": True})
        if not source:
            raise KeyError(profile_id)
        pipeline = [
            {"$vectorSearch": {"index": self.settings.atlas_vector_index, "path": "embedding", "queryVector": source["embedding"], "numCandidates": 50, "limit": limit + 1, "filter": {"synthetic": True}}},
            {"$match": {"profile_id": {"$ne": profile_id}}},
            {"$limit": limit},
            {"$project": {"_id": 0, "profile_id": 1, "display_name": 1, "pattern_text": 1, "average_days_to_repay": 1, "risk_band": 1, "score": {"$meta": "vectorSearchScore"}}},
        ]
        return {
            "source": {key: source[key] for key in ("profile_id", "display_name", "pattern_text")},
            "matches": list(self.collection.aggregate(pipeline)),
            "privacy": "synthetic-data-only",
        }


@lru_cache(maxsize=1)
def embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

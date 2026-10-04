from app.config import settings
from app.db.atlas import AtlasPatternStore


def main() -> None:
    store = AtlasPatternStore(settings)
    store.ping()
    count = store.seed()
    index_name = store.create_vector_index()
    print(f"Seeded {count} synthetic profiles")
    print(f"Vector index requested: {index_name}")
    print("No SQLite ledger data or real customer PII was uploaded")


if __name__ == "__main__":
    main()

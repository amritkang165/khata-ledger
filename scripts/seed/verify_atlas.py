from app.config import settings
from app.db.atlas import AtlasPatternStore


def main() -> None:
    store = AtlasPatternStore(settings)
    store.ping()
    indexes = list(store.collection.list_search_indexes(settings.atlas_vector_index))
    if not indexes:
        raise SystemExit("Vector index was not found")
    index = indexes[0]
    print(f"Index status: {index.get('status', 'unknown')}; queryable={index.get('queryable', False)}")
    if not index.get("queryable", False):
        raise SystemExit("Index is still building; run this check again in about one minute")
    result = store.similar_to_profile("SYN-001")
    print(f"Source: {result['source']['display_name']}")
    for match in result["matches"]:
        print(f"Match: {match['display_name']} score={match['score']:.3f}")
    print("Verified synthetic-only Atlas Vector Search")


if __name__ == "__main__":
    main()

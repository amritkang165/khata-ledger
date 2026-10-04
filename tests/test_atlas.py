from app.db.atlas import SYNTHETIC_PATTERNS


def test_atlas_seed_is_explicitly_synthetic_and_unique():
    assert len(SYNTHETIC_PATTERNS) == 8
    assert len({item["profile_id"] for item in SYNTHETIC_PATTERNS}) == 8
    assert all(item["display_name"].endswith("(synthetic)") for item in SYNTHETIC_PATTERNS)

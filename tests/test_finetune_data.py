from scripts.finetune.prepare_data import prepare


def test_tinker_split_is_deterministic_and_disjoint():
    train, test = prepare()
    train_ids = {row["id"] for row in train}
    test_ids = {row["id"] for row in test}
    assert len(train) == 160
    assert len(test) == 40
    assert train_ids.isdisjoint(test_ids)

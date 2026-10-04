from app.pipeline.match import match_customer


def test_honorific_and_typo_match():
    name, score = match_customer("Rames bhai", ["Ramesh", "Mohan"])
    assert name == "Ramesh"
    assert score >= 70


def test_devanagari_name_matches_latin_ledger_name():
    name, score = match_customer("सुनीता", ["Sunita", "Shabnam"])
    assert name == "Sunita"
    assert score == 100

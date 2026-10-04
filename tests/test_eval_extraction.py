from scripts.finetune.eval_extraction import normalize_name, parse_prediction


def test_prediction_parser_handles_json_fence():
    assert parse_prediction('```json\n{"amount_rupees": 850}\n```') == {"amount_rupees": 850}


def test_name_normalization_removes_honorific():
    assert normalize_name("Iqbal bhai") == normalize_name("Iqbal")

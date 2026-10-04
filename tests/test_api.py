from fastapi.testclient import TestClient

import app.main as main
from app.db.sqlite import Ledger


def test_manual_transcript_golden_path(tmp_path, monkeypatch):
    test_ledger = Ledger(tmp_path / "api.db")
    monkeypatch.setattr(main, "ledger", test_ledger)
    with TestClient(main.app) as client:
        response = client.post("/api/note", data={"transcript": "Ramesh 850 rupaye ration Friday"})
    assert response.status_code == 200
    assert response.json()["status"] == "inserted"
    assert response.json()["extracted"]["amount_rupees"] == 850


def test_uncertain_note_is_not_inserted(tmp_path, monkeypatch):
    test_ledger = Ledger(tmp_path / "review.db")
    monkeypatch.setattr(main, "ledger", test_ledger)
    with TestClient(main.app) as client:
        before = client.get("/api/ledger").json()
        response = client.post("/api/note", data={"transcript": "shayad Ramesh ka kuch baki hai"})
        after = client.get("/api/ledger").json()
    assert response.status_code == 200
    assert response.json()["status"] == "review_required"
    assert before == after

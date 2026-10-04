from fastapi.testclient import TestClient

import app.main as main
from app.db.sqlite import Ledger


def register(client: TestClient, email: str = "owner@example.com"):
    return client.post("/api/auth/register", json={
        "display_name": "Shop Owner", "email": email, "password": "strong-pass-123",
    })


def test_manual_transcript_golden_path(tmp_path, monkeypatch):
    test_ledger = Ledger(tmp_path / "api.db")
    monkeypatch.setattr(main, "ledger", test_ledger)
    with TestClient(main.app) as client:
        assert register(client).status_code == 201
        response = client.post("/api/note", data={"transcript": "Ramesh 850 rupaye ration Friday"})
    assert response.status_code == 200
    assert response.json()["status"] == "inserted"
    assert response.json()["extracted"]["amount_rupees"] == 850


def test_uncertain_note_is_not_inserted(tmp_path, monkeypatch):
    test_ledger = Ledger(tmp_path / "review.db")
    monkeypatch.setattr(main, "ledger", test_ledger)
    with TestClient(main.app) as client:
        assert register(client).status_code == 201
        before = client.get("/api/ledger").json()
        response = client.post("/api/note", data={"transcript": "shayad Ramesh ka kuch baki hai"})
        after = client.get("/api/ledger").json()
    assert response.status_code == 200
    assert response.json()["status"] == "review_required"
    assert before == after


def test_ledger_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ledger", Ledger(tmp_path / "private.db"))
    with TestClient(main.app) as client:
        assert client.get("/api/ledger").status_code == 401


def test_accounts_have_isolated_ledgers(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ledger", Ledger(tmp_path / "isolated.db"))
    with TestClient(main.app) as first:
        assert register(first, "first@example.com").status_code == 201
        assert first.post("/api/note", data={"transcript": "Ramesh 850 rupaye ration Friday"}).status_code == 200
        assert len(first.get("/api/ledger").json()["customers"]) == 1
    with TestClient(main.app) as second:
        assert register(second, "second@example.com").status_code == 201
        assert second.get("/api/ledger").json()["customers"] == []

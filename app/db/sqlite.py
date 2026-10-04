from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    phone TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    amount_rupees INTEGER NOT NULL CHECK(amount_rupees > 0),
    transaction_type TEXT NOT NULL CHECK(transaction_type IN ('credit_given','credit_paid')),
    due_day TEXT,
    context TEXT,
    transcript TEXT,
    happened_on TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pending_reviews (
    id INTEGER PRIMARY KEY,
    transcript TEXT NOT NULL,
    extracted_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def customer_names(self) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute("SELECT name FROM customers ORDER BY name").fetchall()
        return [row["name"] for row in rows]

    def get_or_create_customer(self, name: str) -> sqlite3.Row:
        with self.connect() as connection:
            connection.execute("INSERT OR IGNORE INTO customers(name) VALUES (?)", (name.strip(),))
            return connection.execute(
                "SELECT id, name FROM customers WHERE name = ? COLLATE NOCASE", (name.strip(),)
            ).fetchone()

    def add_transaction(self, *, customer_name: str, amount_rupees: int,
                        transaction_type: str, due_day: str | None,
                        context: str | None, transcript: str,
                        happened_on: str | None = None) -> dict:
        customer = self.get_or_create_customer(customer_name)
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO transactions
                   (customer_id, amount_rupees, transaction_type, due_day, context, transcript, happened_on)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (customer["id"], amount_rupees, transaction_type, due_day, context,
                 transcript, happened_on or date.today().isoformat()),
            )
            row = connection.execute(
                """SELECT t.*, c.name AS customer_name FROM transactions t
                   JOIN customers c ON c.id=t.customer_id WHERE t.id=?""",
                (cursor.lastrowid,),
            ).fetchone()
        return dict(row)

    def add_review(self, transcript: str, extracted_json: str, reason: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO pending_reviews(transcript, extracted_json, reason) VALUES (?,?,?)",
                (transcript, extracted_json, reason),
            )

    def ledger_rows(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT c.id, c.name,
                    COALESCE(SUM(CASE WHEN t.transaction_type='credit_given' THEN t.amount_rupees ELSE -t.amount_rupees END),0) outstanding_rupees,
                    MAX(t.happened_on) last_activity,
                    COUNT(t.id) transaction_count
                   FROM customers c LEFT JOIN transactions t ON t.customer_id=c.id
                   GROUP BY c.id ORDER BY outstanding_rupees DESC, c.name"""
            ).fetchall()
        return [dict(row) for row in rows]

    def transaction_history(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT t.*, c.name AS customer_name FROM transactions t
                   JOIN customers c ON c.id=t.customer_id
                   ORDER BY t.happened_on, t.id"""
            ).fetchall()
        return [dict(row) for row in rows]

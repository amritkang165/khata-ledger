from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
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
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);
CREATE TABLE IF NOT EXISTS ledger_customers (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name TEXT NOT NULL COLLATE NOCASE,
    phone TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name)
);
CREATE TABLE IF NOT EXISTS ledger_transactions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    customer_id INTEGER NOT NULL REFERENCES ledger_customers(id) ON DELETE CASCADE,
    amount_rupees INTEGER NOT NULL CHECK(amount_rupees > 0),
    transaction_type TEXT NOT NULL CHECK(transaction_type IN ('credit_given','credit_paid')),
    due_day TEXT,
    context TEXT,
    transcript TEXT,
    happened_on TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ledger_transactions_user ON ledger_transactions(user_id, happened_on);
CREATE TABLE IF NOT EXISTS ledger_reviews (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    transcript TEXT NOT NULL,
    extracted_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
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

    def create_account(self, display_name: str, email: str, password_hash: str) -> dict | None:
        with self.connect() as connection:
            try:
                cursor = connection.execute(
                    "INSERT INTO accounts(display_name, email, password_hash) VALUES (?,?,?)",
                    (display_name.strip(), email, password_hash),
                )
            except sqlite3.IntegrityError:
                return None
            row = connection.execute(
                "SELECT id, display_name, email FROM accounts WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
        return dict(row)

    def account_by_email(self, email: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, display_name, email, password_hash FROM accounts WHERE email=? COLLATE NOCASE",
                (email,),
            ).fetchone()
        return dict(row) if row else None

    def create_session(self, user_id: int, token_hash: str, days: int = 7) -> None:
        expires_at = (datetime.now(UTC) + timedelta(days=days)).isoformat()
        with self.connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (datetime.now(UTC).isoformat(),))
            connection.execute(
                "INSERT INTO auth_sessions(token_hash, user_id, expires_at) VALUES (?,?,?)",
                (token_hash, user_id, expires_at),
            )

    def account_for_session(self, token_hash: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT a.id, a.display_name, a.email FROM auth_sessions s
                   JOIN accounts a ON a.id=s.user_id
                   WHERE s.token_hash=? AND s.expires_at>?""",
                (token_hash, datetime.now(UTC).isoformat()),
            ).fetchone()
        return dict(row) if row else None

    def delete_session(self, token_hash: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE token_hash=?", (token_hash,))

    def claim_legacy_data_for_first_account(self, user_id: int) -> int:
        """One-time migration of pre-auth ledger rows to the installation owner."""
        with self.connect() as connection:
            claimed = connection.execute(
                "SELECT value FROM app_metadata WHERE key='legacy_ledger_claimed'"
            ).fetchone()
            account_count = connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
            if claimed or account_count != 1:
                return 0
            legacy_customers = connection.execute("SELECT id, name, phone FROM customers").fetchall()
            id_map: dict[int, int] = {}
            for customer in legacy_customers:
                cursor = connection.execute(
                    "INSERT INTO ledger_customers(user_id, name, phone) VALUES (?,?,?)",
                    (user_id, customer["name"], customer["phone"]),
                )
                id_map[customer["id"]] = cursor.lastrowid
            legacy_transactions = connection.execute("SELECT * FROM transactions ORDER BY id").fetchall()
            for transaction in legacy_transactions:
                connection.execute(
                    """INSERT INTO ledger_transactions
                       (user_id, customer_id, amount_rupees, transaction_type, due_day, context,
                        transcript, happened_on, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (user_id, id_map[transaction["customer_id"]], transaction["amount_rupees"],
                     transaction["transaction_type"], transaction["due_day"], transaction["context"],
                     transaction["transcript"], transaction["happened_on"], transaction["created_at"]),
                )
            connection.execute(
                "INSERT INTO app_metadata(key, value) VALUES ('legacy_ledger_claimed', ?)",
                (str(user_id),),
            )
        return len(legacy_transactions)

    def customer_names(self, user_id: int) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT name FROM ledger_customers WHERE user_id=? ORDER BY name", (user_id,)
            ).fetchall()
        return [row["name"] for row in rows]

    def get_or_create_customer(self, user_id: int, name: str) -> sqlite3.Row:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO ledger_customers(user_id, name) VALUES (?,?)",
                (user_id, name.strip()),
            )
            return connection.execute(
                "SELECT id, name FROM ledger_customers WHERE user_id=? AND name=? COLLATE NOCASE",
                (user_id, name.strip()),
            ).fetchone()

    def add_transaction(self, *, user_id: int, customer_name: str, amount_rupees: int,
                        transaction_type: str, due_day: str | None,
                        context: str | None, transcript: str,
                        happened_on: str | None = None) -> dict:
        customer = self.get_or_create_customer(user_id, customer_name)
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO ledger_transactions
                   (user_id, customer_id, amount_rupees, transaction_type, due_day, context, transcript, happened_on)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, customer["id"], amount_rupees, transaction_type, due_day, context,
                 transcript, happened_on or date.today().isoformat()),
            )
            row = connection.execute(
                """SELECT t.*, c.name AS customer_name FROM ledger_transactions t
                   JOIN ledger_customers c ON c.id=t.customer_id WHERE t.id=? AND t.user_id=?""",
                (cursor.lastrowid, user_id),
            ).fetchone()
        return dict(row)

    def add_review(self, user_id: int, transcript: str, extracted_json: str, reason: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO ledger_reviews(user_id, transcript, extracted_json, reason) VALUES (?,?,?,?)",
                (user_id, transcript, extracted_json, reason),
            )

    def ledger_rows(self, user_id: int) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT c.id, c.name,
                    COALESCE(SUM(CASE WHEN t.transaction_type='credit_given' THEN t.amount_rupees ELSE -t.amount_rupees END),0) outstanding_rupees,
                    MAX(t.happened_on) last_activity,
                    COUNT(t.id) transaction_count
                   FROM ledger_customers c LEFT JOIN ledger_transactions t
                     ON t.customer_id=c.id AND t.user_id=c.user_id
                   WHERE c.user_id=?
                   GROUP BY c.id ORDER BY outstanding_rupees DESC, c.name""",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def transaction_history(self, user_id: int) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT t.*, c.name AS customer_name FROM ledger_transactions t
                   JOIN ledger_customers c ON c.id=t.customer_id
                   WHERE t.user_id=? ORDER BY t.happened_on, t.id""",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

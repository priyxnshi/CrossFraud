"""Optional SQLite export (used by the Phase 5 backend). Ground truth is NOT exported."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id)",
    "CREATE INDEX IF NOT EXISTS idx_txn_receiver ON transactions(receiver_id)",
    "CREATE INDEX IF NOT EXISTS idx_txn_sender ON transactions(sender_id)",
]


def load_sqlite(tables: dict[str, pd.DataFrame], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        for name, df in tables.items():
            df.to_sql(name, con, if_exists="replace", index=False)
        for stmt in INDEXES:
            try:
                con.execute(stmt)
            except sqlite3.OperationalError:
                pass
        con.commit()

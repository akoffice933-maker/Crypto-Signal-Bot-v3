#!/usr/bin/env python3
"""Apply pair indexes to existing database."""

import sqlite3
from pathlib import Path

db_path = Path("data/signals.db")
if not db_path.exists():
    print(f"DB not found: {db_path}")
    exit(1)

conn = sqlite3.connect(str(db_path))
conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_pair ON signals(pair, created_at DESC)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_cycle_pair ON cycle_summary(pair, created_at DESC)")
conn.commit()
conn.close()

print("✅ Indexes applied successfully")

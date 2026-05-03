import asyncio
import os
import sys
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import Database


def test_oi_snapshots_are_pair_scoped():
    tmp_root = Path(__file__).resolve().parent / "_tmp_db"
    tmp_dir = tmp_root / uuid4().hex
    tmp_dir.mkdir(parents=True, exist_ok=True)
    db = Database(str(tmp_dir / "test.db"))
    try:
        asyncio.run(db.connect())
        asyncio.run(db._exec(
            "INSERT INTO oi_snapshots (recorded_at, pair, open_interest, price) VALUES "
            "(datetime('now','-70 minutes'), 'BTCUSDT', 1000, 70000), "
            "(datetime('now','-70 minutes'), 'ETHUSDT', 2000, 2000), "
            "(datetime('now','-10 minutes'), 'BTCUSDT', 1100, 71000)"
        ))

        eth_snapshot = asyncio.run(db.get_oi_ago("ETHUSDT", 60))
        btc_snapshot = asyncio.run(db.get_oi_ago("BTCUSDT", 60))

        assert eth_snapshot == (2000.0, 2000.0)
        assert btc_snapshot == (1000.0, 70000.0)
    finally:
        asyncio.run(db.close())
        if tmp_dir.exists():
            rmtree(tmp_dir, ignore_errors=True)


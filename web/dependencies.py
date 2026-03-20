from fastapi import HTTPException
from database.db import Database

_db: Database = None


def set_db(db: Database):
    global _db
    _db = db


async def get_db() -> Database:
    if _db is None:
        raise HTTPException(status_code=500, detail="Database not initialised")
    return _db

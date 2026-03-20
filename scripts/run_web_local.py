import asyncio
import os
import sys

import uvicorn

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import Database
from web.app import app
from web.dependencies import set_db


async def main():
    db = Database("data/signals.db")
    await db.connect()
    set_db(db)
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())

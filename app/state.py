import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from app.config import get_settings
from app.models import StreamState

logger = logging.getLogger(__name__)

_db: aiosqlite.Connection | None = None


async def init_db() -> None:
    global _db
    settings = get_settings()
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _db = await aiosqlite.connect(str(db_path))
    _db.row_factory = aiosqlite.Row
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS streams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            twitch_channel TEXT NOT NULL,
            reddit_thread_id TEXT,
            docket TEXT DEFAULT '[]',
            stream_start TEXT,
            is_live BOOLEAN DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migration: add ended_at column if it doesn't exist
    try:
        await _db.execute("ALTER TABLE streams ADD COLUMN ended_at TEXT")
    except Exception:
        pass  # Column already exists
    await _db.commit()
    logger.info("Database initialized at %s", db_path)


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


def _row_to_state(row: aiosqlite.Row) -> StreamState:
    return StreamState(
        id=row["id"],
        twitch_channel=row["twitch_channel"],
        reddit_thread_id=row["reddit_thread_id"],
        docket=json.loads(row["docket"]) if row["docket"] else [],
        stream_start=row["stream_start"],
        is_live=bool(row["is_live"]),
        ended_at=row["ended_at"],
    )


async def create_stream(
    channel: str, thread_id: str, first_game: str | None, start_time: str
) -> StreamState:
    docket = [first_game] if first_game else []
    cursor = await _db.execute(
        "INSERT INTO streams (twitch_channel, reddit_thread_id, docket, stream_start) VALUES (?, ?, ?, ?)",
        (channel, thread_id, json.dumps(docket), start_time),
    )
    await _db.commit()
    logger.info("Created stream record id=%d for %s", cursor.lastrowid, channel)
    return StreamState(
        id=cursor.lastrowid,
        twitch_channel=channel,
        reddit_thread_id=thread_id,
        docket=docket,
        stream_start=start_time,
        is_live=True,
    )


async def get_active_stream(channel: str) -> StreamState | None:
    cursor = await _db.execute(
        "SELECT * FROM streams WHERE twitch_channel = ? AND is_live = 1 ORDER BY id DESC LIMIT 1",
        (channel,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_state(row)


async def update_docket(stream_id: int, games: list[str]) -> None:
    await _db.execute(
        "UPDATE streams SET docket = ? WHERE id = ?",
        (json.dumps(games), stream_id),
    )
    await _db.commit()


async def update_thread_id(stream_id: int, thread_id: str) -> None:
    await _db.execute(
        "UPDATE streams SET reddit_thread_id = ? WHERE id = ?",
        (thread_id, stream_id),
    )
    await _db.commit()


async def mark_offline(stream_id: int) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    await _db.execute(
        "UPDATE streams SET is_live = 0, ended_at = ? WHERE id = ?",
        (now, stream_id),
    )
    await _db.commit()
    logger.info("Marked stream id=%d as offline at %s", stream_id, now)


async def get_recently_ended_stream(channel: str, grace_seconds: int) -> StreamState | None:
    """Find the most recent stream that ended within the grace period."""
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=grace_seconds)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    cursor = await _db.execute(
        "SELECT * FROM streams WHERE twitch_channel = ? AND is_live = 0 "
        "AND ended_at IS NOT NULL AND ended_at > ? ORDER BY id DESC LIMIT 1",
        (channel, cutoff),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_state(row)


async def reactivate_stream(stream_id: int) -> None:
    """Re-mark a recently-ended stream as live (stream restarted within grace period)."""
    await _db.execute(
        "UPDATE streams SET is_live = 1, ended_at = NULL WHERE id = ?",
        (stream_id,),
    )
    await _db.commit()
    logger.info("Reactivated stream id=%d", stream_id)

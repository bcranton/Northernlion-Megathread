"""Tests for SQLite state persistence layer."""

import os
import tempfile

import pytest

# Set required env vars before importing app modules
os.environ.update({
    "TWITCH_CLIENT_ID": "test_id",
    "TWITCH_CLIENT_SECRET": "test_secret",
    "TWITCH_WEBHOOK_SECRET": "test_webhook_secret",
    "REDDIT_CLIENT_ID": "test_reddit_id",
    "REDDIT_CLIENT_SECRET": "test_reddit_secret",
    "REDDIT_PASSWORD": "test_pass",
    "BASE_URL": "https://test.example.com",
})

from app import state
from app.config import Settings, get_settings


@pytest.fixture(autouse=True)
async def setup_db(tmp_path, monkeypatch):
    """Create a temporary database for each test."""
    db_path = str(tmp_path / "test.db")

    # Override settings to use temp path
    test_settings = Settings(
        twitch_client_id="test",
        twitch_client_secret="test",
        twitch_webhook_secret="test",
        reddit_client_id="test",
        reddit_client_secret="test",
        reddit_password="test",
        base_url="https://test.example.com",
        database_path=db_path,
    )
    monkeypatch.setattr("app.state.get_settings", lambda: test_settings)
    get_settings.cache_clear()

    await state.init_db()
    yield
    await state.close_db()


class TestCreateStream:
    async def test_create_stream(self):
        result = await state.create_stream(
            channel="Northernlion",
            thread_id="abc123",
            first_game="Isaac",
            start_time="2026-02-27T10:00:00Z",
        )
        assert result.id == 1
        assert result.twitch_channel == "Northernlion"
        assert result.reddit_thread_id == "abc123"
        assert result.docket == ["Isaac"]
        assert result.is_live is True

    async def test_create_stream_no_game(self):
        result = await state.create_stream(
            channel="Northernlion",
            thread_id="abc123",
            first_game=None,
            start_time="2026-02-27T10:00:00Z",
        )
        assert result.docket == []


class TestGetActiveStream:
    async def test_get_active_stream(self):
        await state.create_stream("NL", "t1", "Isaac", "2026-01-01T00:00:00Z")
        active = await state.get_active_stream("NL")
        assert active is not None
        assert active.reddit_thread_id == "t1"

    async def test_no_active_stream(self):
        active = await state.get_active_stream("NonExistent")
        assert active is None

    async def test_offline_stream_not_returned(self):
        s = await state.create_stream("NL", "t1", "Isaac", "2026-01-01T00:00:00Z")
        await state.mark_offline(s.id)
        active = await state.get_active_stream("NL")
        assert active is None


class TestUpdateDocket:
    async def test_update_docket(self):
        s = await state.create_stream("NL", "t1", "Isaac", "2026-01-01T00:00:00Z")
        await state.update_docket(s.id, ["Isaac", "Slay The Spire"])
        active = await state.get_active_stream("NL")
        assert active.docket == ["Isaac", "Slay The Spire"]


class TestMarkOffline:
    async def test_mark_offline(self):
        s = await state.create_stream("NL", "t1", "Isaac", "2026-01-01T00:00:00Z")
        await state.mark_offline(s.id)
        active = await state.get_active_stream("NL")
        assert active is None

    async def test_mark_offline_sets_ended_at(self):
        s = await state.create_stream("NL", "t1", "Isaac", "2026-01-01T00:00:00Z")
        await state.mark_offline(s.id)
        recent = await state.get_recently_ended_stream("NL", grace_seconds=3600)
        assert recent is not None
        assert recent.ended_at is not None


class TestGetRecentlyEndedStream:
    async def test_finds_recently_ended_stream(self):
        s = await state.create_stream("NL", "t1", "Isaac", "2026-01-01T00:00:00Z")
        await state.mark_offline(s.id)
        recent = await state.get_recently_ended_stream("NL", grace_seconds=1800)
        assert recent is not None
        assert recent.id == s.id
        assert recent.reddit_thread_id == "t1"

    async def test_ignores_live_streams(self):
        await state.create_stream("NL", "t1", "Isaac", "2026-01-01T00:00:00Z")
        recent = await state.get_recently_ended_stream("NL", grace_seconds=1800)
        assert recent is None

    async def test_ignores_stream_outside_grace_period(self):
        s = await state.create_stream("NL", "t1", "Isaac", "2026-01-01T00:00:00Z")
        await state.mark_offline(s.id)
        # Grace period of 0 seconds means the stream is already outside the window
        recent = await state.get_recently_ended_stream("NL", grace_seconds=0)
        assert recent is None

    async def test_wrong_channel_not_returned(self):
        s = await state.create_stream("NL", "t1", "Isaac", "2026-01-01T00:00:00Z")
        await state.mark_offline(s.id)
        recent = await state.get_recently_ended_stream("OtherChannel", grace_seconds=1800)
        assert recent is None


class TestReactivateStream:
    async def test_reactivate_stream(self):
        s = await state.create_stream("NL", "t1", "Isaac", "2026-01-01T00:00:00Z")
        await state.mark_offline(s.id)

        # Verify it's offline
        active = await state.get_active_stream("NL")
        assert active is None

        # Reactivate
        await state.reactivate_stream(s.id)

        # Verify it's live again
        active = await state.get_active_stream("NL")
        assert active is not None
        assert active.id == s.id
        assert active.is_live is True
        assert active.ended_at is None

    async def test_reactivate_preserves_docket(self):
        s = await state.create_stream("NL", "t1", "Isaac", "2026-01-01T00:00:00Z")
        await state.update_docket(s.id, ["Isaac", "Slay The Spire"])
        await state.mark_offline(s.id)
        await state.reactivate_stream(s.id)

        active = await state.get_active_stream("NL")
        assert active.docket == ["Isaac", "Slay The Spire"]

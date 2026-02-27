"""Tests for Twitch Helix API client."""

import os
from unittest.mock import AsyncMock

import httpx
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

from app import twitch

# Dummy request object needed by httpx.Response.raise_for_status()
_DUMMY_REQUEST = httpx.Request("GET", "https://test.example.com")


def _response(status_code: int, json: dict) -> httpx.Response:
    """Create an httpx.Response with a dummy request attached."""
    return httpx.Response(status_code, json=json, request=_DUMMY_REQUEST)


def _token_response() -> httpx.Response:
    """Create a standard token response."""
    return _response(200, {"access_token": "t", "expires_in": 3600, "token_type": "bearer"})


@pytest.fixture(autouse=True)
def reset_token_cache():
    """Reset the cached token between tests."""
    twitch._access_token = None
    twitch._token_expires_at = 0


class TestGetAppAccessToken:
    async def test_fetches_token(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _response(
            200, {"access_token": "test_token", "expires_in": 3600, "token_type": "bearer"}
        )

        token = await twitch.get_app_access_token(client)
        assert token == "test_token"
        client.post.assert_called_once()

    async def test_caches_token(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _response(
            200, {"access_token": "test_token", "expires_in": 3600, "token_type": "bearer"}
        )

        await twitch.get_app_access_token(client)
        await twitch.get_app_access_token(client)
        # Should only call the API once due to caching
        assert client.post.call_count == 1


class TestGetUserId:
    async def test_resolves_user(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _token_response()
        client.get.return_value = _response(
            200, {"data": [{"id": "12345", "login": "northernlion"}]}
        )

        user_id = await twitch.get_user_id(client, "northernlion")
        assert user_id == "12345"

    async def test_user_not_found(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _token_response()
        client.get.return_value = _response(200, {"data": []})

        with pytest.raises(ValueError, match="not found"):
            await twitch.get_user_id(client, "nonexistent_user")


class TestGetTopClip:
    async def test_returns_clip(self):
        clip_data = {
            "id": "clip1",
            "url": "https://clips.twitch.tv/test",
            "title": "Amazing Clip",
            "creator_name": "clipper",
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _token_response()
        client.get.return_value = _response(200, {"data": [clip_data]})

        result = await twitch.get_top_clip(client, "123", "2026-01-01T00:00:00Z")
        assert result["title"] == "Amazing Clip"

    async def test_no_clips(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _token_response()
        client.get.return_value = _response(200, {"data": []})

        result = await twitch.get_top_clip(client, "123", "2026-01-01T00:00:00Z")
        assert result is None


class TestGetLatestVod:
    async def test_returns_vod(self):
        vod_data = {"id": "v123", "url": "https://www.twitch.tv/videos/123"}
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _token_response()
        client.get.return_value = _response(200, {"data": [vod_data]})

        result = await twitch.get_latest_vod(client, "123")
        assert result["url"] == "https://www.twitch.tv/videos/123"

    async def test_no_vods(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _token_response()
        client.get.return_value = _response(200, {"data": []})

        result = await twitch.get_latest_vod(client, "123")
        assert result is None

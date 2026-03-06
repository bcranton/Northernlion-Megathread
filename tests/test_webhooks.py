"""Tests for Twitch EventSub webhook handler."""

import asyncio
import hashlib
import hmac
import json
import os
import time

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

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

from app.webhooks import _verify_signature


def _make_signature(secret: str, message_id: str, timestamp: str, body: bytes) -> str:
    """Helper to create a valid HMAC-SHA256 signature."""
    hmac_message = message_id.encode() + timestamp.encode() + body
    digest = hmac.new(secret.encode(), hmac_message, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class TestVerifySignature:
    def test_valid_signature(self):
        secret = "my_secret"
        message_id = "msg_123"
        timestamp = "2026-02-27T10:00:00Z"
        body = b'{"test": "data"}'

        sig = _make_signature(secret, message_id, timestamp, body)
        headers = {
            "twitch-eventsub-message-id": message_id,
            "twitch-eventsub-message-timestamp": timestamp,
            "twitch-eventsub-message-signature": sig,
        }
        assert _verify_signature(secret, headers, body) is True

    def test_invalid_signature(self):
        headers = {
            "twitch-eventsub-message-id": "msg_123",
            "twitch-eventsub-message-timestamp": "2026-02-27T10:00:00Z",
            "twitch-eventsub-message-signature": "sha256=invalid",
        }
        assert _verify_signature("my_secret", headers, b"body") is False

    def test_wrong_secret(self):
        secret = "correct_secret"
        message_id = "msg_123"
        timestamp = "2026-02-27T10:00:00Z"
        body = b'{"test": "data"}'

        sig = _make_signature(secret, message_id, timestamp, body)
        headers = {
            "twitch-eventsub-message-id": message_id,
            "twitch-eventsub-message-timestamp": timestamp,
            "twitch-eventsub-message-signature": sig,
        }
        assert _verify_signature("wrong_secret", headers, body) is False

    def test_empty_headers(self):
        assert _verify_signature("secret", {}, b"body") is False


class TestWebhookEndpoint:
    """Integration tests using FastAPI TestClient."""

    @pytest.fixture
    def client(self):
        from httpx import ASGITransport, AsyncClient
        from app.webhooks import router, _processed_message_ids
        from fastapi import FastAPI

        test_app = FastAPI()
        test_app.include_router(router)
        _processed_message_ids.clear()
        transport = ASGITransport(app=test_app)
        return AsyncClient(transport=transport, base_url="http://test")

    def _signed_headers(self, body: bytes, message_id: str = "msg_1") -> dict:
        secret = "test_webhook_secret"
        timestamp = "2026-02-27T10:00:00Z"
        sig = _make_signature(secret, message_id, timestamp, body)
        return {
            "twitch-eventsub-message-id": message_id,
            "twitch-eventsub-message-timestamp": timestamp,
            "twitch-eventsub-message-signature": sig,
            "twitch-eventsub-message-type": "notification",
            "content-type": "application/json",
        }

    async def test_rejects_invalid_signature(self, client):
        headers = {
            "twitch-eventsub-message-id": "msg_1",
            "twitch-eventsub-message-timestamp": "2026-02-27T10:00:00Z",
            "twitch-eventsub-message-signature": "sha256=bad",
            "twitch-eventsub-message-type": "notification",
        }
        resp = await client.post("/webhooks/callback", content=b'{}', headers=headers)
        assert resp.status_code == 403

    async def test_challenge_response(self, client):
        body = json.dumps({
            "challenge": "test_challenge_string",
            "subscription": {
                "id": "sub_1",
                "type": "stream.online",
                "version": "1",
                "condition": {"broadcaster_user_id": "123"},
                "status": "webhook_callback_verification_pending",
            },
        }).encode()

        secret = "test_webhook_secret"
        timestamp = "2026-02-27T10:00:00Z"
        sig = _make_signature(secret, "msg_challenge", timestamp, body)
        headers = {
            "twitch-eventsub-message-id": "msg_challenge",
            "twitch-eventsub-message-timestamp": timestamp,
            "twitch-eventsub-message-signature": sig,
            "twitch-eventsub-message-type": "webhook_callback_verification",
            "content-type": "application/json",
        }
        resp = await client.post("/webhooks/callback", content=body, headers=headers)
        assert resp.status_code == 200
        assert resp.text == "test_challenge_string"

    @patch("app.webhooks._handle_stream_online", new_callable=AsyncMock)
    async def test_stream_online_routes_correctly(self, mock_handler, client):
        body = json.dumps({
            "subscription": {
                "id": "sub_1",
                "type": "stream.online",
                "version": "1",
                "condition": {"broadcaster_user_id": "123"},
            },
            "event": {
                "id": "evt_1",
                "broadcaster_user_id": "123",
                "broadcaster_user_login": "northernlion",
                "broadcaster_user_name": "Northernlion",
                "type": "live",
                "started_at": "2026-02-27T10:00:00Z",
            },
        }).encode()

        headers = self._signed_headers(body)
        resp = await client.post("/webhooks/callback", content=body, headers=headers)
        assert resp.status_code == 204
        mock_handler.assert_called_once()

    @patch("app.webhooks._handle_channel_update", new_callable=AsyncMock)
    async def test_channel_update_routes_correctly(self, mock_handler, client):
        body = json.dumps({
            "subscription": {
                "id": "sub_2",
                "type": "channel.update",
                "version": "1",
                "condition": {"broadcaster_user_id": "123"},
            },
            "event": {
                "broadcaster_user_id": "123",
                "broadcaster_user_login": "northernlion",
                "broadcaster_user_name": "Northernlion",
                "title": "Playing Isaac",
                "language": "en",
                "category_id": "456",
                "category_name": "The Binding of Isaac",
                "content_classification_labels": [],
            },
        }).encode()

        headers = self._signed_headers(body, message_id="msg_2")
        resp = await client.post("/webhooks/callback", content=body, headers=headers)
        assert resp.status_code == 204
        mock_handler.assert_called_once()

    @patch("app.webhooks._handle_stream_online", new_callable=AsyncMock)
    async def test_duplicate_message_rejected(self, mock_handler, client):
        body = json.dumps({
            "subscription": {
                "id": "sub_1",
                "type": "stream.online",
                "version": "1",
                "condition": {"broadcaster_user_id": "123"},
            },
            "event": {
                "id": "evt_1",
                "broadcaster_user_id": "123",
                "broadcaster_user_login": "northernlion",
                "broadcaster_user_name": "Northernlion",
                "type": "live",
                "started_at": "2026-02-27T10:00:00Z",
            },
        }).encode()

        headers = self._signed_headers(body, message_id="msg_dup")

        # First call should process
        resp1 = await client.post("/webhooks/callback", content=body, headers=headers)
        assert resp1.status_code == 204
        assert mock_handler.call_count == 1

        # Second call with same message ID should be ignored
        resp2 = await client.post("/webhooks/callback", content=body, headers=headers)
        assert resp2.status_code == 204
        assert mock_handler.call_count == 1  # Still 1, not called again


class TestStreamRestartGracePeriod:
    """Tests for stream restart detection and grace period reactivation."""

    def _make_online_payload(self):
        from app.models import EventSubNotification
        return EventSubNotification(
            subscription={"id": "sub_1", "type": "stream.online", "version": "1",
                          "condition": {"broadcaster_user_id": "123"}},
            event={
                "id": "evt_1",
                "broadcaster_user_id": "123",
                "broadcaster_user_login": "northernlion",
                "broadcaster_user_name": "Northernlion",
                "type": "live",
                "started_at": "2026-02-27T10:00:00Z",
            },
        )

    def _make_offline_payload(self):
        from app.models import EventSubNotification
        return EventSubNotification(
            subscription={"id": "sub_1", "type": "stream.offline", "version": "1",
                          "condition": {"broadcaster_user_id": "123"}},
            event={
                "broadcaster_user_id": "123",
                "broadcaster_user_login": "northernlion",
                "broadcaster_user_name": "Northernlion",
            },
        )

    @patch("app.webhooks.reddit", new_callable=MagicMock)
    @patch("app.webhooks.state")
    async def test_online_reactivates_recently_ended_stream(self, mock_state, mock_reddit):
        """When no active stream exists but a recently-ended one is within grace period,
        it should reactivate the old stream instead of creating a new one."""
        from app.webhooks import _handle_stream_online, _pending_offline_tasks
        from app.models import StreamState

        recent_stream = StreamState(
            id=5, twitch_channel="northernlion", reddit_thread_id="abc123",
            docket=["Isaac", "Slay The Spire"], stream_start="2026-02-27T10:00:00Z",
            is_live=False, ended_at="2026-02-27T11:00:00",
        )

        mock_state.get_active_stream = AsyncMock(return_value=None)
        mock_state.get_recently_ended_stream = AsyncMock(return_value=recent_stream)
        mock_state.reactivate_stream = AsyncMock()
        mock_reddit.build_thread_body = MagicMock(return_value="live body")
        mock_reddit.update_thread = AsyncMock()
        mock_reddit.create_thread = AsyncMock()

        payload = self._make_online_payload()
        await _handle_stream_online(payload)

        mock_state.reactivate_stream.assert_called_once_with(5)
        mock_reddit.update_thread.assert_called_once_with("abc123", "live body")
        mock_reddit.build_thread_body.assert_called_once_with(
            docket=["Isaac", "Slay The Spire"], is_live=True
        )
        mock_reddit.create_thread.assert_not_called()

    @patch("app.webhooks.reddit", new_callable=MagicMock)
    @patch("app.webhooks.state")
    @patch("app.webhooks.twitch")
    async def test_online_creates_new_thread_when_no_recent_stream(
        self, mock_twitch, mock_state, mock_reddit
    ):
        """When no active or recently-ended stream exists, create a new thread."""
        from app.webhooks import _handle_stream_online
        import httpx

        mock_state.get_active_stream = AsyncMock(return_value=None)
        mock_state.get_recently_ended_stream = AsyncMock(return_value=None)
        mock_state.create_stream = AsyncMock()
        mock_twitch.get_stream_info = AsyncMock(return_value={"game_name": "Isaac"})
        mock_reddit.build_thread_title = MagicMock(return_value="Test Title")
        mock_reddit.build_thread_body = MagicMock(return_value="body")
        mock_reddit.create_thread = AsyncMock(return_value="new_thread_id")

        payload = self._make_online_payload()
        await _handle_stream_online(payload)

        mock_reddit.create_thread.assert_called_once()
        mock_state.create_stream.assert_called_once()
        mock_state.reactivate_stream = AsyncMock()
        # reactivate should never have been called
        mock_state.reactivate_stream.assert_not_called()

    @patch("app.webhooks.state")
    async def test_online_cancels_pending_offline_task(self, mock_state):
        """When stream comes back online, pending offline task should be cancelled."""
        from app.webhooks import _handle_stream_online, _pending_offline_tasks
        from app.models import StreamState

        active_stream = StreamState(
            id=5, twitch_channel="northernlion", reddit_thread_id="abc123",
            docket=["Isaac"], stream_start="2026-02-27T10:00:00Z", is_live=True,
        )
        mock_state.get_active_stream = AsyncMock(return_value=active_stream)

        # Create a mock pending task
        mock_task = MagicMock()
        mock_task.done.return_value = False
        _pending_offline_tasks["northernlion"] = mock_task

        payload = self._make_online_payload()
        await _handle_stream_online(payload)

        mock_task.cancel.assert_called_once()
        assert "northernlion" not in _pending_offline_tasks

    @patch("app.webhooks.reddit", new_callable=MagicMock)
    @patch("app.webhooks.state")
    async def test_offline_aborts_if_stream_state_changed(self, mock_state, mock_reddit):
        """After sleeping, offline handler should abort if stream was reactivated."""
        from app.webhooks import _handle_stream_offline
        from app.models import StreamState

        # First call returns the active stream, second call (after sleep) returns None
        mock_state.get_active_stream = AsyncMock(
            side_effect=[
                StreamState(
                    id=5, twitch_channel="northernlion", reddit_thread_id="abc123",
                    docket=["Isaac"], stream_start="2026-02-27T10:00:00Z", is_live=True,
                ),
                None,  # Stream was reactivated/changed during sleep
            ]
        )
        mock_state.mark_offline = AsyncMock()

        payload = self._make_offline_payload()

        with patch("app.webhooks.asyncio.sleep", new_callable=AsyncMock):
            await _handle_stream_offline(payload)

        # mark_offline should NOT have been called since stream state changed
        mock_state.mark_offline.assert_not_called()
        mock_reddit.update_thread = AsyncMock()
        mock_reddit.update_thread.assert_not_called()

    @patch("app.webhooks.state")
    async def test_offline_handles_cancellation_cleanly(self, mock_state):
        """Offline handler should exit cleanly when cancelled during sleep."""
        from app.webhooks import _handle_stream_offline
        from app.models import StreamState

        mock_state.get_active_stream = AsyncMock(return_value=StreamState(
            id=5, twitch_channel="northernlion", reddit_thread_id="abc123",
            docket=["Isaac"], stream_start="2026-02-27T10:00:00Z", is_live=True,
        ))
        mock_state.mark_offline = AsyncMock()

        payload = self._make_offline_payload()

        with patch("app.webhooks.asyncio.sleep", new_callable=AsyncMock,
                    side_effect=asyncio.CancelledError):
            await _handle_stream_offline(payload)

        mock_state.mark_offline.assert_not_called()


class TestGameDetectionRetry:
    """Tests for the retry logic when fetching game info on stream start."""

    def _make_online_payload(self):
        from app.models import EventSubNotification
        return EventSubNotification(
            subscription={"id": "sub_1", "type": "stream.online", "version": "1",
                          "condition": {"broadcaster_user_id": "123"}},
            event={
                "id": "evt_1",
                "broadcaster_user_id": "123",
                "broadcaster_user_login": "northernlion",
                "broadcaster_user_name": "Northernlion",
                "type": "live",
                "started_at": "2026-02-27T10:00:00Z",
            },
        )

    @patch("app.webhooks.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.webhooks.reddit", new_callable=MagicMock)
    @patch("app.webhooks.state")
    @patch("app.webhooks.twitch")
    async def test_retries_when_stream_info_returns_none(
        self, mock_twitch, mock_state, mock_reddit, mock_sleep
    ):
        """Should retry fetching stream info when API returns None initially."""
        from app.webhooks import _handle_stream_online

        mock_state.get_active_stream = AsyncMock(return_value=None)
        mock_state.get_recently_ended_stream = AsyncMock(return_value=None)
        mock_state.create_stream = AsyncMock()
        # First two calls return None (API not ready), third returns game
        mock_twitch.get_stream_info = AsyncMock(
            side_effect=[None, None, {"game_name": "Slay the Spire 2"}]
        )
        mock_reddit.build_thread_title = MagicMock(return_value="Test Title")
        mock_reddit.build_thread_body = MagicMock(return_value="body")
        mock_reddit.create_thread = AsyncMock(return_value="thread_id")

        await _handle_stream_online(self._make_online_payload())

        assert mock_twitch.get_stream_info.call_count == 3
        mock_state.create_stream.assert_called_once()
        call_kwargs = mock_state.create_stream.call_args
        assert call_kwargs.kwargs.get("first_game") == "Slay the Spire 2"

    @patch("app.webhooks.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.webhooks.reddit", new_callable=MagicMock)
    @patch("app.webhooks.state")
    @patch("app.webhooks.twitch")
    async def test_retries_when_game_name_empty(
        self, mock_twitch, mock_state, mock_reddit, mock_sleep
    ):
        """Should retry when stream info exists but game_name is empty string."""
        from app.webhooks import _handle_stream_online

        mock_state.get_active_stream = AsyncMock(return_value=None)
        mock_state.get_recently_ended_stream = AsyncMock(return_value=None)
        mock_state.create_stream = AsyncMock()
        # First call has empty game_name, second has the real game
        mock_twitch.get_stream_info = AsyncMock(
            side_effect=[{"game_name": ""}, {"game_name": "Slay the Spire 2"}]
        )
        mock_reddit.build_thread_title = MagicMock(return_value="Test Title")
        mock_reddit.build_thread_body = MagicMock(return_value="body")
        mock_reddit.create_thread = AsyncMock(return_value="thread_id")

        await _handle_stream_online(self._make_online_payload())

        assert mock_twitch.get_stream_info.call_count == 2
        call_kwargs = mock_state.create_stream.call_args
        assert call_kwargs.kwargs.get("first_game") == "Slay the Spire 2"

    @patch("app.webhooks.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.webhooks.reddit", new_callable=MagicMock)
    @patch("app.webhooks.state")
    @patch("app.webhooks.twitch")
    async def test_creates_thread_with_empty_docket_after_all_retries_fail(
        self, mock_twitch, mock_state, mock_reddit, mock_sleep
    ):
        """If all retries fail, thread should still be created with empty docket."""
        from app.webhooks import _handle_stream_online

        mock_state.get_active_stream = AsyncMock(return_value=None)
        mock_state.get_recently_ended_stream = AsyncMock(return_value=None)
        mock_state.create_stream = AsyncMock()
        mock_twitch.get_stream_info = AsyncMock(return_value=None)
        mock_reddit.build_thread_title = MagicMock(return_value="Test Title")
        mock_reddit.build_thread_body = MagicMock(return_value="body")
        mock_reddit.create_thread = AsyncMock(return_value="thread_id")

        await _handle_stream_online(self._make_online_payload())

        assert mock_twitch.get_stream_info.call_count == 4
        mock_reddit.create_thread.assert_called_once()
        call_kwargs = mock_state.create_stream.call_args
        assert call_kwargs.kwargs.get("first_game") is None

    @patch("app.webhooks.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.webhooks.reddit", new_callable=MagicMock)
    @patch("app.webhooks.state")
    @patch("app.webhooks.twitch")
    async def test_retries_on_api_exception(
        self, mock_twitch, mock_state, mock_reddit, mock_sleep
    ):
        """Should retry when the Twitch API raises an exception."""
        import httpx
        from app.webhooks import _handle_stream_online

        mock_state.get_active_stream = AsyncMock(return_value=None)
        mock_state.get_recently_ended_stream = AsyncMock(return_value=None)
        mock_state.create_stream = AsyncMock()
        mock_twitch.get_stream_info = AsyncMock(
            side_effect=[
                httpx.HTTPStatusError("Server Error", request=MagicMock(), response=MagicMock()),
                {"game_name": "Slay the Spire 2"},
            ]
        )
        mock_reddit.build_thread_title = MagicMock(return_value="Test Title")
        mock_reddit.build_thread_body = MagicMock(return_value="body")
        mock_reddit.create_thread = AsyncMock(return_value="thread_id")

        await _handle_stream_online(self._make_online_payload())

        assert mock_twitch.get_stream_info.call_count == 2
        call_kwargs = mock_state.create_stream.call_args
        assert call_kwargs.kwargs.get("first_game") == "Slay the Spire 2"

    @patch("app.webhooks.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.webhooks.reddit", new_callable=MagicMock)
    @patch("app.webhooks.state")
    @patch("app.webhooks.twitch")
    async def test_no_retry_when_game_found_immediately(
        self, mock_twitch, mock_state, mock_reddit, mock_sleep
    ):
        """Should not retry when game is found on first attempt."""
        from app.webhooks import _handle_stream_online

        mock_state.get_active_stream = AsyncMock(return_value=None)
        mock_state.get_recently_ended_stream = AsyncMock(return_value=None)
        mock_state.create_stream = AsyncMock()
        mock_twitch.get_stream_info = AsyncMock(
            return_value={"game_name": "Slay the Spire 2"}
        )
        mock_reddit.build_thread_title = MagicMock(return_value="Test Title")
        mock_reddit.build_thread_body = MagicMock(return_value="body")
        mock_reddit.create_thread = AsyncMock(return_value="thread_id")

        await _handle_stream_online(self._make_online_payload())

        # Only called once — no retries needed
        assert mock_twitch.get_stream_info.call_count == 1
        mock_sleep.assert_not_called()

    @patch("app.webhooks.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.webhooks.reddit", new_callable=MagicMock)
    @patch("app.webhooks.state")
    @patch("app.webhooks.twitch")
    async def test_retry_uses_exponential_backoff(
        self, mock_twitch, mock_state, mock_reddit, mock_sleep
    ):
        """Should use exponential backoff delays between retries."""
        from app.webhooks import _handle_stream_online

        mock_state.get_active_stream = AsyncMock(return_value=None)
        mock_state.get_recently_ended_stream = AsyncMock(return_value=None)
        mock_state.create_stream = AsyncMock()
        mock_twitch.get_stream_info = AsyncMock(return_value=None)
        mock_reddit.build_thread_title = MagicMock(return_value="Test Title")
        mock_reddit.build_thread_body = MagicMock(return_value="body")
        mock_reddit.create_thread = AsyncMock(return_value="thread_id")

        await _handle_stream_online(self._make_online_payload())

        # Should sleep with exponential backoff: 1s, 2s, 4s
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_calls == [1, 2, 4]

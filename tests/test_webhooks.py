"""Tests for Twitch EventSub webhook handler."""

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

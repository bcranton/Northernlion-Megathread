"""Tests for Reddit client create/update functions."""

import os
from unittest.mock import MagicMock, patch

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

from app import reddit


class TestCreateThread:
    @patch("app.reddit._get_reddit")
    async def test_create_thread(self, mock_get_reddit):
        mock_reddit = MagicMock()
        mock_submission = MagicMock()
        mock_submission.id = "abc123"
        mock_reddit.subreddit.return_value.submit.return_value = mock_submission
        mock_get_reddit.return_value = mock_reddit

        thread_id = await reddit.create_thread("Test Title", "Test Body")
        assert thread_id == "abc123"
        mock_submission.mod.sticky.assert_called_once()
        mock_submission.mod.flair.assert_called_once_with(
            text="[MEGA THREAD]", css_class="mega"
        )

    @patch("app.reddit._get_reddit")
    async def test_update_thread(self, mock_get_reddit):
        mock_reddit = MagicMock()
        mock_submission = MagicMock()
        mock_reddit.submission.return_value = mock_submission
        mock_get_reddit.return_value = mock_reddit

        await reddit.update_thread("abc123", "Updated body")
        mock_reddit.submission.assert_called_once_with(id="abc123")
        mock_submission.edit.assert_called_once_with("Updated body")

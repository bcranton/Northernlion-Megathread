"""Tests for Reddit client create/update functions."""

import os
from unittest.mock import MagicMock, call, patch

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
    @patch("app.reddit._unpin_own_stickies_sync")
    @patch("app.reddit._get_reddit")
    async def test_create_thread(self, mock_get_reddit, mock_unpin):
        mock_reddit = MagicMock()
        mock_submission = MagicMock()
        mock_submission.id = "abc123"
        mock_reddit.subreddit.return_value.submit.return_value = mock_submission
        mock_get_reddit.return_value = mock_reddit

        thread_id = await reddit.create_thread("Test Title", "Test Body")
        assert thread_id == "abc123"
        mock_unpin.assert_called_once()
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


class TestUnpinOwnStickies:
    @patch("app.reddit._get_reddit")
    def test_unpins_bot_stickied_posts(self, mock_get_reddit):
        mock_reddit = MagicMock()
        mock_get_reddit.return_value = mock_reddit
        subreddit = mock_reddit.subreddit.return_value

        # Simulate a stickied post by the bot in slot 1, non-bot in slot 2
        bot_sticky = MagicMock()
        bot_sticky.author.name = "NorthernlionBot"
        other_sticky = MagicMock()
        other_sticky.author.name = "SomeOtherMod"

        subreddit.sticky.side_effect = lambda number: {1: bot_sticky, 2: other_sticky}[number]

        reddit._unpin_own_stickies_sync()

        bot_sticky.mod.sticky.assert_called_once_with(state=False)
        other_sticky.mod.sticky.assert_not_called()

    @patch("app.reddit._get_reddit")
    def test_handles_empty_sticky_slots(self, mock_get_reddit):
        mock_reddit = MagicMock()
        mock_get_reddit.return_value = mock_reddit
        subreddit = mock_reddit.subreddit.return_value

        # Both slots raise (no stickied posts)
        subreddit.sticky.side_effect = Exception("no sticky")

        # Should not raise
        reddit._unpin_own_stickies_sync()

    @patch("app.reddit._get_reddit")
    def test_case_insensitive_username_match(self, mock_get_reddit):
        mock_reddit = MagicMock()
        mock_get_reddit.return_value = mock_reddit
        subreddit = mock_reddit.subreddit.return_value

        bot_sticky = MagicMock()
        bot_sticky.author.name = "northernlionbot"  # lowercase

        subreddit.sticky.side_effect = lambda number: {1: bot_sticky}[number] if number == 1 else (_ for _ in ()).throw(Exception("no sticky"))

        reddit._unpin_own_stickies_sync()

        bot_sticky.mod.sticky.assert_called_once_with(state=False)

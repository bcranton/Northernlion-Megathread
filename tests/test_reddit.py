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

        # After unpinning the bot post, second pass sees only the non-bot post
        call_count = [0]
        def sticky_side_effect(number):
            call_count[0] += 1
            if call_count[0] <= 2:
                # First pass: bot in slot 1, other mod in slot 2
                return {1: bot_sticky, 2: other_sticky}[number]
            else:
                # Second pass: only other mod remains (in slot 1)
                if number == 1:
                    return other_sticky
                raise Exception("no sticky")

        subreddit.sticky.side_effect = sticky_side_effect

        reddit._unpin_own_stickies_sync()

        bot_sticky.mod.sticky.assert_called_once_with(state=False)
        other_sticky.mod.sticky.assert_not_called()

    @patch("app.reddit._get_reddit")
    def test_unpins_both_when_bot_owns_both_slots(self, mock_get_reddit):
        mock_reddit = MagicMock()
        mock_get_reddit.return_value = mock_reddit
        subreddit = mock_reddit.subreddit.return_value

        bot_sticky_1 = MagicMock()
        bot_sticky_1.author.name = "NorthernlionBot"
        bot_sticky_1.id = "post1"
        bot_sticky_2 = MagicMock()
        bot_sticky_2.author.name = "NorthernlionBot"
        bot_sticky_2.id = "post2"

        # First pass: both slots have bot posts. Second pass: none remain.
        call_count = [0]
        def sticky_side_effect(number):
            call_count[0] += 1
            if call_count[0] <= 2:
                return {1: bot_sticky_1, 2: bot_sticky_2}[number]
            else:
                raise Exception("no sticky")

        subreddit.sticky.side_effect = sticky_side_effect

        reddit._unpin_own_stickies_sync()

        bot_sticky_1.mod.sticky.assert_called_once_with(state=False)
        bot_sticky_2.mod.sticky.assert_called_once_with(state=False)

    @patch("app.reddit._get_reddit")
    def test_unpins_backfilled_announcements(self, mock_get_reddit):
        """When unpinning a bot post causes an old bot announcement to backfill
        into a sticky slot, the loop should keep going until all are cleared."""
        mock_reddit = MagicMock()
        mock_get_reddit.return_value = mock_reddit
        subreddit = mock_reddit.subreddit.return_value

        bot_sticky_current = MagicMock()
        bot_sticky_current.author.name = "NorthernlionBot"
        bot_sticky_current.id = "current"
        bot_sticky_old = MagicMock()
        bot_sticky_old.author.name = "NorthernlionBot"
        bot_sticky_old.id = "old_announcement"

        # Pass 1: bot post in slot 1, slot 2 empty.
        # Pass 2: old bot announcement backfills into slot 1.
        # Pass 3: nothing left.
        call_count = [0]
        def sticky_side_effect(number):
            call_count[0] += 1
            if call_count[0] <= 2:
                # First pass
                if number == 1:
                    return bot_sticky_current
                raise Exception("no sticky")
            elif call_count[0] <= 4:
                # Second pass: old announcement backfilled into slot 1
                if number == 1:
                    return bot_sticky_old
                raise Exception("no sticky")
            else:
                raise Exception("no sticky")

        subreddit.sticky.side_effect = sticky_side_effect

        reddit._unpin_own_stickies_sync()

        bot_sticky_current.mod.sticky.assert_called_once_with(state=False)
        bot_sticky_old.mod.sticky.assert_called_once_with(state=False)

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

        call_count = [0]
        def sticky_side_effect(number):
            call_count[0] += 1
            if call_count[0] <= 2:
                if number == 1:
                    return bot_sticky
                raise Exception("no sticky")
            raise Exception("no sticky")

        subreddit.sticky.side_effect = sticky_side_effect

        reddit._unpin_own_stickies_sync()

        bot_sticky.mod.sticky.assert_called_once_with(state=False)

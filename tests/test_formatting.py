"""Tests for Reddit thread body and title construction."""

import os
from unittest.mock import patch

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

from app.reddit import build_thread_body, build_thread_title


class TestBuildThreadTitle:
    @patch("app.reddit.date")
    @patch("app.reddit.datetime")
    def test_title_format(self, mock_datetime, mock_date):
        mock_date.today.return_value.strftime.return_value = "February 27, 2026"
        mock_datetime.now.return_value.strftime.return_value = "Friday"
        title = build_thread_title()
        assert title == "Stream Discussion Thread -- Friday, February 27, 2026"


class TestBuildThreadBody:
    def test_live_body_with_games(self):
        body = build_thread_body(docket=["Isaac", "Slay The Spire"], is_live=True)
        assert "LIVE" in body
        assert "* Isaac" in body
        assert "* Slay The Spire" in body
        assert "VOD will be added after the stream ends" in body

    def test_live_body_no_games(self):
        body = build_thread_body(docket=[], is_live=True)
        assert "No games detected yet" in body

    def test_finalized_body_with_clip_and_vod(self):
        clip = {"title": "Great Clip", "url": "https://clips.twitch.tv/test", "creator_name": "clipper42"}
        body = build_thread_body(
            docket=["Isaac"],
            vod_url="https://www.twitch.tv/videos/123",
            clip=clip,
            is_live=False,
        )
        assert "Post Stream Discussion Thread" in body
        assert "LIVE" not in body
        assert "Great Clip" in body
        assert "clipper42" in body
        assert "Twitch VOD" in body
        assert "https://www.twitch.tv/videos/123" in body

    def test_finalized_body_no_clip(self):
        body = build_thread_body(
            docket=["Isaac"],
            vod_url="https://www.twitch.tv/videos/123",
            clip=None,
            is_live=False,
        )
        assert "Top Clip" not in body
        assert "Twitch VOD" in body

    def test_finalized_body_no_vod(self):
        body = build_thread_body(docket=["Isaac"], vod_url=None, is_live=False)
        assert "Twitch VOD" not in body

    def test_previous_threads_link_always_present(self):
        body = build_thread_body(docket=[], is_live=True)
        assert "Previous Mega Threads" in body

    def test_footer_always_present(self):
        body = build_thread_body(docket=[], is_live=True)
        assert "AManNamedLear" in body
        assert "GitHub" in body

    def test_sections_separated_by_blank_lines(self):
        body = build_thread_body(docket=["Isaac"], is_live=True)
        # Each section should be separated by double newlines (paragraph breaks)
        assert "\n\n---\n\n" in body

    def test_docket_items_on_separate_lines(self):
        body = build_thread_body(docket=["Isaac", "Slay The Spire"], is_live=True)
        assert "* Isaac\n* Slay The Spire" in body

    def test_clip_creator_link_format(self):
        clip = {"title": "Great Play", "url": "https://clips.twitch.tv/x", "creator_name": "user1"}
        body = build_thread_body(docket=["Isaac"], clip=clip, is_live=False)
        # Superscript syntax should use ^() grouping (new Reddit compatible)
        assert "^(Clipped by Twitch user)" in body
        assert "[^(user1)]" in body

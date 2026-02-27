import asyncio
import logging
from datetime import date, datetime

import praw

from app.config import get_settings

logger = logging.getLogger(__name__)

_reddit: praw.Reddit | None = None


def _get_reddit() -> praw.Reddit:
    """Get or create a praw Reddit instance."""
    global _reddit
    if _reddit is None:
        settings = get_settings()
        _reddit = praw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            password=settings.reddit_password,
            user_agent=f"NorthernlionMegathreadBot/2.0 by /u/{settings.reddit_username}",
            username=settings.reddit_username,
        )
        logger.info("Authenticated with Reddit as %s", _reddit.user.me())
    return _reddit


def build_thread_title() -> str:
    """Build the thread title with today's date."""
    today_date = date.today().strftime("%B %d, %Y")
    day_name = datetime.now().strftime("%A")
    return f"Stream Discussion Thread -- {day_name}, {today_date}"


def build_thread_body(
    docket: list[str],
    vod_url: str | None = None,
    clip: dict | None = None,
    is_live: bool = True,
) -> str:
    """Build the Reddit thread body markdown.

    Args:
        docket: List of games played during the stream.
        vod_url: URL to the Twitch VOD (available after stream ends).
        clip: Dict with 'url', 'title', 'creator_name' keys (available after stream ends).
        is_live: Whether the stream is currently live.
    """
    parts = []

    # Header
    if is_live:
        parts.append("# Stream Discussion Thread\n")
        parts.append("**The stream is currently LIVE!**\n")
    else:
        parts.append("# Post Stream Discussion Thread\n")

    parts.append("---------------------------------------------\n")

    # Docket
    parts.append("### Docket\n")
    if docket:
        for game in docket:
            parts.append(f"* {game}")
    else:
        parts.append("*No games detected yet*")
    parts.append("")

    # Clip (only after stream ends)
    if clip:
        parts.append("*Today's Top Clip:*\n")
        parts.append(f"**[{clip['title']}]({clip['url']})**\n")
        creator = clip["creator_name"]
        parts.append(
            f"^^^Clipped ^^^by ^^^Twitch ^^^user "
            f"^^^[{creator}](https://twitch.tv/{creator})\n"
        )

    # VOD
    parts.append("----------------------------------------------\n")
    if vod_url:
        parts.append(f"### [Twitch VOD]({vod_url})\n")
    elif is_live:
        parts.append("*VOD will be added after the stream ends.*\n")

    # Previous threads
    parts.append(
        "### [Previous Mega Threads]"
        "(https://www.reddit.com/r/northernlion/search?q=flair%3AMEGA+THREAD&sort=new&restrict_sr=on&t=a)"
    )

    # Footer
    parts.append("\n----------------------------------------------\n")
    parts.append(
        "^(^^Bot ^^created ^^by ) "
        "^^^[/u/AManNamedLear](https://www.reddit.com/u/AManNamedLear) "
        "^(^^| ^^Find ^^me ^^on) "
        "^^^[GitHub](https://github.com/bcranton/Northernlion-Megathread)"
    )

    return "\n".join(parts)


def _create_thread_sync(title: str, body: str) -> str:
    """Create a Reddit thread (synchronous). Returns the submission ID."""
    settings = get_settings()
    reddit = _get_reddit()
    subreddit = reddit.subreddit(settings.subreddit)

    submission = subreddit.submit(title, selftext=body)
    submission.mod.sticky()
    submission.mod.flair(text="[MEGA THREAD]", css_class="mega")
    logger.info("Created Reddit thread: %s (id=%s)", title, submission.id)
    return submission.id


def _update_thread_sync(submission_id: str, body: str) -> None:
    """Edit an existing Reddit thread body (synchronous)."""
    reddit = _get_reddit()
    submission = reddit.submission(id=submission_id)
    submission.edit(body)
    logger.info("Updated Reddit thread id=%s", submission_id)


async def create_thread(title: str, body: str) -> str:
    """Create a Reddit thread. Returns the submission ID."""
    return await asyncio.to_thread(_create_thread_sync, title, body)


async def update_thread(submission_id: str, body: str) -> None:
    """Edit an existing Reddit thread body."""
    await asyncio.to_thread(_update_thread_sync, submission_id, body)

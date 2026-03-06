import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

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


_TIMEZONE = ZoneInfo("America/Vancouver")


def build_thread_title() -> str:
    """Build the thread title with today's date in Vancouver time."""
    now = datetime.now(_TIMEZONE)
    day_name = now.strftime("%A")
    today_date = now.strftime("%B %d, %Y")
    return f"Stream Discussion Thread -- {day_name}, {today_date}"


def build_thread_body(
    docket: list[str],
    vod_url: str | None = None,
    clip: dict | None = None,
    is_live: bool = True,
) -> str:
    """Build the Reddit thread body markdown.

    Uses blank lines between sections for consistent paragraph breaks.
    Single newlines within a section keep content together.
    """
    sections = []

    # Header
    if is_live:
        sections.append("# Stream Discussion Thread")
        sections.append("**The stream is currently LIVE!**")
    else:
        sections.append("# Post Stream Discussion Thread")

    sections.append("---")

    # Docket
    docket_lines = ["### Docket", ""]
    if docket:
        for game in docket:
            docket_lines.append(f"* {game}")
    else:
        docket_lines.append("*No games detected yet*")
    sections.append("\n".join(docket_lines))

    # Clip (only after stream ends)
    if clip:
        creator = clip["creator_name"]
        clip_lines = [
            "*Today's Top Clip:*",
            "",
            f"**[{clip['title']}]({clip['url']})**",
            "",
            f"^(Clipped by Twitch user) [^({creator})](https://twitch.tv/{creator})",
        ]
        sections.append("\n".join(clip_lines))

    sections.append("---")

    # VOD
    if vod_url:
        sections.append(f"### [Twitch VOD]({vod_url})")
    elif is_live:
        sections.append("*VOD will be added after the stream ends.*")

    # Previous threads
    sections.append(
        "### [Previous Mega Threads]"
        "(https://www.reddit.com/r/northernlion/search?q=flair%3AMEGA+THREAD&sort=new&restrict_sr=on&t=a)"
    )

    # Footer
    sections.append("---")
    sections.append(
        "^(Bot created by) [^(/u/AManNamedLear)](https://www.reddit.com/u/AManNamedLear) "
        "^(|) "
        "[^(GitHub)](https://github.com/bcranton/Northernlion-Megathread)"
    )

    return "\n\n".join(sections)


def _unpin_own_stickies_sync() -> None:
    """Unpin any stickied posts in the subreddit made by the bot account.

    Community Highlights (new Reddit) can backfill into the two legacy sticky
    slots when one is removed, so we loop until a full pass finds no bot-owned
    stickies.
    """
    settings = get_settings()
    reddit = _get_reddit()
    subreddit = reddit.subreddit(settings.subreddit)
    bot_name = settings.reddit_username.lower()

    # Reddit allows at most 2 stickied posts (slots 1 and 2).
    # Repeat until a full pass finds nothing to unpin — Community Highlights
    # (new Reddit, up to 6 posts) can backfill into these legacy slots.
    unpinned = True
    while unpinned:
        unpinned = False
        for slot in (1, 2):
            try:
                stickied = subreddit.sticky(number=slot)
            except Exception:
                # No sticky in this slot
                continue
            if stickied.author and stickied.author.name.lower() == bot_name:
                stickied.mod.sticky(state=False)
                logger.info("Unpinned previous thread id=%s from slot %d", stickied.id, slot)
                unpinned = True


def _create_thread_sync(title: str, body: str) -> str:
    """Create a Reddit thread (synchronous). Returns the submission ID."""
    settings = get_settings()
    reddit = _get_reddit()
    subreddit = reddit.subreddit(settings.subreddit)

    _unpin_own_stickies_sync()

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

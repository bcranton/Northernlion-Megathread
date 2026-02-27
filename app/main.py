import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app import state, twitch
from app.config import get_settings
from app.webhooks import router as webhook_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

EVENTSUB_TYPES = ["stream.online", "stream.offline", "channel.update"]

_startup_error: str | None = None


async def _setup_eventsub_subscriptions(client: httpx.AsyncClient) -> None:
    """Subscribe to required EventSub webhook events, cleaning up stale subscriptions first."""
    settings = get_settings()
    callback_url = f"{settings.base_url}/webhooks/callback"
    broadcaster_id = await twitch.get_user_id(client, settings.twitch_channel)

    # List existing subscriptions and clean up stale/failed ones
    existing = await twitch.get_eventsub_subscriptions(client)
    active_types = set()
    for sub in existing:
        if sub["status"] != "enabled" or sub["transport"]["callback"] != callback_url:
            await twitch.delete_eventsub_subscription(client, sub["id"])
            logger.info("Cleaned up stale subscription %s (%s)", sub["id"], sub["type"])
        else:
            active_types.add(sub["type"])

    # Subscribe to any missing event types
    for event_type in EVENTSUB_TYPES:
        if event_type in active_types:
            logger.info("EventSub %s already active, skipping", event_type)
            continue
        await twitch.subscribe_eventsub(
            client, event_type, broadcaster_id, callback_url, settings.twitch_webhook_secret
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    global _startup_error
    settings = get_settings()

    # Startup — database init is required, but external API calls must not
    # prevent the server from binding to PORT (Railway health checks need it).
    await state.init_db()
    logger.info("Monitoring channel: %s → r/%s", settings.twitch_channel, settings.subreddit)

    try:
        async with httpx.AsyncClient() as client:
            await twitch.get_app_access_token(client)
            await _setup_eventsub_subscriptions(client)
    except Exception as exc:
        _startup_error = f"{type(exc).__name__}: {exc}"
        logger.error("Twitch setup failed during startup (server will still run): %s", exc)

    # Check for active stream from a previous run (crash recovery)
    try:
        active = await state.get_active_stream(settings.twitch_channel)
        if active:
            logger.info(
                "Recovered active stream (id=%d, thread=%s, docket=%s)",
                active.id, active.reddit_thread_id, active.docket,
            )
    except Exception as exc:
        logger.error("Failed to check for active stream: %s", exc)

    yield

    # Shutdown
    await state.close_db()
    logger.info("Shutdown complete")


app = FastAPI(title="Northernlion Megathread Bot", version="2.0.0", lifespan=lifespan)
app.include_router(webhook_router)


@app.get("/health")
async def health():
    if _startup_error:
        return {"status": "degraded", "error": _startup_error}
    return {"status": "ok"}

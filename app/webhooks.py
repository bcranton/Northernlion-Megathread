import asyncio
import hashlib
import hmac
import logging
import time

import httpx
from fastapi import APIRouter, Request, Response

from app import reddit, state, twitch
from app.config import get_settings
from app.models import ChannelUpdateEvent, EventSubNotification, StreamOnlineEvent

logger = logging.getLogger(__name__)

router = APIRouter()

# Track processed message IDs to reject duplicates (EventSub may redeliver)
_processed_message_ids: dict[str, float] = {}
_MESSAGE_ID_TTL_SECONDS = 600  # Keep IDs for 10 minutes


def _verify_signature(secret: str, headers: dict[str, str], body: bytes) -> bool:
    """Verify the HMAC-SHA256 signature of an EventSub webhook message."""
    message_id = headers.get("twitch-eventsub-message-id", "")
    timestamp = headers.get("twitch-eventsub-message-timestamp", "")
    expected_sig = headers.get("twitch-eventsub-message-signature", "")

    hmac_message = message_id.encode() + timestamp.encode() + body
    digest = hmac.new(secret.encode(), hmac_message, hashlib.sha256).hexdigest()
    computed_sig = f"sha256={digest}"

    return hmac.compare_digest(computed_sig, expected_sig)


def _cleanup_old_message_ids() -> None:
    """Remove expired message IDs from the duplicate tracker."""
    now = time.time()
    expired = [mid for mid, ts in _processed_message_ids.items() if now - ts > _MESSAGE_ID_TTL_SECONDS]
    for mid in expired:
        del _processed_message_ids[mid]


@router.post("/webhooks/callback")
async def eventsub_callback(request: Request) -> Response:
    """Handle incoming Twitch EventSub webhook notifications."""
    settings = get_settings()
    body = await request.body()
    headers = dict(request.headers)

    # Verify HMAC signature
    if not _verify_signature(settings.twitch_webhook_secret, headers, body):
        logger.warning("Invalid webhook signature rejected")
        return Response(status_code=403)

    message_type = headers.get("twitch-eventsub-message-type", "")

    # Handle subscription verification challenge
    if message_type == "webhook_callback_verification":
        payload = await request.json()
        challenge = payload.get("challenge", "")
        logger.info("Responding to EventSub verification challenge")
        return Response(content=challenge, media_type="text/plain")

    # Handle revocation
    if message_type == "revocation":
        payload = await request.json()
        sub_type = payload.get("subscription", {}).get("type", "unknown")
        logger.warning("EventSub subscription revoked: %s", sub_type)
        return Response(status_code=204)

    # Reject duplicate messages
    message_id = headers.get("twitch-eventsub-message-id", "")
    _cleanup_old_message_ids()
    if message_id in _processed_message_ids:
        logger.debug("Ignoring duplicate message %s", message_id)
        return Response(status_code=204)
    _processed_message_ids[message_id] = time.time()

    # Parse and route the notification
    payload = EventSubNotification(**(await request.json()))
    sub_type = payload.subscription.type

    logger.info("Received EventSub notification: %s", sub_type)

    if sub_type == "stream.online":
        await _handle_stream_online(payload)
    elif sub_type == "channel.update":
        await _handle_channel_update(payload)
    elif sub_type == "stream.offline":
        # Run finalization in background so we can respond to Twitch quickly
        asyncio.create_task(_handle_stream_offline(payload))
    else:
        logger.warning("Unhandled EventSub type: %s", sub_type)

    return Response(status_code=204)


async def _handle_stream_online(payload: EventSubNotification) -> None:
    """Stream went live: create a Reddit thread and persist state."""
    settings = get_settings()
    event = StreamOnlineEvent(**payload.event)
    channel = event.broadcaster_user_login

    logger.info("Stream online: %s (started at %s)", channel, event.started_at)

    # Check if we already have an active stream (crash recovery / duplicate event)
    existing = await state.get_active_stream(channel)
    if existing:
        logger.info("Active stream already exists for %s (id=%d), skipping", channel, existing.id)
        return

    # Get the current game being played
    first_game = None
    async with httpx.AsyncClient() as client:
        stream_info = await twitch.get_stream_info(client, event.broadcaster_user_id)
        if stream_info:
            first_game = stream_info.get("game_name")

    # Create the Reddit thread
    title = reddit.build_thread_title()
    docket = [first_game] if first_game else []
    body = reddit.build_thread_body(docket=docket, is_live=True)
    thread_id = await reddit.create_thread(title, body)

    # Save state
    await state.create_stream(
        channel=channel,
        thread_id=thread_id,
        first_game=first_game,
        start_time=event.started_at,
    )


async def _handle_channel_update(payload: EventSubNotification) -> None:
    """Game or title changed: update the docket and edit the Reddit thread."""
    settings = get_settings()
    event = ChannelUpdateEvent(**payload.event)
    channel = event.broadcaster_user_login

    active_stream = await state.get_active_stream(channel)
    if not active_stream:
        logger.debug("No active stream for %s, ignoring channel.update", channel)
        return

    new_game = event.category_name
    if not new_game:
        return

    # Only add the game if it differs from the last entry
    if active_stream.docket and active_stream.docket[-1] == new_game:
        return

    updated_docket = active_stream.docket + [new_game]
    await state.update_docket(active_stream.id, updated_docket)

    # Rebuild and edit the Reddit thread
    body = reddit.build_thread_body(docket=updated_docket, is_live=True)
    await reddit.update_thread(active_stream.reddit_thread_id, body)
    logger.info("Updated docket for %s: %s", channel, updated_docket)


async def _handle_stream_offline(payload: EventSubNotification) -> None:
    """Stream ended: wait for clips/VOD to propagate, then finalize the thread."""
    settings = get_settings()
    channel = payload.event.get("broadcaster_user_login", "")

    active_stream = await state.get_active_stream(channel)
    if not active_stream:
        logger.warning("No active stream for %s on offline event", channel)
        return

    logger.info("Stream offline: %s — waiting 2 minutes for clips/VOD", channel)
    await asyncio.sleep(120)

    # Fetch clip and VOD
    clip = None
    vod_url = None
    async with httpx.AsyncClient() as client:
        broadcaster_id = payload.event.get("broadcaster_user_id", "")

        clip_data = await twitch.get_top_clip(
            client, broadcaster_id, active_stream.stream_start
        )
        if clip_data:
            clip = {
                "title": clip_data["title"],
                "url": clip_data["url"],
                "creator_name": clip_data["creator_name"],
            }

        vod_data = await twitch.get_latest_vod(client, broadcaster_id)
        if vod_data:
            vod_url = vod_data["url"]

    # Final thread edit
    body = reddit.build_thread_body(
        docket=active_stream.docket,
        vod_url=vod_url,
        clip=clip,
        is_live=False,
    )
    await reddit.update_thread(active_stream.reddit_thread_id, body)

    # Mark stream as done
    await state.mark_offline(active_stream.id)
    logger.info("Finalized thread for %s", channel)

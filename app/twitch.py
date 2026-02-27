import logging
import time

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_API_URL = "https://api.twitch.tv/helix"

_access_token: str | None = None
_token_expires_at: float = 0


async def get_app_access_token(client: httpx.AsyncClient) -> str:
    """Fetch or return cached Twitch app access token (Client Credentials flow)."""
    global _access_token, _token_expires_at

    if _access_token and time.time() < _token_expires_at:
        return _access_token

    settings = get_settings()
    resp = await client.post(
        TWITCH_AUTH_URL,
        params={
            "client_id": settings.twitch_client_id,
            "client_secret": settings.twitch_client_secret,
            "grant_type": "client_credentials",
        },
    )
    resp.raise_for_status()
    data = resp.json()

    _access_token = data["access_token"]
    # Refresh 60 seconds before actual expiry
    _token_expires_at = time.time() + data["expires_in"] - 60
    logger.info("Obtained Twitch app access token (expires in %ds)", data["expires_in"])
    return _access_token


def _invalidate_token() -> None:
    """Invalidate the cached token so the next API call fetches a fresh one."""
    global _access_token, _token_expires_at
    _access_token = None
    _token_expires_at = 0
    logger.info("Invalidated cached Twitch access token")


async def _headers(client: httpx.AsyncClient) -> dict[str, str]:
    """Build auth headers for Twitch Helix API calls."""
    settings = get_settings()
    token = await get_app_access_token(client)
    return {
        "Authorization": f"Bearer {token}",
        "Client-Id": settings.twitch_client_id,
    }


async def _request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs,
) -> httpx.Response:
    """Make an authenticated Twitch API request with automatic token refresh on 401.

    If the request returns 401 Unauthorized, the cached token is invalidated and
    the request is retried once with a fresh token.
    """
    headers = await _headers(client)
    resp = await client.request(method, url, headers=headers, **kwargs)

    if resp.status_code == 401:
        logger.warning("Got 401 from Twitch API, refreshing access token and retrying")
        _invalidate_token()
        headers = await _headers(client)
        resp = await client.request(method, url, headers=headers, **kwargs)

    resp.raise_for_status()
    return resp


async def get_user_id(client: httpx.AsyncClient, channel_name: str) -> str:
    """Resolve a Twitch channel name to a broadcaster user ID."""
    resp = await _request(client, "GET", f"{TWITCH_API_URL}/users", params={"login": channel_name})
    data = resp.json()["data"]
    if not data:
        raise ValueError(f"Twitch user '{channel_name}' not found")
    return data[0]["id"]


async def get_stream_info(client: httpx.AsyncClient, user_id: str) -> dict | None:
    """Get current stream info. Returns None if offline."""
    resp = await _request(client, "GET", f"{TWITCH_API_URL}/streams", params={"user_id": user_id})
    data = resp.json()["data"]
    return data[0] if data else None


async def subscribe_eventsub(
    client: httpx.AsyncClient,
    event_type: str,
    broadcaster_id: str,
    callback_url: str,
    secret: str,
) -> dict:
    """Create an EventSub webhook subscription."""
    body = {
        "type": event_type,
        "version": "1",
        "condition": {"broadcaster_user_id": broadcaster_id},
        "transport": {
            "method": "webhook",
            "callback": callback_url,
            "secret": secret,
        },
    }
    resp = await _request(
        client, "POST", f"{TWITCH_API_URL}/eventsub/subscriptions", json=body
    )
    result = resp.json()["data"][0]
    logger.info("Subscribed to EventSub %s (id=%s)", event_type, result["id"])
    return result


async def get_eventsub_subscriptions(client: httpx.AsyncClient) -> list[dict]:
    """List all active EventSub subscriptions for this app."""
    resp = await _request(client, "GET", f"{TWITCH_API_URL}/eventsub/subscriptions")
    return resp.json()["data"]


async def delete_eventsub_subscription(client: httpx.AsyncClient, sub_id: str) -> None:
    """Delete an EventSub subscription by ID."""
    await _request(
        client, "DELETE", f"{TWITCH_API_URL}/eventsub/subscriptions", params={"id": sub_id}
    )
    logger.info("Deleted EventSub subscription %s", sub_id)


async def get_top_clip(
    client: httpx.AsyncClient, broadcaster_id: str, started_at: str
) -> dict | None:
    """Get the top clip for a broadcaster since a given time."""
    resp = await _request(
        client,
        "GET",
        f"{TWITCH_API_URL}/clips",
        params={"broadcaster_id": broadcaster_id, "started_at": started_at, "first": 1},
    )
    data = resp.json()["data"]
    if not data:
        logger.warning("No clips found for broadcaster %s since %s", broadcaster_id, started_at)
        return None
    return data[0]


async def get_latest_vod(client: httpx.AsyncClient, user_id: str) -> dict | None:
    """Get the most recent VOD for a user."""
    resp = await _request(
        client,
        "GET",
        f"{TWITCH_API_URL}/videos",
        params={"user_id": user_id, "type": "archive", "first": 1},
    )
    data = resp.json()["data"]
    if not data:
        logger.warning("No VODs found for user %s", user_id)
        return None
    return data[0]

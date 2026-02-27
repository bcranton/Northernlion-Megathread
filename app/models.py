from pydantic import BaseModel


# --- Twitch EventSub payload models ---


class EventSubSubscription(BaseModel):
    id: str
    type: str
    version: str
    status: str | None = None
    condition: dict


class StreamOnlineEvent(BaseModel):
    id: str
    broadcaster_user_id: str
    broadcaster_user_login: str
    broadcaster_user_name: str
    type: str
    started_at: str


class StreamOfflineEvent(BaseModel):
    broadcaster_user_id: str
    broadcaster_user_login: str
    broadcaster_user_name: str


class ChannelUpdateEvent(BaseModel):
    broadcaster_user_id: str
    broadcaster_user_login: str
    broadcaster_user_name: str
    title: str
    language: str
    category_id: str
    category_name: str
    content_classification_labels: list[dict] = []


class EventSubNotification(BaseModel):
    subscription: EventSubSubscription
    event: dict | None = None
    challenge: str | None = None


# --- Internal state model ---


class StreamState(BaseModel):
    id: int
    twitch_channel: str
    reddit_thread_id: str | None = None
    docket: list[str] = []
    stream_start: str | None = None
    is_live: bool = True
    ended_at: str | None = None

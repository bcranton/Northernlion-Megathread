from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Twitch
    twitch_client_id: str
    twitch_client_secret: str
    twitch_channel: str = "Northernlion"
    twitch_webhook_secret: str

    # Reddit
    reddit_client_id: str
    reddit_client_secret: str
    reddit_username: str = "NorthernlionBot"
    reddit_password: str
    subreddit: str = "NLSSBotTest"

    # App
    base_url: str
    database_path: str = "data/bot.db"
    restart_grace_period_seconds: int = 1800  # 30 minutes

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()

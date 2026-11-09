from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mode: str = "demo"
    database_url: str = "postgresql://obs:obs_local@127.0.0.1:55432/obs"
    jwt_secret: str = "local-demo-only-change-before-live-use-32-characters"
    demo_password: str = "demo"
    cookie_secure: bool = True
    poll_interval_sec: int = 120
    platform_check_sec: int = 60
    warehouse_check_sec: int = 900
    demo_tick_sec: float = 60
    demo_retry_sec: float = 30
    demo_onboard_step_sec: float = 10
    alert_interval_sec: float = 60
    console_url: str = "http://localhost:8080"


@lru_cache
def settings() -> Settings:
    return Settings()


def require_demo() -> None:
    if settings().mode != "demo":
        raise RuntimeError(
            "Live collection and actions are reserved for M5/M6. No systems contacted."
        )

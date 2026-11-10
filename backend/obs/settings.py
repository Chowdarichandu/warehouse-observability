from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEMO_KEY = "local-demo-only-change-before-live-use-32-characters"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mode: Literal["demo", "live"] = "demo"
    database_url: str = "postgresql://obs:obs_local@127.0.0.1:55432/obs"
    jwt_secret: str = DEMO_KEY
    demo_password: str = "demo"
    cookie_secure: bool = True
    poll_interval_sec: int = Field(default=120, ge=10)
    platform_check_sec: int = Field(default=60, ge=10)
    warehouse_check_sec: int = Field(default=900, ge=60)
    demo_tick_sec: float = 60
    demo_retry_sec: float = 30
    demo_onboard_step_sec: float = 10
    alert_interval_sec: float = Field(default=60, ge=1)
    console_url: str = "http://localhost:8080"
    environment_name: str = "Production"
    live_actions_enabled: bool = False
    http_timeout_sec: int = Field(default=20, ge=1, le=120)
    max_pages: int = Field(default=100, ge=1, le=1000)
    aws_region: str = "us-east-1"
    aws_secret_prefix: str = "observability/"
    airflow_transport: Literal["http", "mwaa"] = "http"
    airflow_api_version: Literal["v1", "v2"] = "v1"
    airflow_url: str = ""
    airflow_read_token: str = ""
    airflow_write_token: str = ""
    mwaa_environment: str = ""
    mwaa_write_role_arn: str = ""
    airflow_dags: dict[str, str] = {
        "mysql_initial": "mysql_initial_load",
        "mysql_cdc": "mysql_cdc",
        "mongo_initial": "mongo_initial_load",
        "mongo_cdc": "mongo_cdc",
    }
    sync_task_regex: str = r"(^|\.)sync(_.*)?$"
    tenant_task_regex: str = r"^sync_(?P<tenant>[a-z0-9_]+)$"
    onboarding_dag_id: str = "onboard_tenant"
    registry_dags_enabled: bool = False
    airbyte_url: str = ""
    airbyte_token: str = ""
    airbyte_write_token: str = ""
    airbyte_client_id: str = ""
    airbyte_client_secret: str = ""
    airbyte_config_url: str = ""
    airbyte_workspace_id: str = ""
    airbyte_destination_id: str = ""
    warehouse_engine: Literal["postgres", "redshift"] = "postgres"
    warehouse_url: str = ""
    warehouse_load_column: str = "_airbyte_extracted_at"
    warehouse_statement_timeout_ms: int = Field(default=10000, ge=1000, le=60000)
    quality_enabled: bool = False
    quality_interval_sec: int = Field(default=60, ge=60, le=3600)
    source_allowed_cidrs: list[str] = []
    mysql_binlog_retention_sec: int = Field(default=259200, ge=86400)
    source_ca_file: str = ""
    auth_provider: Literal["local", "oidc"] = "local"
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_groups_claim: str = "groups"
    oidc_group_roles: dict[str, Literal["viewer", "operator", "admin"]] = {}
    session_hours: int = Field(default=8, ge=1, le=24)
    notification_max_attempts: int = Field(default=5, ge=1, le=10)
    notification_allowed_hosts: list[str] = ["hooks.slack.com", "outlook.office.com"]
    ses_from_address: str = ""
    ses_to_addresses: list[str] = []
    sns_topic_arn: str = ""
    retention_enabled: bool = True
    backup_s3_bucket: str = ""
    backup_kms_key_id: str = ""

    @model_validator(mode="after")
    def production_constraints(self) -> "Settings":
        if self.mode == "live":
            if self.jwt_secret == DEMO_KEY or len(self.jwt_secret) < 32:
                raise ValueError("Live mode requires a unique JWT_SECRET of at least 32 characters")
            if not self.cookie_secure or urlsplit(self.console_url).scheme != "https":
                raise ValueError("Live mode requires HTTPS CONSOLE_URL and Secure cookies")
            if "sslmode=verify-full" not in self.database_url:
                raise ValueError("Live DATABASE_URL must use sslmode=verify-full and a trusted CA")
            if self.auth_provider != "oidc" or not self.oidc_group_roles:
                raise ValueError("Live mode requires OIDC and explicit OIDC_GROUP_ROLES")
            if not self.oidc_client_id or urlsplit(self.oidc_issuer).scheme != "https":
                raise ValueError("OIDC requires an HTTPS issuer and client ID")
            for url in (self.airflow_url, self.airbyte_url, self.airbyte_config_url):
                if url and urlsplit(url).scheme != "https":
                    raise ValueError("Live upstream HTTP APIs require HTTPS")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()


def require_demo() -> None:
    if settings().mode != "demo":
        raise RuntimeError("This operation is available only in demo mode")


def require_live() -> None:
    if settings().mode != "live":
        raise RuntimeError("External integration is disabled in offline demo mode")

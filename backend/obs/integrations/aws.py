import json
import os
from functools import lru_cache
from typing import Any

from obs.settings import require_live, settings


def client(service: str, *, write: bool = False) -> Any:
    require_live()
    import boto3
    from botocore.config import Config

    # Never replay a mutating request following an ambiguous network response.
    config = Config(
        connect_timeout=5,
        read_timeout=settings().http_timeout_sec,
        retries={"mode": "standard", "total_max_attempts": 1 if write else 3},
    )
    kwargs: dict = {"region_name": settings().aws_region, "config": config}
    if service == "mwaa" and write and settings().mwaa_write_role_arn:
        assumed = boto3.client("sts", **kwargs).assume_role(
            RoleArn=settings().mwaa_write_role_arn, RoleSessionName="obs-operator"
        )["Credentials"]
        kwargs.update(
            aws_access_key_id=assumed["AccessKeyId"],
            aws_secret_access_key=assumed["SecretAccessKey"],
            aws_session_token=assumed["SessionToken"],
        )
    return boto3.client(service, **kwargs)


def secret(reference: str) -> dict:
    """Resolve only the configured onboarding namespace; never return to the browser."""
    require_live()
    if not reference.startswith("aws://"):
        raise ValueError("Live onboarding requires an aws:// Secrets Manager reference")
    name = reference.removeprefix("aws://")
    if not name.startswith(settings().aws_secret_prefix) or ".." in name:
        raise ValueError("Secret reference is outside the configured namespace")
    response = client("secretsmanager").get_secret_value(SecretId=name)
    value = json.loads(response["SecretString"])
    if not isinstance(value, dict):
        raise ValueError("Secret must be a JSON object")
    return value


@lru_cache
def environment_secret(name: str) -> str:
    require_live()
    if not name.isidentifier() or not name.isupper():
        raise ValueError("Channel target must be an environment variable name")
    value = os.environ.get(name, "")
    if not value:
        raise ValueError(f"Required notification configuration {name} is missing")
    return value

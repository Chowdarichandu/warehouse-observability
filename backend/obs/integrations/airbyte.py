import re
import time
from datetime import UTC, datetime

from obs.integrations import http
from obs.settings import require_live, settings


def duration_seconds(value: str | int | float | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return max(0, int(value))
    match = re.fullmatch(
        r"P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?",
        value,
    )
    if not match:
        raise ValueError("Invalid ISO-8601 Airbyte duration")
    return int(
        sum(float(n or 0) * m for n, m in zip(match.groups(), (86400, 3600, 60, 1), strict=True))
    )


def timestamp(value: str | int | float | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value / 1000 if value > 100000000000 else value, UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class Airbyte:
    def __init__(self, *, write: bool = False):
        require_live()
        self.config = settings()
        self.write = write
        self.access_token = ""
        self.expires = 0.0

    def token(self) -> str:
        if self.write:
            if not self.config.airbyte_write_token:
                raise ValueError("AIRBYTE_WRITE_TOKEN is required for actions")
            return self.config.airbyte_write_token
        if self.config.airbyte_token:
            return self.config.airbyte_token
        if self.access_token and time.monotonic() < self.expires:
            return self.access_token
        if not self.config.airbyte_client_id or not self.config.airbyte_client_secret:
            raise ValueError("Configure read-only Airbyte token or application credentials")
        result = http.request(
            "POST",
            self.config.airbyte_url.rstrip("/") + "/applications/token",
            safe=True,
            json={
                "client_id": self.config.airbyte_client_id,
                "client_secret": self.config.airbyte_client_secret,
                "grant-type": "client_credentials",
            },
        )
        self.access_token = result["access_token"]
        self.expires = time.monotonic() + max(int(result.get("expires_in", 180)) - 30, 1)
        return self.access_token

    def call(self, method: str, path: str, **kwargs: object) -> dict:
        if method != "GET" and not self.write:
            raise ValueError("Collector credential cannot mutate Airbyte")
        if not self.config.airbyte_url:
            raise ValueError("AIRBYTE_URL must include the public API prefix")
        return http.request(
            method, self.config.airbyte_url.rstrip("/") + path, token=self.token(), **kwargs
        )

    def jobs(self, connection_id: str, since: datetime) -> list[dict]:
        items = []
        for page in range(self.config.max_pages):
            result = self.call(
                "GET",
                "/jobs",
                params={
                    "connectionId": connection_id,
                    "jobType": "sync",
                    "updatedAtStart": since.isoformat(),
                    "limit": 100,
                    "offset": page * 100,
                    "orderBy": "updatedAt|DESC",
                },
            )
            batch = result.get("data", [])
            items.extend(batch)
            if len(batch) < 100:
                return items
        raise RuntimeError("Airbyte pagination limit exceeded; watermark was not advanced")

    def job(self, job_id: int) -> dict:
        result = self.call("GET", f"/jobs/{job_id}")
        if self.config.airbyte_config_url:
            try:
                details = http.request(
                    "POST",
                    self.config.airbyte_config_url.rstrip("/") + "/jobs/get",
                    token=self.token(),
                    safe=True,
                    json={"id": job_id},
                )
                result["attempts_detail"] = details.get("attempts", [])
            except http.UpstreamError as exc:
                result["diagnostic_error"] = (
                    f"Airbyte attempt diagnostics unavailable (HTTP {exc.status}); public job status was retained"
                )
        return result

    def sync(self, connection_id: str) -> dict:
        return self.call("POST", "/jobs", json={"connectionId": connection_id, "jobType": "sync"})

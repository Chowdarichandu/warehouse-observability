import time
from typing import Any

import httpx

from obs.settings import require_live, settings


class UpstreamError(RuntimeError):
    def __init__(self, status: int, *, ambiguous: bool = False):
        super().__init__(f"Upstream request failed (HTTP {status})")
        self.status = status
        self.ambiguous = ambiguous


def request(method: str, url: str, *, token: str = "", safe: bool = False, **kwargs: Any) -> Any:
    require_live()
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers.setdefault("Accept", "application/json")
    attempts = 3 if method == "GET" or safe else 1
    with httpx.Client(timeout=settings().http_timeout_sec, follow_redirects=False) as client:
        for attempt in range(attempts):
            try:
                response = client.request(method, url, headers=headers, **kwargs)
            except httpx.TransportError as exc:
                if attempt + 1 < attempts:
                    time.sleep(0.5 * 2**attempt)
                    continue
                raise UpstreamError(503, ambiguous=method != "GET" and not safe) from exc
            if response.status_code in {429, 502, 503, 504} and attempt + 1 < attempts:
                try:
                    delay = min(float(response.headers.get("Retry-After", "1")), 10)
                except ValueError:
                    delay = 1
                time.sleep(max(delay, 0))
                continue
            if not response.is_success:
                raise UpstreamError(
                    response.status_code,
                    ambiguous=response.status_code >= 500 and not safe and method != "GET",
                )
            if not response.content:
                return {}
            if "json" in response.headers.get("content-type", ""):
                return response.json()
            return {"content": response.text}
    raise RuntimeError("Unreachable request state")

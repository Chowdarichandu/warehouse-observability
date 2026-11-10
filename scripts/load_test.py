"""Bounded, authenticated read-only smoke load against a local or explicit staging console."""

import argparse
import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

import httpx

READ_PATHS = (
    "/api/overview?range=24h",
    "/api/tenants?page_size=25",
    "/api/runs?range=24h&page_size=25",
    "/api/freshness?page_size=25",
)
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def validate_target(value: str, confirm_staging: bool) -> str:
    parts = urlsplit(value)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in {"", "/"}
    ):
        raise ValueError(
            "Target must be an HTTP(S) origin without credentials, path, or query"
        )
    # Accessing .port also rejects malformed ports before any request is made.
    _ = parts.port
    if parts.hostname not in LOOPBACK:
        if not confirm_staging or parts.scheme != "https":
            raise ValueError("Non-local targets require HTTPS and --confirm-staging")
    return value.rstrip("/")


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


@dataclass(frozen=True)
class Summary:
    requests: int
    errors: int
    error_rate: float
    p50_ms: float
    p95_ms: float
    elapsed_s: float
    requests_per_second: float
    passed: bool


def run_load(
    client: httpx.Client,
    *,
    requests: int,
    concurrency: int,
    rate: float,
    max_p95_ms: float,
    max_error_rate: float,
) -> Summary:
    """Share the thread-safe HTTPX pool and pace all workers against one global schedule."""
    if not 1 <= requests <= 10_000 or not 1 <= concurrency <= 50 or not 0 < rate <= 200:
        raise ValueError(
            "Use 1–10000 requests, 1–50 workers and a rate up to 200 requests/s"
        )
    if not 0 < max_p95_ms <= 60_000 or not 0 <= max_error_rate <= 1:
        raise ValueError(
            "Latency must be positive and error-rate threshold must be between 0 and 1"
        )
    # Bound wall time, rather than unexpectedly scheduling an hour-long test.
    if requests / rate > 300:
        raise ValueError(
            "The requested schedule exceeds five minutes; reduce requests or raise rate"
        )
    started = time.monotonic()
    pace = threading.Lock()
    next_allowed = started

    def request(index: int) -> tuple[float, bool]:
        nonlocal next_allowed
        with pace:
            if time.monotonic() - started > 300:
                return 0, True
            time.sleep(max(0, next_allowed - time.monotonic()))
            next_allowed = time.monotonic() + 1 / rate
        before = time.monotonic()
        failed = False
        try:
            with client.stream("GET", READ_PATHS[index % len(READ_PATHS)]) as response:
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 1_048_576:
                        failed = True
                        break
                failed = failed or response.status_code != 200
        except httpx.HTTPError:
            failed = True
        return (time.monotonic() - before) * 1000, failed

    with ThreadPoolExecutor(
        max_workers=concurrency, thread_name_prefix="obs-load"
    ) as pool:
        samples = list(pool.map(request, range(requests)))
    elapsed = time.monotonic() - started
    durations = [duration for duration, _ in samples]
    errors = sum(failed for _, failed in samples)
    error_rate = errors / requests
    p95 = percentile(durations, 0.95)
    return Summary(
        requests=requests,
        errors=errors,
        error_rate=round(error_rate, 6),
        p50_ms=round(percentile(durations, 0.5), 2),
        p95_ms=round(p95, 2),
        elapsed_s=round(elapsed, 2),
        requests_per_second=round(requests / max(elapsed, 0.000001), 2),
        passed=p95 <= max_p95_ms and error_rate <= max_error_rate,
    )


def authenticate(client: httpx.Client, session: str) -> str:
    """Return CSRF only for a demo session created by this tool; reuse OIDC sessions verbatim."""
    csrf = ""
    if session:
        client.cookies.set("obs_session", session, path="/api")
    else:
        config = client.get("/api/config")
        if config.status_code != 200 or config.json().get("mode") != "demo":
            raise ValueError(
                "Live staging requires OBS_LOAD_SESSION from a dedicated viewer account"
            )
        response = client.post(
            "/api/auth/login",
            json={
                "email": "viewer@demo.local",
                "password": os.getenv("DEMO_PASSWORD", "demo"),
            },
        )
        if response.status_code != 200:
            raise ValueError("Demo viewer login failed")
        csrf = response.json().get("csrf_token", "")
        # Browsers allow Secure cookies on localhost HTTP; HTTPX does not. The target
        # validator permits plain HTTP only on loopback, and only demo login gets this path.
        demo_session = response.cookies.get("obs_session")
        if not demo_session:
            raise ValueError("Demo session cookie missing")
        client.cookies.clear()
        client.cookies.set("obs_session", demo_session, path="/api")
    response = client.get("/api/me")
    if response.status_code != 200 or response.json().get("role") != "viewer":
        raise ValueError("Use an authenticated viewer session for load tests")
    return csrf


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--confirm-staging", action="store_true")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--rate", type=float, default=20)
    parser.add_argument("--max-p95-ms", type=float, default=1500)
    parser.add_argument("--max-error-rate", type=float, default=0)
    args = parser.parse_args()
    try:
        base_url = validate_target(args.base_url, args.confirm_staging)
        # Never follow a redirect with session credentials or inherit an unexpected proxy.
        with httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(10, connect=5),
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=50),
        ) as client:
            csrf = authenticate(client, os.getenv("OBS_LOAD_SESSION", ""))
            try:
                summary = run_load(
                    client,
                    requests=args.requests,
                    concurrency=args.concurrency,
                    rate=args.rate,
                    max_p95_ms=args.max_p95_ms,
                    max_error_rate=args.max_error_rate,
                )
            finally:
                if csrf:
                    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        print(json.dumps(asdict(summary), indent=2))
        raise SystemExit(0 if summary.passed else 1)
    except (ValueError, httpx.HTTPError):
        # HTTP exception strings can contain URLs/cookies; output only a fixed diagnostic.
        parser.exit(
            2,
            "Load test setup failed. Check target, viewer session and bounded arguments.\n",
        )


if __name__ == "__main__":
    main()

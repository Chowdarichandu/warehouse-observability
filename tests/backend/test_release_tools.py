import httpx
import psycopg
import pytest

from obs.settings import settings
from scripts.load_test import (
    READ_PATHS,
    authenticate,
    percentile,
    run_load,
    validate_target,
)
from scripts.recovery_drill import drill, validate_admin_dsn


@pytest.mark.parametrize(
    "target",
    [
        "https://user:secret@example.com",
        "https://example.com/path",
        "https://example.com?token=secret",
        "https://example.com#token",
        "file:///tmp/console",
        "http://staging.example.com",
        "https://example.com:bad",
    ],
)
def test_load_target_rejects_unsafe_origins(target):
    with pytest.raises(ValueError):
        validate_target(target, True)


def test_nonlocal_load_requires_explicit_staging_confirmation():
    with pytest.raises(ValueError, match="confirm-staging"):
        validate_target("https://staging.example.com", False)
    assert (
        validate_target("https://staging.example.com/", True)
        == "https://staging.example.com"
    )
    assert validate_target("http://localhost:8080", False) == "http://localhost:8080"


def test_load_test_uses_only_bounded_read_endpoints_and_fails_on_server_errors():
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(503 if request.url.path == "/api/runs" else 200, json={})

    with httpx.Client(
        base_url="https://localhost", transport=httpx.MockTransport(handle)
    ) as client:
        result = run_load(
            client,
            requests=4,
            concurrency=2,
            rate=200,
            max_p95_ms=1000,
            max_error_rate=0,
        )
    assert result.requests == 4 and result.errors == 1 and result.error_rate == 0.25
    assert not result.passed
    assert all(request.method == "GET" for request in seen)
    assert {request.url.raw_path.decode() for request in seen} == set(READ_PATHS)


def test_load_test_rejects_redirects_and_transport_failures():
    def handle(request):
        if request.url.path == "/api/tenants":
            raise httpx.ConnectError("sensitive upstream details", request=request)
        return httpx.Response(
            302, headers={"location": "https://untrusted.example.com"}
        )

    with httpx.Client(
        base_url="https://localhost", transport=httpx.MockTransport(handle)
    ) as client:
        result = run_load(
            client,
            requests=4,
            concurrency=2,
            rate=200,
            max_p95_ms=1000,
            max_error_rate=0,
        )
    assert result.errors == 4 and not result.passed


@pytest.mark.parametrize(
    "overrides",
    [
        {"requests": 10001},
        {"concurrency": 51},
        {"rate": 0},
        {"requests": 1000, "rate": 1},
    ],
)
def test_load_budgets_are_checked_before_read_requests(overrides):
    def handle(request):
        pytest.fail("No request should be sent for invalid budgets")

    with httpx.Client(
        base_url="https://localhost", transport=httpx.MockTransport(handle)
    ) as client:
        arguments = dict(
            requests=4, concurrency=2, rate=20, max_p95_ms=1000, max_error_rate=0
        )
        arguments.update(overrides)
        with pytest.raises(ValueError):
            run_load(client, **arguments)


def test_demo_load_login_requires_viewer_and_keeps_session_for_loopback():
    def handle(request):
        if request.url.path == "/api/config":
            return httpx.Response(200, json={"mode": "demo"})
        if request.url.path == "/api/auth/login":
            return httpx.Response(
                200,
                json={"csrf_token": "fixture-csrf"},
                headers={
                    "set-cookie": "obs_session=fixture-session; Secure; Path=/api"
                },
            )
        assert request.headers["cookie"] == "obs_session=fixture-session"
        return httpx.Response(200, json={"role": "viewer"})

    with httpx.Client(
        base_url="http://localhost", transport=httpx.MockTransport(handle)
    ) as client:
        assert authenticate(client, "") == "fixture-csrf"


def test_live_load_never_tries_password_login_without_explicit_viewer_session():
    def handle(request):
        assert request.url.path == "/api/config"
        return httpx.Response(200, json={"mode": "live"})

    with httpx.Client(
        base_url="https://localhost", transport=httpx.MockTransport(handle)
    ) as client:
        with pytest.raises(ValueError, match="OBS_LOAD_SESSION"):
            authenticate(client, "")


def test_live_load_rejects_operator_session():
    with httpx.Client(
        base_url="https://localhost",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"role": "operator"})
        ),
    ) as client:
        with pytest.raises(ValueError, match="viewer"):
            authenticate(client, "fixture-session")


def test_percentile_uses_nearest_rank():
    assert percentile([2, 10, 1, 5], 0.95) == 10
    assert percentile([], 0.95) == 0


def test_restore_drill_rejects_remote_databases():
    for value in (
        "host=rds.example.com dbname=obs",
        "dbname=obs",
        "host=127.0.0.1",
        "host=localhost hostaddr=203.0.113.1 dbname=obs",
        "host=localhost service=remote dbname=obs",
    ):
        with pytest.raises(ValueError):
            validate_admin_dsn(value)
    assert validate_admin_dsn("host=localhost dbname=obs")["hostaddr"] == "127.0.0.1"


def test_recovery_drill_compares_actual_restored_content():
    def scratch_databases():
        with psycopg.connect(settings().database_url) as conn:
            return conn.execute(
                "SELECT datname FROM pg_database WHERE datname LIKE 'obs_drill_%' ORDER BY datname"
            ).fetchall()

    before = scratch_databases()
    result = drill(settings().database_url)
    assert result["passed"] and result["nonempty_target_rejected"]
    assert result["sequence_state_verified"]
    assert result["tables_compared"] >= 20 and result["archive_bytes"] > 0
    assert not result["production_data_accessed"]
    # The source and restore scratch databases have already been dropped by drill().
    assert scratch_databases() == before

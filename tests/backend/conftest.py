import os

import pytest
from fastapi.testclient import TestClient

from obs.api.main import app
from obs.settings import require_demo


@pytest.fixture(scope="session")
def clients() -> dict[str, TestClient]:
    require_demo()
    result = {}
    for role in ("admin", "operator", "viewer"):
        client = TestClient(app, base_url="https://localhost")
        response = client.post(
            "/api/auth/login",
            json={
                "email": f"{role}@demo.local",
                "password": os.getenv("DEMO_PASSWORD", "demo"),
            },
        )
        assert response.status_code == 200, response.text
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        result[role] = client
    yield result
    for client in result.values():
        client.close()

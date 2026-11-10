from uuid import uuid4

from fastapi.testclient import TestClient

from obs.api.main import app
from obs.db import connection, one


def test_saved_views_are_private_audited_and_deletable(clients):
    admin, viewer = clients["admin"], clients["viewer"]
    name = f"Failed CDC {uuid4().hex[:8]}"
    saved = admin.post(
        "/api/saved-views",
        json={
            "name": name,
            "filters": {"status": "failed", "source": "mysql", "range": "7d"},
        },
    )
    assert saved.status_code == 201, saved.text
    view_id = saved.json()["id"]
    try:
        assert saved.json()["filters"]["status"] == "failed"
        assert any(
            v["id"] == view_id for v in admin.get("/api/saved-views").json()["items"]
        )
        assert all(
            v["id"] != view_id for v in viewer.get("/api/saved-views").json()["items"]
        )
        assert viewer.delete(f"/api/saved-views/{view_id}").status_code == 404
        assert (
            admin.post(
                "/api/saved-views", json={"name": name, "filters": {}}
            ).status_code
            == 409
        )
        assert one(
            "SELECT 1 AS ok FROM obs.audit_log WHERE action='view.save' AND target=%s",
            (str(view_id),),
        )["ok"]
    finally:
        assert admin.delete(f"/api/saved-views/{view_id}").status_code == 200


def test_saved_view_guards_and_redaction(clients):
    viewer = clients["viewer"]
    for body in [
        {"name": " ", "filters": {}},
        {"name": "test", "filters": {"redirect": "https://evil.example"}},
        {"name": "test", "filters": {"status": "invented"}},
        {
            "name": "test",
            "filters": {"range": "custom", "from": "2026-01-01", "to": "2026-02-01"},
        },
        {"name": "test", "filters": {"q": "x" * 501}},
    ]:
        assert viewer.post("/api/saved-views", json=body).status_code == 422
    saved = viewer.post(
        "/api/saved-views",
        json={
            "name": f"Private {uuid4().hex[:8]}",
            "filters": {"q": "password=super-secret-123"},
        },
    )
    assert saved.status_code == 201
    try:
        assert "super-secret-123" not in saved.text
        with TestClient(app, base_url="https://localhost") as anonymous:
            assert anonymous.get("/api/saved-views").status_code == 401
            anonymous.cookies.update(viewer.cookies)
            assert (
                anonymous.post(
                    "/api/saved-views", json={"name": "csrf", "filters": {}}
                ).status_code
                == 403
            )
    finally:
        viewer.delete(f"/api/saved-views/{saved.json()['id']}")


def test_saved_view_limit_is_per_user(clients):
    uid = clients["viewer"].get("/api/me").json()["user_id"]
    prefix = uuid4().hex
    with connection() as conn:
        for n in range(30):
            conn.execute(
                "INSERT INTO obs.saved_views(user_id,name) VALUES(%s,%s)",
                (uid, f"{prefix}-{n}"),
            )
    try:
        assert (
            clients["viewer"]
            .post("/api/saved-views", json={"name": "Over limit", "filters": {}})
            .status_code
            == 409
        )
    finally:
        with connection() as conn:
            conn.execute(
                "DELETE FROM obs.saved_views WHERE user_id=%s AND name LIKE %s",
                (uid, prefix + "%"),
            )


def test_timeline_is_bounded_chronological_and_run_scoped(clients):
    run = one(
        "SELECT run_key,tenant_id FROM obs.pipeline_runs WHERE tenant_id='acme_retail' AND status='failed' ORDER BY started_at DESC LIMIT 1"
    )
    response = clients["viewer"].get(
        "/api/investigation/timeline", params={"run_key": run["run_key"], "range": "7d"}
    )
    assert response.status_code == 200, response.text
    events = response.json()["items"]
    assert events
    assert len(events) <= 200
    assert [e["at"] for e in events] == sorted([e["at"] for e in events], reverse=True)
    assert all(e["tenant_id"] == run["tenant_id"] for e in events)
    assert all(e["run_key"] == run["run_key"] for e in events if e["kind"] == "run")
    assert "actor" not in response.text
    assert (
        clients["viewer"]
        .get("/api/investigation/timeline?tenant=does_not_exist")
        .status_code
        == 404
    )
    assert (
        clients["viewer"].get("/api/investigation/timeline?range=forever").status_code
        == 422
    )
    assert (
        clients["viewer"].get("/api/investigation/timeline?run_key=missing").status_code
        == 404
    )


def test_timeline_includes_uncertain_tenant_onboarding_without_payload(clients):
    operation_id = str(uuid4())
    with connection() as conn:
        conn.execute(
            """INSERT INTO obs.operations(id,idempotency_key,kind,target,actor,status,payload)
            VALUES(%s,%s,'onboard','acme_retail','private@example.org','uncertain',
            '{"credential":"private-fixture-value"}')""",
            (operation_id, operation_id),
        )
    try:
        response = clients["viewer"].get(
            "/api/investigation/timeline?tenant=acme_retail"
        )
        assert response.status_code == 200
        event = next(
            e for e in response.json()["items"] if e["id"] == "action:" + operation_id
        )
        assert event["status"] == "uncertain" and event["title"] == "onboard"
        assert "private@example.org" not in response.text
        assert "private-fixture-value" not in response.text
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM obs.operations WHERE id=%s", (operation_id,))


def test_configured_console_origin_allows_proxy_actions_and_rejects_other_origins(
    clients, monkeypatch
):
    from obs import auth
    from obs.settings import settings

    config = settings().model_copy(
        update={"console_url": "https://console.example.test"}
    )
    monkeypatch.setattr(auth, "settings", lambda: config)
    viewer = clients["viewer"]
    response = viewer.post(
        "/api/saved-views",
        headers={"Origin": config.console_url},
        json={"name": "Proxy " + uuid4().hex[:8], "filters": {}},
    )
    assert response.status_code == 201, response.text
    try:
        assert (
            viewer.post(
                "/api/saved-views",
                headers={"Origin": "https://untrusted.example.test"},
                json={"name": "Untrusted", "filters": {}},
            ).status_code
            == 403
        )
    finally:
        viewer.delete(f"/api/saved-views/{response.json()['id']}")

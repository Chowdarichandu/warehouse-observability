"""Maintenance windows API, alerter suppression, and the dev mailbox."""

from datetime import UTC, datetime, timedelta

import pytest

from obs.alerter.rules import evaluate
from obs.db import connection, one

TENANT = "maint_window_test"


@pytest.fixture()
def scratch_tenant():
    now = datetime.now(UTC)
    with connection() as conn:
        conn.execute(
            "INSERT INTO obs.tenants(tenant_id,display_name,status,has_mongo,freshness_sla_min,created_at,registered_at) VALUES(%s,'Test','active',false,120,%s,%s) ON CONFLICT DO NOTHING",
            (TENANT, now, now),
        )
    yield TENANT
    with connection() as conn:
        conn.execute(
            "DELETE FROM obs.notification_deliveries WHERE alert_id IN (SELECT id FROM obs.alerts WHERE tenant_id=%s)",
            (TENANT,),
        )
        conn.execute("DELETE FROM obs.alerts WHERE tenant_id=%s", (TENANT,))
        conn.execute("DELETE FROM obs.incidents WHERE tenant_id=%s", (TENANT,))
        conn.execute(
            "DELETE FROM obs.maintenance_windows WHERE tenant_id=%s", (TENANT,)
        )
        conn.execute("DELETE FROM obs.pipeline_runs WHERE tenant_id=%s", (TENANT,))
        conn.execute("DELETE FROM obs.tenants WHERE tenant_id=%s", (TENANT,))


def test_windows_require_manage_tenants(clients, scratch_tenant):
    payload = {
        "starts_at": "2026-11-12T01:00:00Z",
        "ends_at": "2026-11-12T03:00:00Z",
        "reason": "Nightly maintenance",
    }
    assert (
        clients["viewer"]
        .post(f"/api/tenants/{scratch_tenant}/maintenance-windows", json=payload)
        .status_code
        == 403
    )
    assert (
        clients["viewer"]
        .get(f"/api/tenants/{scratch_tenant}/maintenance-windows")
        .status_code
        == 200
    )


def test_window_create_list_delete(clients, scratch_tenant):
    payload = {
        "starts_at": "2026-11-12T01:00:00Z",
        "ends_at": "2026-11-12T03:00:00Z",
        "reason": "Nightly maintenance",
    }
    created = clients["operator"].post(
        f"/api/tenants/{scratch_tenant}/maintenance-windows", json=payload
    )
    assert created.status_code == 201, created.text
    window_id = created.json()["id"]
    listed = (
        clients["operator"]
        .get(f"/api/tenants/{scratch_tenant}/maintenance-windows")
        .json()
    )
    assert [item["id"] for item in listed["items"]] == [window_id]
    inverted = clients["operator"].post(
        f"/api/tenants/{scratch_tenant}/maintenance-windows",
        json={**payload, "ends_at": "2026-11-12T00:00:00Z"},
    )
    assert inverted.status_code == 422
    removed = clients["operator"].delete(
        f"/api/tenants/{scratch_tenant}/maintenance-windows/{window_id}"
    )
    assert removed.status_code == 200
    assert (
        clients["operator"]
        .get(f"/api/tenants/{scratch_tenant}/maintenance-windows")
        .json()["items"]
        == []
    )


def test_maintenance_failures_do_not_raise_consecutive_failure_alerts(scratch_tenant):
    now = datetime.now(UTC).replace(microsecond=0)
    with connection() as conn:
        for index in range(2):
            started = now - timedelta(minutes=30 - index * 10)
            conn.execute(
                """INSERT INTO obs.pipeline_runs(run_key,tenant_id,source_type,load_type,status,
                       triggered_by,started_at,ended_at,duration_s,collected_at,in_maintenance)
                   VALUES(%s,%s,'mysql','cdc','failed','schedule',%s,%s,60,%s,true)""",
                (
                    f"maint|{index}|{scratch_tenant}",
                    scratch_tenant,
                    started,
                    started,
                    now,
                ),
            )
    evaluate()
    alert = one(
        "SELECT 1 AS x FROM obs.alerts WHERE tenant_id=%s AND rule_id='cdc_consecutive_failures' AND state<>'resolved'",
        (TENANT,),
    )
    assert not alert  # one() returns {} when no alert row exists


def test_dev_mailbox_records_invites_and_is_admin_only(clients):
    email = "mailbox.check@demo.local"
    with connection() as conn:
        conn.execute("DELETE FROM obs.dev_mailbox WHERE recipient=%s", (email,))
        conn.execute("DELETE FROM obs.users WHERE email=%s", (email,))
    created = clients["admin"].post(
        "/api/users",
        json={"email": email, "display_name": "Mailbox Check", "role": "viewer"},
    )
    assert created.status_code == 200, created.text
    try:
        assert clients["viewer"].get("/api/dev/mailbox").status_code == 403
        mailbox = clients["admin"].get("/api/dev/mailbox").json()
        invite = next(item for item in mailbox["items"] if item["recipient"] == email)
        assert invite["subject"] == "Your Pravah account is ready"
        assert created.json()["temporary_password"] in invite["body"]
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM obs.dev_mailbox WHERE recipient=%s", (email,))
            conn.execute("DELETE FROM obs.users WHERE email=%s", (email,))

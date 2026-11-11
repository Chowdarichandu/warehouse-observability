from datetime import UTC, datetime, timedelta
from uuid import uuid4

from obs.alerter.rules import evaluate
from obs.db import connection, one
from obs.demo.scenarios import MESSAGES, enrich_failure, upsert_run
from obs.demo.seed import make_run
from obs.repositories.analytics import _sla_cache, sla, sla_rate


def cleanup(tenant: str) -> None:
    with connection() as conn:
        conn.execute(
            "DELETE FROM obs.notification_deliveries WHERE alert_id IN (SELECT id FROM obs.alerts WHERE tenant_id=%s)",
            (tenant,),
        )
        conn.execute("DELETE FROM obs.alerts WHERE tenant_id=%s", (tenant,))
        conn.execute("DELETE FROM obs.incidents WHERE tenant_id=%s", (tenant,))
        conn.execute("DELETE FROM obs.pipeline_runs WHERE tenant_id=%s", (tenant,))
        conn.execute("DELETE FROM obs.tenants WHERE tenant_id=%s", (tenant,))
        conn.execute(
            "DELETE FROM obs.error_groups WHERE fingerprint NOT IN(SELECT fingerprint FROM obs.run_errors)"
        )
    _sla_cache.clear()


def test_sla_uses_five_minute_buckets_and_includes_a_missing_initial_success() -> None:
    tenant = "test_" + uuid4().hex[:8]
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    end = now.replace(minute=now.minute - now.minute % 5)
    start = end - timedelta(minutes=20)
    try:
        with connection() as conn:
            conn.execute(
                "INSERT INTO obs.tenants(tenant_id,display_name,status,has_mongo,freshness_sla_min,created_at,registered_at) VALUES(%s,'Test','active',false,5,%s,%s)",
                (tenant, start, start),
            )
            run = make_run(
                tenant, "mysql", "cdc", start + timedelta(minutes=4), 60, 991
            )
            upsert_run(conn, run)
        _sla_cache.clear()
        compliance = next(
            r for r in sla(start=start, end=end) if r["tenant_id"] == tenant
        )
        assert float(compliance["compliance"]) == 50.0
    finally:
        cleanup(tenant)


def test_new_tenants_are_not_charged_for_buckets_before_registration() -> None:
    tenant = "test_" + uuid4().hex[:8]
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    end = now.replace(minute=now.minute - now.minute % 5)
    created = end - timedelta(minutes=10)
    try:
        with connection() as conn:
            conn.execute(
                "INSERT INTO obs.tenants(tenant_id,display_name,status,has_mongo,freshness_sla_min,created_at,registered_at) VALUES(%s,'Test','active',false,5,%s,%s)",
                (tenant, created, created),
            )
            upsert_run(conn, make_run(tenant, "mysql", "cdc", created, 0, 999))
        _sla_cache.clear()
        sample = next(
            r
            for r in sla(start=end - timedelta(minutes=20), end=end)
            if r["tenant_id"] == tenant
        )
        assert sample["buckets"] == 2
        assert float(sample["compliance"]) == 100
        assert (
            sla_rate(
                [
                    {"good_buckets": 288, "buckets": 288},
                    {"good_buckets": 0, "buckets": 1},
                ]
            )
            == 99.65
        )
    finally:
        cleanup(tenant)


def test_alert_dedup_ack_suppression_and_automatic_resolution(clients: dict) -> None:
    tenant = "test_" + uuid4().hex[:8]
    now = datetime.now(UTC)
    try:
        with connection() as conn:
            conn.execute(
                "INSERT INTO obs.tenants(tenant_id,display_name,status,has_mongo) VALUES(%s,'Test','active',false)",
                (tenant,),
            )
            run = make_run(
                tenant, "mysql", "cdc", now - timedelta(minutes=3), 60, 992, "failed"
            )
            upsert_run(conn, run)
            enrich_failure(conn, run, MESSAGES["MYSQL_BINLOG_PURGED"])
            enrich_failure(conn, run, MESSAGES["MYSQL_BINLOG_PURGED"])
            group = conn.execute(
                "SELECT g.occurrences,(SELECT count(*) FROM obs.run_errors WHERE fingerprint=g.fingerprint) AS actual FROM obs.error_groups g JOIN obs.run_errors e USING(fingerprint) WHERE e.run_key=%s",
                (run["run_key"],),
            ).fetchone()
            assert group["occurrences"] == group["actual"]
        evaluate()
        evaluate()
        alert = one(
            "SELECT * FROM obs.alerts WHERE tenant_id=%s AND rule_id='cdc_position_lost' AND state<>'resolved'",
            (tenant,),
        )
        assert alert["severity"] == "critical"
        incident = one(
            "SELECT * FROM obs.incidents WHERE tenant_id=%s AND state<>'resolved'",
            (tenant,),
        )
        assert incident["source_type"] == "mysql"
        assert (
            one("SELECT incident_id FROM obs.alerts WHERE id=%s", (alert["id"],))[
                "incident_id"
            ]
            == incident["id"]
        )
        assert (
            one(
                "SELECT count(*) AS n FROM obs.alerts WHERE tenant_id=%s AND rule_id='cdc_position_lost'",
                (tenant,),
            )["n"]
            == 1
        )
        with connection() as conn:
            pending = make_run(
                tenant,
                "mysql",
                "cdc",
                now - timedelta(minutes=1),
                0,
                994,
                "running",
                "retry",
            )
            upsert_run(conn, pending)
        evaluate()
        # An in-progress retry has not recovered the replication position.
        assert (
            one("SELECT state FROM obs.alerts WHERE id=%s", (alert["id"],))["state"]
            == "firing"
        )
        assert (
            clients["operator"].post(f"/api/alerts/{alert['id']}/ack").status_code
            == 200
        )
        with connection() as conn:
            conn.execute(
                "UPDATE obs.alerts SET last_notified_at=now()-interval '1 day' WHERE id=%s",
                (alert["id"],),
            )
        before = one(
            "SELECT count(*) AS n FROM obs.notification_deliveries WHERE alert_id=%s",
            (alert["id"],),
        )["n"]
        evaluate()
        assert (
            one(
                "SELECT count(*) AS n FROM obs.notification_deliveries WHERE alert_id=%s",
                (alert["id"],),
            )["n"]
            == before
        )
        with connection() as conn:
            recovery = make_run(
                tenant, "mysql", "cdc", now - timedelta(seconds=30), 20, 993
            )
            upsert_run(conn, recovery)
        evaluate()
        assert (
            one("SELECT state FROM obs.alerts WHERE id=%s", (alert["id"],))["state"]
            == "resolved"
        )
        assert (
            one("SELECT state FROM obs.incidents WHERE id=%s", (incident["id"],))[
                "state"
            ]
            == "resolved"
        )
        assert (
            one(
                "SELECT count(*) AS n FROM obs.notification_deliveries WHERE alert_id=%s AND kind='resolved'",
                (alert["id"],),
            )["n"]
            == 1
        )
    finally:
        cleanup(tenant)


def test_incident_pagination_rejects_unbounded_queries(clients: dict) -> None:
    client = clients["admin"]
    assert client.get("/api/incidents?page=0").status_code == 422
    assert client.get("/api/incidents?page_size=201").status_code == 422


def test_incident_read_and_response_actions_follow_workspace_roles(
    clients: dict,
) -> None:
    with connection() as conn:
        incident_id = conn.execute(
            "INSERT INTO obs.incidents(severity,title) VALUES('high','RBAC test') RETURNING id"
        ).fetchone()["id"]
    path = f"/api/incidents/{incident_id}"
    try:
        for role in ("viewer", "operator", "admin"):
            assert clients[role].get("/api/incidents").status_code == 200
            assert clients[role].get(path).status_code == 200

        assert clients["viewer"].post(f"{path}/ack").status_code == 403
        assert clients["viewer"].post(f"{path}/resolve").status_code == 403
        assert (
            clients["viewer"]
            .post(f"{path}/notes", json={"body": "Reviewing"})
            .status_code
            == 403
        )
        assert (
            clients["operator"]
            .post(f"{path}/notes", json={"body": "Reviewing"})
            .status_code
            == 200
        )
        assert clients["operator"].post(f"{path}/ack").status_code == 200
        assert clients["admin"].post(f"{path}/resolve").status_code == 200
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM obs.incidents WHERE id=%s", (incident_id,))

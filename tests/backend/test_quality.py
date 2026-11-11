from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb
from psycopg.rows import dict_row
from pydantic import ValidationError

from obs.db import connection
from obs.quality import engine
from obs.quality.models import QualityCheckInput
from obs.settings import settings


def definition(**changes) -> dict:
    return {
        "tenant_id": "acme_retail",
        "name": "Amount required",
        "table_name": "orders",
        "kind": "null_rate",
        "params": {"column": "amount", "max_null_rate": 0},
        "sample_limit": 100,
        "interval_sec": 900,
        "enabled": True,
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"table_name": "orders; DROP SCHEMA obs CASCADE"},
        {"params": {"column": "amount", "sql": "DELETE FROM orders"}},
        {"params": {"column": "amount", "max_null_rate": float("nan")}},
        {"sample_limit": 10001},
        {"kind": "duplicate_keys", "params": {"columns": ["id", "id"]}},
        {"kind": "schema_contract", "params": {"columns": {"id": "text); DELETE"}}},
    ],
)
def test_quality_rejects_unbounded_or_free_sql(changes):
    with pytest.raises(ValidationError):
        QualityCheckInput.model_validate(definition(**changes))


def test_aggregates_only_and_empty_sample_is_unknown():
    check = definition()
    rows = [{"amount": None}, {"amount": "sensitive-row-value"}]
    status, evidence = engine.assess(check, rows, {"amount": "text"})
    assert status == "fail" and evidence["violations"] == 1
    assert "sensitive-row-value" not in str(evidence)
    assert engine.assess(check, [], {"amount": "text"})[0] == "error"
    isolation = definition(
        kind="tenant_isolation",
        params={"tenant_field": "tenant_id"},
    )
    assert engine.assess(
        isolation,
        [{"foreign_rows": 2, "total_rows": 10}],
        {"tenant_id": "text"},
    ) == (
        "fail",
        {
            "foreign_rows": 2,
            "total_rows": 10,
            "scope": "full-table tenant field aggregate",
        },
    )
    assert (
        engine.assess(
            isolation,
            [{"foreign_rows": 0, "total_rows": 10}],
            {"tenant_id": "text"},
        )[0]
        == "pass"
    )
    duplicate = definition(
        kind="duplicate_keys", params={"columns": ["id"], "max_duplicate_rate": 0}
    )
    assert (
        engine.assess(duplicate, [{"id": None}, {"id": None}], {"id": "bigint"})[1][
            "violations"
        ]
        == 1
    )
    accepted = definition(
        kind="accepted_values",
        params={"column": "state", "values": ["ok"], "max_invalid_rate": 0},
    )
    assert engine.assess(accepted, [{"state": None}], {"state": "text"})[0] == "fail"
    contract = definition(
        kind="schema_contract",
        params={"columns": {"id": "bigint"}, "allow_extra": False},
    )
    assert engine.assess(contract, [], {"id": "text", "extra": "numeric"}) == (
        "fail",
        {
            "missing_columns": [],
            "type_mismatches": ["id"],
            "unexpected_columns": ["extra"],
            "scope": "catalog schema contract",
        },
    )


def test_quality_api_roles_validation_and_result_history(clients):
    admin, operator, viewer = (
        clients[role] for role in ("admin", "operator", "viewer")
    )
    body = definition(name="Quality test " + uuid4().hex)
    assert viewer.post("/api/quality/checks", json=body).status_code == 403
    assert operator.post("/api/quality/checks", json=body).status_code == 403
    assert (
        admin.post(
            "/api/quality/checks", json={**body, "tenant_id": "not_registered"}
        ).status_code
        == 404
    )
    created = admin.post("/api/quality/checks", json=body)
    assert created.status_code == 201, created.text
    check = created.json()
    try:
        assert admin.post("/api/quality/checks", json=body).status_code == 409
        assert viewer.post(f"/api/quality/checks/{check['id']}/run").status_code == 403
        result = operator.post(f"/api/quality/checks/{check['id']}/run")
        assert result.status_code == 200, result.text
        assert result.json()["simulated"] is True
        assert result.json()["status"] == "fail"
        assert result.json()["sampled_rows"] == 100
        assert result.json()["details"]["violations"] == 8
        history = viewer.get(f"/api/quality/results?check_id={check['id']}")
        assert history.status_code == 200 and history.json()["total"] == 1
        edited = admin.put(
            f"/api/quality/checks/{check['id']}",
            json={**body, "params": {"column": "amount", "max_null_rate": 0.1}},
        )
        assert edited.status_code == 200, edited.text
        # Preserve old evidence in history without using it as validation of a new definition.
        history = viewer.get(f"/api/quality/results?check_id={check['id']}")
        assert history.json()["total"] == 1
        listed = viewer.get("/api/quality/checks?tenant_id=acme_retail").json()
        assert (
            next(item for item in listed["items"] if item["id"] == check["id"])[
                "latest_result"
            ]
            is None
        )
        assert (
            operator.post(f"/api/quality/checks/{check['id']}/run").json()["status"]
            == "pass"
        )
        assert (
            admin.patch(
                f"/api/quality/checks/{check['id']}", json={"enabled": False}
            ).status_code
            == 200
        )
        assert (
            operator.post(f"/api/quality/checks/{check['id']}/run").status_code == 409
        )
        assert (
            admin.put(
                f"/api/quality/checks/{check['id']}",
                json={**body, "tenant_id": "northwind"},
            ).status_code
            == 422
        )
        with connection() as conn:
            audits = conn.execute(
                "SELECT action FROM obs.audit_log WHERE target=%s AND action LIKE 'quality_%%'",
                (str(check["id"]),),
            ).fetchall()
            assert {item["action"] for item in audits} >= {
                "quality_check_created",
                "quality_check_run",
                "quality_check_updated",
                "quality_check_disabled",
            }
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM obs.quality_checks WHERE id=%s", (check["id"],))


def test_live_sample_uses_timeout_readonly_schema_and_limit(monkeypatch):
    schema = "quality_" + uuid4().hex[:12]
    with connection() as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
        conn.execute(f'CREATE TABLE "{schema}".orders(id bigint,amount numeric)')
        conn.execute(
            f'INSERT INTO "{schema}".orders SELECT i,NULL FROM generate_series(1,200) i'
        )
    recorded = []

    @contextmanager
    def local_warehouse():
        with psycopg.connect(settings().database_url, row_factory=dict_row) as conn:

            class Source:
                def execute(self, query, args=None):
                    recorded.append(
                        (
                            query.as_string(conn)
                            if hasattr(query, "as_string")
                            else query,
                            args,
                        )
                    )
                    result = conn.execute(query, args)
                    if recorded[-1][0].startswith('SELECT "amount"'):
                        assert (
                            conn.execute("SHOW transaction_read_only").fetchone()[
                                "transaction_read_only"
                            ]
                            == "on"
                        )
                        assert (
                            conn.execute("SHOW statement_timeout").fetchone()[
                                "statement_timeout"
                            ]
                            == "10s"
                        )
                    return result

            yield Source()

    monkeypatch.setattr(engine.warehouse, "connect", local_warehouse)
    try:
        samples, columns = engine.live_evidence(definition(sample_limit=7), schema)
        assert len(samples) == 7 and columns == {"id": "bigint", "amount": "numeric"}
        assert any(q == "SET LOCAL statement_timeout TO 10000" for q, _ in recorded)
        query, args = next(
            (q, args) for q, args in recorded if q.startswith('SELECT "amount"')
        )
        assert query == f'SELECT "amount" FROM "{schema}"."orders" LIMIT %s'
        assert args == (7,)
        assert not any("count(" in q.lower() for q, _ in recorded)
    finally:
        with connection() as conn:
            conn.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_live_tenant_isolation_uses_full_table_aggregate(monkeypatch):
    schema = "quality_" + uuid4().hex[:12]
    with connection() as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
        conn.execute(
            f'CREATE TABLE "{schema}".orders(id bigint,tenant_id text,amount numeric)'
        )
        conn.execute(
            f"INSERT INTO \"{schema}\".orders VALUES (1,'acme_retail',1),(2,'other',2)"
        )

    @contextmanager
    def local_warehouse():
        with psycopg.connect(settings().database_url, row_factory=dict_row) as conn:

            class Source:
                def execute(self, query, args=None):
                    return conn.execute(query, args)

            yield Source()

    monkeypatch.setattr(engine.warehouse, "connect", local_warehouse)
    try:
        samples, columns = engine.live_evidence(
            definition(
                kind="tenant_isolation",
                params={"tenant_field": "tenant_id"},
            ),
            schema,
        )
        assert samples == [{"foreign_rows": 1, "total_rows": 2}]
        assert columns == {"id": "bigint", "tenant_id": "text", "amount": "numeric"}
    finally:
        with connection() as conn:
            conn.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_tenant_isolation_failure_is_idempotent_for_open_incidents(monkeypatch):
    tenant = "isolation_" + uuid4().hex[:10]
    check = None
    monkeypatch.setattr(engine, "settings", lambda: SimpleNamespace(mode="demo"))

    def failing_evidence(conn, definition):
        return [{"foreign_rows": 2, "total_rows": 10}], {"tenant_id": "text"}

    monkeypatch.setattr(engine, "demo_evidence", failing_evidence)
    with connection() as conn:
        conn.execute(
            """INSERT INTO obs.tenants(tenant_id,display_name,status,sources)
            VALUES(%s,%s,'active',%s)""",
            (
                tenant,
                "Isolation Fixture",
                Jsonb({"mongo": {"shared": True, "tenant_field": "tenant_id"}}),
            ),
        )
        check = conn.execute(
            """INSERT INTO obs.quality_checks
            (tenant_id,name,table_name,kind,params,sample_limit)
            VALUES(%s,%s,'orders','tenant_isolation',%s,100) RETURNING *""",
            (tenant, "Isolation check", Jsonb({"tenant_field": "tenant_id"})),
        ).fetchone()
    try:
        with connection() as conn:
            assert engine.execute(conn, check)["status"] == "fail"
        with connection() as conn:
            assert engine.execute(conn, check)["status"] == "fail"
            incidents = conn.execute(
                """SELECT count(*) AS count FROM obs.incidents
                WHERE tenant_id=%s AND cause_rule='tenant_isolation' AND state='open'""",
                (tenant,),
            ).fetchone()["count"]
            assert incidents == 1
    finally:
        with connection() as conn:
            conn.execute(
                "DELETE FROM obs.quality_results WHERE tenant_id=%s", (tenant,)
            )
            conn.execute("DELETE FROM obs.quality_checks WHERE tenant_id=%s", (tenant,))
            conn.execute("DELETE FROM obs.incidents WHERE tenant_id=%s", (tenant,))
            conn.execute("DELETE FROM obs.tenants WHERE tenant_id=%s", (tenant,))


def test_live_error_never_persists_driver_values(monkeypatch):
    with connection() as conn:
        item = conn.execute(
            """INSERT INTO obs.quality_checks(tenant_id,name,table_name,kind,params)
        VALUES('acme_retail',%s,'orders','null_rate','{"column":"amount","max_null_rate":0}') RETURNING *""",
            ("Safe failure " + uuid4().hex,),
        ).fetchone()
        original = conn.execute(
            "SELECT warehouse_schema FROM obs.tenants WHERE tenant_id='acme_retail'"
        ).fetchone()["warehouse_schema"]
        conn.execute(
            "UPDATE obs.tenants SET warehouse_schema='acme_retail' WHERE tenant_id='acme_retail'"
        )
    monkeypatch.setattr(engine, "settings", lambda: SimpleNamespace(mode="live"))

    def broken(*args):
        raise RuntimeError(
            "warehouse_password=secret-password person@example.org private-row-value"
        )

    monkeypatch.setattr(engine, "live_evidence", broken)
    try:
        with connection() as conn:
            result = engine.execute(conn, item)
            assert result["status"] == "error"
            assert "private-row-value" not in str(
                result
            ) and "secret-password" not in str(result)
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM obs.quality_checks WHERE id=%s", (item["id"],))
            conn.execute(
                "UPDATE obs.tenants SET warehouse_schema=%s WHERE tenant_id='acme_retail'",
                (original,),
            )


def test_live_scheduler_disabled_does_not_contact_warehouse(monkeypatch):
    monkeypatch.setattr(
        engine, "settings", lambda: SimpleNamespace(mode="live", quality_enabled=False)
    )

    def forbidden(*args):
        pytest.fail("Disabled quality checks must not query the database or warehouse")

    monkeypatch.setattr(engine, "rows", forbidden)
    engine.evaluate_due()

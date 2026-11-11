from obs.db import connection, one
from obs.demo.seed import TENANTS, columns_for, stream_shares, tables_for
from obs.quality.demo import seed_quality
from obs.quality.engine import demo_evidence


def test_demo_catalog_contains_the_volume_and_schema_drift_assets() -> None:
    assert {tenant_id for tenant_id, _, _ in TENANTS} == {
        "acme_retail",
        "bluefin_health",
        "northwind",
        "orbit_logistics",
        "cedar_foods",
        "helix_energy",
        "evergreen_market",
        "summit_media",
        "pinecrest_edu",
        "beacon_finance",
    }
    assert "shipments" in tables_for("orbit_logistics")
    assert "orders" in tables_for("orbit_logistics")
    assert {column["name"] for column in columns_for("orbit_logistics", "orders")} == {
        "id",
        "created_at",
        "amount",
    }


def test_demo_stream_shares_are_deterministic_and_complete() -> None:
    shares = stream_shares("orbit_logistics")
    assert [name for name, _ in shares] == tables_for("orbit_logistics")
    assert sum(share for _, share in shares) == 1


def test_demo_isolation_evidence_passes_without_a_catalog() -> None:
    # Demo isolation evidence models shared collections partitioned by the
    # tenant field; it must not depend on the table catalog being present.
    samples, columns = demo_evidence(
        None,
        {
            "kind": "tenant_isolation",
            "tenant_id": "bluefin_health",
            "table_name": "orders",
            "params": {"tenant_field": "tenant_id"},
        },
    )
    assert samples == [{"foreign_rows": 0, "total_rows": 100}]
    assert columns == {"tenant_id": "text"}


def test_seeded_isolation_checks_pass_with_pinecrest_history() -> None:
    with connection() as conn:
        seed_quality(conn)
    latest = one(
        """SELECT count(*) AS n FROM obs.quality_checks q
           WHERE q.kind='tenant_isolation' AND (
             SELECT r.status FROM obs.quality_results r
              WHERE r.check_id=q.id ORDER BY r.checked_at DESC LIMIT 1) <> 'pass'"""
    )
    assert latest["n"] == 0
    incident = one(
        """SELECT * FROM obs.incidents
            WHERE tenant_id='pinecrest_edu' AND cause_rule='tenant_isolation'"""
    )
    assert incident["state"] == "resolved"
    assert incident["root_cause_category"] == "Configuration"
    alert = one("SELECT * FROM obs.alerts WHERE incident_id=%s", (incident["id"],))
    assert alert["state"] == "resolved"

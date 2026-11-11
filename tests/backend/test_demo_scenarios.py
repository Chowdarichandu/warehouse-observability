from obs.demo.seed import TENANTS, columns_for, stream_shares, tables_for


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
        "luminous_labs",
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

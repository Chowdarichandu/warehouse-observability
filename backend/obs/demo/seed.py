import hashlib
import json
import random
from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from obs.auth import hasher
from obs.db import connection, notify
from obs.demo.scenarios import MESSAGES, enrich_failure, upsert_run
from obs.settings import require_demo, settings

TENANTS = [
    ("acme_retail", "Acme Retail", 4),
    ("bluefin_health", "Bluefin Health", 3),
    ("northwind", "Northwind", 17),
    ("orbit_logistics", "Orbit Logistics", 11),
    ("cedar_foods", "Cedar Foods", 5),
    ("helix_energy", "Helix Energy", 14),
    ("evergreen_market", "Evergreen Market", 2),
    ("summit_media", "Summit Media", 4),
    ("luminous_labs", "Luminous Labs", 3),
    ("beacon_finance", "Beacon Finance", 9),
]
STREAMS = [
    "customers",
    "orders",
    "products",
    "payments",
    "events",
    "inventory",
    "invoices",
    "sessions",
]

# Each tenant syncs its own business catalog: (table, relative record volume,
# extra columns as "name:type" beyond the shared id/created_at pair). A
# healthcare tenant's warehouse holds patients and claims, not a copy of the
# retail tenant's orders — the console should read like ten real clients.
TENANT_TABLES: dict[str, list[tuple[str, float, list[str]]]] = {
    "acme_retail": [
        ("customers", 0.7, ["email:text", "full_name:text", "segment:text"]),
        ("orders", 1.6, ["customer_id:bigint", "amount:numeric", "status:text"]),
        (
            "order_items",
            2.6,
            ["order_id:bigint", "product_id:bigint", "quantity:integer", "unit_price:numeric"],
        ),
        ("products", 0.35, ["sku:text", "name:text", "price:numeric", "category:text"]),
        ("payments", 1.5, ["order_id:bigint", "amount:numeric", "method:text"]),
        ("refunds", 0.3, ["payment_id:bigint", "amount:numeric", "reason:text"]),
        ("inventory", 0.9, ["product_id:bigint", "store_id:bigint", "quantity:integer"]),
        ("stores", 0.05, ["name:text", "city:text"]),
        ("promotions", 0.12, ["code:text", "discount_pct:numeric"]),
        ("sessions", 2.2, ["customer_id:bigint", "device:text", "started_at:timestamp"]),
    ],
    "bluefin_health": [
        ("patients", 0.8, ["full_name:text", "date_of_birth:date", "gender:text"]),
        (
            "appointments",
            1.7,
            ["patient_id:bigint", "provider_id:bigint", "scheduled_at:timestamp", "status:text"],
        ),
        ("encounters", 1.9, ["patient_id:bigint", "department_id:bigint", "diagnosis_code:text"]),
        ("prescriptions", 1.4, ["patient_id:bigint", "medication:text", "dosage:text"]),
        ("claims", 1.2, ["patient_id:bigint", "amount:numeric", "status:text"]),
        ("providers", 0.15, ["full_name:text", "specialty:text"]),
        ("departments", 0.05, ["name:text"]),
        (
            "lab_results",
            2.4,
            ["patient_id:bigint", "test_code:text", "result_value:numeric", "unit:text"],
        ),
    ],
    "northwind": [
        ("customers", 0.6, ["company_name:text", "contact_name:text", "country:text"]),
        ("orders", 1.5, ["customer_id:bigint", "amount:numeric", "ship_country:text"]),
        (
            "order_details",
            2.8,
            ["order_id:bigint", "product_id:bigint", "quantity:integer", "unit_price:numeric"],
        ),
        ("products", 0.3, ["name:text", "category_id:bigint", "unit_price:numeric"]),
        ("suppliers", 0.12, ["company_name:text", "country:text"]),
        ("shippers", 0.05, ["company_name:text", "phone:text"]),
        ("employees", 0.08, ["full_name:text", "title:text"]),
        ("categories", 0.04, ["name:text"]),
        ("territories", 0.1, ["name:text", "region_id:bigint"]),
        ("invoices", 1.3, ["order_id:bigint", "amount:numeric", "due_date:date"]),
    ],
    "orbit_logistics": [
        # orders keeps exactly id/created_at/amount: the seeded schema
        # contract check and the delivery_region drift story depend on it.
        ("orders", 1.4, ["amount:numeric"]),
        ("shipments", 1.8, ["order_id:bigint", "status:text", "weight_kg:numeric"]),
        ("parcels", 2.6, ["shipment_id:bigint", "barcode:text", "weight_kg:numeric"]),
        ("tracking_events", 3.2, ["parcel_id:bigint", "event_type:text", "location:text"]),
        ("routes", 0.4, ["origin_hub:text", "destination_hub:text", "distance_km:numeric"]),
        ("vehicles", 0.2, ["plate:text", "vehicle_type:text", "capacity_kg:numeric"]),
        ("drivers", 0.25, ["full_name:text", "license_no:text"]),
        ("warehouses", 0.06, ["name:text", "city:text"]),
        ("deliveries", 1.6, ["shipment_id:bigint", "delivered_at:timestamp", "signed_by:text"]),
        ("hubs", 0.08, ["name:text", "city:text"]),
    ],
    "cedar_foods": [
        ("menu_items", 0.3, ["name:text", "price:numeric", "category:text"]),
        ("orders", 1.7, ["outlet_id:bigint", "amount:numeric", "status:text"]),
        ("order_items", 2.4, ["order_id:bigint", "menu_item_id:bigint", "quantity:integer"]),
        ("ingredients", 0.5, ["name:text", "unit:text"]),
        ("recipes", 0.35, ["menu_item_id:bigint", "ingredient_id:bigint", "quantity:numeric"]),
        ("suppliers", 0.12, ["name:text", "city:text"]),
        ("outlets", 0.06, ["name:text", "city:text"]),
        ("deliveries", 1.1, ["order_id:bigint", "rider_id:bigint", "delivered_at:timestamp"]),
        ("waste_logs", 0.4, ["ingredient_id:bigint", "quantity:numeric", "reason:text"]),
    ],
    "helix_energy": [
        ("customers", 0.7, ["full_name:text", "tariff_id:bigint", "address:text"]),
        ("meters", 0.9, ["customer_id:bigint", "serial_no:text", "installed_at:date"]),
        ("readings", 3.4, ["meter_id:bigint", "reading_kwh:numeric", "read_at:timestamp"]),
        ("billing", 1.3, ["customer_id:bigint", "amount:numeric", "period_start:date"]),
        ("payments", 1.2, ["billing_id:bigint", "amount:numeric", "method:text"]),
        ("outages", 0.3, ["region:text", "started_at:timestamp", "restored_at:timestamp"]),
        ("assets", 0.5, ["asset_type:text", "location:text", "status:text"]),
        ("work_orders", 0.8, ["asset_id:bigint", "status:text", "priority:text"]),
        ("tariffs", 0.05, ["name:text", "rate_per_kwh:numeric"]),
    ],
    "evergreen_market": [
        ("products", 0.4, ["sku:text", "name:text", "price:numeric", "category:text"]),
        ("orders", 1.5, ["customer_id:bigint", "amount:numeric", "status:text"]),
        ("baskets", 2.0, ["order_id:bigint", "product_id:bigint", "quantity:integer"]),
        ("suppliers", 0.12, ["name:text", "city:text"]),
        ("stores", 0.05, ["name:text", "city:text"]),
        ("inventory", 0.9, ["product_id:bigint", "store_id:bigint", "quantity:integer"]),
        ("loyalty_members", 0.6, ["full_name:text", "points:integer"]),
        ("deliveries", 1.1, ["order_id:bigint", "delivered_at:timestamp"]),
    ],
    "summit_media": [
        ("content", 0.5, ["title:text", "creator_id:bigint", "content_type:text"]),
        ("views", 3.4, ["content_id:bigint", "viewer_id:bigint", "watched_seconds:integer"]),
        ("subscriptions", 0.9, ["user_id:bigint", "plan:text", "status:text"]),
        ("creators", 0.2, ["full_name:text", "channel_name:text"]),
        ("ad_impressions", 3.0, ["campaign_id:bigint", "content_id:bigint", "shown_at:timestamp"]),
        ("campaigns", 0.15, ["advertiser:text", "budget:numeric", "status:text"]),
        ("comments", 1.8, ["content_id:bigint", "user_id:bigint", "body:text"]),
        ("payouts", 0.4, ["creator_id:bigint", "amount:numeric", "period:text"]),
    ],
    "luminous_labs": [
        ("experiments", 0.4, ["name:text", "project_id:bigint", "status:text"]),
        ("samples", 1.6, ["experiment_id:bigint", "sample_code:text", "collected_at:timestamp"]),
        ("instruments", 0.2, ["name:text", "instrument_type:text", "status:text"]),
        ("protocols", 0.25, ["name:text", "version:text"]),
        ("results", 2.2, ["sample_id:bigint", "metric:text", "value:numeric", "unit:text"]),
        ("projects", 0.15, ["name:text", "lead_researcher:text"]),
        ("reagents", 0.5, ["name:text", "lot_no:text", "expires_on:date"]),
        ("researchers", 0.1, ["full_name:text", "team:text"]),
    ],
    "beacon_finance": [
        ("customers", 0.7, ["full_name:text", "kyc_status:text", "segment:text"]),
        ("accounts", 1.0, ["customer_id:bigint", "account_type:text", "balance:numeric"]),
        ("transactions", 3.2, ["account_id:bigint", "amount:numeric", "txn_type:text"]),
        ("loans", 0.5, ["customer_id:bigint", "principal:numeric", "status:text"]),
        ("cards", 0.6, ["account_id:bigint", "card_type:text", "status:text"]),
        ("payments", 1.8, ["account_id:bigint", "amount:numeric", "beneficiary:text"]),
        ("branches", 0.05, ["name:text", "city:text"]),
        ("kyc_documents", 0.8, ["customer_id:bigint", "doc_type:text", "verified:boolean"]),
    ],
}


_DEFAULT_TABLES: list[tuple[str, float, list[str]]] = [
    (name, 1.0, ["amount:numeric"]) for name in STREAMS
]


def _tables(tenant_id: str) -> list[tuple[str, float, list[str]]]:
    # Tenants onboarded after seeding fall back to the generic catalog.
    return TENANT_TABLES.get(tenant_id, _DEFAULT_TABLES)


def tables_for(tenant_id: str) -> list[str]:
    return [name for name, _, _ in _tables(tenant_id)]


def columns_for(tenant_id: str, table: str) -> list[dict]:
    extras = next(extra for name, _, extra in _tables(tenant_id) if name == table)
    return [
        {"name": "id", "type": "bigint"},
        {"name": "created_at", "type": "timestamp"},
        *({"name": n, "type": t} for n, t in (e.split(":") for e in extras)),
    ]


def stream_shares(tenant_id: str) -> list[tuple[str, float]]:
    tables = _tables(tenant_id)
    total = sum(weight for _, weight, _ in tables)
    return [(name, weight / total) for name, weight, _ in tables]


DEFAULT_RULES = [
    ("cdc_consecutive_failures", "Consecutive CDC failures", "high", {"n": 2}),
    ("cdc_position_lost", "CDC replication position lost", "critical", {}),
    ("freshness_breach", "Freshness SLA breached", "high", {"pct": 100}),
    ("stuck_run", "Run exceeds usual duration", "medium", {"multiplier": 3}),
    ("volume_anomaly", "Warehouse volume anomaly", "medium", {"drop_pct": 30}),
    ("schema_drift", "Warehouse schema changed", "low", {}),
    ("queue_backlog", "Airflow queue backlog", "medium", {"minutes": 15}),
    ("dag_import_errors", "DAG import errors", "high", {}),
    ("platform_down", "Platform component down", "critical", {}),
    ("collector_silent", "Collector heartbeat missing", "critical", {"minutes": 10}),
]


def make_run(
    tenant: str,
    source: str,
    load: str,
    at: datetime,
    duration: int,
    job_id: int,
    status: str = "success",
    triggered_by: str = "schedule",
) -> dict:
    dag = f"{source}_{'initial_load' if load == 'initial' else 'cdc'}"
    # Deterministic per-run variation: identical durations must not produce
    # identical queue delays and row counts across tenants (a visible demo tell).
    jitter = int(hashlib.sha256(f"{tenant}|{source}|{load}|{job_id}".encode()).hexdigest()[:6], 16)
    queue_delay = 8 + jitter % 40
    rows_per_s = 380 + jitter % 120
    return {
        "run_key": f"{dag}|scheduled__{at.isoformat()}|sync_{tenant}|-1",
        "tenant_id": tenant,
        "source_type": source,
        "load_type": load,
        "status": status,
        "failed_stage": "airbyte" if status == "failed" else None,
        "triggered_by": triggered_by,
        "scheduled_for": at - timedelta(seconds=queue_delay),
        "queued_at": at - timedelta(seconds=queue_delay),
        "started_at": at,
        "ended_at": at + timedelta(seconds=duration)
        if status not in {"running", "queued"}
        else None,
        "duration_s": duration if status not in {"running", "queued"} else None,
        "queue_delay_s": queue_delay,
        "rows_synced": duration * rows_per_s if status == "success" else 0,
        "bytes_synced": duration * rows_per_s * 160 if status == "success" else 0,
        "dag_id": dag,
        "dag_run_id": f"scheduled__{at.isoformat()}",
        "task_id": f"sync_{tenant}",
        "map_index": -1,
        "try_number": 1,
        "airbyte_connection_id": f"demo-{tenant}-{source}-{load}",
        "airbyte_job_id": job_id,
        "airbyte_attempts": 1,
        "collected_at": at,
    }


def seed() -> None:
    require_demo()
    rng = random.Random(271828)
    now = datetime.now(UTC).replace(microsecond=0)
    anchor = now.replace(minute=0, second=0)
    outage = now - timedelta(hours=8)
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(110528)")
        for role in ("admin", "operator", "viewer"):
            conn.execute(
                """INSERT INTO obs.users(email,display_name,role,password_hash) VALUES(%s,%s,%s,%s)
                ON CONFLICT(email) DO NOTHING""",
                (
                    f"{role}@demo.local",
                    f"Demo {role.title()}",
                    role,
                    hasher.hash(settings().demo_password),
                ),
            )
        for key, name, severity, params in DEFAULT_RULES:
            conn.execute(
                """INSERT INTO obs.alert_rules(rule_id,name,severity,params,channels) VALUES(%s,%s,%s,%s,%s)
                ON CONFLICT(rule_id) DO NOTHING""",
                (key, name, severity, Jsonb(params), ["slack-data-eng"]),
            )
        for channel, kind, env in [
            ("slack-data-eng", "slack", "SLACK_WEBHOOK_URL"),
            ("teams-operations", "teams", "TEAMS_WEBHOOK_URL"),
            ("email-oncall", "email", "SMTP_URL"),
        ]:
            conn.execute(
                "INSERT INTO obs.notification_channels(channel_id,kind,target_env) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                (channel, kind, env),
            )
        if conn.execute("SELECT count(*) AS n FROM obs.pipeline_runs").fetchone()["n"]:
            from obs.quality.demo import seed_quality

            seed_quality(conn)
            print(
                "Demo history already present; seed is idempotent. Use make reset for a fresh history."
            )
            return
        for tenant, name, size in TENANTS:
            mapping = {
                f"{s}_{load_kind}": f"demo-{tenant}-{s}-{load_kind}"
                for s in ("mysql", "mongo")
                for load_kind in ("initial", "cdc")
            }
            conn.execute(
                """INSERT INTO obs.tenants(tenant_id,display_name,status,airbyte_connections,warehouse_schema,owner_email,created_at)
                VALUES(%s,%s,'active',%s,%s,%s,%s) ON CONFLICT(tenant_id) DO NOTHING""",
                (
                    tenant,
                    name,
                    Jsonb(mapping),
                    tenant,
                    f"data@{tenant}.example",
                    now - timedelta(days=45),
                ),
            )
            for hour in range(168, 0, -1):
                at = anchor - timedelta(hours=hour) + timedelta(seconds=rng.randint(0, 60))
                for source in ("mysql", "mongo"):
                    for load in ("initial", "cdc"):
                        duration = max(
                            45,
                            int(
                                rng.lognormvariate(0, 0.35)
                                * size
                                * 60
                                * (4 if load == "initial" else 1)
                            ),
                        )
                        duration = min(duration, int((now - at).total_seconds()) - 180)
                        fail = rng.random() < 0.033 and at < now - timedelta(hours=24)
                        error = rng.choice(list(MESSAGES))
                        if tenant == "cedar_foods" and at.hour < 5 and rng.random() < 0.48:
                            fail, error = True, "SOURCE_UNREACHABLE"
                        if (
                            tenant == "acme_retail"
                            and source == "mysql"
                            and load == "cdc"
                            and at >= outage
                        ):
                            fail, error = True, "MYSQL_BINLOG_PURGED"
                        if (
                            tenant == "bluefin_health"
                            and source == "mongo"
                            and at > now - timedelta(minutes=125)
                        ):
                            # A recovery 100 min ago keeps this tenant degraded, as defined in §7.
                            continue
                        job_id = int(
                            hashlib.sha1(f"{tenant}{source}{load}{hour}".encode()).hexdigest()[:10],
                            16,
                        )
                        run = make_run(
                            tenant,
                            source,
                            load,
                            at,
                            duration,
                            job_id,
                            "failed" if fail else "success",
                        )
                        delay = rng.randint(4, 48) + (
                            rng.randint(90, 240) if 18 <= at.hour <= 21 else 0
                        )
                        run.update(
                            queue_delay_s=delay,
                            queued_at=at - timedelta(seconds=delay),
                            airbyte_attempts=3 if fail else 1,
                        )
                        if fail and error == "AIRFLOW_INFRA":
                            run["failed_stage"] = "airflow"
                        upsert_run(conn, run)
                        if fail:
                            enrich_failure(
                                conn,
                                run,
                                MESSAGES[error],
                                "destination" if error == "DESTINATION_ERROR" else "source",
                                streams=tables_for(tenant),
                            )
                        else:
                            with conn.cursor() as cur:
                                cur.executemany(
                                    "INSERT INTO obs.run_stream_stats(run_key,stream_name,records,bytes) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                                    [
                                        (
                                            run["run_key"],
                                            stream,
                                            int(run["rows_synced"] * share),
                                            int(run["bytes_synced"] * share),
                                        )
                                        for stream, share in stream_shares(tenant)
                                    ],
                                )
            for table_index, (table, weight, _extra) in enumerate(TENANT_TABLES[tenant]):
                base = int((table_index + 1) * weight * size * 24000)
                columns = columns_for(tenant, table)
                for i in range(672, -1, -1):
                    checked = now - timedelta(minutes=i * 15)
                    count = base + int(max(0, 672 - i) * size * 19 * weight)
                    if (
                        tenant == "orbit_logistics"
                        and table == "orders"
                        and checked >= now - timedelta(days=1)
                    ):
                        count = int(count * 0.6)
                    loaded = now - timedelta(
                        minutes=205
                        if tenant == "acme_retail"
                        else 100
                        if tenant == "bluefin_health"
                        else 12 + table_index
                    )
                    conn.execute(
                        "INSERT INTO obs.warehouse_snapshots VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (tenant, table, count, min(loaded, checked), checked),
                    )
                    snapshot = columns + (
                        [{"name": "delivery_region", "type": "text"}]
                        if tenant == "orbit_logistics"
                        and table == "orders"
                        and checked >= now - timedelta(days=1)
                        else []
                    )
                    digest = hashlib.sha256(
                        json.dumps(snapshot, sort_keys=True).encode()
                    ).hexdigest()
                    conn.execute(
                        "INSERT INTO obs.schema_snapshots VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (tenant, table, Jsonb(snapshot), digest, checked),
                    )
        for load in ("initial", "cdc"):
            run = make_run(
                "bluefin_health",
                "mongo",
                load,
                now - timedelta(minutes=112),
                180,
                88001 + (load == "cdc"),
                "failed",
            )
            run["airbyte_attempts"] = 3
            upsert_run(conn, run)
            enrich_failure(
                conn,
                run,
                MESSAGES["SOURCE_UNREACHABLE"],
                streams=tables_for("bluefin_health"),
            )
            recovery = make_run(
                "bluefin_health",
                "mongo",
                load,
                now - timedelta(minutes=104),
                240,
                88011 + (load == "cdc"),
            )
            upsert_run(conn, recovery)
        stuck = make_run(
            "northwind", "mysql", "cdc", now - timedelta(minutes=58), 0, 99001, "running"
        )
        upsert_run(conn, stuck)
        for tenant, _, _ in TENANTS[3:]:
            if tenant == "cedar_foods":
                continue
            # Selected latest runs are visibly in progress without compromising source freshness.
            if tenant in {"orbit_logistics", "helix_energy", "summit_media"}:
                upsert_run(
                    conn,
                    make_run(
                        tenant,
                        "mongo",
                        "cdc",
                        now - timedelta(minutes=2),
                        0,
                        99002 + len(tenant),
                        "running",
                    ),
                )
        components = [
            "airflow_scheduler",
            "airflow_metadb",
            "airflow_pools",
            "airflow_import_errors",
            "airbyte",
            "warehouse",
            "collector",
            "alerter",
        ]
        for i in range(48 * 60, -1, -1):
            checked = now - timedelta(minutes=i)
            for comp in components:
                was_broken = comp == "airflow_import_errors" and now - timedelta(
                    hours=30
                ) <= checked < now - timedelta(hours=27)
                details = {
                    "message": "onboard_tenant.py: ModuleNotFoundError (fixed yesterday)"
                    if was_broken
                    else "All checks passing"
                }
                if comp == "airflow_pools":
                    details = {"pool": "default_pool", "occupied": 12, "queued": 2, "slots": 32}
                conn.execute(
                    "INSERT INTO obs.platform_health VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (comp, "degraded" if was_broken else "up", Jsonb(details), checked),
                )
        for comp in ("airflow", "airbyte", "warehouse", "demo_ticker"):
            conn.execute(
                "INSERT INTO obs.collector_state(component,watermark,last_success_at,last_poll_ms) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (comp, now, now, rng.randint(40, 185)),
            )
        notify(
            conn,
            "run.updated",
            {
                "tenant_id": "acme_retail",
                "status": "failed",
                "source_type": "mysql",
                "load_type": "cdc",
            },
        )
        from obs.quality.demo import seed_quality

        seed_quality(conn)
    from obs.alerter.rules import evaluate

    evaluate()
    print("Seeded 10 tenants, ~6,700 runs, 7 days of warehouse history and scripted scenarios.")


if __name__ == "__main__":
    seed()

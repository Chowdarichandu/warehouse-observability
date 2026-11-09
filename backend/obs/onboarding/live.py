import ipaddress
import socket
from urllib.parse import urlsplit

from obs.api.schemas import OnboardInput
from obs.integrations import aws, warehouse
from obs.settings import require_live, settings


def allowed_host(host: str) -> None:
    networks = [ipaddress.ip_network(c) for c in settings().source_allowed_cidrs]
    addresses = {r[4][0] for r in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
    if (
        not networks
        or not addresses
        or any(not any(ipaddress.ip_address(a) in n for n in networks) for a in addresses)
    ):
        raise ValueError("Source host is outside SOURCE_ALLOWED_CIDRS")


def mysql_check(data: OnboardInput) -> dict:
    import pymysql

    allowed_host(data.mysql_host)
    credentials = aws.secret(data.mysql_secret_ref)
    with pymysql.connect(
        host=data.mysql_host,
        port=data.mysql_port,
        user=data.mysql_user,
        password=credentials["password"],
        database=data.mysql_database,
        connect_timeout=5,
        read_timeout=10,
        ssl_ca=settings().source_ca_file or None,
        ssl_verify_cert=True,
        ssl_verify_identity=True,
        cursorclass=pymysql.cursors.DictCursor,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SHOW VARIABLES WHERE Variable_name IN ('binlog_format','binlog_row_image','binlog_expire_logs_seconds','expire_logs_days','log_bin')"
            )
            variables = {r["Variable_name"]: r["Value"] for r in cursor.fetchall()}
            cursor.execute("SHOW GRANTS FOR CURRENT_USER()")
            grants = " ".join(str(v) for row in cursor.fetchall() for v in row.values()).upper()
            cursor.execute("SELECT 1")
    retention = int(
        variables.get("binlog_expire_logs_seconds")
        or int(variables.get("expire_logs_days", "0")) * 86400
    )
    checks = [
        variables.get("log_bin") == "ON",
        variables.get("binlog_format") == "ROW",
        variables.get("binlog_row_image") == "FULL",
        retention >= settings().mysql_binlog_retention_sec,
        all(p in grants for p in ("REPLICATION SLAVE", "REPLICATION CLIENT", "SELECT"))
        or "ALL PRIVILEGES ON *.*" in grants,
    ]
    return {
        "name": "MySQL CDC readiness",
        "passed": all(checks),
        "message": "TLS connection, ROW/FULL binlog, retention and replication privileges verified."
        if all(checks)
        else "Enable binlog ROW/FULL, sufficient retention, SELECT and replication privileges.",
    }


def mongo_check(data: OnboardInput) -> dict:
    from pymongo import MongoClient

    credentials = aws.secret(data.mongo_secret_ref)
    uri = credentials["uri"]
    parsed = urlsplit(uri)
    if not parsed.hostname:
        raise ValueError("Mongo secret requires a valid uri")
    allowed_host(parsed.hostname)
    kwargs = {
        "tls": True,
        "serverSelectionTimeoutMS": 5000,
        "connectTimeoutMS": 5000,
        "socketTimeoutMS": 5000,
    }
    if settings().source_ca_file:
        kwargs["tlsCAFile"] = settings().source_ca_file
    with MongoClient(uri, **kwargs) as client:
        hello = client.admin.command("hello")
        topology = bool(hello.get("setName") or hello.get("msg") == "isdbgrid")
        db = client[data.mongo_database]
        db.list_collection_names()
        with db.watch(max_await_time_ms=1000) as stream:
            stream.try_next()
    return {
        "name": "MongoDB CDC readiness",
        "passed": topology,
        "message": "TLS, replica topology, database read and changeStream access verified."
        if topology
        else "A replica set or sharded cluster is required.",
    }


def preflight(data: OnboardInput) -> dict:
    require_live()
    checks = []
    for enabled, name, fn in [
        (data.has_mysql, "MySQL CDC readiness", mysql_check),
        (data.has_mongo, "MongoDB CDC readiness", mongo_check),
    ]:
        if enabled:
            try:
                checks.append(fn(data))
            except Exception:
                checks.append(
                    {
                        "name": name,
                        "passed": False,
                        "message": "Connection or permissions check failed. Check the secret reference, source allowlist, TLS and source privileges.",
                    }
                )
    try:
        with warehouse.connect() as conn:
            result = conn.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name=%s",
                (data.warehouse_schema or data.tenant_id,),
            ).fetchone()
        checks.append(
            {
                "name": "Warehouse namespace",
                "passed": bool(result),
                "message": "Destination schema exists and is visible."
                if result
                else "Create the destination schema and grant the ingestion and catalog roles access before onboarding.",
            }
        )
    except Exception:
        checks.append(
            {
                "name": "Warehouse namespace",
                "passed": False,
                "message": "Warehouse TLS connectivity or catalog access failed.",
            }
        )
    return {"passed": all(c["passed"] for c in checks), "checks": checks, "simulated": False}

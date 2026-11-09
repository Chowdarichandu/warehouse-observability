from obs.api.schemas import OnboardInput
from obs.settings import require_demo, settings


def preflight(data: OnboardInput) -> dict:
    if settings().mode == "live":
        from obs.onboarding.live import preflight as live_preflight

        return live_preflight(data)
    require_demo()
    checks = []
    if data.has_mysql:
        checks.extend(
            [
                {
                    "name": "MySQL connectivity",
                    "passed": True,
                    "message": "Demo source reachable using its secret reference.",
                },
                {
                    "name": "Binlog configuration",
                    "passed": True,
                    "message": "ROW format, FULL row image; retention 7 days.",
                },
                {
                    "name": "Replication permissions",
                    "passed": True,
                    "message": "SELECT, REPLICATION SLAVE and REPLICATION CLIENT granted.",
                },
            ]
        )
    if data.has_mongo:
        checks.extend(
            [
                {
                    "name": "MongoDB topology",
                    "passed": True,
                    "message": "Replica set available; change streams supported.",
                },
                {
                    "name": "MongoDB permissions",
                    "passed": True,
                    "message": "Read and changeStream privileges granted.",
                },
            ]
        )
    checks.append(
        {
            "name": "Warehouse namespace",
            "passed": True,
            "message": f"Schema {data.warehouse_schema or data.tenant_id} is available.",
        }
    )
    return {"passed": True, "checks": checks, "simulated": True}

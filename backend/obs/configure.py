"""Apply reviewed tenant/channel/rule configuration: python -m obs.configure config/live.yaml."""

import argparse
from pathlib import Path

import yaml
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from obs.alerter.rules import PARAMS
from obs.api.schemas import RulePatch
from obs.audit import audit
from obs.db import connection


class Tenant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,47}$")
    display_name: str
    status: str = Field(default="active", pattern="^(active|paused)$")
    has_mysql: bool = True
    has_mongo: bool = True
    warehouse_schema: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    freshness_sla_min: int = Field(default=120, ge=5, le=10080)
    airbyte_connections: dict[str, str]

    @model_validator(mode="after")
    def pipelines(self) -> "Tenant":
        expected = {
            f"{source}_{load}"
            for source in ("mysql", "mongo")
            if getattr(self, f"has_{source}")
            for load in ("initial", "cdc")
        }
        if set(self.airbyte_connections) != expected:
            raise ValueError(
                "Provide exactly the initial and CDC connection IDs for each enabled source"
            )
        return self


class Channel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel_id: str = Field(pattern=r"^[a-z0-9_-]+$")
    kind: str = Field(pattern="^(slack|teams|email|ses|sns)$")
    target_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$")
    enabled: bool = True


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenants: list[Tenant] = []
    channels: list[Channel] = []
    rules: dict[str, RulePatch] = {}

    @model_validator(mode="after")
    def unique_connections(self) -> "Configuration":
        ids = [c for tenant in self.tenants for c in tenant.airbyte_connections.values()]
        if len(ids) != len(set(ids)) or len({t.tenant_id for t in self.tenants}) != len(
            self.tenants
        ):
            raise ValueError("Tenant and connection IDs must be unique")
        for key, rule in self.rules.items():
            if (
                key not in PARAMS
                or set(rule.params) != PARAMS[key]
                or any(v <= 0 or v > 10080 for v in rule.params.values())
            ):
                raise ValueError("Use the built-in alert rule parameter schema")
        return self


def apply(config: Configuration, actor: str = "deployment") -> None:
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(110542)")
        incoming = {t.tenant_id for t in config.tenants}
        existing = conn.execute("SELECT tenant_id,airbyte_connections FROM obs.tenants").fetchall()
        reserved = {
            c
            for t in existing
            if t["tenant_id"] not in incoming
            for c in t["airbyte_connections"].values()
        }
        if any(c in reserved for t in config.tenants for c in t.airbyte_connections.values()):
            raise ValueError("Connection already assigned to another tenant")
        for tenant in config.tenants:
            conn.execute(
                """INSERT INTO obs.tenants(tenant_id,display_name,status,has_mysql,has_mongo,warehouse_schema,freshness_sla_min,airbyte_connections)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(tenant_id) DO UPDATE SET display_name=excluded.display_name,status=excluded.status,
                has_mysql=excluded.has_mysql,has_mongo=excluded.has_mongo,warehouse_schema=excluded.warehouse_schema,
                freshness_sla_min=excluded.freshness_sla_min,airbyte_connections=excluded.airbyte_connections,updated_at=now()""",
                (
                    tenant.tenant_id,
                    tenant.display_name,
                    tenant.status,
                    tenant.has_mysql,
                    tenant.has_mongo,
                    tenant.warehouse_schema,
                    tenant.freshness_sla_min,
                    Jsonb(tenant.airbyte_connections),
                ),
            )
        for channel in config.channels:
            conn.execute(
                """INSERT INTO obs.notification_channels(channel_id,kind,target_env,enabled) VALUES(%s,%s,%s,%s)
                ON CONFLICT(channel_id) DO UPDATE SET kind=excluded.kind,target_env=excluded.target_env,enabled=excluded.enabled""",
                (channel.channel_id, channel.kind, channel.target_env, channel.enabled),
            )
        for key, rule in config.rules.items():
            for channel in rule.channels:
                if not conn.execute(
                    "SELECT 1 FROM obs.notification_channels WHERE channel_id=%s", (channel,)
                ).fetchone():
                    raise ValueError("Rule references an unknown channel")
            result = conn.execute(
                "UPDATE obs.alert_rules SET severity=%s,params=%s,enabled=%s,repeat_min=%s,channels=%s WHERE rule_id=%s",
                (
                    rule.severity,
                    Jsonb(rule.params),
                    rule.enabled,
                    rule.repeat_min,
                    rule.channels,
                    key,
                ),
            )
            if not result.rowcount:
                raise ValueError("Initialize the API before applying alert configuration")
        audit(
            conn,
            actor,
            "apply_configuration",
            details={
                "tenants": len(config.tenants),
                "channels": len(config.channels),
                "rules": len(config.rules),
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    config = Configuration.model_validate(yaml.safe_load(args.path.read_text()))
    if not args.check:
        apply(config)
    print("Configuration valid" if args.check else "Configuration applied")


if __name__ == "__main__":
    main()

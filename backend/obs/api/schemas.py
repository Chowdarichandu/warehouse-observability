from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    page_size: int = 25


class User(BaseModel):
    user_id: int
    email: str
    display_name: str
    role: Literal["viewer", "operator", "admin"]
    role_name: str | None = None
    permissions: list[str] = []
    active_sessions: int = 0
    csrf_token: str = ""


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class ChangePassword(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class Message(BaseModel):
    message: str
    simulated: bool = True


class ErrorInfo(BaseModel):
    run_key: str
    tenant_id: str
    stage: str
    failure_origin: str | None = None
    error_class: str
    severity: str
    fingerprint: str | None = None
    error_message: str | None = None
    hint: str | None = None
    created_at: datetime


class Run(BaseModel):
    run_key: str
    tenant_id: str
    source_type: Literal["mysql", "mongo"]
    load_type: Literal["initial", "cdc"]
    status: Literal["queued", "running", "success", "failed", "cancelled", "skipped"]
    failed_stage: str | None = None
    triggered_by: str
    scheduled_for: datetime | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_s: int | None = None
    queue_delay_s: int | None = None
    rows_synced: int | None = None
    bytes_synced: int | None = None
    dag_id: str | None = None
    dag_run_id: str | None = None
    task_id: str | None = None
    map_index: int | None = None
    try_number: int | None = None
    airbyte_connection_id: str | None = None
    airbyte_job_id: int | None = None
    airbyte_attempts: int | None = None
    collected_at: datetime
    error_class: str | None = None


class StreamStat(BaseModel):
    stream_name: str
    records: int | None = None
    bytes: int | None = None


class RunDetail(BaseModel):
    run: Run
    error: ErrorInfo | None = None
    streams: list[StreamStat]
    previous_runs: list[Run]
    usual_duration_s: float | None = None


class Log(BaseModel):
    content: str
    source: str
    redacted: bool = True


class Tenant(BaseModel):
    tenant_id: str
    display_name: str
    tenant_status: str
    health: str
    freshness_sla_min: int
    failures_24h: int
    worst_stale_min: float | None = None
    sla_compliance: float | None = None
    avg_duration_min: float | None = None
    last_success_at: datetime | None = None
    analytics_eligible: bool = False
    latest_runs: list[Run] = []


class TenantConfig(BaseModel):
    tenant_id: str
    display_name: str
    status: str
    has_mysql: bool
    has_mongo: bool
    airbyte_connections: dict[str, str]
    warehouse_schema: str | None = None
    freshness_sla_min: int
    owner_email: str | None = None
    created_at: datetime
    updated_at: datetime


class Freshness(BaseModel):
    tenant_id: str
    display_name: str
    source_type: str
    freshness_sla_min: int
    last_success_at: datetime | None = None
    minutes_stale: float | None = None
    sla_7d: float | None = None
    sla_30d: float | None = None


class WarehouseTable(BaseModel):
    tenant_id: str
    table_name: str
    row_count: int | None = None
    last_loaded_at: datetime | None = None
    checked_at: datetime


class Change(BaseModel):
    tenant_id: str
    table_name: str
    checked_at: datetime
    change_pct: float | None = None
    row_count: int | None = None
    previous_count: int | None = None
    added: list[str] = []
    removed: list[str] = []
    type_changed: list[str] = []


class Alert(BaseModel):
    id: int
    rule_id: str
    fingerprint: str
    tenant_id: str | None = None
    severity: str
    state: str
    title: str
    details: dict[str, str | float | int | None] = {}
    first_fired_at: datetime
    last_seen_at: datetime
    last_notified_at: datetime | None = None
    acked_by: str | None = None
    acked_at: datetime | None = None
    resolved_at: datetime | None = None


class TenantEvent(BaseModel):
    id: int
    tenant_id: str
    step: str
    status: str
    message: str | None = None
    at: datetime


class Baseline(BaseModel):
    source_type: str
    load_type: str
    median_s: float


class Breakdown(BaseModel):
    name: str
    count: int


class PipelineMetric(BaseModel):
    source_type: str
    load_type: str
    runs: int
    avg_s: float | None = None
    p95_s: float | None = None
    queue_avg_s: float | None = None
    queue_p95_s: float | None = None


class PipelineHour(BaseModel):
    bucket: datetime
    source_type: str
    load_type: str
    avg_s: float | None = None


class ActivityBucket(BaseModel):
    bucket: datetime
    success: int
    failed: int
    running: int


class TenantMetrics(BaseModel):
    pipelines: list[PipelineMetric] = []
    hourly: list[PipelineHour] = []
    activity: list[ActivityBucket] = []


class TenantDetail(BaseModel):
    config: TenantConfig
    health: Tenant
    tables: list[WarehouseTable]
    alerts: list[Alert]
    events: list[TenantEvent]
    errors: list[ErrorInfo]
    schema_changes: list[Change]
    baselines: list[Baseline]


class Component(BaseModel):
    component: str
    status: str
    details: dict[str, str | int | float | None] = {}
    checked_at: datetime


class CollectorState(BaseModel):
    component: str
    watermark: datetime | None = None
    last_success_at: datetime | None = None
    last_poll_ms: int | None = None
    last_error: str | None = None
    updated_at: datetime


class Platform(BaseModel):
    components: list[Component]
    history: list[Component]
    collectors: list[CollectorState]
    database_bytes: int


class DurationMetric(BaseModel):
    name: str
    avg_min: float | None = None
    p50_min: float | None = None
    p95_min: float | None = None
    queue_avg_min: float | None = None
    queue_p95_min: float | None = None
    count: int


class HourMetric(BaseModel):
    hour: datetime
    success: int
    failed: int
    running: int
    mysql_cdc: float | None = None
    mongo_cdc: float | None = None
    mysql_initial: float | None = None
    mongo_initial: float | None = None


class Kpis(BaseModel):
    healthy: int
    degraded: int
    down: int
    success_rate: float | None = None
    failed_runs: int
    cdc_avg_min: float | None = None
    cdc_p95_min: float | None = None
    sla_compliance: float | None = None
    running_now: int
    open_alerts: int
    total_runs: int


class Overview(BaseModel):
    kpis: Kpis
    platform: list[Component]
    series: list[HourMetric]
    durations: list[DurationMetric]
    recent_failures: list[Run]
    as_of: datetime


class ErrorGroup(BaseModel):
    fingerprint: str
    error_class: str
    sample_message: str | None = None
    occurrences: int
    tenants: list[str]
    first_seen: datetime
    last_seen: datetime
    trend: list[int] = []


class ErrorGroupDetail(BaseModel):
    group: ErrorGroup
    runs: Page[Run]


class Mttr(BaseModel):
    tenant_id: str
    avg_min: float | None = None
    recovered: int
    unresolved: int


class HeatCell(BaseModel):
    weekday: int
    hour: int
    failures: int


class TenantPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "paused"] | None = None
    freshness_sla_min: int | None = Field(default=None, ge=5, le=10080)
    owner_email: str | None = Field(default=None, max_length=254)


class RetryResult(BaseModel):
    run_key: str
    message: str
    simulated: bool = True


class Rule(BaseModel):
    rule_id: str
    name: str
    severity: Literal["critical", "high", "medium", "low"]
    params: dict[str, float] = {}
    enabled: bool
    repeat_min: int
    channels: list[str]


class RulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity: Literal["critical", "high", "medium", "low"]
    params: dict[str, float]
    enabled: bool
    repeat_min: int = Field(ge=1, le=10080)
    channels: list[str]


class Channel(BaseModel):
    channel_id: str
    kind: str
    target_env: str
    enabled: bool


class OnboardInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,47}$")
    display_name: str = Field(min_length=2, max_length=100)
    has_mysql: bool = True
    has_mongo: bool = True
    mysql_host: str = Field(default="mysql.demo.internal", max_length=254)
    mysql_port: int = Field(default=3306, ge=1, le=65535)
    mysql_database: str = Field(default="app", max_length=100)
    mysql_user: str = Field(default="replication_reader", max_length=100)
    mysql_secret_ref: str = Field(
        default="demo://zenith/mysql", pattern=r"^(vault|aws|secret|demo)://[^\s@]+$"
    )
    mongo_database: str = Field(default="app", max_length=100)
    mongo_secret_ref: str = Field(
        default="demo://zenith/mongo", pattern=r"^(vault|aws|secret|demo)://[^\s@]+$"
    )
    warehouse_schema: str = Field(default="", pattern=r"^[a-z0-9_]*$", max_length=63)
    freshness_sla_min: int = Field(default=120, ge=5, le=10080)
    owner_email: str = Field(default="owner@zenith.example", max_length=254)
    run_initial: bool = True

    @model_validator(mode="after")
    def sources_required(self) -> "OnboardInput":
        if not (self.has_mysql or self.has_mongo):
            raise ValueError("Choose at least one source.")
        return self


class PreflightCheck(BaseModel):
    name: str
    passed: bool
    message: str


class Preflight(BaseModel):
    passed: bool
    checks: list[PreflightCheck]
    simulated: bool = True


OnboardState = Literal[
    "pending",
    "queued",
    "running",
    "success",
    "failed",
    "blocked",
    "skipped",
    "uncertain",
    "awaiting_initial",
]


class OnboardTask(BaseModel):
    task_id: str
    label: str
    status: OnboardState
    started_at: datetime | None = None
    ended_at: datetime | None = None
    last_error: str | None = None


class OnboardDag(BaseModel):
    node_id: str
    label: str
    source_type: Literal["mysql", "mongo"] | None = None
    phase: Literal["coordinator", "provision", "initial", "cdc"]
    dag_id: str
    dag_run_id: str | None = None
    parent_node_id: str | None = None
    parent_dag_run_id: str | None = None
    status: OnboardState
    attempt: int
    started_at: datetime | None = None
    ended_at: datetime | None = None
    blocked_reason: str | None = None
    last_error: str | None = None
    run_key: str | None = None
    tasks: list[OnboardTask] = []


class OnboardResume(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_initial: bool = True


class OnboardProgress(BaseModel):
    tenant_id: str
    status: str
    events: list[TenantEvent]
    workflow_id: str | None = None
    display_name: str = ""
    workflow_status: Literal["running", "failed", "uncertain", "awaiting_initial", "success"] = (
        "running"
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None
    simulated: bool = True
    can_resume: bool = False
    resume_reason: str | None = None
    dags: list[OnboardDag] = []


class AuditEntry(BaseModel):
    id: int
    actor: str
    action: str
    target: str | None = None
    details: dict[str, object] = {}
    at: datetime


class SearchHit(BaseModel):
    run_key: str
    tenant_id: str
    error_class: str | None = None
    excerpt: str
    started_at: datetime | None = None


class UserPatch(BaseModel):
    role: Literal["viewer", "operator", "admin"] | None = None
    role_name: str | None = None


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    display_name: str = Field(min_length=1, max_length=120)
    role: Literal["viewer", "operator", "admin"] = "viewer"
    role_name: str | None = None
    initial_password: str | None = Field(default=None, min_length=8, max_length=200)


class UserCreateResult(BaseModel):
    message: str
    user_id: int
    temporary_password: str | None = None
    simulated: bool = True


class RoleIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    base_level: Literal["viewer", "operator", "admin"]
    permissions: list[str] = []
    description: str | None = None


class RoleOut(BaseModel):
    name: str
    base_level: str
    permissions: list[str] = []
    description: str | None = None
    system: bool = False
    created_by: str | None = None


class TriggerIn(BaseModel):
    dag: str = Field(max_length=80)


class PasswordResetResult(BaseModel):
    message: str
    temporary_password: str
    simulated: bool = True


class UserPermissionsIn(BaseModel):
    grants: list[str] = []
    revokes: list[str] = []


class PermissionMeta(BaseModel):
    name: str
    min_role: str


class UserPermissionsOut(BaseModel):
    user_id: int
    email: str
    role: str
    role_name: str | None = None
    bundle: list[str] = []
    grants: list[str] = []
    revokes: list[str] = []
    effective: list[str] = []
    permissions: list[PermissionMeta] = []


class ForgotPasswordIn(BaseModel):
    email: str = Field(max_length=254)


class ForgotPasswordResult(BaseModel):
    message: str
    temporary_password: str | None = None


class WorkflowSource(BaseModel):
    source: str
    initial_status: str
    cdc_status: str
    last_initial_at: str | None = None
    last_cdc_at: str | None = None


class AnalyticsDag(BaseModel):
    id: str
    name: str
    last_status: str | None = None
    last_at: str | None = None


class WorkflowState(BaseModel):
    tenant_id: str
    sources: list[WorkflowSource]
    analytics_eligible: bool
    analytics: list[AnalyticsDag]


class WarehouseColumn(BaseModel):
    name: str
    type: str


class WarehouseTable(BaseModel):
    table_name: str
    row_count: int | None = None
    last_loaded_at: str | None = None
    columns: list[WarehouseColumn] = []


class WarehouseView(BaseModel):
    tenant_id: str
    tables: list[WarehouseTable]
    table_count: int
    total_rows: int


class RuntimeConfig(BaseModel):
    mode: Literal["demo", "live"]
    environment: str
    auth_provider: Literal["local", "oidc"]
    live_actions_enabled: bool


class OperationResolution(BaseModel):
    status: Literal["succeeded", "failed"]
    note: str = Field(min_length=10, max_length=1000)


class Operation(BaseModel):
    id: str
    kind: str
    target: str
    actor: str
    status: str
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class Delivery(BaseModel):
    id: int
    channel_id: str
    kind: str
    status: str
    attempts: int
    last_error: str | None = None
    at: datetime
    delivered_at: datetime | None = None

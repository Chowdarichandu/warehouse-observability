import psycopg

from obs.redact import redact
from obs.settings import require_demo, settings


def deliver(
    conn: psycopg.Connection, channel_id: str, kind: str, title: str, alert_id: int | None = None
) -> None:
    """M4 notifications are durable local deliveries. Never call Slack/SMTP in demo."""
    require_demo()
    channel = conn.execute(
        "SELECT * FROM obs.notification_channels WHERE channel_id=%s AND enabled", (channel_id,)
    ).fetchone()
    if not channel:
        return
    message = title
    if alert_id is not None:
        alert = conn.execute("SELECT * FROM obs.alerts WHERE id=%s", (alert_id,)).fetchone()
        if alert:
            details = alert["details"] or {}
            target = f"/tenants/{alert['tenant_id']}" if alert["tenant_id"] else "/platform"
            message += f"\nTenant: {alert['tenant_id'] or 'platform'}\nSeverity: {alert['severity']}\nState: {kind}"
            message += f"\nReason: {details.get('reason', alert['rule_id'])}\nFix hint: {details.get('hint', 'Inspect the console for diagnostics.')}"
            message += f"\n{settings().console_url.rstrip('/')}{target}"
    else:
        message += f"\n{settings().console_url.rstrip('/')}/alerts"
    conn.execute(
        """INSERT INTO obs.notification_deliveries(channel_id,alert_id,kind,status,message)
       VALUES(%s,%s,%s,'simulated',%s)""",
        (channel_id, alert_id, kind, redact(message)),
    )

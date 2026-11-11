import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import unquote, urlsplit

import httpx
import psycopg
from psycopg.types.json import Jsonb

from obs.db import connection
from obs.integrations import aws
from obs.redact import redact
from obs.settings import require_live, settings


def deliver(
    conn: psycopg.Connection, channel_id: str, kind: str, title: str, alert_id: int | None = None
) -> None:
    """Queue delivery in the alert transaction; the network worker runs after commit."""
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
    thread_key = f"{channel_id}:{alert_id or 'workspace'}:{kind}"
    delivery = conn.execute(
        """INSERT INTO obs.notification_deliveries(channel_id,alert_id,kind,status,message)
        VALUES(%s,%s,%s,%s,%s) RETURNING id""",
        (
            channel_id,
            alert_id,
            kind,
            "simulated" if settings().mode == "demo" else "pending",
            redact(message),
        ),
    ).fetchone()
    if settings().mode != "demo":
        queued = conn.execute(
            """INSERT INTO obs.notification_outbox(channel_id,payload,thread_key)
            VALUES(%s,%s,%s)
            ON CONFLICT (thread_key)
            WHERE thread_key IS NOT NULL AND state IN ('pending','sending') DO NOTHING
            RETURNING id""",
            (
                channel_id,
                Jsonb(
                    {
                        "message": redact(message),
                        "kind": kind,
                        "alert_id": alert_id,
                        "legacy_delivery_id": delivery["id"],
                    }
                ),
                thread_key,
            ),
        ).fetchone()
        if not queued:
            # The outbox row owns dispatch while a notification is in flight.
            # Remove the duplicate compatibility row so legacy draining cannot
            # send the same notification a second time.
            conn.execute("DELETE FROM obs.notification_deliveries WHERE id=%s", (delivery["id"],))


def send(item: dict) -> None:
    require_live()
    kind, message = item["channel_kind"], item["message"]
    if kind in {"slack", "teams"}:
        target = aws.environment_secret(item["target_env"])
        parsed = urlsplit(target)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in settings().notification_allowed_hosts
            or parsed.username
        ):
            raise ValueError(
                "Webhook must use HTTPS and a configured NOTIFICATION_ALLOWED_HOSTS host"
            )
        payload = (
            {"text": message}
            if kind == "slack"
            else {
                "type": "message",
                "attachments": [
                    {
                        "contentType": "application/vnd.microsoft.card.adaptive",
                        "contentUrl": None,
                        "content": {
                            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                            "type": "AdaptiveCard",
                            "version": "1.2",
                            "body": [{"type": "TextBlock", "text": message, "wrap": True}],
                        },
                    }
                ],
            }
        )
        with httpx.Client(timeout=settings().http_timeout_sec, follow_redirects=False) as client:
            response = client.post(target, json=payload)
            if not response.is_success:
                raise RuntimeError(f"Notification provider returned HTTP {response.status_code}")
    elif kind == "sns":
        topic = aws.environment_secret(item["target_env"])
        if not topic.startswith(f"arn:aws:sns:{settings().aws_region}:"):
            raise ValueError("SNS topic must be in the configured AWS region")
        aws.client("sns", write=True).publish(
            TopicArn=topic, Subject=message.splitlines()[0][:100], Message=message
        )
    elif kind in {"ses", "email"}:
        config = settings()
        if not config.ses_from_address or not config.ses_to_addresses:
            raise ValueError("Configure SES_FROM_ADDRESS and SES_TO_ADDRESSES")
        if kind == "ses":
            aws.client("sesv2", write=True).send_email(
                FromEmailAddress=config.ses_from_address,
                Destination={"ToAddresses": config.ses_to_addresses},
                Content={
                    "Simple": {
                        "Subject": {"Data": message.splitlines()[0][:200]},
                        "Body": {"Text": {"Data": message}},
                    }
                },
            )
        else:
            target = urlsplit(aws.environment_secret(item["target_env"]))
            if target.scheme != "smtps" or target.hostname not in config.notification_allowed_hosts:
                raise ValueError("SMTP requires smtps:// and an allowlisted host")
            email = EmailMessage()
            email["Subject"] = message.splitlines()[0][:200]
            email["From"] = config.ses_from_address
            email["To"] = ", ".join(config.ses_to_addresses)
            email["X-Observability-Delivery"] = str(item["id"])
            email.set_content(message)
            with smtplib.SMTP_SSL(
                target.hostname,
                target.port or 465,
                timeout=config.http_timeout_sec,
                context=ssl.create_default_context(),
            ) as smtp:
                if target.username:
                    smtp.login(unquote(target.username), unquote(target.password or ""))
                smtp.send_message(email)
    else:
        raise ValueError("Unknown notification provider")


def dispatch(limit: int = 20) -> None:
    if settings().mode == "demo":
        return
    for _ in range(limit):
        with connection() as conn:
            item = conn.execute(
                """SELECT o.*,c.kind AS channel_kind,c.target_env,c.enabled
                FROM obs.notification_outbox o JOIN obs.notification_channels c USING(channel_id)
                WHERE (o.state='pending' AND o.next_attempt_at<=now())
                   OR (o.state='sending' AND o.lease_until<now())
                ORDER BY o.id FOR UPDATE OF o SKIP LOCKED LIMIT 1"""
            ).fetchone()
            queue = "outbox"
            if item:
                payload = item["payload"] or {}
                item = {
                    **dict(item),
                    "message": payload.get("message", ""),
                    "kind": payload.get("kind", "firing"),
                    "alert_id": payload.get("alert_id"),
                    "legacy_delivery_id": payload.get("legacy_delivery_id"),
                }
                conn.execute(
                    "UPDATE obs.notification_outbox SET state='sending',attempts=attempts+1,lease_until=now()+interval '5 minutes' WHERE id=%s",
                    (item["id"],),
                )
            else:
                item = conn.execute(
                    """SELECT d.*,c.kind AS channel_kind,c.target_env,c.enabled FROM obs.notification_deliveries d
                    JOIN obs.notification_channels c USING(channel_id)
                    WHERE (d.status='pending' AND d.next_attempt_at<=now()) OR (d.status='sending' AND d.lease_until<now())
                    ORDER BY d.id FOR UPDATE OF d SKIP LOCKED LIMIT 1"""
                ).fetchone()
                queue = "legacy"
                if not item:
                    return
                conn.execute(
                    "UPDATE obs.notification_deliveries SET status='sending',attempts=attempts+1,lease_until=now()+interval '5 minutes' WHERE id=%s",
                    (item["id"],),
                )
        error = None
        if item["alert_id"] is not None and item["kind"] == "firing":
            with connection() as conn:
                current = conn.execute(
                    "SELECT state FROM obs.alerts WHERE id=%s", (item["alert_id"],)
                ).fetchone()
            item["enabled"] = item["enabled"] and bool(current and current["state"] == "firing")
        try:
            if item["enabled"]:
                send(item)
        except Exception as exc:
            # Webhook URLs and SMTP credentials never appear in persisted exceptions.
            error = (
                type(exc).__name__
                + ": Delivery failed; check provider configuration, permissions, TLS and channel health."
            )
        with connection() as conn:
            attempts = item["attempts"] + 1
            if queue == "outbox":
                state = (
                    "pending"
                    if error and attempts < settings().notification_max_attempts
                    else "dead"
                    if error or not item["enabled"]
                    else "delivered"
                )
                outbox_error = error or (
                    "Channel disabled or alert no longer firing; delivery cancelled."
                    if not item["enabled"]
                    else None
                )
                conn.execute(
                    """UPDATE obs.notification_outbox SET state=%s,last_error=%s,lease_until=NULL,
                    next_attempt_at=now()+%s*interval '1 second',delivered_at=CASE WHEN %s='delivered' THEN now() ELSE NULL END WHERE id=%s""",
                    (state, outbox_error, min(30 * 2**attempts, 3600), state, item["id"]),
                )
                if item.get("legacy_delivery_id"):
                    legacy_status = (
                        "sent"
                        if state == "delivered"
                        else "failed"
                        if state == "dead"
                        else "pending"
                    )
                    conn.execute(
                        """UPDATE obs.notification_deliveries SET status=%s,attempts=%s,last_error=%s,lease_until=NULL,
                        next_attempt_at=now()+%s*interval '1 second',delivered_at=CASE WHEN %s='sent' THEN now() ELSE NULL END WHERE id=%s""",
                        (
                            legacy_status,
                            attempts,
                            outbox_error,
                            min(30 * 2**attempts, 3600),
                            legacy_status,
                            item["legacy_delivery_id"],
                        ),
                    )
            else:
                status = (
                    "pending"
                    if error and attempts < settings().notification_max_attempts
                    else "failed"
                    if error
                    else "sent"
                    if item["enabled"]
                    else "cancelled"
                )
                conn.execute(
                    """UPDATE obs.notification_deliveries SET status=%s,last_error=%s,lease_until=NULL,
                    next_attempt_at=now()+%s*interval '1 second',delivered_at=CASE WHEN %s='sent' THEN now() ELSE NULL END WHERE id=%s""",
                    (status, error, min(30 * 2**attempts, 3600), status, item["id"]),
                )

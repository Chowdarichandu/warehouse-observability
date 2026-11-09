"""Encrypted S3 backups with pg_dump; restore requires an explicit empty database."""

import argparse
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict

from obs.integrations import aws
from obs.settings import require_live, settings


def pg_environment(dsn: str) -> dict[str, str]:
    values = conninfo_to_dict(dsn)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    mapping = {
        "host": "PGHOST",
        "port": "PGPORT",
        "dbname": "PGDATABASE",
        "user": "PGUSER",
        "password": "PGPASSWORD",
        "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT",
        "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY",
    }
    env.update({mapping[k]: v for k, v in values.items() if k in mapping})
    return env


def dump(dsn: str, destination: Path) -> None:
    binary = shutil.which("pg_dump")
    if not binary:
        raise RuntimeError("PostgreSQL 16 pg_dump is required")
    result = subprocess.run(
        [binary, "--format=custom", "--no-owner", "--no-acl", "--file", str(destination)],
        env=pg_environment(dsn),
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(
            "pg_dump failed. Check the backup role, database connectivity, and client/server versions."
        )
    destination.chmod(0o600)
    subprocess.run(
        ["pg_restore", "--list", str(destination)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def restore(dsn: str, source: Path) -> None:
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        if conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') LIMIT 1"
        ).fetchone():
            raise RuntimeError("Restore target must be an empty, isolated database")
    result = subprocess.run(
        [
            "pg_restore",
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-acl",
            "--dbname",
            conninfo_to_dict(dsn)["dbname"],
            str(source),
        ],
        env=pg_environment(dsn),
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(
            "Restore failed. Check role prerequisites and PostgreSQL versions; no partial transaction was committed."
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["create", "restore"])
    parser.add_argument("--key", default="")
    parser.add_argument("--confirm-empty", action="store_true")
    args = parser.parse_args()
    require_live()
    config = settings()
    if not config.backup_s3_bucket or not config.backup_kms_key_id:
        raise ValueError("Configure BACKUP_S3_BUCKET and BACKUP_KMS_KEY_ID")
    with tempfile.TemporaryDirectory(prefix="obs-backup-") as directory:
        path = Path(directory) / "obs.dump"
        client = aws.client("s3", write=True)
        if args.action == "create":
            dump(config.database_url, path)
            key = f"observability/{datetime.now(UTC):%Y/%m/%d/%H%M%S}-{uuid4()}.dump"
            client.upload_file(
                str(path),
                config.backup_s3_bucket,
                key,
                ExtraArgs={
                    "ServerSideEncryption": "aws:kms",
                    "SSEKMSKeyId": config.backup_kms_key_id,
                },
            )
            print(f"Backup verified and uploaded: s3://{config.backup_s3_bucket}/{key}")
        else:
            if not args.confirm_empty or not args.key.startswith("observability/"):
                raise ValueError("Restore needs --confirm-empty and an observability/ backup key")
            client.download_file(config.backup_s3_bucket, args.key, str(path))
            path.chmod(0o600)
            restore(config.database_url, path)
            print("Backup restored into the empty target database")


if __name__ == "__main__":
    main()

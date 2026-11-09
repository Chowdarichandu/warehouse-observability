"""Load one service's secret JSON using its AWS role, then exec without a shell."""

import argparse
import json
import os


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret-id", default=os.environ.get("OBS_CONFIG_SECRET_ID", ""))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.secret_id and os.environ.get("MODE", "demo") == "live":
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "secretsmanager",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            config=Config(connect_timeout=5, read_timeout=10),
        )
        values = json.loads(client.get_secret_value(SecretId=args.secret_id)["SecretString"])
        if not isinstance(values, dict) or any(
            not isinstance(v, str) or not k.isidentifier() or not k.isupper()
            for k, v in values.items()
        ):
            raise ValueError(
                "Service secret must be a JSON object of uppercase environment names and string values"
            )
        if any(
            k.startswith(("AWS_", "LD_", "PYTHON")) or k in {"PATH", "HOME", "OBS_CONFIG_SECRET_ID"}
            for k in values
        ):
            raise ValueError(
                "Service secret cannot override process or AWS credential configuration"
            )
        os.environ.update(values)
    from obs.settings import settings

    settings()  # Reject unsafe live configuration before running the process.
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        raise ValueError("A command is required")
    os.execvpe(command[0], command, os.environ)


if __name__ == "__main__":
    main()

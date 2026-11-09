import argparse
import re
from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache
def rules() -> list[dict]:
    return yaml.safe_load(Path(__file__).with_name("errors.yaml").read_text())


def classify(message: str, origin: str | None = None) -> dict:
    for rule in rules():
        if origin == "destination" and rule["class"] != "DESTINATION_ERROR":
            continue
        if origin == "destination" or any(
            re.search(pattern, message, re.I) for pattern in rule["patterns"]
        ):
            return {
                "error_class": rule["class"],
                "severity": rule["severity"],
                "hint": rule["hint"],
            }
    return {"error_class": "UNKNOWN", "severity": "error", "hint": "Read the redacted log."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", action="store_true", required=True)
    parser.parse_args()
    from obs.db import connection
    from obs.demo.scenarios import enrich_failure

    with connection() as conn:
        for error in conn.execute("SELECT * FROM obs.run_errors").fetchall():
            run = conn.execute(
                "SELECT * FROM obs.pipeline_runs WHERE run_key=%s", (error["run_key"],)
            ).fetchone()
            enrich_failure(conn, run, error["error_message"], error["failure_origin"])
        conn.execute(
            "DELETE FROM obs.error_groups WHERE fingerprint NOT IN (SELECT fingerprint FROM obs.run_errors)"
        )

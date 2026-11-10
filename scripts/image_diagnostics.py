"""Expose bounded scanner failures as annotations without requiring private job logs."""

import json
import sys
from pathlib import Path


def main() -> None:
    for filename in sys.argv[1:]:
        path = Path(filename)
        if not path.is_file():
            continue
        report = json.loads(path.read_text())
        shown = 0
        for item in report.get("matches", []):
            vulnerability, artifact = item["vulnerability"], item["artifact"]
            fixes = vulnerability.get("fix", {}).get("versions", [])
            if (
                vulnerability.get("severity", "").lower() not in {"high", "critical"}
                or not fixes
            ):
                continue
            message = (
                f"{vulnerability['id']} ({vulnerability['severity']}): "
                f"{artifact['name']} {artifact['version']}; fixed in {', '.join(fixes[:3])}"
            )[:700]
            message = (
                message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            )
            print(f"::error title=Fixable image vulnerability::{message}")
            shown += 1
            if shown >= 20:
                break


if __name__ == "__main__":
    main()

import json
from pathlib import Path

from obs.api.main import app

target = Path(__file__).resolve().parents[1] / "backend/openapi.json"
spec = app.openapi()
target.write_text(json.dumps(spec, indent=2) + "\n")

lines = [
    "# API reference",
    "",
    "The API serves its OpenAPI contract at `/api/openapi.json` and the interactive reference at `/api/docs`.",
    "",
    "## Routes",
    "",
    "| Method | Path | Operation |",
    "|---|---|---|",
]
for path, operations in sorted(spec["paths"].items()):
    for method, operation in sorted(operations.items()):
        if method not in {"get", "post", "put", "patch", "delete"}:
            continue
        summary = (
            operation.get("summary") or operation.get("operationId") or "API operation"
        )
        summary = summary.replace("|", "\\|")
        lines.append(f"| `{method.upper()}` | `{path}` | {summary} |")

api_docs = Path(__file__).resolve().parents[1] / "docs/api.md"
api_docs.write_text("\n".join(lines) + "\n")
print(f"Wrote {target}")

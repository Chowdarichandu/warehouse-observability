"""Render the application settings section in docs/configuration.md."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

from obs.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/configuration.md"
START = "<!-- BEGIN GENERATED SETTINGS -->"
END = "<!-- END GENERATED SETTINGS -->"
SECRET_SUFFIXES = ("_SECRET", "_PASSWORD", "_TOKEN")


def render_type(annotation: Any) -> str:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Literal:
        return "one of: " + ", ".join(str(value) for value in args)
    if origin is list:
        item_type = render_type(args[0]) if args else "value"
        return f"array of {item_type}"
    if origin is dict:
        value_type = render_type(args[-1]) if len(args) > 1 else "value"
        return f"object with {value_type} values"
    if origin is not None and type(None) in args:
        remaining = tuple(arg for arg in args if arg is not type(None))
        return render_type(remaining[0]) if len(remaining) == 1 else "value"
    if annotation is str:
        return "string"
    if annotation is bool:
        return "boolean"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    return "value"


def render_default(name: str, value: Any) -> str:
    if name.endswith(SECRET_SUFFIXES):
        return "set per environment"
    if value is None:
        return "not set"
    if isinstance(value, bool):
        rendered = str(value).lower()
    elif isinstance(value, (list, dict)):
        rendered = json.dumps(value, sort_keys=True, separators=(",", ":"))
    else:
        rendered = str(value)
    return "`" + rendered.replace("`", "\\`") + "`"


def render_settings() -> str:
    lines = []
    for name, field in Settings.model_fields.items():
        key = name.upper()
        setting_type = render_type(field.annotation)
        default = render_default(key, field.default)
        lines.append(f"- `{key}`: {setting_type}. Default: {default}.")
    return "\n".join(lines)


def update_document(content: str, settings: str) -> str:
    start = content.find(START)
    end = content.find(END)
    if start < 0 or end < start:
        raise ValueError(f"{DOC.relative_to(ROOT)} must contain settings markers")
    body_start = start + len(START)
    return content[:body_start] + "\n\n" + settings + "\n\n" + content[end:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    current = DOC.read_text()
    generated = update_document(current, render_settings())
    if args.check:
        if generated != current:
            print(
                f"{DOC.relative_to(ROOT)} is stale; run `make config-docs`",
                file=sys.stderr,
            )
            return 1
        print(f"{DOC.relative_to(ROOT)} is up to date")
        return 0
    DOC.write_text(generated)
    print(f"Updated {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

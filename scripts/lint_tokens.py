#!/usr/bin/env python3
"""Enforce design-token usage for colors and typography in frontend sources."""

from pathlib import Path
import re
import sys

SOURCE = Path(__file__).resolve().parents[1] / "frontend" / "src"
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;{}]+)", re.IGNORECASE)
FONT_PROPERTY = re.compile(r"fontFamily\s*:\s*([^,}\n]+)", re.IGNORECASE)
UPPERCASE_TRANSFORM = re.compile(r"text-transform\s*:\s*uppercase\b", re.IGNORECASE)
TOKEN_OR_KEYWORD = re.compile(
    r"^(?:var\s*\(|inherit\b|initial\b|unset\b|revert\b)", re.IGNORECASE
)

errors: list[str] = []
for path in sorted(SOURCE.rglob("*")):
    if not path.is_file() or path.suffix not in {".css", ".ts", ".tsx"}:
        continue
    if path.relative_to(SOURCE).as_posix() == "styles/tokens.css":
        continue
    content = path.read_text(encoding="utf-8")
    relative = path.relative_to(SOURCE).as_posix()
    checks = [
        (HEX, "raw hex color"),
        (UPPERCASE_TRANSFORM, "text-transform: uppercase"),
    ]
    for pattern, message in checks:
        errors.extend(
            f"{relative}:{content.count(chr(10), 0, match.start()) + 1}: {message}"
            for match in pattern.finditer(content)
        )
    for match in FONT_FAMILY.finditer(content):
        if not TOKEN_OR_KEYWORD.match(match.group(1).strip()):
            errors.append(
                f"{relative}:{content.count(chr(10), 0, match.start()) + 1}: raw font-family value"
            )
    for match in FONT_PROPERTY.finditer(content):
        if not match.group(1).strip().startswith(
            "cssFont("
        ) and not TOKEN_OR_KEYWORD.match(match.group(1).strip()):
            errors.append(
                f"{relative}:{content.count(chr(10), 0, match.start()) + 1}: raw fontFamily value"
            )
if errors:
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)
print("Design token lint passed.")

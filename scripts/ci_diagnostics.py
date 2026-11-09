"""Expose a bounded, sanitized container failure in the GitHub check annotation."""

from pathlib import Path
import re
import sys

for value in sys.argv[1:]:
    path = Path(value)
    if not path.exists():
        continue
    message = (
        path.name
        + ":\n"
        + "\n".join(path.read_text(errors="replace").splitlines()[-25:])
    )
    message = message[-3000:]
    message = re.sub(r"(?i)(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", message)
    message = re.sub(r"(?i)(password|secret|token)=\S+", r"\1=[REDACTED]", message)
    message = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print("::error title=Container smoke diagnostics::" + message)

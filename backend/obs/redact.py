import re


def redact(text: str | None) -> str:
    """Mask secrets before persistence and at the response boundary; keep the log tail."""
    value = text or ""
    value = re.sub(r"(?i)([a-z][a-z0-9+.-]*://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", value)
    value = re.sub(
        r"""(?ix)(["']?(?:password|passwd|pwd|secret|access_token|api_key)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;&}]+)""",
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(r"(?i)Bearer\s+[A-Za-z0-9_.~+/=-]+", "Bearer [REDACTED]", value)
    value = re.sub(r"\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[JWT]", value)
    value = re.sub(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "[AWS_KEY]", value)
    value = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9._-]+\.[A-Z]{2,}", "[EMAIL]", value, flags=re.I)
    return value.encode("utf-8")[-512 * 1024 :].decode("utf-8", errors="ignore")


def redact_tree(value: object) -> object:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: redact_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_tree(item) for item in value]
    return value

import hashlib
import re


def normalize(message: str) -> str:
    value = message.lower()
    for pattern, replacement in [
        (r"\d{4}-\d\d-\d\d[t ][\d:.+-]+z?", "<time>"),
        (r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<id>"),
        (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "<ip>"),
        (r"0x[0-9a-f]+|\b[0-9a-f]{16,}\b", "<id>"),
        (r"\"[^\"]*\"|'[^']*'", "<value>"),
        (r"\b\d+(?:\.\d+)?\b", "<n>"),
    ]:
        value = re.sub(pattern, replacement, value)
    return " ".join(value.split())


def fingerprint(error_class: str, message: str) -> str:
    return hashlib.sha1((error_class + normalize(message)).encode()).hexdigest()

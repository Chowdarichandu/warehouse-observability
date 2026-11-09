import pytest

from obs.collector.classify import classify
from obs.collector.fingerprint import fingerprint
from obs.demo.scenarios import MESSAGES


@pytest.mark.parametrize("error_class,message", MESSAGES.items())
def test_all_error_patterns(error_class: str, message: str) -> None:
    assert classify(message)["error_class"] == error_class


def test_destination_origin_overrides_text() -> None:
    assert (
        classify("Connection refused", "destination")["error_class"]
        == "DESTINATION_ERROR"
    )


def test_unknown() -> None:
    assert classify("unrecognized failure")["error_class"] == "UNKNOWN"


def test_fingerprint_normalizes_identifiers() -> None:
    a = "2026-01-01T12:00:00Z task 19 at 10.1.2.3 user 'alice' id 123e4567-e89b-12d3-a456-426614174000 failed"
    b = "2026-02-02T13:22:01Z task 83 at 192.168.1.2 user 'bob' id 123e4567-e89b-12d3-a456-426614174001 failed"
    assert fingerprint("SOURCE_AUTH", a) == fingerprint("SOURCE_AUTH", b)
    assert fingerprint("SOURCE_AUTH", a) != fingerprint("UNKNOWN", a)

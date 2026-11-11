import pytest

from obs.redact import redact


@pytest.mark.parametrize(
    "value,secret",
    [
        ("password=hunter2 pwd=short", "hunter2"),
        ('{"password":"a b c"}', "a b c"),
        ("mysql://alice:topsecret@db.internal/app", "topsecret"),
        ("mongodb+srv://alice:secret@cluster/app", "alice"),
        ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
        ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature", "eyJhbGci"),
        ("AWS " + "AKIA" + "ABCDEFGHIJKLMNOP", "AKIA" + "ABCDEFGHIJKLMNOP"),
        ("owner=test.person@example.org", "test.person@example.org"),
        ("owner=data@acme_retail.example", "data@acme_retail.example"),
    ],
)
def test_masks_secrets(value: str, secret: str) -> None:
    assert secret not in redact(value)
    assert redact(redact(value)) == redact(value)


def test_keeps_utf8_tail() -> None:
    result = redact("é" * 400_000 + " end")
    assert len(result.encode()) <= 512 * 1024
    assert result.endswith(" end")


def test_webhook_urls_are_secret_material():
    from obs.redact import redact

    text = "https://hooks.slack.com/services/T000/B000/private-value"
    assert "private-value" not in redact(text)

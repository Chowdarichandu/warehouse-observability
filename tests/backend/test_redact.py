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


def test_redact_tree_preserves_identity_fields() -> None:
    from obs.redact import redact_tree

    payload = {
        "acknowledged_by": "operator@demo.local",
        "assignee": "admin@demo.local",
        "notes": [
            {
                "author": "operator@demo.local",
                "body": "ping owner@demo.local for access",
            }
        ],
        "title": "Contact owner@demo.local",
    }
    result = redact_tree(payload, frozenset({"acknowledged_by", "assignee", "author"}))
    assert result["acknowledged_by"] == "operator@demo.local"
    assert result["assignee"] == "admin@demo.local"
    assert result["notes"][0]["author"] == "operator@demo.local"
    # Free text is still redacted, including inside preserved subtrees' siblings.
    assert "owner@demo.local" not in result["notes"][0]["body"]
    assert "owner@demo.local" not in result["title"]
    # Without preserve_keys the identity fields redact like any other text.
    assert redact_tree(payload)["acknowledged_by"] == "[EMAIL]"

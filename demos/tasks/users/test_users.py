"""Acceptance tests for demo task 1 (users module). They fail until the task is implemented."""
import pytest
from pydantic import ValidationError


def test_user_valid_and_email_normalized():
    from taskboard.users import User
    u = User(username="dev_42", email="Dev@Example.COM")
    assert u.email == "dev@example.com"


def test_username_rules():
    from taskboard.users import User
    for bad in ["ab", "Has-Caps", "x" * 21, "bad space"]:
        with pytest.raises(ValidationError):
            User(username=bad, email="a@b.co")


def test_public_dict_hides_email():
    from taskboard.users import User
    u = User(username="dev_42", email="dev@example.com")
    assert u.to_public_dict() == {"username": "dev_42"}

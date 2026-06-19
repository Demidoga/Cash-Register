"""Access control at the HTTP seam: authentication proves identity, the
allowlist (a Membership) is authorization (PRD stories 5-7, ADR-0005)."""

from __future__ import annotations

from tests.util import OWNER_EMAIL, auth, make_token, setup_clinic

STRANGER_EMAIL = "stranger@example.com"


def test_no_token_is_unauthorized(client):
    assert client.get("/me").status_code == 401


def test_garbage_token_is_unauthorized(client):
    headers = {"Authorization": "Bearer not-a-real-jwt"}
    assert client.get("/me", headers=headers).status_code == 401


def test_token_signed_with_wrong_secret_is_unauthorized(client):
    setup_clinic(client)
    forged = {"Authorization": f"Bearer {make_token(OWNER_EMAIL, secret='attacker-secret')}"}
    assert client.get("/me", headers=forged).status_code == 401


def test_valid_login_not_on_allowlist_is_forbidden(client):
    setup_clinic(client)
    # A perfectly valid, correctly-signed token — but this email was never invited.
    assert client.get("/me", headers=auth(STRANGER_EMAIL)).status_code == 403
    assert (
        client.post("/patients", json={"name": "X"}, headers=auth(STRANGER_EMAIL)).status_code
        == 403
    )


def test_allowlisted_owner_is_permitted(client):
    setup_clinic(client)
    assert client.get("/me", headers=auth(OWNER_EMAIL)).status_code == 200


def test_unknown_settlement_statement_is_not_found_not_leaked(client):
    setup_clinic(client)
    # A scoped lookup miss is a 404, never a 500 or a cross-clinic read.
    assert client.get("/settlements/999999", headers=auth(OWNER_EMAIL)).status_code == 404

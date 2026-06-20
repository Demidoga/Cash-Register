"""Members / the allowlist: invite by email, list+pending, revoke, reactivate
(ADR-0008, GitHub issues #1 and #2).

Authentication proves the email (a signed JWT); authorization is the Membership.
"Invite" just adds an email to the allowlist — no email sent, no token issued.
"""

from __future__ import annotations

from app.models import Membership, Role, User
from tests.util import OWNER_EMAIL, auth, setup_clinic

INVITEE = "newdoc@smileclinic.test"


# --- issue #1: invite by email -----------------------------------------------


def test_owner_invites_member_then_invitee_reaches_dashboard(client):
    setup_clinic(client)
    r = client.post("/members", json={"email": INVITEE}, headers=auth(OWNER_EMAIL))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "invited"
    assert body["member"]["email"] == INVITEE
    assert body["member"]["role"] == "partner"  # the access tier, not a Partner
    assert body["member"]["status"] == "pending"  # has not signed in yet

    # The invitee signs in to Supabase with that email and is let in (no token
    # was ever issued by us).
    assert client.get("/me", headers=auth(INVITEE)).status_code == 200
    assert client.get("/dashboard/summary", headers=auth(INVITEE)).status_code == 200


def test_non_owner_cannot_invite(client):
    setup_clinic(client)
    client.post("/members", json={"email": INVITEE}, headers=auth(OWNER_EMAIL))
    assert client.get("/me", headers=auth(INVITEE)).status_code == 200  # is a member
    # ...but only an owner may invite — the app's first real role gate.
    r = client.post(
        "/members", json={"email": "third@smileclinic.test"}, headers=auth(INVITEE)
    )
    assert r.status_code == 403


def test_duplicate_invite_is_idempotent(client):
    setup_clinic(client)
    first = client.post("/members", json={"email": INVITEE}, headers=auth(OWNER_EMAIL))
    assert first.status_code == 201 and first.json()["status"] == "invited"
    second = client.post("/members", json={"email": INVITEE}, headers=auth(OWNER_EMAIL))
    assert second.status_code == 200 and second.json()["status"] == "already_member"
    # No duplicate Membership (would otherwise violate uq_membership).
    members = client.get("/members", headers=auth(OWNER_EMAIL)).json()
    assert [m["email"] for m in members].count(INVITEE) == 1


def test_first_sign_in_backfills_stub(client):
    setup_clinic(client)
    client.post("/members", json={"email": INVITEE}, headers=auth(OWNER_EMAIL))
    invitee = _find(client, INVITEE)
    assert invitee["status"] == "pending" and invitee["full_name"] is None

    # The verified JWT is where we first learn the sub and display name.
    r = client.get("/me", headers=auth(INVITEE, name="Dr Hassan", sub="sub-hassan-1"))
    assert r.status_code == 200
    invitee = _find(client, INVITEE)
    assert invitee["status"] == "active" and invitee["full_name"] == "Dr Hassan"


def test_invite_normalizes_email_to_lowercase(client):
    setup_clinic(client)
    r = client.post(
        "/members", json={"email": "MixedCase@Smile.TEST"}, headers=auth(OWNER_EMAIL)
    )
    assert r.status_code == 201
    assert r.json()["member"]["email"] == "mixedcase@smile.test"
    # get_identity lowercases the JWT email too, so the match holds.
    assert client.get("/me", headers=auth("mixedcase@smile.test")).status_code == 200


def test_invite_is_audit_logged(client):
    setup_clinic(client)
    client.post("/members", json={"email": INVITEE}, headers=auth(OWNER_EMAIL))
    logs = client.get("/audit-logs", headers=auth(OWNER_EMAIL)).json()
    assert "invite" in {e["action"] for e in logs}


def test_invalid_email_is_rejected(client):
    setup_clinic(client)
    r = client.post("/members", json={"email": "not-an-email"}, headers=auth(OWNER_EMAIL))
    assert r.status_code == 422


# --- issue #2: list, pending, revoke, reactivate -----------------------------


def test_list_shows_owner_active_and_invitee_pending_then_active(client):
    setup_clinic(client)
    members = client.get("/members", headers=auth(OWNER_EMAIL)).json()
    assert len(members) == 1
    assert members[0]["email"] == OWNER_EMAIL
    assert members[0]["role"] == "owner" and members[0]["status"] == "active"

    client.post("/members", json={"email": INVITEE}, headers=auth(OWNER_EMAIL))
    statuses = {m["email"]: m["status"] for m in _list(client)}
    assert statuses[OWNER_EMAIL] == "active" and statuses[INVITEE] == "pending"

    client.get("/me", headers=auth(INVITEE))  # first sign-in backfills the stub
    assert {m["email"]: m["status"] for m in _list(client)}[INVITEE] == "active"


def test_revoke_blocks_access_despite_valid_jwt(client):
    setup_clinic(client)
    client.post("/members", json={"email": INVITEE}, headers=auth(OWNER_EMAIL))
    assert client.get("/me", headers=auth(INVITEE)).status_code == 200

    invitee = _find(client, INVITEE)
    assert client.delete(
        f"/members/{invitee['id']}", headers=auth(OWNER_EMAIL)
    ).status_code == 204

    # The revoked user still holds a valid Supabase JWT, but is off the allowlist:
    # blocked at get_current_member (authorization), not at the token (auth).
    assert client.get("/me", headers=auth(INVITEE)).status_code == 403
    assert client.post(
        "/patients", json={"name": "X"}, headers=auth(INVITEE)
    ).status_code == 403
    assert INVITEE not in {m["email"] for m in _list(client)}


def test_cannot_revoke_last_owner(client):
    setup_clinic(client)
    owner = _find(client, OWNER_EMAIL)
    r = client.delete(f"/members/{owner['id']}", headers=auth(OWNER_EMAIL))
    assert r.status_code == 400 and "last owner" in r.json()["detail"]


def test_cannot_revoke_self_when_a_co_owner_exists(client, db):
    data = setup_clinic(client)
    # No endpoint promotes a member to owner, so seed a second owner directly to
    # make the acting owner no longer the *last* owner — isolating the self guard.
    co = User(email="co@smileclinic.test", supabase_sub="co-sub")
    db.add(co)
    db.flush()
    db.add(
        Membership(
            clinic_id=data["clinic_id"], user_id=co.id, role=Role.OWNER, created_by=co.id
        )
    )
    db.commit()

    mine = _find(client, OWNER_EMAIL)
    r = client.delete(f"/members/{mine['id']}", headers=auth(OWNER_EMAIL))
    assert r.status_code == 400 and "yourself" in r.json()["detail"]

    # An owner *can* revoke a co-owner while another owner remains (not the last).
    co_member = _find(client, "co@smileclinic.test")
    assert client.delete(
        f"/members/{co_member['id']}", headers=auth(OWNER_EMAIL)
    ).status_code == 204


def test_reinvite_reactivates_revoked_membership(client):
    setup_clinic(client)
    membership_id = (
        client.post("/members", json={"email": INVITEE}, headers=auth(OWNER_EMAIL))
        .json()["member"]["id"]
    )
    client.delete(f"/members/{membership_id}", headers=auth(OWNER_EMAIL))
    assert client.get("/me", headers=auth(INVITEE)).status_code == 403

    # uq_membership is (clinic_id, user_id) ignoring soft-delete, so re-invite
    # must reactivate the same row, not insert a colliding one.
    again = client.post("/members", json={"email": INVITEE}, headers=auth(OWNER_EMAIL))
    assert again.status_code == 200 and again.json()["status"] == "reactivated"
    assert again.json()["member"]["id"] == membership_id
    assert client.get("/me", headers=auth(INVITEE)).status_code == 200  # access returns
    assert [m["email"] for m in _list(client)].count(INVITEE) == 1


# --- helpers -----------------------------------------------------------------


def _list(client) -> list[dict]:
    return client.get("/members", headers=auth(OWNER_EMAIL)).json()


def _find(client, email: str) -> dict:
    return next(m for m in _list(client) if m["email"] == email)

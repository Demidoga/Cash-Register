"""The Milestone 0 walking skeleton, end to end at the HTTP seam.

setup -> /me -> patient + case -> open period -> take a payment -> dashboard
number -> close period + settlement statement -> record settlement payment.
Asserts observable outcomes (payloads, derived balances, locked state), never
internal structure (Testing Decisions).
"""

from __future__ import annotations

from tests.util import OWNER_EMAIL, auth, setup_clinic


def test_setup_seeds_clinic_partners_and_accounts(client):
    data = setup_clinic(client)
    assert data["clinic_id"] > 0
    assert [p["name"] for p in data["partners"]] == ["Saad", "Hassan"]
    kinds = {a["name"]: a["kind"] for a in data["accounts"]}
    assert kinds == {"Saad Cash": "personal", "Hassan Cash": "personal", "Joint": "joint"}

    me = client.get("/me", headers=auth(OWNER_EMAIL)).json()
    assert me["role"] == "owner"
    assert me["clinic_id"] == data["clinic_id"]


def test_setup_is_idempotent_guarded(client):
    setup_clinic(client)
    again = client.post(
        "/setup",
        json={
            "effective_from": "2026-01-01",
            "partners": [{"name": "X", "share_num": 1, "share_den": 1}],
            "accounts": [{"name": "Cash", "kind": "joint"}],
        },
        headers=auth(OWNER_EMAIL),
    )
    assert again.status_code == 409


def test_setup_rejects_shares_that_do_not_sum_to_one(client):
    bad = client.post(
        "/setup",
        json={
            "effective_from": "2026-01-01",
            "partners": [
                {"name": "A", "share_num": 1, "share_den": 2},
                {"name": "B", "share_num": 1, "share_den": 3},
            ],
            "accounts": [{"name": "Cash", "kind": "joint"}],
        },
        headers=auth(OWNER_EMAIL),
    )
    assert bad.status_code == 422


def test_full_skeleton_payment_through_settlement(client):
    data = setup_clinic(client)
    saad, hassan = data["partners"]
    saad_acc, hassan_acc, _joint = data["accounts"]

    patient = client.post(
        "/patients", json={"name": "Ali", "phone": "0300-1234567"}, headers=auth(OWNER_EMAIL)
    ).json()
    case = client.post(
        "/cases",
        json={"patient_id": patient["id"], "procedure_name": "Filling", "agreed_price": 10000},
        headers=auth(OWNER_EMAIL),
    ).json()
    assert case["outstanding"] == 10000

    period = client.post(
        "/periods",
        json={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        headers=auth(OWNER_EMAIL),
    ).json()

    # Saad collects the full 10000 into his personal account.
    pay = client.post(
        "/payments",
        json={
            "case_id": case["id"],
            "account_id": saad_acc["id"],
            "partner_id": saad["id"],
            "amount": 10000,
            "date": "2026-01-10",
        },
        headers=auth(OWNER_EMAIL),
    )
    assert pay.status_code == 201
    body = pay.json()
    assert body["movement"]["type"] == "income"
    assert body["case"]["outstanding"] == 0  # case is now settled

    # The one dashboard number: net profit for the period.
    dash = client.get("/dashboard/summary", headers=auth(OWNER_EMAIL)).json()
    assert (dash["income"], dash["expense"], dash["net_profit"]) == (10000, 0, 10000)
    balances = {a["account_id"]: a["balance"] for a in dash["account_balances"]}
    assert balances[saad_acc["id"]] == 10000

    # Close the period -> a settlement statement. Saad holds all the profit, so
    # he owes Hassan half (5000). Closing moves no cash (ADR-0003).
    closed = client.post(f"/periods/{period['id']}/close", headers=auth(OWNER_EMAIL))
    assert closed.status_code == 200
    statement = closed.json()
    assert statement["profit"] == 10000
    settle = {b["partner_id"]: b["settlement_balance"] for b in statement["balances"]}
    assert settle[saad["id"]] == 5000
    assert settle[hassan["id"]] == -5000
    assert len(statement["obligations"]) == 1
    obligation = statement["obligations"][0]
    assert obligation["from_partner_id"] == saad["id"]
    assert obligation["to_partner_id"] == hassan["id"]
    assert obligation["amount"] == 5000
    assert obligation["paid"] is False

    # A closed period is locked: a payment dated inside it is rejected (story 54).
    locked = client.post(
        "/payments",
        json={
            "case_id": case["id"],
            "account_id": saad_acc["id"],
            "partner_id": saad["id"],
            "amount": 1,
            "date": "2026-01-20",
        },
        headers=auth(OWNER_EMAIL),
    )
    assert locked.status_code == 409

    # Record the real settlement payment as a Transfer, dated when cash moves.
    paid = client.post(
        f"/settlements/{statement['id']}/payments",
        json={
            "obligation_id": obligation["id"],
            "from_account_id": saad_acc["id"],
            "to_account_id": hassan_acc["id"],
            "date": "2026-02-01",
        },
        headers=auth(OWNER_EMAIL),
    )
    assert paid.status_code == 201
    movement = paid.json()
    assert movement["type"] == "transfer"
    assert movement["amount"] == 5000

    # The obligation is now satisfied, and the cash actually moved between the
    # two personal accounts — without changing profit.
    after = client.get(f"/settlements/{statement['id']}", headers=auth(OWNER_EMAIL)).json()
    assert after["obligations"][0]["paid"] is True
    dash2 = client.get("/dashboard/summary", headers=auth(OWNER_EMAIL)).json()
    bal2 = {a["account_id"]: a["balance"] for a in dash2["account_balances"]}
    assert bal2[saad_acc["id"]] == 5000
    assert bal2[hassan_acc["id"]] == 5000
    assert dash2["net_profit"] == 10000  # transfer never touches profit


def test_double_close_is_rejected(client):
    data = setup_clinic(client)
    period = client.post(
        "/periods",
        json={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        headers=auth(OWNER_EMAIL),
    ).json()
    assert client.post(f"/periods/{period['id']}/close", headers=auth(OWNER_EMAIL)).status_code == 200
    assert client.post(f"/periods/{period['id']}/close", headers=auth(OWNER_EMAIL)).status_code == 409


def test_overpayment_becomes_an_advance_on_the_case(client):
    data = setup_clinic(client)
    saad = data["partners"][0]
    saad_acc = data["accounts"][0]
    patient = client.post("/patients", json={"name": "Bilal"}, headers=auth(OWNER_EMAIL)).json()
    case = client.post(
        "/cases",
        json={"patient_id": patient["id"], "procedure_name": "Cleaning", "agreed_price": 3000},
        headers=auth(OWNER_EMAIL),
    ).json()
    pay = client.post(
        "/payments",
        json={
            "case_id": case["id"],
            "account_id": saad_acc["id"],
            "partner_id": saad["id"],
            "amount": 5000,
            "date": "2026-01-05",
        },
        headers=auth(OWNER_EMAIL),
    ).json()
    assert pay["case"]["outstanding"] == -2000  # 2000 advance/credit

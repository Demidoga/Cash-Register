"""HTTP-seam coverage for the full-V1 features (Milestones 1-8)."""

from __future__ import annotations

from tests.util import OWNER_EMAIL, auth, setup_clinic

H = auth(OWNER_EMAIL)


def _ctx(client):
    data = setup_clinic(client)
    saad, hassan = data["partners"]
    saad_acc, hassan_acc, joint = data["accounts"]
    period = client.post(
        "/periods", json={"start_date": "2026-01-01", "end_date": "2026-01-31"}, headers=H
    ).json()
    patient = client.post("/patients", json={"name": "Ali"}, headers=H).json()
    case = client.post(
        "/cases",
        json={"patient_id": patient["id"], "procedure_name": "Filling", "agreed_price": 10000},
        headers=H,
    ).json()
    return {
        "saad": saad, "hassan": hassan, "saad_acc": saad_acc, "hassan_acc": hassan_acc,
        "joint": joint, "period": period, "patient": patient, "case": case,
    }


def _pay(client, c, amount, on="2026-01-10"):
    return client.post(
        "/payments",
        json={"case_id": c["case"]["id"], "account_id": c["saad_acc"]["id"],
              "partner_id": c["saad"]["id"], "amount": amount, "date": on},
        headers=H,
    ).json()


def test_log_expense_reduces_net_profit(client):
    c = _ctx(client)
    cat = client.post("/categories", json={"name": "Rent"}, headers=H).json()
    _pay(client, c, 10000)
    r = client.post(
        "/expenses",
        json={"account_id": c["joint"]["id"], "partner_id": c["hassan"]["id"], "amount": 3000,
              "category_id": cat["id"], "date": "2026-01-12"},
        headers=H,
    )
    assert r.status_code == 201 and r.json()["type"] == "expense"
    dash = client.get("/dashboard/summary", headers=H).json()
    assert (dash["income"], dash["expense"], dash["net_profit"]) == (10000, 3000, 7000)


def test_transfer_capital_drawing_never_touch_profit(client):
    c = _ctx(client)
    _pay(client, c, 10000)
    for path, body in [
        ("/transfers", {"from_account_id": c["saad_acc"]["id"], "to_account_id": c["joint"]["id"],
                        "amount": 2000, "partner_id": c["saad"]["id"], "date": "2026-01-15"}),
        ("/capital", {"account_id": c["saad_acc"]["id"], "partner_id": c["saad"]["id"],
                      "amount": 5000, "date": "2026-01-15"}),
        ("/drawings", {"account_id": c["saad_acc"]["id"], "partner_id": c["saad"]["id"],
                       "amount": 1000, "date": "2026-01-15"}),
    ]:
        assert client.post(path, json=body, headers=H).status_code == 201
    dash = client.get("/dashboard/summary", headers=H).json()
    assert dash["net_profit"] == 10000 and dash["expense"] == 0
    bal = {a["account_id"]: a["balance"] for a in dash["account_balances"]}
    # saad: +10000 income -2000 transfer +5000 capital -1000 drawing = 12000
    assert bal[c["saad_acc"]["id"]] == 12000
    assert bal[c["joint"]["id"]] == 2000


def test_refund_raises_outstanding_and_lowers_profit(client):
    c = _ctx(client)
    _pay(client, c, 10000)  # outstanding 0
    r = client.post(
        "/refunds",
        json={"case_id": c["case"]["id"], "account_id": c["saad_acc"]["id"],
              "partner_id": c["saad"]["id"], "amount": 4000, "date": "2026-01-20"},
        headers=H,
    )
    assert r.status_code == 201
    case = client.get(f"/cases/{c['case']['id']}", headers=H).json()
    assert case["outstanding"] == 4000
    dash = client.get("/dashboard/summary", headers=H).json()
    assert dash["income"] == 6000 and dash["net_profit"] == 6000


def test_discount_and_writeoff_reduce_outstanding_not_income(client):
    c = _ctx(client)
    _pay(client, c, 2000)  # outstanding 8000
    after_discount = client.post(
        f"/cases/{c['case']['id']}/discount", json={"amount": 1000}, headers=H
    ).json()
    assert after_discount["outstanding"] == 7000
    after_writeoff = client.post(
        f"/cases/{c['case']['id']}/write-off", json={}, headers=H
    ).json()
    assert after_writeoff["outstanding"] == 0
    dash = client.get("/dashboard/summary", headers=H).json()
    assert dash["income"] == 2000  # adjustments are not income


def test_edit_void_restore_and_lock(client):
    c = _ctx(client)
    movement = _pay(client, c, 10000)["movement"]
    mid = movement["id"]

    client.patch(f"/movements/{mid}", json={"amount": 8000}, headers=H)
    assert client.get(f"/cases/{c['case']['id']}", headers=H).json()["outstanding"] == 2000

    assert client.delete(f"/movements/{mid}", headers=H).status_code == 204
    assert client.get(f"/cases/{c['case']['id']}", headers=H).json()["outstanding"] == 10000

    client.post(f"/movements/{mid}/restore", headers=H)
    assert client.get(f"/cases/{c['case']['id']}", headers=H).json()["outstanding"] == 2000

    # Once the period is closed, the entry is locked.
    client.post(f"/periods/{c['period']['id']}/close", headers=H)
    assert client.patch(f"/movements/{mid}", json={"amount": 1}, headers=H).status_code == 409
    assert client.delete(f"/movements/{mid}", headers=H).status_code == 409


def test_reports(client):
    c = _ctx(client)
    cat = client.post("/categories", json={"name": "Rent"}, headers=H).json()
    _pay(client, c, 6000)
    client.post(
        "/expenses",
        json={"account_id": c["joint"]["id"], "partner_id": c["hassan"]["id"], "amount": 2000,
              "category_id": cat["id"], "date": "2026-01-12"},
        headers=H,
    )
    assert client.get("/reports/pnl", headers=H).json()["net_profit"] == 4000
    by_cat = client.get("/reports/by-category", headers=H).json()
    assert by_cat[0] == {"category_id": cat["id"], "name": "Rent", "total": 2000}
    recv = client.get("/reports/receivables", headers=H).json()
    assert recv["total"] == 4000  # 10000 agreed - 6000 paid
    collectors = {r["partner_id"]: r["collected"] for r in client.get("/reports/by-collector", headers=H).json()}
    assert collectors[c["saad"]["id"]] == 6000
    contrib = {r["partner_id"]: r for r in client.get("/reports/per-partner", headers=H).json()}
    assert contrib[c["saad"]["id"]]["collected"] == 6000
    assert contrib[c["hassan"]["id"]]["paid"] == 2000


def test_config_crud_and_new_share_window(client):
    setup_clinic(client)
    partners = client.get("/partners", headers=H).json()
    assert client.post("/procedures", json={"name": "Crown", "default_price": 25000}, headers=H).status_code == 201
    assert client.post("/employees", json={"name": "Sara", "role": "Nurse", "salary": 40000}, headers=H).status_code == 201
    acc = client.post(
        "/accounts", json={"name": "Bank", "kind": "joint", "opening_balance": 1000}, headers=H
    )
    assert acc.status_code == 201
    # disable it (story 14 toggle)
    toggled = client.patch(f"/accounts/{acc.json()['id']}", json={"is_active": False}, headers=H).json()
    assert toggled["is_active"] is False
    # a new effective-dated share window
    win = client.post(
        "/share-windows",
        json={"effective_from": "2026-02-01", "shares": [
            {"partner_id": partners[0]["id"], "share_num": 6, "share_den": 10},
            {"partner_id": partners[1]["id"], "share_num": 4, "share_den": 10},
        ]},
        headers=H,
    )
    assert win.status_code == 201
    assert len(client.get("/share-windows", headers=H).json()) == 2


def test_reminders_surface_outstanding_and_due_period(client):
    c = _ctx(client)  # period ends 2026-01-31 (past), case unpaid
    reminders = client.get("/reminders", headers=H).json()
    kinds = {r["kind"] for r in reminders}
    assert "outstanding" in kinds or "large_balance_cold" in kinds
    assert "period_due" in kinds


def test_exports(client):
    c = _ctx(client)
    _pay(client, c, 4000)
    journal = client.get("/exports/journal.csv", headers=H)
    assert journal.status_code == 200
    assert journal.headers["content-type"].startswith("text/csv")
    assert "date,type,amount" in journal.text
    pdf = client.get(f"/exports/periods/{c['period']['id']}/summary.pdf", headers=H)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    stmt = client.get(f"/exports/patients/{c['patient']['id']}/statement.csv", headers=H)
    assert stmt.status_code == 200 and "outstanding" in stmt.text


def test_audit_trail_records_writes(client):
    c = _ctx(client)
    _pay(client, c, 1000)
    logs = client.get("/audit-logs", headers=H).json()
    actions = {entry["action"] for entry in logs}
    assert "take_payment" in actions
    assert "setup" in actions


def test_dev_login_issues_usable_token(client):
    setup_clinic(client)  # OWNER_EMAIL is now allowlisted
    token = client.post(
        "/dev/login", json={"email": OWNER_EMAIL, "name": "Saad"}
    ).json()["access_token"]
    me = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == OWNER_EMAIL
    # A valid token for a non-allowlisted email still can't get in.
    stranger = client.post("/dev/login", json={"email": "x@y.z"}).json()["access_token"]
    assert client.get("/me", headers={"Authorization": f"Bearer {stranger}"}).status_code == 403

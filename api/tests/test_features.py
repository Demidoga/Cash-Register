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


def test_payment_with_inline_discount_applies_and_records(client):
    c = _ctx(client)  # case agreed price 10000
    res = client.post(
        "/payments",
        json={"case_id": c["case"]["id"], "account_id": c["saad_acc"]["id"],
              "partner_id": c["saad"]["id"], "amount": 2000, "date": "2026-01-10",
              "discount": 1000},
        headers=H,
    )
    assert res.status_code == 201
    # 10000 − 2000 paid − 1000 discount = 7000, reflected in the response.
    assert res.json()["case"]["outstanding"] == 7000

    dash = client.get("/dashboard/summary", headers=H).json()
    assert dash["income"] == 2000  # the discount is an adjustment, never income

    # The discount is recorded as an audited case_adjustment, not silently dropped.
    logs = client.get("/audit-logs", headers=H).json()
    discount_logs = [
        log for log in logs
        if log["action"] == "discount" and log["entity_type"] == "case_adjustment"
    ]
    assert len(discount_logs) == 1
    assert discount_logs[0]["detail"] == {"case_id": c["case"]["id"], "amount": 1000}


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


def test_edit_flags_entry_and_records_diff(client):
    c = _ctx(client)
    movement = _pay(client, c, 10000, on="2026-01-02")["movement"]
    mid = movement["id"]
    assert movement["edited"] is False  # freshly recorded — not flagged

    # Correct a fat-fingered date; the entry is now flagged as edited.
    fixed = client.patch(f"/movements/{mid}", json={"date": "2026-01-20"}, headers=H).json()
    assert fixed["edited"] is True
    assert fixed["date"] == "2026-01-20"
    assert fixed["updated_by"] is not None

    # The audit trail explains the correction (old -> new), not just that one happened.
    log = next(
        l for l in client.get("/audit-logs", headers=H).json()
        if l["action"] == "edit" and l["entity_id"] == mid
    )
    assert log["detail"]["date"] == {"from": "2026-01-02", "to": "2026-01-20"}


def test_edit_can_repoint_partner_case_and_account(client):
    c = _ctx(client)
    # A second case to move the income onto.
    other_case = client.post(
        "/cases",
        json={"patient_id": c["patient"]["id"], "procedure_name": "Cleaning", "agreed_price": 5000},
        headers=H,
    ).json()
    mid = _pay(client, c, 10000)["movement"]["id"]
    # Original case is fully paid; the new one is untouched.
    assert client.get(f"/cases/{c['case']['id']}", headers=H).json()["outstanding"] == 0
    assert client.get(f"/cases/{other_case['id']}", headers=H).json()["outstanding"] == 5000

    # Re-point the entry: different collector, account, and case in one edit.
    res = client.patch(
        f"/movements/{mid}",
        json={"partner_id": c["hassan"]["id"], "to_account_id": c["joint"]["id"],
              "case_id": other_case["id"]},
        headers=H,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["partner_id"] == c["hassan"]["id"]
    assert body["to_account_id"] == c["joint"]["id"]
    assert body["case_id"] == other_case["id"]

    # The 10000 now lands on the new case (over-paid by 5000) and leaves the old one owing again.
    assert client.get(f"/cases/{c['case']['id']}", headers=H).json()["outstanding"] == 10000
    assert client.get(f"/cases/{other_case['id']}", headers=H).json()["outstanding"] == -5000

    # The audit trail captures each re-pointing as an old -> new diff.
    log = next(
        l for l in client.get("/audit-logs", headers=H).json()
        if l["action"] == "edit" and l["entity_id"] == mid
    )
    assert log["detail"]["partner_id"] == {"from": c["saad"]["id"], "to": c["hassan"]["id"]}
    assert log["detail"]["case_id"] == {"from": c["case"]["id"], "to": other_case["id"]}


def test_edit_rewrites_linked_discount_instead_of_stacking(client):
    c = _ctx(client)
    # Pay 2000 with a 1000 discount: case 10000 − 2000 − 1000 = 7000 outstanding.
    res = client.post(
        "/payments",
        json={"case_id": c["case"]["id"], "account_id": c["saad_acc"]["id"],
              "partner_id": c["saad"]["id"], "amount": 2000, "date": "2026-01-10",
              "discount": 1000},
        headers=H,
    ).json()
    assert res["case"]["outstanding"] == 7000
    mid = res["movement"]["id"]

    # The payment row carries its linked discount for the editor to pre-fill.
    income = client.get("/movements?type=income", headers=H).json()
    assert next(m for m in income if m["id"] == mid)["discount"] == 1000

    # Raise the discount to 3000: it should REWRITE the same adjustment, not add a
    # second. Outstanding = 10000 − 2000 − 3000 = 5000 (would be 4000 if stacked).
    body = client.patch(f"/movements/{mid}", json={"discount": 3000}, headers=H).json()
    assert body["discount"] == 3000
    assert client.get(f"/cases/{c['case']['id']}", headers=H).json()["outstanding"] == 5000

    # Clearing the discount (0) removes it entirely: outstanding back to 8000.
    client.patch(f"/movements/{mid}", json={"discount": 0}, headers=H)
    assert client.get(f"/cases/{c['case']['id']}", headers=H).json()["outstanding"] == 8000
    income = client.get("/movements?type=income", headers=H).json()
    assert next(m for m in income if m["id"] == mid)["discount"] == 0


def test_edit_rejects_unknown_repoint_targets(client):
    c = _ctx(client)
    mid = _pay(client, c, 10000)["movement"]["id"]
    assert client.patch(f"/movements/{mid}", json={"partner_id": 9999}, headers=H).status_code == 404
    assert client.patch(f"/movements/{mid}", json={"case_id": 9999}, headers=H).status_code == 404
    assert client.patch(f"/movements/{mid}", json={"to_account_id": 9999}, headers=H).status_code == 404


def test_noop_edit_leaves_no_trace(client):
    c = _ctx(client)
    mid = _pay(client, c, 10000, on="2026-01-02")["movement"]["id"]
    before = len(client.get("/audit-logs", headers=H).json())

    # Re-submitting identical values changes nothing — no flag, no audit row.
    same = client.patch(f"/movements/{mid}", json={"amount": 10000, "date": "2026-01-02"}, headers=H).json()
    assert same["edited"] is False
    assert len(client.get("/audit-logs", headers=H).json()) == before


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


def test_account_activity_splits_income_and_expense_by_account(client):
    c = _ctx(client)
    cat = client.post("/categories", json={"name": "Rent"}, headers=H).json()
    # Payment lands in saad's account; expense leaves the joint account.
    _pay(client, c, 6000)
    client.post(
        "/expenses",
        json={"account_id": c["joint"]["id"], "partner_id": c["hassan"]["id"], "amount": 2000,
              "category_id": cat["id"], "date": "2026-01-12"},
        headers=H,
    )
    activity = {a["account_id"]: a for a in client.get("/reports/account-activity", headers=H).json()}

    saad = activity[c["saad_acc"]["id"]]
    assert (saad["income"], saad["expense"]) == (6000, 0)
    assert [(r["type"], r["amount"]) for r in saad["rows"]] == [("income", 6000)]

    joint = activity[c["joint"]["id"]]
    assert (joint["income"], joint["expense"]) == (0, 2000)
    assert [(r["type"], r["amount"]) for r in joint["rows"]] == [("expense", 2000)]

    # An untouched account is still listed, with empty history.
    hassan = activity[c["hassan_acc"]["id"]]
    assert (hassan["income"], hassan["expense"], hassan["rows"]) == (0, 0, [])


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


def test_edit_case_updates_details_and_audits(client):
    c = _ctx(client)  # case "Filling", agreed 10000
    _pay(client, c, 4000)  # outstanding 6000
    proc = client.post(
        "/procedures", json={"name": "Crown", "default_price": 15000}, headers=H
    ).json()
    body = client.patch(
        f"/cases/{c['case']['id']}",
        json={"procedure_name": "Crown", "procedure_id": proc["id"], "agreed_price": 12000},
        headers=H,
    ).json()
    assert body["procedure_name"] == "Crown"
    assert body["agreed_price"] == 12000
    # New agreed price reprices the outstanding (12000 − 4000 paid).
    assert body["outstanding"] == 8000
    # The change is audited as a per-field diff so the correction is explained.
    edit = next(
        log for log in client.get("/audit-logs", headers=H).json()
        if log["action"] == "edit" and log["entity_type"] == "case"
    )
    assert edit["detail"]["agreed_price"] == {"from": 10000, "to": 12000}


def test_edit_case_validates_procedure_and_no_ops_leave_no_trace(client):
    c = _ctx(client)
    # An unknown procedure is rejected.
    assert client.patch(
        f"/cases/{c['case']['id']}", json={"procedure_id": 9999}, headers=H
    ).status_code == 404
    # Re-sending the same values changes nothing and writes no audit row.
    before = len(client.get("/audit-logs", headers=H).json())
    client.patch(
        f"/cases/{c['case']['id']}",
        json={"procedure_name": "Filling", "agreed_price": 10000},
        headers=H,
    )
    assert len(client.get("/audit-logs", headers=H).json()) == before


def test_delete_patient_cascades_cases_and_is_restorable(client):
    c = _ctx(client)
    pid = c["patient"]["id"]
    _pay(client, c, 4000)  # money really moved; it must survive the delete

    assert client.delete(f"/patients/{pid}", headers=H).status_code == 204
    # Gone from listings and reads; its cases go down with it.
    assert client.get(f"/patients/{pid}", headers=H).status_code == 404
    assert all(p["id"] != pid for p in client.get("/patients", headers=H).json())
    assert all(ca["patient_id"] != pid for ca in client.get("/cases", headers=H).json())
    # But the income stayed on the books — deleting a patient never rewrites profit.
    assert client.get("/dashboard/summary", headers=H).json()["income"] == 4000

    # Undo brings back the patient and the case that was cascaded.
    restored = client.post(f"/patients/{pid}/restore", headers=H)
    assert restored.status_code == 200 and restored.json()["id"] == pid
    assert any(p["id"] == pid for p in client.get("/patients", headers=H).json())
    cases = client.get(f"/patients/{pid}", headers=H).json()["cases"]
    assert len(cases) == 1 and cases[0]["outstanding"] == 6000
    # Restoring something that isn't deleted is a conflict, not a silent no-op.
    assert client.post(f"/patients/{pid}/restore", headers=H).status_code == 409


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

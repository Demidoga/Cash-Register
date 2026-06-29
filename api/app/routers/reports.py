"""Dashboard intelligence (Milestone 4): where money comes from and where it
goes — P&L for any range, by-category, by-procedure, by-collector, receivables,
month-over-month trends, and per-partner contribution.

Aggregations are computed in Python from the movement rows: clear, DB-agnostic,
and fast at the data sizes a single clinic produces.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from fractions import Fraction

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.deps import CurrentMember, get_current_member
from app.models import Account, Case, Category, MoneyMovement, PartnerShare, Patient, ShareWindow
from app.money_math.types import MovementType
from app.services import case_outstanding_value, list_alive

router = APIRouter(prefix="/reports", tags=["reports"])


def _movements(session: Session, clinic_id: int, start: date | None, end: date | None):
    stmt = select(MoneyMovement).where(
        MoneyMovement.clinic_id == clinic_id, MoneyMovement.deleted_at.is_(None)
    )
    if start is not None:
        stmt = stmt.where(MoneyMovement.date >= start)
    if end is not None:
        stmt = stmt.where(MoneyMovement.date <= end)
    return list(session.scalars(stmt))


@router.get("/pnl", response_model=schemas.PnL)
def pnl(
    start: date | None = None,
    end: date | None = None,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    movements = _movements(session, member.clinic_id, start, end)
    income = sum(m.amount for m in movements if m.type is MovementType.INCOME)
    expense = sum(m.amount for m in movements if m.type is MovementType.EXPENSE)
    return schemas.PnL(start=start, end=end, income=income, expense=expense, net_profit=income - expense)


@router.get("/by-category", response_model=list[schemas.CategoryTotal])
def by_category(
    start: date | None = None,
    end: date | None = None,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    names = {c.id: c.name for c in list_alive(session, Category, member.clinic_id)}
    totals: dict[int | None, int] = defaultdict(int)
    for m in _movements(session, member.clinic_id, start, end):
        if m.type is MovementType.EXPENSE:
            totals[m.category_id] += m.amount
    rows = [
        schemas.CategoryTotal(
            category_id=cid, name=names.get(cid, "Uncategorized") if cid else "Uncategorized", total=t
        )
        for cid, t in totals.items()
    ]
    return sorted(rows, key=lambda r: r.total, reverse=True)


@router.get("/by-procedure", response_model=list[schemas.ProcedureStat])
def by_procedure(
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    cases = list_alive(session, Case, member.clinic_id)
    procedure_of = {c.id: c.procedure_name for c in cases}
    count: dict[str, int] = defaultdict(int)
    revenue: dict[str, int] = defaultdict(int)
    for c in cases:
        count[c.procedure_name] += 1
    for m in _movements(session, member.clinic_id, None, None):
        if m.type is MovementType.INCOME and m.case_id in procedure_of:
            revenue[procedure_of[m.case_id]] += m.amount
    rows = [
        schemas.ProcedureStat(procedure_name=name, count=count[name], revenue=revenue.get(name, 0))
        for name in count
    ]
    return sorted(rows, key=lambda r: r.revenue, reverse=True)


@router.get("/by-collector", response_model=list[schemas.CollectorTotal])
def by_collector(
    start: date | None = None,
    end: date | None = None,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    from app.models import Partner

    names = {p.id: p.name for p in list_alive(session, Partner, member.clinic_id)}
    collected: dict[int, int] = defaultdict(int)
    for m in _movements(session, member.clinic_id, start, end):
        if m.type is MovementType.INCOME and m.partner_id is not None:
            collected[m.partner_id] += m.amount
    rows = [
        schemas.CollectorTotal(partner_id=pid, name=names.get(pid, "?"), collected=total)
        for pid, total in collected.items()
    ]
    return sorted(rows, key=lambda r: r.collected, reverse=True)


@router.get("/receivables", response_model=schemas.Receivables)
def receivables(
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    patients = {p.id: p.name for p in list_alive(session, Patient, member.clinic_id)}
    per_patient: dict[int, int] = defaultdict(int)
    for case in list_alive(session, Case, member.clinic_id):
        per_patient[case.patient_id] += case_outstanding_value(session, member.clinic_id, case)
    rows = [
        schemas.ReceivableRow(patient_id=pid, name=patients.get(pid, "?"), outstanding=amount)
        for pid, amount in per_patient.items()
        if amount > 0  # only patients who actually owe
    ]
    rows.sort(key=lambda r: r.outstanding, reverse=True)
    return schemas.Receivables(total=sum(r.outstanding for r in rows), rows=rows)


@router.get("/trends", response_model=list[schemas.TrendPoint])
def trends(
    months: int = 6,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    income: dict[str, int] = defaultdict(int)
    expense: dict[str, int] = defaultdict(int)
    for m in _movements(session, member.clinic_id, None, None):
        key = f"{m.date.year:04d}-{m.date.month:02d}"
        if m.type is MovementType.INCOME:
            income[key] += m.amount
        elif m.type is MovementType.EXPENSE:
            expense[key] += m.amount
    keys = sorted(set(income) | set(expense))[-max(months, 1):]
    return [
        schemas.TrendPoint(
            month=k, income=income.get(k, 0), expense=expense.get(k, 0),
            net_profit=income.get(k, 0) - expense.get(k, 0),
        )
        for k in keys
    ]


@router.get("/account-activity", response_model=list[schemas.AccountActivity])
def account_activity(
    start: date | None = None,
    end: date | None = None,
    limit: int = 8,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Per-account income/expense history — what came in and what went out of
    each cash container. Income lands in `to_account`; expense leaves
    `from_account` (ADR-0007). Transfers/capital/drawings are out of scope here;
    the Journal shows the full ledger. Totals span the range; `rows` are capped
    at `limit` most-recent entries per account for the dashboard preview."""
    accounts = list_alive(session, Account, member.clinic_id)
    income: dict[int, int] = defaultdict(int)
    expense: dict[int, int] = defaultdict(int)
    rows: dict[int, list[schemas.AccountActivityRow]] = defaultdict(list)

    # Most-recent first so per-account `rows` previews show the latest activity.
    movements = sorted(
        _movements(session, member.clinic_id, start, end),
        key=lambda m: (m.date, m.id),
        reverse=True,
    )
    for m in movements:
        if m.type is MovementType.INCOME and m.to_account_id is not None:
            account_id = m.to_account_id
            income[account_id] += m.amount
        elif m.type is MovementType.EXPENSE and m.from_account_id is not None:
            account_id = m.from_account_id
            expense[account_id] += m.amount
        else:
            continue
        if len(rows[account_id]) < limit:
            rows[account_id].append(
                schemas.AccountActivityRow(
                    movement_id=m.id, date=m.date, type=m.type,
                    amount=m.amount, note=m.note, case_id=m.case_id,
                )
            )

    return [
        schemas.AccountActivity(
            account_id=a.id, name=a.name, kind=a.kind,
            income=income.get(a.id, 0), expense=expense.get(a.id, 0),
            rows=rows.get(a.id, []),
        )
        for a in accounts
    ]


def _current_shares(session: Session, clinic_id: int) -> dict[int, Fraction]:
    window = session.scalar(
        select(ShareWindow)
        .where(ShareWindow.clinic_id == clinic_id, ShareWindow.deleted_at.is_(None))
        .order_by(ShareWindow.effective_from.desc())
    )
    if window is None:
        return {}
    shares = session.scalars(
        select(PartnerShare).where(PartnerShare.share_window_id == window.id)
    ).all()
    return {s.partner_id: Fraction(s.share_num, s.share_den) for s in shares}


@router.get("/per-partner", response_model=list[schemas.PartnerContribution])
def per_partner(
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    from app.models import Partner

    partners = list_alive(session, Partner, member.clinic_id)
    shares = _current_shares(session, member.clinic_id)
    collected: dict[int, int] = defaultdict(int)
    paid: dict[int, int] = defaultdict(int)
    income_total = 0
    expense_total = 0
    for m in _movements(session, member.clinic_id, None, None):
        if m.type is MovementType.INCOME:
            income_total += m.amount
            if m.partner_id is not None:
                collected[m.partner_id] += m.amount
        elif m.type is MovementType.EXPENSE:
            expense_total += m.amount
            if m.partner_id is not None:
                paid[m.partner_id] += m.amount
    profit = income_total - expense_total
    return [
        schemas.PartnerContribution(
            partner_id=p.id,
            name=p.name,
            collected=collected.get(p.id, 0),
            paid=paid.get(p.id, 0),
            entitled=int(shares.get(p.id, Fraction(0)) * profit),
        )
        for p in partners
    ]

"""In-app "needs attention" panel (Milestone 7): the system surfaces what to
act on — outstanding patients, large balances going cold, periods due to close,
and settlement statements with unpaid obligations."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.deps import CurrentMember, get_current_member
from app.models import Case, Patient, Period, PeriodStatus, SettlementObligation, SettlementStatement
from app.services import case_outstanding_value, list_alive

router = APIRouter(tags=["reminders"])

LARGE_BALANCE = 20000  # rupees; a balance worth chasing
COLD_DAYS = 45


@router.get("/reminders", response_model=list[schemas.Reminder])
def reminders(
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    today = date.today()
    out: list[schemas.Reminder] = []

    # Outstanding patients, with a louder alert for large balances going cold.
    patients = {p.id: p for p in list_alive(session, Patient, member.clinic_id)}
    owed: dict[int, int] = {}
    oldest: dict[int, date] = {}
    for case in list_alive(session, Case, member.clinic_id):
        amount = case_outstanding_value(session, member.clinic_id, case)
        if amount <= 0:
            continue
        owed[case.patient_id] = owed.get(case.patient_id, 0) + amount
        opened = case.created_at.date() if case.created_at else today
        oldest[case.patient_id] = min(oldest.get(case.patient_id, opened), opened)
    for pid, amount in sorted(owed.items(), key=lambda kv: kv[1], reverse=True):
        patient = patients.get(pid)
        name = patient.name if patient else "Patient"
        cold = (today - oldest.get(pid, today)).days >= COLD_DAYS
        big = amount >= LARGE_BALANCE
        out.append(
            schemas.Reminder(
                kind="large_balance_cold" if (big and cold) else "outstanding",
                severity="high" if (big and cold) else "medium",
                message=(
                    f"{name} owes Rs {amount:,}"
                    + (" — large balance going cold" if (big and cold) else "")
                ),
                entity_type="patient",
                entity_id=pid,
            )
        )

    # Open periods past their end date are due to close & settle.
    due = session.scalars(
        select(Period).where(
            Period.clinic_id == member.clinic_id,
            Period.deleted_at.is_(None),
            Period.status == PeriodStatus.OPEN,
            Period.end_date < today,
        )
    ).all()
    for period in due:
        out.append(
            schemas.Reminder(
                kind="period_due",
                severity="medium",
                message=f"Period ending {period.end_date:%Y-%m-%d} is due to close and settle",
                entity_type="period",
                entity_id=period.id,
            )
        )

    # Settlement statements with obligations not yet paid.
    statements = session.scalars(
        select(SettlementStatement).where(
            SettlementStatement.clinic_id == member.clinic_id,
            SettlementStatement.deleted_at.is_(None),
        )
    ).all()
    for stmt in statements:
        unpaid = session.scalars(
            select(SettlementObligation).where(
                SettlementObligation.statement_id == stmt.id,
                SettlementObligation.paid_movement_id.is_(None),
            )
        ).all()
        if unpaid:
            owed_total = sum(o.amount for o in unpaid)
            out.append(
                schemas.Reminder(
                    kind="settlement_unpaid",
                    severity="medium",
                    message=f"Settlement statement #{stmt.id} has Rs {owed_total:,} unpaid",
                    entity_type="settlement_statement",
                    entity_id=stmt.id,
                )
            )

    return out

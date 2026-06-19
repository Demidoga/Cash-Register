"""Exports & data ownership (Milestone 8): the data is never trapped.

CSV journal (the accountant's escape hatch), plus PDF monthly summary and
per-patient statements.
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import CurrentMember, get_current_member
from app.models import (
    Account,
    Case,
    Category,
    MoneyMovement,
    Partner,
    Patient,
    Period,
    SettlementObligation,
    SettlementStatement,
)
from app.money_math.types import MovementType
from app.services import build_settlement, case_outstanding_value, get_scoped, list_alive

router = APIRouter(prefix="/exports", tags=["exports"])


def _names(session: Session, clinic_id: int):
    return (
        {p.id: p.name for p in list_alive(session, Partner, clinic_id)},
        {a.id: a.name for a in list_alive(session, Account, clinic_id)},
        {c.id: c.name for c in list_alive(session, Category, clinic_id)},
    )


@router.get("/journal.csv")
def journal_csv(
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    partners, accounts, categories = _names(session, member.clinic_id)
    movements = session.scalars(
        select(MoneyMovement)
        .where(MoneyMovement.clinic_id == member.clinic_id, MoneyMovement.deleted_at.is_(None))
        .order_by(MoneyMovement.date, MoneyMovement.id)
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["date", "type", "amount", "partner", "from_account", "to_account", "case_id", "category", "note"]
    )
    for m in movements:
        writer.writerow(
            [
                m.date.isoformat(),
                m.type.value,
                m.amount,
                partners.get(m.partner_id or 0, ""),
                accounts.get(m.from_account_id or 0, ""),
                accounts.get(m.to_account_id or 0, ""),
                m.case_id or "",
                categories.get(m.category_id or 0, ""),
                m.note or "",
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=journal.csv"},
    )


def _patient_statement_rows(session: Session, clinic_id: int, patient: Patient):
    cases = session.scalars(
        select(Case).where(
            Case.patient_id == patient.id, Case.clinic_id == clinic_id, Case.deleted_at.is_(None)
        )
    ).all()
    rows = []
    for case in cases:
        paid = sum(
            session.scalars(
                select(MoneyMovement.amount).where(
                    MoneyMovement.case_id == case.id,
                    MoneyMovement.type == MovementType.INCOME,
                    MoneyMovement.deleted_at.is_(None),
                )
            ).all()
        )
        rows.append(
            {
                "procedure": case.procedure_name,
                "agreed_price": case.agreed_price,
                "paid": paid,
                "outstanding": case_outstanding_value(session, clinic_id, case),
            }
        )
    return rows


@router.get("/patients/{patient_id}/statement.csv")
def patient_statement_csv(
    patient_id: int,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    patient = get_scoped(session, Patient, patient_id, member.clinic_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "patient not found")
    rows = _patient_statement_rows(session, member.clinic_id, patient)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["procedure", "agreed_price", "paid", "outstanding"])
    for r in rows:
        writer.writerow([r["procedure"], r["agreed_price"], r["paid"], r["outstanding"]])
    writer.writerow([])
    writer.writerow(["TOTAL", "", "", sum(r["outstanding"] for r in rows)])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=statement-{patient.name}.csv"
        },
    )


def _pdf(title: str, lines: list[tuple[str, str]], table: list[list[str]] | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=title)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    for label, value in lines:
        story.append(Paragraph(f"<b>{label}:</b> {value}", styles["Normal"]))
    if table:
        story.append(Spacer(1, 12))
        t = Table(table, hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ]
            )
        )
        story.append(t)
    doc.build(story)
    return buffer.getvalue()


@router.get("/periods/{period_id}/summary.pdf")
def period_summary_pdf(
    period_id: int,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    period = get_scoped(session, Period, period_id, member.clinic_id)
    if period is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "period not found")
    try:
        computed = build_settlement(session, member.clinic_id, period)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    partners = {p.id: p.name for p in list_alive(session, Partner, member.clinic_id)}

    table = [["Partner", "Personal profit", "Settlement balance"]]
    for pid, balance in computed.settlement_balance.items():
        table.append(
            [partners.get(pid, str(pid)), f"{computed.personal_profit.get(pid, 0):,}", f"{balance:,}"]
        )
    pdf = _pdf(
        "Monthly Summary",
        [
            ("Period", f"{period.start_date:%Y-%m-%d} to {period.end_date:%Y-%m-%d}"),
            ("Net profit", f"Rs {computed.profit:,}"),
            ("Joint pool (standing)", f"Rs {computed.joint_standing:,}"),
        ],
        table,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=summary-{period.id}.pdf"},
    )


@router.get("/patients/{patient_id}/statement.pdf")
def patient_statement_pdf(
    patient_id: int,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    patient = get_scoped(session, Patient, patient_id, member.clinic_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "patient not found")
    rows = _patient_statement_rows(session, member.clinic_id, patient)
    table = [["Procedure", "Agreed", "Paid", "Outstanding"]]
    for r in rows:
        table.append(
            [r["procedure"], f"{r['agreed_price']:,}", f"{r['paid']:,}", f"{r['outstanding']:,}"]
        )
    pdf = _pdf(
        "Patient Statement",
        [("Patient", patient.name), ("Phone", patient.phone or "—"),
         ("Total outstanding", f"Rs {sum(r['outstanding'] for r in rows):,}")],
        table,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=statement-{patient.id}.pdf"},
    )

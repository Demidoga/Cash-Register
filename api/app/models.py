"""SQLAlchemy 2.0 models for the Clinic Cash Register.

Every top-level table carries ``clinic_id`` (ADR-0005), is soft-delete-capable
(``deleted_at``), and is audit-stamped (``created_by`` / ``updated_by``) — these
are foundational from Milestone 0 (ADR-0006), even though their UI surfaces ship
in later milestones. Money is stored as integer rupees (ADR-0001/0007).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.money_math.types import AccountKind, MovementType


class Role(str, Enum):
    OWNER = "owner"
    PARTNER = "partner"
    STAFF = "staff"  # dormant in V1 (ADR / PRD)


class PeriodStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class AdjustmentType(str, Enum):
    DISCOUNT = "discount"
    WRITE_OFF = "write_off"


def _enum_col(python_enum: type[Enum], **kw):
    """A VARCHAR-backed enum column that stores the member *values* — portable
    across SQLite (tests) and Postgres (prod)."""
    return mapped_column(
        SAEnum(
            python_enum,
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        **kw,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


class AuditMixin:
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Clinic(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "clinics"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="PKR")


class User(Base, TimestampMixin, SoftDeleteMixin):
    """A global authenticated identity (from Supabase). Access to the clinic is
    granted by a Membership row — the allowlist (ADR-0005)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    supabase_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Membership(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """The allowlist: a user's role within a clinic."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("clinic_id", "user_id", name="uq_membership"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[Role] = _enum_col(Role, nullable=False, default=Role.PARTNER)


class Partner(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "partners"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ShareWindow(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """An effective-dated set of partner shares (ADR-0004)."""

    __tablename__ = "share_windows"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)


class PartnerShare(Base):
    """One partner's share within a window, stored as an exact fraction."""

    __tablename__ = "partner_shares"

    id: Mapped[int] = mapped_column(primary_key=True)
    share_window_id: Mapped[int] = mapped_column(
        ForeignKey("share_windows.id"), nullable=False, index=True
    )
    partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id"), nullable=False)
    share_num: Mapped[int] = mapped_column(Integer, nullable=False)
    share_den: Mapped[int] = mapped_column(Integer, nullable=False)


class Account(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[AccountKind] = _enum_col(AccountKind, nullable=False)
    owner_partner_id: Mapped[int | None] = mapped_column(ForeignKey("partners.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    opening_balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class Patient(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)


class Case(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """A treatment case: agreed price, against which payments accumulate."""

    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    procedure_name: Mapped[str] = mapped_column(String(200), nullable=False)
    procedure_id: Mapped[int | None] = mapped_column(ForeignKey("procedures.id"), nullable=True)
    agreed_price: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")


class Period(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[PeriodStatus] = _enum_col(PeriodStatus, nullable=False, default=PeriodStatus.OPEN)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class MoneyMovement(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """One typed cash event with optional from/to legs (ADR-0007)."""

    __tablename__ = "money_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    type: Mapped[MovementType] = _enum_col(MovementType, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    partner_id: Mapped[int | None] = mapped_column(ForeignKey("partners.id"), nullable=True)
    from_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    to_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    # Set when this Transfer is a settlement payment against a statement (ADR-0003).
    settlement_statement_id: Mapped[int | None] = mapped_column(
        ForeignKey("settlement_statements.id"), nullable=True
    )


class SettlementStatement(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """The locked artifact a close produces (ADR-0003). Closing moves no cash."""

    __tablename__ = "settlement_statements"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"), nullable=False, index=True)
    profit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    joint_standing: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class SettlementBalance(Base):
    __tablename__ = "settlement_balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    statement_id: Mapped[int] = mapped_column(
        ForeignKey("settlement_statements.id"), nullable=False, index=True
    )
    partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id"), nullable=False)
    personal_profit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    settlement_balance: Mapped[int] = mapped_column(BigInteger, nullable=False)


class SettlementObligation(Base):
    """A single "X pays Y" line; marked paid when matched by a Transfer."""

    __tablename__ = "settlement_obligations"

    id: Mapped[int] = mapped_column(primary_key=True)
    statement_id: Mapped[int] = mapped_column(
        ForeignKey("settlement_statements.id"), nullable=False, index=True
    )
    from_partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id"), nullable=False)
    to_partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id"), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    paid_movement_id: Mapped[int | None] = mapped_column(
        ForeignKey("money_movements.id"), nullable=True
    )


class Category(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """An editable expense category (PRD story 15)."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class Procedure(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """A catalog procedure with an overridable default price (PRD story 16)."""

    __tablename__ = "procedures"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    default_price: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class Employee(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """A light employee entity that salary expenses reference (PRD story 17)."""

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    salary: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class CaseAdjustment(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """A discount or write-off against a case (PRD stories 59-60). Reduces what
    is owed; a write-off is explicitly **not** income."""

    __tablename__ = "case_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    type: Mapped[AdjustmentType] = _enum_col(AdjustmentType, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    note: Mapped[str | None] = mapped_column(String, nullable=True)


class AuditLog(Base):
    """Who changed what and when — complete from the first write (ADR-0006)."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

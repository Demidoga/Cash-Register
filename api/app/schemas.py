"""Pydantic request/response schemas (the API contract surface)."""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import PeriodStatus, Role
from app.money_math.types import AccountKind, MovementType

# --- setup / config ----------------------------------------------------------


class PartnerInput(BaseModel):
    name: str
    share_num: int = Field(gt=0)
    share_den: int = Field(gt=0)


class AccountInput(BaseModel):
    name: str
    kind: AccountKind
    owner_partner_index: int | None = None  # index into the partners list (personal)
    opening_balance: int = 0


class SetupRequest(BaseModel):
    clinic_name: str | None = None
    currency: str = "PKR"
    effective_from: datetime.date
    partners: list[PartnerInput] = Field(min_length=1)
    accounts: list[AccountInput] = Field(min_length=1)


class PartnerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    kind: AccountKind
    owner_partner_id: int | None
    opening_balance: int


class SetupResponse(BaseModel):
    clinic_id: int
    share_window_id: int
    partners: list[PartnerOut]
    accounts: list[AccountOut]


class MeResponse(BaseModel):
    user_id: int
    email: str
    clinic_id: int
    role: Role


# --- members / allowlist (invite by email, ADR-0008) -------------------------


class InviteRequest(BaseModel):
    # Plain str (not EmailStr) to avoid the email-validator dependency; the
    # router lowercases and does a minimal shape check (matches get_identity).
    email: str


class MemberOut(BaseModel):
    id: int  # the Membership id (the thing you revoke), not the user id
    user_id: int
    email: str
    full_name: str | None
    role: Role
    # "pending" until the invitee first signs in and the stub is backfilled.
    status: str


class InviteResponse(BaseModel):
    member: MemberOut
    # "invited" (new), "reactivated" (revoked email re-invited), or
    # "already_member" (idempotent no-op).
    status: str


# --- patients / cases --------------------------------------------------------


class PatientCreate(BaseModel):
    name: str
    phone: str | None = None
    notes: str | None = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    phone: str | None
    notes: str | None


class PatientDetailOut(BaseModel):
    id: int
    name: str
    phone: str | None
    notes: str | None
    total_outstanding: int
    cases: list["CaseOut"]


class CaseCreate(BaseModel):
    patient_id: int
    procedure_name: str
    procedure_id: int | None = None
    agreed_price: int = Field(ge=0)


class CaseOut(BaseModel):
    id: int
    patient_id: int
    procedure_name: str
    agreed_price: int
    status: str
    outstanding: int


# --- movements ---------------------------------------------------------------


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: MovementType
    amount: int
    date: datetime.date
    partner_id: int | None
    from_account_id: int | None
    to_account_id: int | None
    case_id: int | None
    note: str | None


class TakePaymentRequest(BaseModel):
    case_id: int
    account_id: int
    partner_id: int
    amount: int = Field(gt=0)
    date: datetime.date | None = None  # defaults to today (smart default, story 21)
    note: str | None = None


class TakePaymentResponse(BaseModel):
    movement: MovementOut
    case: CaseOut


# --- periods / settlement ----------------------------------------------------


class PeriodCreate(BaseModel):
    start_date: datetime.date
    end_date: datetime.date


class PeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    start_date: datetime.date
    end_date: datetime.date
    status: PeriodStatus


class SettlementBalanceOut(BaseModel):
    partner_id: int
    personal_profit: int
    settlement_balance: int


class SettlementObligationOut(BaseModel):
    id: int
    from_partner_id: int
    to_partner_id: int
    amount: int
    paid: bool


class SettlementStatementOut(BaseModel):
    id: int
    period_id: int
    profit: int
    joint_standing: int
    balances: list[SettlementBalanceOut]
    obligations: list[SettlementObligationOut]


class SettlementPaymentRequest(BaseModel):
    obligation_id: int
    from_account_id: int
    to_account_id: int
    # A settlement payment settles its obligation in full (one payment per
    # obligation in V1); partial settlement is a later concern.
    date: datetime.date | None = None
    note: str | None = None


# --- dashboard ---------------------------------------------------------------


class AccountBalanceOut(BaseModel):
    account_id: int
    name: str
    balance: int


class DashboardSummary(BaseModel):
    period_id: int | None
    income: int
    expense: int
    net_profit: int
    account_balances: list[AccountBalanceOut]


# --- configuration (Milestone 1) ---------------------------------------------


class CategoryCreate(BaseModel):
    name: str


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class ProcedureCreate(BaseModel):
    name: str
    default_price: int = Field(ge=0, default=0)


class ProcedureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    default_price: int


class EmployeeCreate(BaseModel):
    name: str
    role: str | None = None
    salary: int = Field(ge=0, default=0)


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    role: str | None
    salary: int


class AccountCreate(BaseModel):
    name: str
    kind: AccountKind
    owner_partner_id: int | None = None
    opening_balance: int = 0


class AccountUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None  # enable/disable (e.g. the joint account, story 14)


class AccountFullOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    kind: AccountKind
    owner_partner_id: int | None
    opening_balance: int
    is_active: bool


class ShareEntry(BaseModel):
    partner_id: int
    share_num: int = Field(gt=0)
    share_den: int = Field(gt=0)


class ShareWindowCreate(BaseModel):
    effective_from: datetime.date
    shares: list[ShareEntry] = Field(min_length=1)


class ShareWindowOut(BaseModel):
    id: int
    effective_from: datetime.date
    shares: list[ShareEntry]


# --- money entry (Milestone 2) -----------------------------------------------


class LogExpenseRequest(BaseModel):
    account_id: int
    partner_id: int
    amount: int = Field(gt=0)
    category_id: int | None = None
    case_id: int | None = None
    date: datetime.date | None = None
    note: str | None = None


class TransferRequest(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: int = Field(gt=0)
    partner_id: int | None = None
    date: datetime.date | None = None
    note: str | None = None


class CapitalRequest(BaseModel):
    account_id: int  # destination (money in)
    partner_id: int
    amount: int = Field(gt=0)
    date: datetime.date | None = None
    note: str | None = None


class DrawingRequest(BaseModel):
    account_id: int  # source (money out)
    partner_id: int
    amount: int = Field(gt=0)
    date: datetime.date | None = None
    note: str | None = None


class RefundRequest(BaseModel):
    case_id: int
    account_id: int  # the account the refunded cash leaves
    partner_id: int
    amount: int = Field(gt=0)
    date: datetime.date | None = None
    note: str | None = None


# --- corrections & adjustments (Milestone 6) ---------------------------------


class MovementUpdate(BaseModel):
    amount: int | None = None
    date: datetime.date | None = None
    note: str | None = None
    category_id: int | None = None


class AdjustmentRequest(BaseModel):
    # For a write-off, omit amount to clear the whole current outstanding.
    amount: int | None = None
    note: str | None = None


class AdjustmentOut(BaseModel):
    id: int
    case_id: int
    type: str
    amount: int
    note: str | None


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int | None
    action: str
    entity_type: str
    entity_id: int | None
    at: datetime.datetime


# --- reports (Milestone 4) ---------------------------------------------------


class PnL(BaseModel):
    start: datetime.date | None
    end: datetime.date | None
    income: int
    expense: int
    net_profit: int


class CategoryTotal(BaseModel):
    category_id: int | None
    name: str
    total: int


class ProcedureStat(BaseModel):
    procedure_name: str
    count: int
    revenue: int


class CollectorTotal(BaseModel):
    partner_id: int
    name: str
    collected: int


class ReceivableRow(BaseModel):
    patient_id: int
    name: str
    outstanding: int


class Receivables(BaseModel):
    total: int
    rows: list[ReceivableRow]


class TrendPoint(BaseModel):
    month: str
    income: int
    expense: int
    net_profit: int


class PartnerContribution(BaseModel):
    partner_id: int
    name: str
    collected: int
    paid: int
    entitled: int


# --- reminders (Milestone 7) -------------------------------------------------


class Reminder(BaseModel):
    kind: str
    severity: str
    message: str
    entity_type: str | None = None
    entity_id: int | None = None


# --- dev auth (local runnability only) ---------------------------------------


class DevLoginRequest(BaseModel):
    email: str
    name: str | None = None


class DevLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

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

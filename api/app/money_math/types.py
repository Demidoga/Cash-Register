"""Pure value types for the money-math seam — no I/O, no framework imports.

These mirror the domain glossary (see ``context.md``) but are deliberately
decoupled from the SQLAlchemy models so the settlement/profit arithmetic can be
proven in isolation (the secondary test seam, ADR-0001).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from fractions import Fraction


class MovementType(str, Enum):
    """The five money-movement types. Only INCOME/EXPENSE affect profit."""

    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    CAPITAL = "capital"
    DRAWING = "drawing"


class AccountKind(str, Enum):
    PERSONAL = "personal"
    JOINT = "joint"


@dataclass(frozen=True)
class Account:
    """A cash container. ``owner_partner_id`` is required for personal accounts."""

    id: int
    kind: AccountKind
    owner_partner_id: int | None = None


@dataclass(frozen=True)
class Movement:
    """A single cash event with optional from/to legs (ADR-0007).

    Income/Capital fill ``to_account_id``; Expense/Drawing fill
    ``from_account_id``; Transfer fills both. ``amount`` is non-negative
    integer rupees; the leg directions carry the sign.
    """

    type: MovementType
    amount: int
    date: date
    partner_id: int | None = None
    from_account_id: int | None = None
    to_account_id: int | None = None


@dataclass(frozen=True)
class ShareWindow:
    """An effective-dated set of partner shares. ``shares`` must sum to 1."""

    effective_from: date
    shares: dict[int, Fraction]


@dataclass(frozen=True)
class SettlementTransfer:
    """One leg of the minimal settlement: ``from`` pays ``to`` ``amount`` rupees."""

    from_partner_id: int
    to_partner_id: int
    amount: int


@dataclass(frozen=True)
class SettlementStatement:
    """The computed obligations for a closed period (ADR-0003).

    ``settlement_balance`` > 0 ⇒ partner holds more profit than their share ⇒
    pays in; < 0 ⇒ is owed. The joint pool stays standing (ADR-0002).
    """

    profit: int
    joint_standing: int
    personal_profit: dict[int, int]
    settlement_balance: dict[int, int]
    transfers: list[SettlementTransfer] = field(default_factory=list)

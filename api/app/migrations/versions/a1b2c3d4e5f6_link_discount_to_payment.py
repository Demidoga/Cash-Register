"""link ride-along discount to its payment

Adds case_adjustments.movement_id so a discount recorded alongside a payment
(take_payment) points back to that MoneyMovement. Lets editing the payment
rewrite its own discount instead of stacking a new adjustment.

Revision ID: a1b2c3d4e5f6
Revises: 6e352769454d
Create Date: 2026-06-22 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '6e352769454d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('case_adjustments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('movement_id', sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_case_adjustments_movement_id'), ['movement_id'], unique=False
        )
        batch_op.create_foreign_key(
            batch_op.f('fk_case_adjustments_movement_id_money_movements'),
            'money_movements', ['movement_id'], ['id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('case_adjustments', schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f('fk_case_adjustments_movement_id_money_movements'), type_='foreignkey'
        )
        batch_op.drop_index(batch_op.f('ix_case_adjustments_movement_id'))
        batch_op.drop_column('movement_id')

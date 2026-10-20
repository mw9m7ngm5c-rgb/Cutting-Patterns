"""planner: a typical log per class, and sample logs

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('log_class') as b:
        b.add_column(sa.Column('plan_length_m', sa.Float(), nullable=True))
        b.add_column(sa.Column('plan_taper', sa.Float(), nullable=True))
    with op.batch_alter_table('log') as b:
        b.add_column(sa.Column('sample', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('log') as b:
        b.drop_column('sample')
    with op.batch_alter_table('log_class') as b:
        b.drop_column('plan_taper')
        b.drop_column('plan_length_m')

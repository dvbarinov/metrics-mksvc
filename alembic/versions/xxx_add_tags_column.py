"""add tags column to metrics table

Revision ID: xxx
Revises: xxx
Create Date: 2026-02-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'xxx'
down_revision = 'xxx'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('metrics', sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'))
    op.create_index('ix_metrics_tags', 'metrics', ['tags'], unique=False, postgresql_using='gin')

def downgrade():
    op.drop_index('ix_metrics_tags', table_name='metrics')
    op.drop_column('metrics', 'tags')

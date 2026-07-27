"""AI Broadcast Campaign — Audience Selection (CSV/manual/groups/tags)

NEW: Purely additive. Backs the missing audience-selection step of the
Campaign Manager (Step 2 of the Campaign Flow):
- campaigns.audience_type / audience_config     which audience source +
                                                 its parameters a campaign
                                                 was launched with
- whatsapp_contacts.city / company / tags       personalization + tag
                                                 filtering on existing
                                                 opted-in contacts
- campaign_recipients.contact_city / contact_company / source
                                                 personalization snapshot +
                                                 audience-source tracking
                                                 per recipient
- contact_groups / contact_group_members        new tables backing the
                                                 "Contact groups" audience
                                                 source

Revision ID: 022_campaign_audience
Revises: 021_personal_email_part2
Create Date: 2026-07-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '022_campaign_audience'
down_revision = '021_personal_email_part2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('campaigns', sa.Column('audience_type', sa.String(20), nullable=False, server_default='contacts'))
    op.add_column('campaigns', sa.Column('audience_config', postgresql.JSONB(), nullable=False, server_default='{}'))

    op.add_column('whatsapp_contacts', sa.Column('city', sa.String(255), nullable=True))
    op.add_column('whatsapp_contacts', sa.Column('company', sa.String(255), nullable=True))
    op.add_column('whatsapp_contacts', sa.Column('tags', postgresql.JSONB(), nullable=False, server_default='[]'))

    op.add_column('campaign_recipients', sa.Column('contact_city', sa.String(255), nullable=True))
    op.add_column('campaign_recipients', sa.Column('contact_company', sa.String(255), nullable=True))
    op.add_column('campaign_recipients', sa.Column('source', sa.String(20), nullable=False, server_default='contacts'))

    op.create_table(
        'contact_groups',
        sa.Column('id',         sa.String(36), primary_key=True),
        sa.Column('user_id',    sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name',       sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_contact_groups_user_id', 'contact_groups', ['user_id'])

    op.create_table(
        'contact_group_members',
        sa.Column('id',            sa.String(36), primary_key=True),
        sa.Column('group_id',      sa.String(36),
                  sa.ForeignKey('contact_groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('wa_id',         sa.String(32), nullable=False),
        sa.Column('contact_name',  sa.String(255)),
        sa.Column('city',          sa.String(255)),
        sa.Column('company',       sa.String(255)),
        sa.Column('created_at',    sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('group_id', 'wa_id', name='uq_contact_group_member_wa_id'),
    )
    op.create_index('idx_contact_group_members_group', 'contact_group_members', ['group_id'])


def downgrade() -> None:
    op.drop_index('idx_contact_group_members_group', table_name='contact_group_members')
    op.drop_table('contact_group_members')
    op.drop_index('ix_contact_groups_user_id', table_name='contact_groups')
    op.drop_table('contact_groups')

    op.drop_column('campaign_recipients', 'source')
    op.drop_column('campaign_recipients', 'contact_company')
    op.drop_column('campaign_recipients', 'contact_city')

    op.drop_column('whatsapp_contacts', 'tags')
    op.drop_column('whatsapp_contacts', 'company')
    op.drop_column('whatsapp_contacts', 'city')

    op.drop_column('campaigns', 'audience_config')
    op.drop_column('campaigns', 'audience_type')

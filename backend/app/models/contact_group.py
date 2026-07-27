"""
ThunderBots AI Broadcast Campaign — Contact Groups
NEW: Purely additive. Two small tables backing the "Contact groups" audience
source in the Campaign Manager's audience picker (app/api/v1/campaigns.py,
app/services/audience_service.py). Does not touch WhatsAppContact,
Workflow, or Campaign execution in any way.

- contact_groups          A named list a business owner curates once (e.g.
                          "VIP Customers", "Mumbai Store") and reuses across
                          campaigns.
- contact_group_members   The phone numbers in a group. Deliberately stores
                          its own contact_name/city/company snapshot (not a
                          FK to WhatsAppContact) so a group can include
                          numbers that have never messaged the bot yet
                          (e.g. added via CSV) — audience_service.py merges
                          this with live WhatsAppContact data by wa_id when
                          both exist.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class ContactGroup(Base):
    __tablename__ = "contact_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    members: Mapped[list["ContactGroupMember"]] = relationship(
        "ContactGroupMember", back_populates="group", cascade="all, delete-orphan", passive_deletes=True
    )


class ContactGroupMember(Base):
    __tablename__ = "contact_group_members"

    __table_args__ = (
        UniqueConstraint("group_id", "wa_id", name="uq_contact_group_member_wa_id"),
        Index("idx_contact_group_members_group", "group_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("contact_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    wa_id: Mapped[str] = mapped_column(String(32), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    group: Mapped["ContactGroup"] = relationship(
        "ContactGroup", back_populates="members", passive_deletes=True
    )

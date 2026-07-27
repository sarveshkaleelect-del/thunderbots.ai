"""
ThunderBots Interactive Tutorial System — persistence (NEW, v106)

Purely additive: one new table, no existing model/table touched. Stores,
per user and per feature key, which step the user is on and whether the
tutorial for that feature has been completed/skipped. This is what lets a
completed tutorial stay hidden across sessions/devices until the user
explicitly hits "Restart" (see frontend store/tutorialStore.ts).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Integer, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class TutorialProgress(Base):
    __tablename__ = "tutorial_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "feature_key", name="uq_tutorial_progress_user_feature"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Matches a key in the frontend tutorial registry, e.g. "dashboard",
    # "workflow-builder", "shop-assistant", "ai-chat", "knowledge-base",
    # "call-agent". Free-form string so new features never need a migration.
    feature_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_started")  # not_started | in_progress | completed | skipped
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )

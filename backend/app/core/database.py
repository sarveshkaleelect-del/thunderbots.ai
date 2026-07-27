import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

logger = logging.getLogger(__name__)


def _async_url(url: str) -> str:
    """Normalize postgres URL to asyncpg driver format."""

    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix):]
            break

    url = url.replace("sslmode=require", "ssl=require")

    return url


engine = create_async_engine(
    _async_url(settings.DATABASE_URL),
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,       # re-checks connection before use (handles DB restarts)
    pool_recycle=3600,        # recycle connections every hour
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,   # keep ORM objects usable after commit
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    """
    Creates all tables from ORM metadata.
    Used for development. In production, use: alembic upgrade head
    """
    from app.models import user, workflow, knowledge, analytics, whatsapp, team, notification, session, audit_log, campaign, campaign_broadcast, live_agent, ai_supervisor, personal_email, shop_assistant  # noqa: F401 — register metadata
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified/created via create_all")
    except Exception as e:
        logger.error(f"Database init failed: {e}")
        raise


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

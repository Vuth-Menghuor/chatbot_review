"""Async SQLAlchemy engine and session factory for the operational database."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_engine = None
_session_factory = None


def get_operational_engine():
    """Get or create the operational DB engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.operational_db_url,
            echo=settings.debug,
            pool_size=10,
            max_overflow=5,
            pool_pre_ping=True,
        )
    return _engine


def get_operational_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory for operational DB."""
    global _session_factory
    if _session_factory is None:
        engine = get_operational_engine()
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def get_operational_session():
    """FastAPI dependency that yields an operational DB session."""
    factory = get_operational_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def close_operational_engine() -> None:
    """Dispose the operational engine on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None

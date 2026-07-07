"""Async SQLAlchemy engine and session factory for the metadata database."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_engine = None
_session_factory = None


def get_metadata_engine():
    """Get or create the metadata DB engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.metadata_db_url,
            echo=settings.debug,
            pool_size=10,
            max_overflow=5,
            pool_pre_ping=True,
        )
    return _engine


def get_metadata_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory for metadata DB."""
    global _session_factory
    if _session_factory is None:
        engine = get_metadata_engine()
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def get_metadata_session():
    """FastAPI dependency that yields a metadata DB session."""
    factory = get_metadata_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def close_metadata_engine() -> None:
    """Dispose the metadata engine on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None

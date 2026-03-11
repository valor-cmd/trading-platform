from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


engine = None
async_session = None


def init_db(database_url: str):
    global engine, async_session
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
    engine = create_async_engine(database_url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    if async_session is None:
        raise RuntimeError("Database not initialized. Running in paper mode.")
    async with async_session() as session:
        yield session

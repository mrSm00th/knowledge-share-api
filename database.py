from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

DATABASE_URL = "sqlite+aiosqlite:///./knowledge_share.db"

engine = create_async_engine(DATABASE_URL, conect_args={"check_same_thread": False})

local_asyncSession = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()


async def get_db():
    async with local_asyncSession() as session:
        yield session

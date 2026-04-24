from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.models.base import Base

# Import all models so their tables are registered on Base.metadata
import app.models.plan_config  # noqa: F401
import app.models.employer     # noqa: F401
import app.models.member       # noqa: F401
import app.models.address      # noqa: F401
import app.models.contact      # noqa: F401
import app.models.beneficiary  # noqa: F401
import app.models.employment   # noqa: F401
import app.models.salary       # noqa: F401
import app.models.leave        # noqa: F401
import app.models.service_credit  # noqa: F401

TEST_DATABASE_URL = settings.database_url.replace("/openflow_pension", "/openflow_pension_test")


@pytest_asyncio.fixture(scope="function")
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture(scope="function")
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine, expire_on_commit=False) as sess:
        yield sess
        await sess.rollback()

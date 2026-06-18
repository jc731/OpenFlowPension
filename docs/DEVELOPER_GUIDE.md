# Developer Guide

How to add a module, a config key, and what patterns the codebase uses. Read `CLAUDE.md` first for the invariants and module index; this document is the recipe layer on top of that.

---

## Adding a module

Every module follows the same three-layer pattern: **model → service → router**. This checklist covers all eight steps in order.

### 1. Model

Create `app/models/your_module.py`. Subclass `TimestampMixin, Base`:

```python
from app.models.base import Base, TimestampMixin

class YourThing(TimestampMixin, Base):
    __tablename__ = "your_things"

    name: Mapped[str] = mapped_column(String, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    # FK example — no cascade on financial/ledger relationships
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=False
    )
```

Conventions:
- `TimestampMixin` gives you `id` (UUID, `gen_random_uuid()`), `created_at`, and `updated_at` — don't redefine them
- All timestamps are `DateTime(timezone=True)` — no naive datetimes anywhere
- No `cascade="all, delete"` on relationships to financial or history tables
- FKs reference the table name string, not the Python class

Register the model in two places:

**`app/models/__init__.py`** — add the import and add to `__all__`:
```python
from app.models.your_module import YourThing
# add "YourThing" to __all__
```

**`tests/conftest.py`** — add the import so the table is created in the test database:
```python
import app.models.your_module  # noqa: F401
```

### 2. Schema

Create `app/schemas/your_module.py`. Use Pydantic v2 with `ConfigDict(from_attributes=True)` on every response schema:

```python
from pydantic import BaseModel, ConfigDict
from datetime import date
import uuid

class YourThingCreate(BaseModel):
    name: str
    effective_date: date
    member_id: uuid.UUID

class YourThingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    effective_date: date
    member_id: uuid.UUID
```

Rules:
- Separate `Create` and `Read` schemas — `Read` has `id` and timestamps, `Create` does not
- Never include `*_encrypted` fields in any response schema
- Expose `ssn_last_four` and `account_last_four` for display; never the encrypted value

### 3. Service

Create `app/services/your_module_service.py`. All business logic lives here — routers are thin.

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.your_module import YourThing
from app.services.config_service import get_config

async def create_thing(name: str, member_id: uuid.UUID, session: AsyncSession) -> YourThing:
    # Fund rules come from config, never hardcoded
    config = await get_config("your_config_key", date.today(), session)
    rule = config.config_value["some_rule"]

    thing = YourThing(name=name, member_id=member_id, effective_date=date.today())
    session.add(thing)
    await session.flush()
    return thing
```

Key rules:
- Accept `session: AsyncSession` as a parameter — never create sessions inside services
- Use `await session.flush()` after adds to get the DB-assigned `id` without committing
- The router owns the transaction (`async with session.begin()`) — services do not commit
- For ledger tables: new row + void original. Never `UPDATE` or `DELETE` applied records
- `get_config(key, as_of, session)` raises `ConfigNotFoundError` if the key is missing — let it propagate rather than silently defaulting to a hardcoded value

### 4. Router

Create `app/api/v1/routers/your_module.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, principal_uuid, require_scope
from app.database import get_session
from app.schemas.your_module import YourThingCreate, YourThingRead
from app.services import your_module_service

router = APIRouter(tags=["your-module"])

@router.post("/your-things", response_model=YourThingRead, status_code=201)
async def create_thing(
    body: YourThingCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("member:write")),
):
    async with session.begin():
        thing = await your_module_service.create_thing(
            name=body.name,
            member_id=body.member_id,
            session=session,
        )
        return YourThingRead.model_validate(thing)
```

Rules:
- `Depends(get_session)` not `get_db` — `get_session` is the correct import from `app.database`
- `async with session.begin()` wraps the write path; reads can omit the transaction if they don't write
- `require_scope("scope")` gates the endpoint; `"*"` in scopes = all permissions (dev bypass only)
- Return `Schema.model_validate(orm_object)` — don't return ORM objects directly
- No business logic in the router; if you're doing more than calling a service function and returning its result, move it to the service

### 5. Register the router

In `app/main.py`, add the import and `include_router` call alongside the others:

```python
from app.api.v1.routers.your_module import router as your_module_router
# ...
app.include_router(your_module_router, prefix="/api/v1")
```

If you forget this step, the router import error won't surface until `test_smoke.py` runs — which is exactly what the smoke test is for.

### 6. Migration

```bash
alembic revision --autogenerate -m "add your_things table"
```

Always review the generated file in `alembic/versions/` before running it. Autogenerate misses: index creation on non-FK columns, custom column defaults, and `server_default` expressions. Add those manually if needed.

```bash
make migrate   # applies to the running container's DB
```

### 7. Tests

Create `tests/test_your_module_service.py`. The pattern in this project uses async helper functions (not pytest fixtures) to build test data:

```python
import pytest
from datetime import date
from app.models.member import Member
from app.services import your_module_service as svc


async def _make_member(session) -> Member:
    # build the minimum required graph for this test
    tier = PlanTier(tier_code="t1", tier_label="Tier I", effective_date=date(1980, 1, 1))
    plan = PlanType(plan_code="db", plan_label="DB")
    session.add_all([tier, plan])
    await session.flush()
    member = Member(
        member_number="T001",
        first_name="Test",
        last_name="User",
        date_of_birth=date(1970, 1, 1),
        ssn_encrypted=encrypt_ssn("111223333"),
        ssn_last_four="3333",
        plan_tier_id=tier.id,
        plan_type_id=plan.id,
    )
    session.add(member)
    await session.flush()
    return member


@pytest.mark.asyncio
async def test_create_thing(session):
    member = await _make_member(session)
    thing = await svc.create_thing(name="foo", member_id=member.id, session=session)
    assert thing.id is not None
    assert thing.name == "foo"
```

The `session` fixture (from `conftest.py`) creates a fresh schema per test function and rolls back after — tests are isolated by default.

If your service requires a `system_configurations` row, seed it in the test using `SystemConfiguration` directly rather than calling `get_config` and hoping the key exists.

### 8. Documentation

Two files must be updated when a module ships:

**`CLAUDE.md` module index** — add a row:
```
| Your module | `app/services/your_module_service.py` | one-line summary |
```

**`docs/ARCHITECTURE.md`** — add a section with: endpoint list, service functions, key design decisions, what's implemented vs not. The goal is documenting the *why* and cross-cutting patterns, not restating what's readable from the code.

If your module spawns deferred work (things you consciously didn't build), add entries to `docs/BACKLOG.md` with design notes explaining the tradeoffs.

---

## Adding a system config key

Fund rules belong in `system_configurations`, not in code. When you need a new rule:

**1. Name the key** — snake_case, descriptive. Examples: `contribution_interest_rate`, `disability_benefit_config`.

**2. Design the JSONB schema** — document the shape before writing code. Include all fields, their types, and what happens if a field is absent. Look at existing keys in `docs/ARCHITECTURE.md` for examples.

**3. Seed a row** — add an entry to the `configs_data` list in `scripts/seed_mvp.py` with a sensible default value and an `effective_date` far enough back to cover all existing test data.

**4. Consume via config service** — call `get_config(key, as_of, session)` in your service. The `as_of` date is typically the business date of the operation (e.g. `period_end` for a payroll row, `retirement_date` for a benefit calc). Don't use `date.today()` for historical operations.

**5. Update `CLAUDE.md`** — add the key to the "Seeded" list under "System config keys".

**6. Document the schema** — add a subsection under `System configuration keys` in `docs/ARCHITECTURE.md` with the full JSONB shape, all fields, and any format differences across effective dates (see `federal_income_tax_withholding` as an example of a key whose schema changed between years).

---

## Testing patterns reference

**Session fixture** — `conftest.py` creates a fresh schema per test function, yields the session, then rolls back. Never call `session.commit()` in tests.

**Async helpers** — build test data with `async def _make_xxx(session)` functions at the top of each test file. Keep them minimal: only create the rows the test actually needs.

**Config rows in tests** — if your service calls `get_config()`, create the `SystemConfiguration` row directly in the helper:
```python
from app.models.plan_config import SystemConfiguration
from datetime import date

async def _seed_config(session):
    config = SystemConfiguration(
        config_key="your_config_key",
        config_value={"some_rule": "value"},
        effective_date=date(2000, 1, 1),
    )
    session.add(config)
    await session.flush()
```

**Smoke test** — `tests/test_smoke.py` imports `app.main` via `TestClient`, builds the OpenAPI schema, and runs a real WeasyPrint render. Run it after any router registration change or template edit. It catches the class of error the service-level suite cannot: a router that fails to import, or a PDF renderer that's silently broken.

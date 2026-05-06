"""Tests for document generation framework.

Renderer is stubbed throughout — these tests verify:
  - Context assembly (providers called, dict merged correctly)
  - Template registration and lookup
  - generate_for_member end-to-end (with stub renderer)
  - Explicit assembler override (Option A escape hatch)
  - Unknown provider raises an informative error
  - list_member_documents query
"""

from datetime import date
from decimal import Decimal

import pytest

from app.crypto import encrypt_ssn
from app.models.address import MemberAddress
from app.models.document import DocumentTemplate
from app.models.employer import Employer
from app.models.employment import EmploymentRecord
from app.models.member import Member
from app.models.plan_config import PlanTier, PlanType, SystemConfiguration
from app.models.service_credit import ServiceCreditEntry
from app.schemas.document import DocumentTemplateCreate
from app.services.document_assembler import EXPLICIT_ASSEMBLERS, assemble
from app.services.document_service import (
    create_template,
    generate_for_member,
    get_template,
    list_member_documents,
    list_templates,
)


# ── Stub renderer ─────────────────────────────────────────────────────────────

def _stub_renderer(template_file: str, context: dict) -> bytes:
    return f"PDF:{template_file}".encode()


# ── Fixtures ──────────────────────────────────────────────────────────────────

async def _setup(session):
    tier = PlanTier(tier_code="t1", tier_label="Tier I", effective_date=date(1980, 1, 1))
    plan = PlanType(plan_code="traditional", plan_label="Traditional")
    session.add_all([tier, plan])
    await session.flush()

    fund_cfg = SystemConfiguration(
        config_key="fund_info",
        config_value={"name": "Test Pension Fund", "short_name": "TPF", "phone": "555-1234"},
        effective_date=date(2000, 1, 1),
    )
    session.add(fund_cfg)

    employer = Employer(name="Test University", employer_code="TST-001", employer_type="university")
    session.add(employer)
    await session.flush()

    member = Member(
        member_number="DOC-001",
        first_name="Jane",
        last_name="Smith",
        date_of_birth=date(1965, 3, 15),
        ssn_encrypted=encrypt_ssn("123456789"),
        ssn_last_four="6789",
        certification_date=date(2000, 1, 15),
        plan_tier_id=tier.id,
        plan_type_id=plan.id,
        member_status="active",
    )
    session.add(member)
    await session.flush()

    address = MemberAddress(
        member_id=member.id,
        address_type="mailing",
        line1="123 Main St",
        city="Springfield",
        state="IL",
        zip="62701",
        effective_date=date(2000, 1, 1),
    )
    session.add(address)

    employment = EmploymentRecord(
        member_id=member.id,
        employer_id=employer.id,
        employment_type="general_staff",
        hire_date=date(2000, 1, 15),
        percent_time=100.0,
    )
    session.add(employment)
    await session.flush()

    sc = ServiceCreditEntry(
        member_id=member.id,
        employment_id=employment.id,
        entry_type="earned",
        credit_days=Decimal("20"),
        credit_years=Decimal("1.0"),
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
    )
    session.add(sc)
    await session.flush()

    return member, employer, employment


def _make_template(slug="test_letter", context=None) -> dict:
    return {
        "slug": slug,
        "document_type": "letter",
        "template_file": "benefit_estimate_letter.html",
        "description": "Test letter",
        "config_value": {"context": context or ["member_info"]},
    }


# ── Template CRUD ─────────────────────────────────────────────────────────────

async def test_create_and_get_template(session):
    async with session.begin():
        data = DocumentTemplateCreate(**_make_template())
        t = await create_template(data, session)

    assert t.slug == "test_letter"
    assert t.active is True

    async with session.begin():
        found = await get_template("test_letter", session)
    assert found.id == t.id


async def test_get_template_not_found(session):
    async with session.begin():
        with pytest.raises(ValueError, match="No active document template"):
            await get_template("does_not_exist", session)


async def test_create_duplicate_slug_raises(session):
    async with session.begin():
        data = DocumentTemplateCreate(**_make_template(slug="dup_test"))
        await create_template(data, session)

    async with session.begin():
        with pytest.raises(ValueError, match="already exists"):
            data2 = DocumentTemplateCreate(**_make_template(slug="dup_test"))
            await create_template(data2, session)


async def test_list_templates(session):
    async with session.begin():
        await create_template(DocumentTemplateCreate(**_make_template("a_letter")), session)
        await create_template(DocumentTemplateCreate(**_make_template("b_letter")), session)

    async with session.begin():
        templates = await list_templates(session)
    slugs = [t.slug for t in templates]
    assert "a_letter" in slugs
    assert "b_letter" in slugs


# ── Context assembly ──────────────────────────────────────────────────────────

async def test_assemble_fund_info_always_included(session):
    async with session.begin():
        member, _, _ = await _setup(session)
        template = DocumentTemplate(
            slug="fi_test",
            document_type="letter",
            template_file="x.html",
            config_value={"context": []},  # empty — fund_info should still appear
        )
        session.add(template)
        await session.flush()
        ctx = await assemble(template, member.id, {}, session)

    assert "fund_name" in ctx
    assert ctx["fund_name"] == "Test Pension Fund"


async def test_assemble_member_info(session):
    async with session.begin():
        member, _, _ = await _setup(session)
        template = DocumentTemplate(
            slug="mi_test",
            document_type="letter",
            template_file="x.html",
            config_value={"context": ["member_info"]},
        )
        session.add(template)
        await session.flush()
        ctx = await assemble(template, member.id, {}, session)

    assert ctx["member_full_name"] == "Jane Smith"
    assert ctx["member_number"] == "DOC-001"
    assert ctx["address_city"] == "Springfield"


async def test_assemble_service_credit_summary(session):
    async with session.begin():
        member, _, _ = await _setup(session)
        template = DocumentTemplate(
            slug="sc_test",
            document_type="letter",
            template_file="x.html",
            config_value={"context": ["service_credit_summary"]},
        )
        session.add(template)
        await session.flush()
        ctx = await assemble(template, member.id, {}, session)

    assert ctx["total_service_credit_years"] == pytest.approx(1.0)


async def test_assemble_unknown_provider_raises(session):
    async with session.begin():
        template = DocumentTemplate(
            slug="bad_provider",
            document_type="letter",
            template_file="x.html",
            config_value={"context": ["does_not_exist"]},
        )
        session.add(template)
        await session.flush()
        with pytest.raises(ValueError, match="Unknown context provider"):
            await assemble(template, None, {}, session)


async def test_explicit_assembler_override(session):
    """Registering an explicit assembler bypasses the declarative context spec."""
    async with session.begin():
        member, _, _ = await _setup(session)
        template = DocumentTemplate(
            slug="explicit_test",
            document_type="letter",
            template_file="x.html",
            config_value={"context": ["member_info"]},
        )
        session.add(template)
        await session.flush()

        # Register explicit assembler
        async def _my_assembler(mid, params, sess):
            return {"custom_key": "custom_value"}

        EXPLICIT_ASSEMBLERS["explicit_test"] = _my_assembler
        try:
            ctx = await assemble(template, member.id, {}, session)
        finally:
            EXPLICIT_ASSEMBLERS.pop("explicit_test", None)

    assert ctx == {"custom_key": "custom_value"}
    assert "member_full_name" not in ctx  # declarative path was skipped


# ── generate_for_member ───────────────────────────────────────────────────────

async def test_generate_for_member_produces_audit_record(session):
    async with session.begin():
        member, _, _ = await _setup(session)
        tmpl_data = DocumentTemplateCreate(**_make_template(
            slug="gen_test",
            context=["member_info"],
        ))
        await create_template(tmpl_data, session)

    async with session.begin():
        doc = await generate_for_member(
            slug="gen_test",
            member_id=member.id,
            params={"note": "test"},
            session=session,
            _renderer=_stub_renderer,
        )

    assert doc.status == "generated"
    assert doc.member_id == member.id
    assert doc.content == b"PDF:benefit_estimate_letter.html"
    assert doc.filename.startswith("gen_test_")
    assert doc.params == {"note": "test"}


async def test_generate_for_member_unknown_slug_raises(session):
    async with session.begin():
        with pytest.raises(ValueError, match="No active document template"):
            await generate_for_member(
                slug="ghost_slug",
                member_id=None,
                params={},
                session=session,
                _renderer=_stub_renderer,
            )


async def test_list_member_documents(session):
    async with session.begin():
        member, _, _ = await _setup(session)
        tmpl_data = DocumentTemplateCreate(**_make_template(slug="list_test", context=["member_info"]))
        await create_template(tmpl_data, session)

    async with session.begin():
        await generate_for_member("list_test", member.id, {}, session, _renderer=_stub_renderer)
        await generate_for_member("list_test", member.id, {}, session, _renderer=_stub_renderer)

    async with session.begin():
        docs = await list_member_documents(member.id, session)
    assert len(docs) == 2

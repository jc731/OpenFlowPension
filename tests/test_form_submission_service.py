"""Tests for form submission lifecycle (US-DG13)."""

from datetime import date

import pytest

from app.crypto import encrypt_ssn
from app.models.document import DocumentTemplate
from app.models.member import Member
from app.models.plan_config import PlanTier, PlanType
from app.services import form_submission_service


async def _make_member(session) -> Member:
    tier = PlanTier(tier_code="tier_1", tier_label="Tier I", effective_date=date(1980, 1, 1))
    plan = PlanType(plan_code="traditional", plan_label="Traditional")
    session.add_all([tier, plan])
    await session.flush()
    member = Member(
        member_number="FS-001",
        first_name="Alice",
        last_name="Doe",
        date_of_birth=date(1965, 1, 1),
        ssn_encrypted=encrypt_ssn("111223333"),
        ssn_last_four="3333",
        certification_date=date(2005, 1, 1),
        plan_tier_id=tier.id,
        plan_type_id=plan.id,
    )
    session.add(member)
    await session.flush()
    return member


async def _make_template(session) -> DocumentTemplate:
    tmpl = DocumentTemplate(
        slug="w4p_test",
        document_type="form",
        template_file="w4p.html",
        config_value={},
    )
    session.add(tmpl)
    await session.flush()
    return tmpl


async def test_create_form_submission_status_sent(session):
    async with session.begin():
        member = await _make_member(session)
        tmpl = await _make_template(session)
        sub = await form_submission_service.create_form_submission(tmpl.id, member.id, session)

    assert sub.status == "sent"
    assert sub.sent_at is not None


async def test_mark_returned_transitions_status(session):
    async with session.begin():
        member = await _make_member(session)
        tmpl = await _make_template(session)
        sub = await form_submission_service.create_form_submission(tmpl.id, member.id, session)
        sub_id = sub.id

    async with session.begin():
        returned = await form_submission_service.mark_returned(
            sub_id, {"filing_status": "single"}, session
        )

    assert returned.status == "returned"
    assert returned.return_data == {"filing_status": "single"}
    assert returned.returned_at is not None


async def test_mark_returned_wrong_status_raises(session):
    async with session.begin():
        member = await _make_member(session)
        tmpl = await _make_template(session)
        sub = await form_submission_service.create_form_submission(tmpl.id, member.id, session)
        sub_id = sub.id
        await form_submission_service.mark_returned(sub_id, {}, session)
        with pytest.raises(ValueError, match="Cannot mark as returned"):
            await form_submission_service.mark_returned(sub_id, {}, session)


async def test_cancel_submission(session):
    async with session.begin():
        member = await _make_member(session)
        tmpl = await _make_template(session)
        sub = await form_submission_service.create_form_submission(tmpl.id, member.id, session)
        cancelled = await form_submission_service.cancel_submission(sub.id, session)

    assert cancelled.status == "cancelled"


async def test_expire_submission(session):
    async with session.begin():
        member = await _make_member(session)
        tmpl = await _make_template(session)
        sub = await form_submission_service.create_form_submission(tmpl.id, member.id, session)
        expired = await form_submission_service.expire_submission(sub.id, session)

    assert expired.status == "expired"


async def test_list_member_submissions(session):
    async with session.begin():
        member = await _make_member(session)
        tmpl = await _make_template(session)
        await form_submission_service.create_form_submission(tmpl.id, member.id, session)
        await form_submission_service.create_form_submission(tmpl.id, member.id, session)

    subs = await form_submission_service.list_member_submissions(member.id, session)
    assert len(subs) == 2

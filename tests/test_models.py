import pytest
from pydantic import ValidationError

from app.crypto import decrypt_ssn, encrypt_ssn
from app.models.service_credit import ServiceCreditEntry
from app.schemas.beneficiary import BeneficiaryCreate


TEST_SSN = "123456789"


def test_ssn_encrypt_decrypt_roundtrip():
    ciphertext = encrypt_ssn(TEST_SSN)
    assert decrypt_ssn(ciphertext) == TEST_SSN


def test_ssn_encrypted_not_plaintext():
    ciphertext = encrypt_ssn(TEST_SSN)
    assert ciphertext != TEST_SSN.encode()
    assert ciphertext != TEST_SSN


def test_beneficiary_share_percent_zero_invalid():
    with pytest.raises(ValidationError):
        BeneficiaryCreate(
            first_name="Jane",
            last_name="Doe",
            relationship="spouse",
            beneficiary_type="primary",
            share_percent=0,
            effective_date="2020-01-01",
        )


def test_beneficiary_share_percent_over_100_invalid():
    with pytest.raises(ValidationError):
        BeneficiaryCreate(
            first_name="Jane",
            last_name="Doe",
            relationship="spouse",
            beneficiary_type="primary",
            share_percent=101,
            effective_date="2020-01-01",
        )


def test_beneficiary_share_percent_valid():
    b = BeneficiaryCreate(
        first_name="Jane",
        last_name="Doe",
        relationship="spouse",
        beneficiary_type="primary",
        share_percent=50.5,
        effective_date="2020-01-01",
    )
    assert b.share_percent == 50.5


async def test_service_credit_immutability_guard(session):
    from datetime import date, timezone
    from datetime import datetime

    from app.models.member import Member
    from app.crypto import encrypt_ssn

    member = Member(
        member_number="TEST-001",
        first_name="Test",
        last_name="User",
        date_of_birth=date(1970, 1, 1),
        ssn_encrypted=encrypt_ssn("987654321"),
        ssn_last_four="4321",
    )
    session.add(member)
    await session.flush()

    entry = ServiceCreditEntry(
        member_id=member.id,
        entry_type="earned",
        credit_days=365,
        credit_years=1.0,
        period_start=date(2020, 1, 1),
        period_end=date(2020, 12, 31),
    )
    session.add(entry)
    await session.flush()

    entry.credit_days = 366

    with pytest.raises(RuntimeError, match="append-only"):
        await session.flush()

"""Unit tests for payroll_validation_service — pure functions, no DB needed."""

from datetime import date
from decimal import Decimal

import pytest

from app.schemas.payroll import PayrollRowInput
from app.services.payroll_validation_service import validate_fund, validate_system


# ── Helpers ────────────────────────────────────────────────────────────────────

def _row(
    period_start=date(2025, 1, 1),
    period_end=date(2025, 1, 31),
    days_worked=20,
    gross_earnings=Decimal("5000.00"),
    employee_contribution=Decimal("400.00"),
    employer_contribution=Decimal("250.00"),
):
    return PayrollRowInput(
        member_number="PRY-001",
        period_start=period_start,
        period_end=period_end,
        gross_earnings=gross_earnings,
        employee_contribution=employee_contribution,
        employer_contribution=employer_contribution,
        days_worked=days_worked,
    )


_BASE_FUND_CONFIG = {
    "max_gross_earnings": 50000,
    "max_days_per_period": 31,
    "employee_contribution_rate": 0.08,
    "employer_contribution_rate": 0.05,
    "contribution_rate_tolerance": 0.005,
    "mode": "warn",
}


# ── System validation ─────────────────────────────────────────────────────────

def test_system_valid_row():
    assert validate_system(_row()) == []


def test_system_period_end_before_start():
    errors = validate_system(_row(period_start=date(2025, 1, 31), period_end=date(2025, 1, 1)))
    assert len(errors) == 1
    assert "before period_start" in errors[0]


def test_system_inverted_period_stops_further_checks():
    # Inverted period with also-impossible days — only period error returned
    errors = validate_system(_row(
        period_start=date(2025, 1, 31),
        period_end=date(2025, 1, 1),
        days_worked=99,
    ))
    assert len(errors) == 1
    assert "before period_start" in errors[0]


def test_system_days_exceed_calendar():
    # Jan has 31 days; claiming 32 is impossible
    errors = validate_system(_row(days_worked=32))
    assert len(errors) == 1
    assert "exceeds calendar days" in errors[0]


def test_system_days_exactly_calendar_length():
    # 31 days in January — edge case should pass
    assert validate_system(_row(days_worked=31)) == []


def test_system_zero_days_passes():
    assert validate_system(_row(days_worked=0)) == []


def test_system_same_day_period():
    # Single-day period: 1 calendar day, 1 day worked = valid
    assert validate_system(_row(
        period_start=date(2025, 6, 15),
        period_end=date(2025, 6, 15),
        days_worked=1,
    )) == []


def test_system_same_day_too_many_days():
    errors = validate_system(_row(
        period_start=date(2025, 6, 15),
        period_end=date(2025, 6, 15),
        days_worked=2,
    ))
    assert len(errors) == 1
    assert "exceeds calendar days" in errors[0]


def test_system_multi_month_period():
    # Jan 1 – Feb 28 = 59 calendar days; 58 days worked = valid
    assert validate_system(_row(
        period_start=date(2025, 1, 1),
        period_end=date(2025, 2, 28),
        days_worked=58,
    )) == []


# ── Fund validation ───────────────────────────────────────────────────────────

def test_fund_valid_row():
    assert validate_fund(_row(), _BASE_FUND_CONFIG) == []


def test_fund_empty_config():
    # No config keys = no checks = no warnings
    assert validate_fund(_row(), {}) == []


def test_fund_gross_exceeds_max():
    # Use a gross-only config to isolate the check (avoids rate-warning noise)
    config = {"max_gross_earnings": 50000}
    warnings = validate_fund(_row(gross_earnings=Decimal("51000.00")), config)
    assert len(warnings) == 1
    assert "gross_earnings" in warnings[0]
    assert "50000" in warnings[0]


def test_fund_gross_at_max_passes():
    config = {"max_gross_earnings": 50000}
    assert validate_fund(_row(gross_earnings=Decimal("50000.00")), config) == []


def test_fund_days_exceed_max():
    warnings = validate_fund(_row(days_worked=32), _BASE_FUND_CONFIG)
    assert len(warnings) == 1
    assert "days_worked" in warnings[0]


def test_fund_days_at_max_passes():
    assert validate_fund(_row(days_worked=31), _BASE_FUND_CONFIG) == []


def test_fund_employee_rate_too_high():
    # 10% employee rate; expected 8% ± 0.5% → outside tolerance
    warnings = validate_fund(
        _row(gross_earnings=Decimal("5000.00"), employee_contribution=Decimal("500.00")),
        _BASE_FUND_CONFIG,
    )
    assert any("employee contribution rate" in w for w in warnings)


def test_fund_employee_rate_within_tolerance():
    # 8.4% is within 8% ± 0.5%
    assert validate_fund(
        _row(gross_earnings=Decimal("5000.00"), employee_contribution=Decimal("420.00")),
        _BASE_FUND_CONFIG,
    ) == []


def test_fund_employer_rate_too_low():
    # 2% employer rate; expected 5% ± 0.5% → outside tolerance
    warnings = validate_fund(
        _row(gross_earnings=Decimal("5000.00"), employer_contribution=Decimal("100.00")),
        _BASE_FUND_CONFIG,
    )
    assert any("employer contribution rate" in w for w in warnings)


def test_fund_multiple_warnings():
    # Both gross and days over threshold; use targeted config to isolate from rate checks
    config = {"max_gross_earnings": 50000, "max_days_per_period": 31}
    warnings = validate_fund(
        _row(gross_earnings=Decimal("60000.00"), days_worked=35),
        config,
    )
    assert len(warnings) == 2
    assert any("gross_earnings" in w for w in warnings)
    assert any("days_worked" in w for w in warnings)


def test_fund_zero_gross_skips_rate_checks():
    # Zero gross is structurally odd but rate checks divide by gross — must not raise
    warnings = validate_fund(
        _row(gross_earnings=Decimal("0"), employee_contribution=Decimal("0"), employer_contribution=Decimal("0")),
        _BASE_FUND_CONFIG,
    )
    # Only gross check fires (0 < 50000 so actually no gross warning either)
    assert all("rate" not in w for w in warnings)


def test_fund_missing_rate_keys_skips_rate_checks():
    config = {"max_gross_earnings": 50000}
    assert validate_fund(_row(), config) == []


def test_fund_zero_tolerance_exact_rate_passes():
    config = {
        "employee_contribution_rate": 0.08,
        "contribution_rate_tolerance": 0.0,
    }
    assert validate_fund(
        _row(gross_earnings=Decimal("5000.00"), employee_contribution=Decimal("400.00")),
        config,
    ) == []


def test_fund_zero_tolerance_any_deviation_warns():
    config = {
        "employee_contribution_rate": 0.08,
        "contribution_rate_tolerance": 0.0,
    }
    warnings = validate_fund(
        _row(gross_earnings=Decimal("5000.00"), employee_contribution=Decimal("401.00")),
        config,
    )
    assert any("employee contribution rate" in w for w in warnings)

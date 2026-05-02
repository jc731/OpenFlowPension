"""Automatic Annual Increase (AAI / COLA) logic.

Tier I: 3% compounded (or 3% simple for some funds), first increase
        January 1 following month of retirement.
Tier II: lesser of 3% or ½ CPI-U, first increase January 1 on or after the
         later of the configured deferral age or first anniversary of annuity start.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from app.services.benefit.eligibility import age_years_months

_DEFAULT_TIER_II_DEFERRAL_AGE = 67
_DEFAULT_INCREASE_MONTH = 1
_DEFAULT_INCREASE_DAY = 1


def _next_period_start(d: date, month: int = 1, day: int = 1) -> date:
    """First occurrence of month/day on or after d (same day if d already lands on it)."""
    target_this_year = date(d.year, month, day)
    if d <= target_this_year:
        return target_this_year
    return date(d.year + 1, month, day)


def compute_aai(
    tier: str,
    retirement_date: date,
    birth_date: date,
    basis_amount: Decimal,
    *,
    tier_i_cola_type: Literal["3pct_compound", "3pct_simple"] = "3pct_compound",
    tier_ii_deferral_age: int = _DEFAULT_TIER_II_DEFERRAL_AGE,
    increase_month: int = _DEFAULT_INCREASE_MONTH,
    increase_day: int = _DEFAULT_INCREASE_DAY,
) -> tuple[Literal["3pct_compound", "3pct_simple", "cpi_u_half"], date, Decimal]:
    """Return (rate_type, first_increase_date, basis_amount)."""
    if tier == "I":
        first_increase = _next_period_start(retirement_date, increase_month, increase_day)
        return tier_i_cola_type, first_increase, basis_amount

    # Tier II — later of deferral_age or first anniversary of annuity start
    first_anniversary = date(
        retirement_date.year + 1,
        retirement_date.month,
        retirement_date.day,
    )

    age_deferral_date = date(birth_date.year + tier_ii_deferral_age, birth_date.month, birth_date.day)

    later = max(first_anniversary, age_deferral_date)
    first_increase = _next_period_start(later, increase_month, increase_day)

    return "cpi_u_half", first_increase, basis_amount

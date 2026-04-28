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


def _next_january_1(d: date) -> date:
    """January 1 of the year following d (or same Jan 1 if d is already Jan 1)."""
    if d.month == 1 and d.day == 1:
        return d
    return date(d.year + 1, 1, 1)


def compute_aai(
    tier: str,
    retirement_date: date,
    birth_date: date,
    basis_amount: Decimal,
    *,
    tier_i_cola_type: Literal["3pct_compound", "3pct_simple"] = "3pct_compound",
    tier_ii_deferral_age: int = _DEFAULT_TIER_II_DEFERRAL_AGE,
) -> tuple[Literal["3pct_compound", "3pct_simple", "cpi_u_half"], date, Decimal]:
    """Return (rate_type, first_increase_date, basis_amount)."""
    if tier == "I":
        first_increase = _next_january_1(retirement_date)
        return tier_i_cola_type, first_increase, basis_amount

    # Tier II — later of deferral_age or first anniversary of annuity start
    first_anniversary = date(
        retirement_date.year + 1,
        retirement_date.month,
        retirement_date.day,
    )

    age_67_date = date(birth_date.year + tier_ii_deferral_age, birth_date.month, birth_date.day)

    later = max(first_anniversary, age_67_date)
    first_increase = _next_january_1(later)

    return "cpi_u_half", first_increase, basis_amount

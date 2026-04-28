"""Benefit maximum cap lookup.

Standard (term on/after 1997-07-07): 80% of FAE.
Earlier terminations: age/date-dependent table (spec Section 9).
"""

from datetime import date
from decimal import Decimal

_MODERN_TERM_DATE = date(1997, 7, 7)
_MODERN_CAP_PCT = Decimal("80")


def _pre_modern_cap(term_date: date, age_at_retirement: int, cert_date: date) -> Decimal:
    """Cap for terminations before 1997-07-07, per spec Section 9."""
    # Exception: cert on/after 1977-09-15 AND term before 1997-07-07 → max 75%
    if cert_date >= date(1977, 9, 15):
        return Decimal("75")

    # Age-and-period table
    if term_date < date(1969, 8, 15):
        if age_at_retirement <= 60:
            return Decimal("60")
        elif age_at_retirement == 61:
            return Decimal("61.67")
        elif age_at_retirement == 62:
            return Decimal("63.33")
        elif age_at_retirement == 63:
            return Decimal("65")
        elif age_at_retirement == 64:
            return Decimal("66.67")
        elif age_at_retirement == 65:
            return Decimal("68.33")
        else:
            return Decimal("70")

    elif term_date < date(1973, 8, 27):
        if age_at_retirement <= 60:
            return Decimal("70")
        elif age_at_retirement == 61:
            return Decimal("71.67")
        elif age_at_retirement == 62:
            return Decimal("73.33")
        elif age_at_retirement == 63:
            return Decimal("75")
        elif age_at_retirement == 64:
            return Decimal("76.67")
        elif age_at_retirement == 65:
            return Decimal("78.33")
        else:
            return Decimal("80")

    elif term_date < date(1977, 9, 14):
        if age_at_retirement <= 60:
            return Decimal("70")
        elif age_at_retirement == 61:
            return Decimal("72")
        elif age_at_retirement == 62:
            return Decimal("74")
        elif age_at_retirement == 63:
            return Decimal("76")
        elif age_at_retirement == 64:
            return Decimal("78")
        else:
            return Decimal("80")

    else:  # 1977-09-14 to 1997-07-06
        if age_at_retirement <= 62:
            return Decimal("75")
        elif age_at_retirement == 63:
            return Decimal("76")
        elif age_at_retirement == 64:
            return Decimal("78")
        else:
            return Decimal("80")


def determine_benefit_cap(
    termination_date: date,
    age_at_retirement: int,
    cert_date: date,
    *,
    modern_cap_pct: Decimal = _MODERN_CAP_PCT,
    modern_term_date: date = _MODERN_TERM_DATE,
    use_historical_table: bool = True,
) -> Decimal:
    """Return the cap percentage (e.g. Decimal('80') means 80%)."""
    if termination_date >= modern_term_date or not use_historical_table:
        return modern_cap_pct
    return _pre_modern_cap(termination_date, age_at_retirement, cert_date)

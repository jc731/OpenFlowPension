from datetime import date
from decimal import Decimal

# Spec Section 3.2
_SICK_LEAVE_TABLE: list[tuple[int, Decimal]] = [
    (180, Decimal("1.00")),
    (120, Decimal("0.75")),
    (60, Decimal("0.50")),
    (20, Decimal("0.25")),
]


def sick_leave_credit(unused_days: int, retirement_date: date, termination_date: date) -> Decimal:
    """Return service credit for unused sick leave. Zero if conditions not met."""
    if unused_days < 20:
        return Decimal("0")
    gap = (retirement_date - termination_date).days
    if gap > 60:
        return Decimal("0")
    for min_days, credit in _SICK_LEAVE_TABLE:
        if unused_days >= min_days:
            return credit
    return Decimal("0")


def compute_service_credit_totals(
    surs_service_years: Decimal,
    sick_credit: Decimal,
    ope_service_years: Decimal,
    military_service_years: Decimal,
    reciprocal_service_years: Decimal,
) -> Decimal:
    return surs_service_years + sick_credit + ope_service_years + military_service_years + reciprocal_service_years

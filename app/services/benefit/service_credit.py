from datetime import date
from decimal import Decimal, ROUND_HALF_UP

# Spec Section 3.2 — SURS defaults
_DEFAULT_STEP_TABLE: list[tuple[int, Decimal]] = [
    (180, Decimal("1.00")),
    (120, Decimal("0.75")),
    (60, Decimal("0.50")),
    (20, Decimal("0.25")),
]
_DEFAULT_PROPORTIONAL_DAYS_PER_MONTH = 20
_DEFAULT_MAX_CREDIT_YEARS = Decimal("1.0")
_DEFAULT_MIN_DAYS = 20
_DEFAULT_MAX_GAP_DAYS = 60


def sick_leave_credit(
    unused_days: int,
    retirement_date: date,
    termination_date: date,
    *,
    method: str = "step_table",
    step_table: list[tuple[int, Decimal]] = _DEFAULT_STEP_TABLE,
    proportional_days_per_month: int = _DEFAULT_PROPORTIONAL_DAYS_PER_MONTH,
    max_credit_years: Decimal = _DEFAULT_MAX_CREDIT_YEARS,
    min_days: int = _DEFAULT_MIN_DAYS,
    max_gap_days: int = _DEFAULT_MAX_GAP_DAYS,
) -> Decimal:
    """Return service credit for unused sick leave. Zero if conditions not met."""
    if unused_days < min_days:
        return Decimal("0")
    gap = (retirement_date - termination_date).days
    if gap > max_gap_days:
        return Decimal("0")

    if method == "proportional":
        months = Decimal(str(unused_days)) / Decimal(str(proportional_days_per_month)) / Decimal("12")
        return min(months, max_credit_years).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    # step_table (default)
    for min_d, credit in step_table:
        if unused_days >= min_d:
            return credit
    return Decimal("0")


def compute_service_credit_totals(
    system_service_years: Decimal,
    sick_credit: Decimal,
    ope_service_years: Decimal,
    military_service_years: Decimal,
    reciprocal_service_years: Decimal,
) -> Decimal:
    return system_service_years + sick_credit + ope_service_years + military_service_years + reciprocal_service_years

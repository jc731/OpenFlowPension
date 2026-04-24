"""Money Purchase Formula.

Eligible: cert_date before 2005-07-01 (Tier I only).

Formula:
  standard = (normal_ci * 2.4) / actuarial_factor
  ope      = (ope_ci * 2)     / actuarial_factor
  military = (military_ci * 1) / actuarial_factor
  total    = standard + ope + military
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

MP_ELIGIBILITY_CUTOFF = date(2005, 7, 1)


def is_mp_eligible(cert_date: date) -> bool:
    return cert_date < MP_ELIGIBILITY_CUTOFF


def compute_money_purchase_monthly(
    normal_ci: Decimal,
    ope_ci: Decimal,
    military_ci: Decimal,
    actuarial_factor: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Return (standard_monthly, ope_monthly, military_monthly, total_monthly)."""
    if actuarial_factor == Decimal("0"):
        return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")

    def _calc(ci: Decimal, multiplier: Decimal) -> Decimal:
        return (ci * multiplier / actuarial_factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    standard = _calc(normal_ci, Decimal("2.4"))
    ope = _calc(ope_ci, Decimal("2"))
    military = _calc(military_ci, Decimal("1"))
    total = (standard + ope + military).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return standard, ope, military, total

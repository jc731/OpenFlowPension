"""General Formula benefit computation.

Post-1997-07-07: flat 2.2% multiplier.
Pre-1997-07-07: graduated tiers (1.67% / 1.90% / 2.10% / 2.30%).
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

_MODERN_TERM_DATE = date(1997, 7, 7)

_GRADUATED = [
    (Decimal("10"), Decimal("0.0167")),
    (Decimal("10"), Decimal("0.0190")),
    (Decimal("10"), Decimal("0.0210")),
    (None, Decimal("0.0230")),   # remaining years
]


def _graduated_multiplier(service_years: Decimal) -> Decimal:
    """Effective combined multiplier for the graduated formula."""
    total = Decimal("0")
    remaining = service_years
    for band_years, rate in _GRADUATED:
        if band_years is None:
            years_in_band = remaining
        else:
            years_in_band = min(remaining, band_years)
        total += years_in_band * rate
        remaining -= years_in_band
        if remaining <= 0:
            break
    return total  # total service × effective_rate = annual_benefit when × fae


def compute_general_annual(
    service_years: Decimal,
    fae_annual: Decimal,
    termination_date: date,
) -> Decimal:
    if termination_date >= _MODERN_TERM_DATE:
        annual = service_years * Decimal("0.022") * fae_annual
    else:
        annual = _graduated_multiplier(service_years) * fae_annual

    return annual.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

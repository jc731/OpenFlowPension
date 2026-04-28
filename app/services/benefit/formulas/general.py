"""General Formula benefit computation.

Post-1997-07-07: flat 2.2% multiplier.
Pre-1997-07-07: graduated tiers (1.67% / 1.90% / 2.10% / 2.30%).
Some funds (e.g. IMRF) always use a graduated band formula regardless of date.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

_MODERN_TERM_DATE = date(1997, 7, 7)
_MODERN_MULTIPLIER = Decimal("0.022")

# SURS pre-1997 graduated bands: (years_in_band | None for remainder, rate)
_DEFAULT_PRE_BANDS: list[tuple[Decimal | None, Decimal]] = [
    (Decimal("10"), Decimal("0.0167")),
    (Decimal("10"), Decimal("0.0190")),
    (Decimal("10"), Decimal("0.0210")),
    (None, Decimal("0.0230")),
]


def _apply_bands(
    service_years: Decimal,
    bands: list[tuple[Decimal | None, Decimal]],
) -> Decimal:
    """Compute total benefit factor (service × rate sum) from graduated bands."""
    total = Decimal("0")
    remaining = service_years
    for band_years, rate in bands:
        if band_years is None:
            years_in_band = remaining
        else:
            years_in_band = min(remaining, band_years)
        total += years_in_band * rate
        remaining -= years_in_band
        if remaining <= 0:
            break
    return total


def compute_general_annual(
    service_years: Decimal,
    fae_annual: Decimal,
    termination_date: date,
    *,
    multiplier: Decimal = _MODERN_MULTIPLIER,
    effective_date: date = _MODERN_TERM_DATE,
    pre_bands: list[tuple[Decimal | None, Decimal]] = _DEFAULT_PRE_BANDS,
    always_use_bands: bool = False,
    bands: list[tuple[Decimal | None, Decimal]] | None = None,
) -> Decimal:
    if always_use_bands and bands:
        annual = _apply_bands(service_years, bands) * fae_annual
    elif termination_date >= effective_date:
        annual = service_years * multiplier * fae_annual
    else:
        annual = _apply_bands(service_years, pre_bands) * fae_annual

    return annual.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

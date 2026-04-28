"""Final Average Earnings (FAE) computation.

Supports:
  Method A — High 4 (or 8 for Tier II) consecutive academic years
  Method C — Actual service/earnings (fewer than 4/8 years available)

Academic year: July 1 – June 30 (SURS convention; other funds may differ).
Earnings cap: any AY after 1997-06-30 where earnings increased ≥ 20% over
the prior AY with the same employer are capped at prior + 20%.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.schemas.benefit import SalaryPeriod

SPIKE_CAP_EFFECTIVE = date(1997, 7, 1)
DAYS_PER_YEAR = Decimal("365")


def _ay_start(d: date) -> date:
    """July 1 of the academic year that contains d."""
    return date(d.year, 7, 1) if d.month >= 7 else date(d.year - 1, 7, 1)


def _ay_end(ay_start: date) -> date:
    return date(ay_start.year + 1, 6, 30)


def _next_ay(ay_start: date) -> date:
    return date(ay_start.year + 1, 7, 1)


def build_academic_year_earnings(
    salary_history: list[SalaryPeriod],
    as_of: date | None = None,
) -> dict[date, Decimal]:
    """Return {ay_start: total_earnings} by prorating each salary period across AYs."""
    earnings: dict[date, Decimal] = {}

    for sp in salary_history:
        start = sp.start_date
        end = sp.end_date if sp.end_date is not None else as_of
        if end is None:
            continue
        if end < start:
            continue

        daily_rate = Decimal(str(sp.annual_salary)) / DAYS_PER_YEAR

        ay = _ay_start(start)
        while ay <= _ay_start(end):
            ay_end = _ay_end(ay)
            overlap_start = max(start, ay)
            overlap_end = min(end, ay_end)
            if overlap_start <= overlap_end:
                days = Decimal(str((overlap_end - overlap_start).days + 1))
                earnings[ay] = earnings.get(ay, Decimal("0")) + (daily_rate * days).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            ay = _next_ay(ay)

    return earnings


def apply_spike_cap(earnings: dict[date, Decimal]) -> dict[date, Decimal]:
    """Cap year-over-year increases ≥ 20% for AYs after 1997-06-30."""
    sorted_ays = sorted(earnings.keys())
    capped: dict[date, Decimal] = {}
    for i, ay in enumerate(sorted_ays):
        if ay < SPIKE_CAP_EFFECTIVE or i == 0:
            capped[ay] = earnings[ay]
        else:
            prior_ay = sorted_ays[i - 1]
            prior = capped.get(prior_ay, Decimal("0"))
            if prior > 0:
                cap = (prior * Decimal("1.20")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                capped[ay] = min(earnings[ay], cap)
            else:
                capped[ay] = earnings[ay]
    return capped


def _best_consecutive_window(
    earnings: dict[date, Decimal],
    window_size: int,
    restrict_to_last_n_years: int | None = None,
    term_date: date | None = None,
) -> tuple[Decimal, list[date]]:
    """
    Return (best_annual_fae, [ay_start, ...]) for the highest-sum window of
    `window_size` consecutive AYs from the earnings dict.

    If restrict_to_last_n_years and term_date are given, only AYs within that
    trailing window are considered (Tier II uses last 10 AYs).
    """
    active_ays = sorted(ay for ay, e in earnings.items() if e > Decimal("0"))

    if restrict_to_last_n_years and term_date:
        cutoff_ay = _ay_start(date(term_date.year - restrict_to_last_n_years, term_date.month, term_date.day))
        active_ays = [ay for ay in active_ays if ay >= cutoff_ay]

    if len(active_ays) < window_size:
        return Decimal("0"), []

    best_sum = Decimal("0")
    best_window: list[date] = []
    for i in range(len(active_ays) - window_size + 1):
        window = active_ays[i : i + window_size]
        total = sum(earnings[ay] for ay in window)
        if total > best_sum:
            best_sum = total
            best_window = list(window)

    annual_fae = (best_sum / window_size).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return annual_fae, best_window


def _actual_fae(earnings: dict[date, Decimal]) -> Decimal:
    """Method C: sum all earnings, divide by number of AYs worked (for < 4 years)."""
    active = {ay: e for ay, e in earnings.items() if e > 0}
    if not active:
        return Decimal("0")
    total = sum(active.values())
    return (total / len(active)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_fae(
    salary_history: list[SalaryPeriod],
    tier: str,
    termination_date: date,
    is_twelve_month_contract: bool = False,
) -> tuple[Decimal, str, dict[date, Decimal]]:
    """
    Returns (fae_annual, method_label, capped_earnings_by_ay).

    method_label is one of: 'high_4', 'high_8', 'actual'.
    The 48-month method (Method B) is not yet implemented; 12-month contracts
    fall through to Method A/C.
    """
    raw = build_academic_year_earnings(salary_history, as_of=termination_date)
    capped = apply_spike_cap(raw)

    window = 4 if tier == "I" else 8
    restrict = None if tier == "I" else 10

    fae, best_ays = _best_consecutive_window(
        capped,
        window_size=window,
        restrict_to_last_n_years=restrict,
        term_date=termination_date if tier == "II" else None,
    )

    if fae == Decimal("0"):
        # Fewer than window_size years — use actual
        fae = _actual_fae(capped)
        method = "actual"
    else:
        method = "high_4" if tier == "I" else "high_8"

    return fae, method, capped

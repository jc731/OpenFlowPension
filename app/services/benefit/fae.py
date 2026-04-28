"""Final Average Earnings (FAE) computation.

Supports:
  Method A — High N (configurable; 4 for Tier I, 8 for Tier II) consecutive
             academic years
  Method C — Actual service/earnings (fewer than N years available)

Academic year start is configurable (Jul 1 for SURS; other funds may differ).
Earnings cap: any AY after spike_cap_effective_date where earnings increased
≥ spike_cap_rate over the prior AY with the same employer are capped.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.schemas.benefit import SalaryPeriod

SPIKE_CAP_EFFECTIVE = date(1997, 7, 1)
DAYS_PER_YEAR = Decimal("365")

_DEFAULT_AY_MONTH = 7
_DEFAULT_AY_DAY = 1


def _ay_start(d: date, ay_month: int = _DEFAULT_AY_MONTH, ay_day: int = _DEFAULT_AY_DAY) -> date:
    """Start of the academic year containing d."""
    ay_this_year = date(d.year, ay_month, ay_day)
    if d >= ay_this_year:
        return ay_this_year
    return date(d.year - 1, ay_month, ay_day)


def _ay_end(ay_start: date) -> date:
    """Last day of the academic year that begins on ay_start."""
    next_ay = date(ay_start.year + 1, ay_start.month, ay_start.day)
    return next_ay - timedelta(days=1)


def _next_ay(ay_start: date) -> date:
    return date(ay_start.year + 1, ay_start.month, ay_start.day)


def build_academic_year_earnings(
    salary_history: list[SalaryPeriod],
    as_of: date | None = None,
    *,
    ay_month: int = _DEFAULT_AY_MONTH,
    ay_day: int = _DEFAULT_AY_DAY,
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

        ay = _ay_start(start, ay_month, ay_day)
        while ay <= _ay_start(end, ay_month, ay_day):
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


def apply_spike_cap(
    earnings: dict[date, Decimal],
    *,
    enabled: bool = True,
    cap_rate: Decimal = Decimal("0.20"),
    effective_date: date = SPIKE_CAP_EFFECTIVE,
) -> dict[date, Decimal]:
    """Cap year-over-year increases ≥ cap_rate for AYs on/after effective_date."""
    if not enabled:
        return dict(earnings)
    sorted_ays = sorted(earnings.keys())
    capped: dict[date, Decimal] = {}
    cap_multiplier = Decimal("1") + cap_rate
    for i, ay in enumerate(sorted_ays):
        if ay < effective_date or i == 0:
            capped[ay] = earnings[ay]
        else:
            prior_ay = sorted_ays[i - 1]
            prior = capped.get(prior_ay, Decimal("0"))
            if prior > 0:
                cap = (prior * cap_multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                capped[ay] = min(earnings[ay], cap)
            else:
                capped[ay] = earnings[ay]
    return capped


def _best_consecutive_window(
    earnings: dict[date, Decimal],
    window_size: int,
    restrict_to_last_n_years: int | None = None,
    term_date: date | None = None,
    *,
    ay_month: int = _DEFAULT_AY_MONTH,
    ay_day: int = _DEFAULT_AY_DAY,
) -> tuple[Decimal, list[date]]:
    """
    Return (best_annual_fae, [ay_start, ...]) for the highest-sum window of
    `window_size` consecutive AYs from the earnings dict.

    If restrict_to_last_n_years and term_date are given, only AYs within that
    trailing window are considered (Tier II uses last 10 AYs).
    """
    active_ays = sorted(ay for ay, e in earnings.items() if e > Decimal("0"))

    if restrict_to_last_n_years and term_date:
        cutoff_ay = _ay_start(
            date(term_date.year - restrict_to_last_n_years, term_date.month, term_date.day),
            ay_month,
            ay_day,
        )
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
    """Method C: sum all earnings, divide by number of AYs worked (for < N years)."""
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
    *,
    tier_i_years: int = 4,
    tier_ii_years: int = 8,
    tier_ii_restrict_last_n_years: int | None = 10,
    ay_month: int = _DEFAULT_AY_MONTH,
    ay_day: int = _DEFAULT_AY_DAY,
    spike_cap_enabled: bool = True,
    spike_cap_rate: Decimal = Decimal("0.20"),
    spike_cap_effective_date: date = SPIKE_CAP_EFFECTIVE,
) -> tuple[Decimal, str, dict[date, Decimal]]:
    """
    Returns (fae_annual, method_label, capped_earnings_by_ay).

    method_label is one of: 'high_4', 'high_8', 'actual'.
    The 48-month method (Method B) is not yet implemented; 12-month contracts
    fall through to Method A/C.
    """
    raw = build_academic_year_earnings(salary_history, as_of=termination_date, ay_month=ay_month, ay_day=ay_day)
    capped = apply_spike_cap(
        raw,
        enabled=spike_cap_enabled,
        cap_rate=spike_cap_rate,
        effective_date=spike_cap_effective_date,
    )

    window = tier_i_years if tier == "I" else tier_ii_years
    restrict = None if tier == "I" else tier_ii_restrict_last_n_years

    fae, best_ays = _best_consecutive_window(
        capped,
        window_size=window,
        restrict_to_last_n_years=restrict,
        term_date=termination_date if tier == "II" else None,
        ay_month=ay_month,
        ay_day=ay_day,
    )

    if fae == Decimal("0"):
        fae = _actual_fae(capped)
        method = "actual"
    else:
        method = f"high_{window}"

    return fae, method, capped

"""Two-level payroll row validation.

Level 1 — system validation (structural, hard block, no config needed):
    validate_system(row) → list[str]
    Any errors here set row status=error and skip business logic entirely.

Level 2 — fund validation (threshold-based, config-driven):
    validate_fund(row, config) → list[str]
    Warnings store in validation_warnings JSONB. Behavior depends on config["mode"]:
        "warn"   (default) → row status=flagged, still applied
        "reject"           → row status=error, not applied
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from app.schemas.payroll import PayrollRowInput


def validate_system(row: PayrollRowInput) -> list[str]:
    """Structural sanity checks. Returns a list of error strings; empty = pass."""
    errors: list[str] = []

    if row.period_end < row.period_start:
        errors.append(
            f"period_end ({row.period_end}) is before period_start ({row.period_start})"
        )
        return errors  # further checks are meaningless if dates are inverted

    calendar_days = (row.period_end - row.period_start).days + 1
    if row.days_worked > calendar_days:
        errors.append(
            f"days_worked ({row.days_worked}) exceeds calendar days in period ({calendar_days})"
        )

    return errors


def check_plan_type_earnings_cap(
    gross_earnings: Decimal,
    config: dict,
    plan_type_code: str | None,
) -> list[str]:
    """Per-plan-type earnings cap check. Called after member lookup provides plan_type_code.

    Config keys (from payroll_validation_config):
        earnings_cap_by_plan_type — dict mapping plan_code → per-period cap amount
        irs_401a17_limit          — global IRS cap used when plan_type_code has no entry
    """
    cap_dict = config.get("earnings_cap_by_plan_type", {})
    if not cap_dict and "irs_401a17_limit" not in config:
        return []

    if plan_type_code and plan_type_code in cap_dict:
        cap = Decimal(str(cap_dict[plan_type_code]))
        label = f"plan type '{plan_type_code}'"
    elif "irs_401a17_limit" in config:
        cap = Decimal(str(config["irs_401a17_limit"]))
        label = "IRS 401(a)(17)"
    else:
        return []

    if gross_earnings > cap:
        return [f"gross_earnings {gross_earnings} exceeds {label} annual earnings cap {cap}"]
    return []


def validate_fund(row: PayrollRowInput, config: dict) -> list[str]:
    """Fund-specific threshold checks. Returns a list of warning strings; empty = pass.

    config keys (all optional; missing key skips that check):
        max_gross_earnings         — per-period cap (global fallback; use earnings_cap_by_plan_type for per-type)
        max_days_per_period        — per-period day cap
        employee_contribution_rate — expected rate as decimal (e.g. 0.08)
        employer_contribution_rate — expected rate as decimal (e.g. 0.05)
        contribution_rate_tolerance — allowed deviation (e.g. 0.005 = ±0.5%)
        earnings_cap_by_plan_type  — plan-code → cap dict; evaluated in _process_row after member lookup
        irs_401a17_limit           — global IRS cap; evaluated in _process_row after member lookup
    """
    warnings: list[str] = []

    try:
        gross = Decimal(str(row.gross_earnings))
    except InvalidOperation:
        return warnings

    # Gross earnings cap (global fallback only — plan-type-specific cap handled in _process_row)
    if "max_gross_earnings" in config:
        cap = Decimal(str(config["max_gross_earnings"]))
        if gross > cap:
            warnings.append(
                f"gross_earnings {gross} exceeds fund maximum {cap}"
            )

    # Days-worked cap
    if "max_days_per_period" in config:
        max_days = int(config["max_days_per_period"])
        if row.days_worked > max_days:
            warnings.append(
                f"days_worked {row.days_worked} exceeds fund maximum {max_days}"
            )

    # Contribution rate checks (only meaningful when gross > 0)
    if gross > 0:
        tolerance = Decimal(str(config.get("contribution_rate_tolerance", "0")))

        if "employee_contribution_rate" in config:
            expected = Decimal(str(config["employee_contribution_rate"]))
            actual = Decimal(str(row.employee_contribution)) / gross
            if abs(actual - expected) > tolerance:
                warnings.append(
                    f"employee contribution rate {actual:.4%} is outside "
                    f"expected {expected:.4%} ± {tolerance:.4%}"
                )

        if "employer_contribution_rate" in config:
            expected = Decimal(str(config["employer_contribution_rate"]))
            actual = Decimal(str(row.employer_contribution)) / gross
            if abs(actual - expected) > tolerance:
                warnings.append(
                    f"employer contribution rate {actual:.4%} is outside "
                    f"expected {expected:.4%} ± {tolerance:.4%}"
                )

    return warnings

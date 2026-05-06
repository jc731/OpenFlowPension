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


def validate_fund(row: PayrollRowInput, config: dict) -> list[str]:
    """Fund-specific threshold checks. Returns a list of warning strings; empty = pass.

    config keys (all optional; missing key skips that check):
        max_gross_earnings         — per-period cap
        max_days_per_period        — per-period day cap
        employee_contribution_rate — expected rate as decimal (e.g. 0.08)
        employer_contribution_rate — expected rate as decimal (e.g. 0.05)
        contribution_rate_tolerance — allowed deviation (e.g. 0.005 = ±0.5%)
    """
    warnings: list[str] = []

    try:
        gross = Decimal(str(row.gross_earnings))
    except InvalidOperation:
        return warnings

    # Gross earnings cap
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

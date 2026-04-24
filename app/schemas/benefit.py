from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SalaryPeriod(BaseModel):
    start_date: date
    end_date: date | None = None
    annual_salary: Decimal


class MoneyPurchaseContributions(BaseModel):
    normal_ci: Decimal = Decimal("0")
    ope_ci: Decimal = Decimal("0")
    military_ci: Decimal = Decimal("0")


class BenefitOptionRequest(BaseModel):
    option_type: Literal["single_life", "reversionary", "js_50", "js_75", "js_100", "lump_sum"]
    beneficiary_age: int | None = None
    desired_reversionary_monthly: Decimal | None = None


class BenefitCalculationRequest(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    member_id: uuid.UUID | None = None

    plan_type: Literal["traditional", "portable"]
    cert_date: date
    birth_date: date
    retirement_date: date
    termination_date: date

    surs_service_years: Decimal
    sick_leave_days: int = 0
    ope_service_years: Decimal = Decimal("0")
    military_service_years: Decimal = Decimal("0")
    reciprocal_service_years: Decimal = Decimal("0")

    salary_history: list[SalaryPeriod]

    money_purchase_contributions: MoneyPurchaseContributions | None = None
    mp_actuarial_factor: Decimal | None = None

    is_police_fire: bool = False
    police_fire_service_years: Decimal | None = None

    benefit_option: BenefitOptionRequest | None = None

    is_twelve_month_contract: bool = False


# ── Output schemas ─────────────────────────────────────────────────────────────

class ServiceCreditResult(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    surs_service: Decimal
    sick_leave_credit: Decimal
    ope_service: Decimal
    military_service: Decimal
    reciprocal_service: Decimal
    total: Decimal


class FaeResult(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    method_used: str
    annual: Decimal
    monthly: Decimal
    earnings_by_academic_year: dict[str, Decimal] = {}


class GeneralFormulaResult(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    applicable: bool
    unreduced_annual: Decimal
    unreduced_monthly: Decimal
    age_reduction_months: int
    age_reduction_factor: Decimal
    reduced_monthly: Decimal


class MoneyPurchaseResult(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    applicable: bool
    standard_monthly: Decimal = Decimal("0")
    ope_monthly: Decimal = Decimal("0")
    military_monthly: Decimal = Decimal("0")
    total_monthly: Decimal = Decimal("0")


class PoliceFireResult(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    applicable: bool
    monthly: Decimal = Decimal("0")


class FormulasResult(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    general: GeneralFormulaResult
    money_purchase: MoneyPurchaseResult
    police_fire: PoliceFireResult


class BenefitOptionResult(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    option_type: str
    reduction_amount: Decimal
    reduced_annuity_monthly: Decimal
    beneficiary_annuity_monthly: Decimal = Decimal("0")


class AaiResult(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    rate_type: Literal["3pct_compound", "cpi_u_half"]
    first_increase_date: date
    basis_amount: Decimal


class Hb2616Result(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    minimum_monthly: Decimal
    supplemental_payment: Decimal


class MaxCapResult(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    percentage: Decimal
    capped: bool
    cap_amount_monthly: Decimal


class BenefitCalculationResult(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    member_id: uuid.UUID | None
    retirement_date: date
    tier: str
    plan_type: str
    service_credit: ServiceCreditResult
    fae: FaeResult
    formulas: FormulasResult
    formula_selected: str
    base_unreduced_annuity_monthly: Decimal
    benefit_option: BenefitOptionResult
    aai: AaiResult
    hb2616_minimum: Hb2616Result
    maximum_benefit_cap: MaxCapResult
    final_monthly_annuity: Decimal
    eligible_insurance_service_years: Decimal

"""Benefit calculation orchestrator.

Implements the 15-step decision tree from spec Section 15.
Pure function — no database access.  All inputs come via BenefitCalculationRequest.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.schemas.benefit import (
    AaiResult,
    BenefitCalculationRequest,
    BenefitCalculationResult,
    BenefitOptionResult,
    FaeResult,
    FormulasResult,
    GeneralFormulaResult,
    Hb2616Result,
    MaxCapResult,
    MoneyPurchaseResult,
    PoliceFireResult,
    ServiceCreditResult,
)
from app.services.benefit.aai import compute_aai
from app.services.benefit.age_reduction import compute_age_reduction
from app.services.benefit.eligibility import age_years_months, determine_tier
from app.services.benefit.fae import compute_fae
from app.services.benefit.formulas.general import compute_general_annual
from app.services.benefit.formulas.money_purchase import (
    compute_money_purchase_monthly,
    is_mp_eligible,
)
from app.services.benefit.formulas.police_fire import (
    check_pf_eligibility,
    compute_police_fire_monthly,
)
from app.services.benefit.max_cap import determine_benefit_cap
from app.services.benefit.service_credit import (
    compute_service_credit_totals,
    sick_leave_credit,
)


def _quantize(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_benefit(req: BenefitCalculationRequest) -> BenefitCalculationResult:
    # ── 1. Tier ────────────────────────────────────────────────────────────────
    tier = determine_tier(req.cert_date)

    # ── 2. Service credit ──────────────────────────────────────────────────────
    sick_credit = sick_leave_credit(req.sick_leave_days, req.retirement_date, req.termination_date)
    total_service = compute_service_credit_totals(
        req.system_service_years,
        sick_credit,
        req.ope_service_years,
        req.military_service_years,
        req.reciprocal_service_years,
    )
    service_result = ServiceCreditResult(
        system_service=_quantize(req.system_service_years),
        sick_leave_credit=sick_credit,
        ope_service=_quantize(req.ope_service_years),
        military_service=_quantize(req.military_service_years),
        reciprocal_service=_quantize(req.reciprocal_service_years),
        total=_quantize(total_service),
    )

    # ── 3. FAE ─────────────────────────────────────────────────────────────────
    fae_annual, fae_method, earnings_by_ay = compute_fae(
        req.salary_history,
        tier,
        req.termination_date,
        req.is_twelve_month_contract,
    )
    fae_result = FaeResult(
        method_used=fae_method,
        annual=fae_annual,
        monthly=_quantize(fae_annual / 12),
        earnings_by_academic_year={str(ay): amt for ay, amt in sorted(earnings_by_ay.items())},
    )

    # ── 4. Benefit cap ─────────────────────────────────────────────────────────
    age_y, _ = age_years_months(req.birth_date, req.retirement_date)
    cap_pct = determine_benefit_cap(req.termination_date, age_y, req.cert_date)
    cap_monthly = _quantize(fae_annual * cap_pct / 100 / 12)

    # ── 5. General Formula ─────────────────────────────────────────────────────
    general_annual = compute_general_annual(total_service, fae_annual, req.termination_date)
    general_monthly_unreduced = _quantize(general_annual / 12)

    age_red_months, age_red_factor = compute_age_reduction(
        tier, req.birth_date, req.retirement_date, total_service
    )
    general_monthly_reduced = _quantize(general_monthly_unreduced * age_red_factor)

    general_result = GeneralFormulaResult(
        applicable=True,
        unreduced_annual=general_annual,
        unreduced_monthly=general_monthly_unreduced,
        age_reduction_months=age_red_months,
        age_reduction_factor=age_red_factor,
        reduced_monthly=general_monthly_reduced,
    )

    # ── 6. Money Purchase (if eligible) ────────────────────────────────────────
    mp_applicable = is_mp_eligible(req.cert_date) and req.money_purchase_contributions is not None
    if mp_applicable and req.mp_actuarial_factor:
        mpc = req.money_purchase_contributions  # type: ignore[union-attr]
        std_mp, ope_mp, mil_mp, total_mp = compute_money_purchase_monthly(
            mpc.normal_ci, mpc.ope_ci, mpc.military_ci, req.mp_actuarial_factor
        )
        mp_result = MoneyPurchaseResult(
            applicable=True,
            standard_monthly=std_mp,
            ope_monthly=ope_mp,
            military_monthly=mil_mp,
            total_monthly=total_mp,
        )
    else:
        mp_result = MoneyPurchaseResult(applicable=mp_applicable)

    # ── 7. Police/Fire (if eligible) ───────────────────────────────────────────
    pf_applicable = False
    pf_monthly = Decimal("0")
    if req.is_police_fire and req.police_fire_service_years is not None:
        pf_applicable = check_pf_eligibility(
            tier,
            req.birth_date,
            req.retirement_date,
            req.police_fire_service_years,
            contributed_9_5_pct=True,  # assumed when is_police_fire=True
        )
        if pf_applicable:
            pf_monthly = compute_police_fire_monthly(req.police_fire_service_years, fae_annual)
    pf_result = PoliceFireResult(applicable=pf_applicable, monthly=pf_monthly)

    formulas_result = FormulasResult(
        general=general_result,
        money_purchase=mp_result,
        police_fire=pf_result,
    )

    # ── 8. Select highest formula ──────────────────────────────────────────────
    candidates: list[tuple[str, Decimal]] = [("general", general_monthly_reduced)]
    if mp_result.applicable and mp_result.total_monthly > 0:
        candidates.append(("money_purchase", mp_result.total_monthly))
    if pf_result.applicable and pf_result.monthly > 0:
        candidates.append(("police_fire", pf_result.monthly))

    formula_selected, base_monthly = max(candidates, key=lambda x: x[1])

    # Apply 80% (or applicable) cap
    capped = base_monthly > cap_monthly
    if capped:
        base_monthly = cap_monthly

    max_cap_result = MaxCapResult(
        percentage=cap_pct,
        capped=capped,
        cap_amount_monthly=cap_monthly,
    )

    # ── 9. Benefit option ──────────────────────────────────────────────────────
    option_result = _apply_benefit_option(req, base_monthly, age_y, tier)

    final_monthly = option_result.reduced_annuity_monthly

    # ── 10. AAI ────────────────────────────────────────────────────────────────
    # Tier I AAI basis = unreduced annuity (even if reversionary elected)
    # Tier II AAI basis = reduced annuity (J&S elected)
    if req.plan_type == "traditional":
        aai_basis = base_monthly
    else:
        aai_basis = final_monthly

    rate_type, first_increase_date, aai_basis_used = compute_aai(
        tier, req.retirement_date, req.birth_date, aai_basis
    )
    aai_result = AaiResult(
        rate_type=rate_type,
        first_increase_date=first_increase_date,
        basis_amount=aai_basis_used,
    )

    # ── 11. HB2616 minimum ─────────────────────────────────────────────────────
    min_svc = min(total_service, Decimal("30"))
    hb2616_min = _quantize(Decimal("25") * min_svc)
    supplemental = max(Decimal("0"), _quantize(hb2616_min - final_monthly))

    hb2616_result = Hb2616Result(
        minimum_monthly=hb2616_min,
        supplemental_payment=supplemental,
    )

    # ── 12. Insurance service years ────────────────────────────────────────────
    eligible_insurance_years = _quantize(req.system_service_years + req.ope_service_years)

    return BenefitCalculationResult(
        member_id=req.member_id,
        retirement_date=req.retirement_date,
        tier=tier,
        plan_type=req.plan_type,
        service_credit=service_result,
        fae=fae_result,
        formulas=formulas_result,
        formula_selected=formula_selected,
        base_unreduced_annuity_monthly=base_monthly,
        benefit_option=option_result,
        aai=aai_result,
        hb2616_minimum=hb2616_result,
        maximum_benefit_cap=max_cap_result,
        final_monthly_annuity=final_monthly,
        eligible_insurance_service_years=eligible_insurance_years,
    )


def _apply_benefit_option(
    req: BenefitCalculationRequest,
    base_monthly: Decimal,
    member_age: int,
    tier: str,
) -> BenefitOptionResult:
    """Compute the benefit option reduction and return the option result."""
    if req.benefit_option is None:
        return BenefitOptionResult(
            option_type="single_life",
            reduction_amount=Decimal("0"),
            reduced_annuity_monthly=base_monthly,
        )

    opt = req.benefit_option

    if opt.option_type == "single_life":
        return BenefitOptionResult(
            option_type="single_life",
            reduction_amount=Decimal("0"),
            reduced_annuity_monthly=base_monthly,
        )

    if opt.option_type == "reversionary":
        if req.plan_type != "traditional":
            raise ValueError("Reversionary annuity is only available for Traditional plan members")
        if opt.beneficiary_age is None or opt.desired_reversionary_monthly is None:
            raise ValueError("beneficiary_age and desired_reversionary_monthly required for reversionary option")

        from app.services.benefit.actuarial import reversionary_reduction_factor
        factor = reversionary_reduction_factor(member_age, opt.beneficiary_age)
        reduction = _quantize(opt.desired_reversionary_monthly * factor)
        reduced = _quantize(max(Decimal("0"), base_monthly - reduction))
        return BenefitOptionResult(
            option_type="reversionary",
            reduction_amount=reduction,
            reduced_annuity_monthly=reduced,
            beneficiary_annuity_monthly=opt.desired_reversionary_monthly,
        )

    if opt.option_type in ("js_50", "js_75", "js_100"):
        if req.plan_type != "portable":
            raise ValueError("Joint & Survivor is only available for Portable plan members")
        if opt.beneficiary_age is None:
            raise ValueError("beneficiary_age required for J&S option")

        from app.services.benefit.actuarial import js_factor
        factor = js_factor(opt.option_type, member_age, opt.beneficiary_age)
        reduced = _quantize(base_monthly * factor)
        reduction = _quantize(base_monthly - reduced)

        survivor_pct = {"js_50": Decimal("0.50"), "js_75": Decimal("0.75"), "js_100": Decimal("1.00")}[opt.option_type]
        survivor_monthly = _quantize(reduced * survivor_pct)

        return BenefitOptionResult(
            option_type=opt.option_type,
            reduction_amount=reduction,
            reduced_annuity_monthly=reduced,
            beneficiary_annuity_monthly=survivor_monthly,
        )

    # lump_sum — not implemented in this phase, return single life
    return BenefitOptionResult(
        option_type="lump_sum",
        reduction_amount=Decimal("0"),
        reduced_annuity_monthly=base_monthly,
        beneficiary_annuity_monthly=Decimal("0"),
    )

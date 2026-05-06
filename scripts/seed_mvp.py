"""
MVP seed script: Jane Smith — 25-year retirement scenario.

Run with: make seed  (or: docker compose exec api python scripts/seed_mvp.py)
"""
import asyncio
import sys
from datetime import date, datetime, timezone
from decimal import Decimal

sys.path.insert(0, "/app")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.crypto import encrypt_ssn
from app.models.beneficiary import Beneficiary
from app.models.employer import Employer
from app.models.employment import EmploymentRecord
from app.models.leave import LeaveType
from app.models.member import Member
from app.models.address import MemberAddress
from app.models.contact import MemberContact  # noqa: F401 — registers mapper
from app.models.plan_config import PlanConfiguration, PlanTier, PlanType, SystemConfiguration
from app.models.salary import SalaryHistory
from app.models.service_credit import ServiceCreditEntry

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_or_create(session: AsyncSession, model, lookup: dict, create: dict):
    result = await session.execute(select(model).filter_by(**lookup))
    obj = result.scalar_one_or_none()
    if obj:
        return obj, False
    obj = model(**lookup, **create)
    session.add(obj)
    await session.flush()
    return obj, True


async def seed():
    async with SessionLocal() as session:
        async with session.begin():
            # ── System configurations ─────────────────────────────────────────
            configs_data = [
                dict(
                    config_key="service_credit_accrual_rule",
                    config_value={"rule": "proportional_percent_time", "description": "Service credit = percent time worked"},
                    effective_date=date(1980, 1, 1),
                    superseded_date=date(2024, 9, 1),
                    note="Original accrual rule",
                ),
                dict(
                    config_key="service_credit_accrual_rule",
                    config_value={"rule": "monthly_floor", "description": "1 day worked in a calendar month = 1/12 year service credit"},
                    effective_date=date(2024, 9, 1),
                    superseded_date=None,
                    note="Rule change effective Sept 1 2024",
                ),
                dict(
                    config_key="concurrent_employment_max_annual_credit",
                    config_value={"max_years_per_year": 1.0, "allow_concurrent": True, "cap_enforcement": "hard"},
                    effective_date=date(2024, 1, 1),
                    superseded_date=None,
                    note="No more than 1 year of service credit per calendar year",
                ),
                dict(
                    config_key="service_credit_percent_time_threshold",
                    config_value={"minimum_percent_time": 0.0, "proration_method": "monthly_floor"},
                    effective_date=date(2024, 9, 1),
                    superseded_date=None,
                    note="Post-2024 rule: any time in month = full month credit",
                ),
                # ── Federal income tax withholding — IRS Pub 15-T 2025 percentage method ──
                dict(
                    config_key="federal_income_tax_withholding",
                    config_value={
                        "tax_year": 2025,
                        # IRS Pub 15-T Table 1 — Step 2 NOT checked (single pension source)
                        "standard_withholding_deduction": {
                            "single": 15000,
                            "married_filing_separately": 15000,
                            "head_of_household": 22500,
                            "married_filing_jointly": 30000,
                            "qualifying_surviving_spouse": 30000,
                        },
                        # IRS Pub 15-T Table 1 — Step 2 checked (multiple jobs/pensions)
                        # Halved to prevent under-withholding across income sources
                        "higher_withholding_deduction": {
                            "single": 7500,
                            "married_filing_separately": 7500,
                            "head_of_household": 11250,
                            "married_filing_jointly": 15000,
                            "qualifying_surviving_spouse": 15000,
                        },
                        "brackets": {
                            "single": [
                                {"min": 0, "max": 11925, "rate": 0.10, "base_tax": 0},
                                {"min": 11925, "max": 48475, "rate": 0.12, "base_tax": 1192.50},
                                {"min": 48475, "max": 103350, "rate": 0.22, "base_tax": 5578.50},
                                {"min": 103350, "max": 197300, "rate": 0.24, "base_tax": 17651.50},
                                {"min": 197300, "max": 250525, "rate": 0.32, "base_tax": 40199.50},
                                {"min": 250525, "max": 626350, "rate": 0.35, "base_tax": 57231.50},
                                {"min": 626350, "max": None, "rate": 0.37, "base_tax": 188769.75},
                            ],
                            "married_filing_jointly": [
                                {"min": 0, "max": 23850, "rate": 0.10, "base_tax": 0},
                                {"min": 23850, "max": 96950, "rate": 0.12, "base_tax": 2385.00},
                                {"min": 96950, "max": 206700, "rate": 0.22, "base_tax": 11157.00},
                                {"min": 206700, "max": 394600, "rate": 0.24, "base_tax": 35302.00},
                                {"min": 394600, "max": 501050, "rate": 0.32, "base_tax": 80397.00},
                                {"min": 501050, "max": 751600, "rate": 0.35, "base_tax": 114462.00},
                                {"min": 751600, "max": None, "rate": 0.37, "base_tax": 202154.50},
                            ],
                        },
                    },
                    effective_date=date(2025, 1, 1),
                    superseded_date=None,
                    note="IRS Pub 15-T 2025 — annualized percentage method for pension payments",
                ),
                # ── Federal income tax withholding — IRS Pub 15-T 2026 percentage method ──
                # Structural change from 2025: standard deduction (line 1g) is now smaller
                # because a 0% band is baked into the bracket tables themselves.
                # Step 2 checkbox uses dedicated bracket tables (not halved line 1g).
                dict(
                    config_key="federal_income_tax_withholding",
                    config_value={
                        "tax_year": 2026,
                        # Line 1g amounts — subtracted from annualized payment before brackets
                        # (only when Step 2 is NOT checked; $0 when Step 2 IS checked)
                        "standard_withholding_deduction": {
                            "single": 8600,
                            "married_filing_separately": 8600,
                            "head_of_household": 8600,
                            "married_filing_jointly": 12900,
                            "qualifying_surviving_spouse": 12900,
                        },
                        # Standard brackets (Step 2 NOT checked) — 0% band at bottom
                        "brackets": {
                            "single": [
                                {"min": 0, "max": 7500, "rate": 0.00, "base_tax": 0},
                                {"min": 7500, "max": 19900, "rate": 0.10, "base_tax": 0},
                                {"min": 19900, "max": 57900, "rate": 0.12, "base_tax": 1240.00},
                                {"min": 57900, "max": 113200, "rate": 0.22, "base_tax": 5800.00},
                                {"min": 113200, "max": 209275, "rate": 0.24, "base_tax": 17966.00},
                                {"min": 209275, "max": 263725, "rate": 0.32, "base_tax": 41024.00},
                                {"min": 263725, "max": 648100, "rate": 0.35, "base_tax": 58448.00},
                                {"min": 648100, "max": None, "rate": 0.37, "base_tax": 192979.25},
                            ],
                            "married_filing_jointly": [
                                {"min": 0, "max": 19300, "rate": 0.00, "base_tax": 0},
                                {"min": 19300, "max": 44100, "rate": 0.10, "base_tax": 0},
                                {"min": 44100, "max": 120100, "rate": 0.12, "base_tax": 2480.00},
                                {"min": 120100, "max": 230700, "rate": 0.22, "base_tax": 11600.00},
                                {"min": 230700, "max": 422850, "rate": 0.24, "base_tax": 35932.00},
                                {"min": 422850, "max": 531750, "rate": 0.32, "base_tax": 82048.00},
                                {"min": 531750, "max": 788000, "rate": 0.35, "base_tax": 116896.00},
                                {"min": 788000, "max": None, "rate": 0.37, "base_tax": 206583.50},
                            ],
                            "head_of_household": [
                                {"min": 0, "max": 15550, "rate": 0.00, "base_tax": 0},
                                {"min": 15550, "max": 33250, "rate": 0.10, "base_tax": 0},
                                {"min": 33250, "max": 83000, "rate": 0.12, "base_tax": 1770.00},
                                {"min": 83000, "max": 121250, "rate": 0.22, "base_tax": 7740.00},
                                {"min": 121250, "max": 217300, "rate": 0.24, "base_tax": 16155.00},
                                {"min": 217300, "max": 271750, "rate": 0.32, "base_tax": 39207.00},
                                {"min": 271750, "max": 656150, "rate": 0.35, "base_tax": 56631.00},
                                {"min": 656150, "max": None, "rate": 0.37, "base_tax": 191171.00},
                            ],
                        },
                        # Step 2 checkbox bracket tables — line 1g = $0 when Step 2 is checked
                        "step2_brackets": {
                            "single": [
                                {"min": 0, "max": 8050, "rate": 0.00, "base_tax": 0},
                                {"min": 8050, "max": 14250, "rate": 0.10, "base_tax": 0},
                                {"min": 14250, "max": 33250, "rate": 0.12, "base_tax": 620.00},
                                {"min": 33250, "max": 60900, "rate": 0.22, "base_tax": 2900.00},
                                {"min": 60900, "max": 108938, "rate": 0.24, "base_tax": 8983.00},
                                {"min": 108938, "max": 136163, "rate": 0.32, "base_tax": 20512.00},
                                {"min": 136163, "max": 328350, "rate": 0.35, "base_tax": 29224.00},
                                {"min": 328350, "max": None, "rate": 0.37, "base_tax": 96489.63},
                            ],
                            "married_filing_jointly": [
                                {"min": 0, "max": 16100, "rate": 0.00, "base_tax": 0},
                                {"min": 16100, "max": 28500, "rate": 0.10, "base_tax": 0},
                                {"min": 28500, "max": 66500, "rate": 0.12, "base_tax": 1240.00},
                                {"min": 66500, "max": 121800, "rate": 0.22, "base_tax": 5800.00},
                                {"min": 121800, "max": 217875, "rate": 0.24, "base_tax": 17966.00},
                                {"min": 217875, "max": 272325, "rate": 0.32, "base_tax": 41024.00},
                                {"min": 272325, "max": 400450, "rate": 0.35, "base_tax": 58448.00},
                                {"min": 400450, "max": None, "rate": 0.37, "base_tax": 103291.75},
                            ],
                            "head_of_household": [
                                {"min": 0, "max": 12075, "rate": 0.00, "base_tax": 0},
                                {"min": 12075, "max": 20925, "rate": 0.10, "base_tax": 0},
                                {"min": 20925, "max": 45800, "rate": 0.12, "base_tax": 885.00},
                                {"min": 45800, "max": 64925, "rate": 0.22, "base_tax": 3870.00},
                                {"min": 64925, "max": 112950, "rate": 0.24, "base_tax": 8077.50},
                                {"min": 112950, "max": 140175, "rate": 0.32, "base_tax": 19603.50},
                                {"min": 140175, "max": 332375, "rate": 0.35, "base_tax": 28315.50},
                                {"min": 332375, "max": None, "rate": 0.37, "base_tax": 95585.50},
                            ],
                        },
                    },
                    effective_date=date(2026, 1, 1),
                    superseded_date=None,
                    note="IRS Pub 15-T 2026 — annualized percentage method; 0% band baked into brackets; dedicated Step 2 checkbox tables",
                ),
                # ── Illinois income tax — flat rate ───────────────────────────
                dict(
                    config_key="illinois_income_tax",
                    config_value={
                        "tax_year": 2025,
                        "rate": 0.0495,
                        "description": "Illinois flat income tax rate effective 2017-07-01",
                    },
                    effective_date=date(2025, 1, 1),
                    superseded_date=None,
                    note="IL flat rate 4.95%",
                ),
                # ── Payroll validation thresholds ─────────────────────────────
                dict(
                    config_key="payroll_validation_config",
                    config_value={
                        "max_gross_earnings": 50000,
                        "max_days_per_period": 31,
                        "employee_contribution_rate": 0.08,
                        "employer_contribution_rate": 0.05,
                        "contribution_rate_tolerance": 0.005,
                        "mode": "warn",
                    },
                    effective_date=date(2024, 1, 1),
                    superseded_date=None,
                    note="Fund-level payroll validation thresholds; mode=warn flags rows without rejecting",
                ),
            ]

            config_rows = {}
            for cd in configs_data:
                obj, _ = await get_or_create(
                    session,
                    SystemConfiguration,
                    {"config_key": cd["config_key"], "effective_date": cd["effective_date"]},
                    {k: v for k, v in cd.items() if k not in ("config_key", "effective_date")},
                )
                config_rows[(cd["config_key"], str(cd["effective_date"]))] = obj

            proportional_config = config_rows[("service_credit_accrual_rule", "1980-01-01")]
            monthly_floor_config = config_rows[("service_credit_accrual_rule", "2024-09-01")]

            # ── Plan tiers ────────────────────────────────────────────────────
            tier1, _ = await get_or_create(
                session, PlanTier,
                {"tier_code": "tier_1"},
                {"tier_label": "Tier I", "effective_date": date(1980, 1, 1)},
            )
            tier2, _ = await get_or_create(
                session, PlanTier,
                {"tier_code": "tier_2"},
                {"tier_label": "Tier II", "effective_date": date(2011, 1, 1)},
            )

            # ── Plan types ────────────────────────────────────────────────────
            traditional, _ = await get_or_create(
                session, PlanType,
                {"plan_code": "traditional"},
                {"plan_label": "Traditional"},
            )
            portable, _ = await get_or_create(
                session, PlanType,
                {"plan_code": "portable"},
                {"plan_label": "Portable"},
            )

            # ── Plan configuration: Tier I Traditional general_staff ──────────
            await get_or_create(
                session, PlanConfiguration,
                {"plan_tier_id": tier1.id, "plan_type_id": traditional.id, "employment_type": "general_staff", "effective_date": date(1980, 1, 1)},
                {
                    "benefit_multiplier": Decimal("0.0167"),
                    "fac_years": 4,
                    "vesting_years": 5,
                    "normal_retirement_age": 62,
                    "member_contribution_rate": Decimal("0.0800"),
                    "cola_type": "compound",
                    "cola_rate": Decimal("0.0300"),
                    "cola_cap": Decimal("0.0300"),
                    "sick_time_eligible": True,
                    "sick_time_conversion_rate": Decimal("1.0"),
                },
            )

            # ── Leave types ───────────────────────────────────────────────────
            for code, label in [
                ("sick", "Sick Leave"),
                ("sick_retirement_eligible", "Sick Leave (Retirement Eligible)"),
                ("sick_cba", "Sick Leave (CBA)"),
                ("vacation", "Vacation"),
            ]:
                await get_or_create(session, LeaveType, {"type_code": code}, {"type_label": label})

            # ── Employer ──────────────────────────────────────────────────────
            employer, _ = await get_or_create(
                session, Employer,
                {"employer_code": "SUIL-001"},
                {"name": "State University of Illinois", "employer_type": "university"},
            )

            # ── Member: Jane Smith ────────────────────────────────────────────
            jane_ssn = "987654321"
            member, created = await get_or_create(
                session, Member,
                {"member_number": "MVP-001"},
                {
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "date_of_birth": date(1965, 3, 15),
                    "ssn_encrypted": encrypt_ssn(jane_ssn),
                    "ssn_last_four": jane_ssn[-4:],
                    "member_status": "retired",
                    "status_date": date(2025, 1, 15),
                    "plan_tier_id": tier1.id,
                    "plan_type_id": traditional.id,
                    "plan_choice_date": date(2000, 1, 15),
                    "plan_choice_locked": True,
                    "certification_date": date(2000, 1, 15),
                },
            )

            # ── Address ───────────────────────────────────────────────────────
            existing_addr = await session.execute(
                select(MemberAddress).where(MemberAddress.member_id == member.id)
            )
            if not existing_addr.scalar_one_or_none():
                session.add(MemberAddress(
                    member_id=member.id,
                    address_type="primary",
                    line1="123 Main Street",
                    city="Springfield",
                    state="IL",
                    zip="62701",
                    effective_date=date(2000, 1, 15),
                ))

            # ── Employment record ─────────────────────────────────────────────
            emp, _ = await get_or_create(
                session, EmploymentRecord,
                {"member_id": member.id, "employer_id": employer.id, "hire_date": date(2000, 1, 15)},
                {
                    "employment_type": "general_staff",
                    "position_title": "Administrative Specialist",
                    "percent_time": Decimal("100.00"),
                    "termination_date": date(2025, 1, 15),
                    "termination_reason": "retirement",
                    "is_primary": True,
                },
            )

            # ── Salary history ────────────────────────────────────────────────
            salary_rows = [
                (date(2000, 1, 15), date(2005, 8, 31), Decimal("45000.00"), "Initial hire salary"),
                (date(2005, 9, 1),  date(2012, 8, 31), Decimal("52000.00"), "Merit increase"),
                (date(2012, 9, 1),  date(2019, 8, 31), Decimal("62000.00"), "Promotion"),
                (date(2019, 9, 1),  date(2025, 1, 15), Decimal("72000.00"), "Senior classification"),
            ]
            existing_salaries = await session.execute(
                select(SalaryHistory).where(SalaryHistory.employment_id == emp.id)
            )
            if not existing_salaries.scalars().all():
                for eff, end, sal, reason in salary_rows:
                    session.add(SalaryHistory(
                        employment_id=emp.id,
                        effective_date=eff,
                        end_date=end,
                        annual_salary=sal,
                        change_reason=reason,
                    ))

            # ── Beneficiary: Robert Smith ─────────────────────────────────────
            await get_or_create(
                session, Beneficiary,
                {"member_id": member.id, "first_name": "Robert", "last_name": "Smith"},
                {
                    "relationship": "spouse",
                    "beneficiary_type": "primary",
                    "share_percent": Decimal("100.00"),
                    "effective_date": date(2000, 1, 15),
                },
            )

            # ── Service credit entries ────────────────────────────────────────
            existing_sc = await session.execute(
                select(ServiceCreditEntry).where(ServiceCreditEntry.member_id == member.id)
            )
            if not existing_sc.scalars().all():
                # Period 1: 2000-01-15 to 2024-08-31 — proportional_percent_time rule
                # Days: (2024-09-01 - 2000-01-15) = 24 years, 7 months, 16 days
                period1_start = date(2000, 1, 15)
                period1_end = date(2024, 8, 31)
                days1 = (date(2024, 9, 1) - period1_start).days
                years1 = round(days1 / 365.25, 6)

                session.add(ServiceCreditEntry(
                    member_id=member.id,
                    employment_id=emp.id,
                    entry_type="earned",
                    credit_days=Decimal(str(days1)),
                    credit_years=Decimal(str(years1)),
                    period_start=period1_start,
                    period_end=period1_end,
                    accrual_rule_config_id=proportional_config.id,
                    note="Earned service credit: proportional_percent_time rule",
                ))

                # Period 2: 2024-09-01 to 2025-01-15 — monthly_floor rule
                # Months: Sep, Oct, Nov, Dec 2024, Jan 2025 = 5 months (any time in month = 1/12 year)
                period2_start = date(2024, 9, 1)
                period2_end = date(2025, 1, 15)
                months2 = 5  # Sep, Oct, Nov, Dec, Jan
                days2 = months2 * 30  # representative days for 5 months
                years2 = round(months2 / 12, 6)

                session.add(ServiceCreditEntry(
                    member_id=member.id,
                    employment_id=emp.id,
                    entry_type="earned",
                    credit_days=Decimal(str(days2)),
                    credit_years=Decimal(str(years2)),
                    period_start=period2_start,
                    period_end=period2_end,
                    accrual_rule_config_id=monthly_floor_config.id,
                    note="Earned service credit: monthly_floor rule (post-2024-09-01)",
                ))

        # ── Summary ───────────────────────────────────────────────────────────
        result = await session.execute(
            select(ServiceCreditEntry).where(ServiceCreditEntry.member_id == member.id)
        )
        entries = result.scalars().all()
        total_years = sum(float(e.credit_years or 0) for e in entries)

        print(f"\nSeeded Jane Smith (id: {member.id})")
        print(f"Total service credit years: {total_years:.4f}")
        print(f"Expected: ~25.0 years\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())

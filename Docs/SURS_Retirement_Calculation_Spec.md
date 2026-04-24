# SURS Retirement Benefit Calculation — Technical Specification

**Scope:** Traditional and Portable Plan only. RSP (Self-Managed Plan) is excluded.  
**Authority:** 40 ILCS 5/15-136 (Illinois Pension Code); JCAR Section 1600.420  
**Source docs:** 03 Retirement Claims BPR v2.0 (2020), 11 Retirement Estimates BPR v2.0 (2020), SURS FAQs

---

## 1. Member Classification (Required Inputs)

| Field | Notes |
|---|---|
| `plan_type` | `"traditional"` or `"portable"` |
| `tier` | Determined by certification (participation begin) date |
| `cert_date` | Certification/participation begin date |
| `birth_date` | Required. Must be verified before PEP can be issued. |
| `retirement_date` | Effective date of retirement (first day of month, or any day — but payment starts first of following month) |
| `termination_date` | Last day worked + 1; or last day of employment |
| `employer` | SURS-covered employer (one of ~60 agencies) |
| `position` | Optional. Defaults to "staff." Used to confirm salary classification and contribution rate. |

**Tier logic:**
- **Tier I** = cert_date before `2011-01-01`
- **Tier II** = cert_date on or after `2011-01-01`

---

## 2. Eligibility Requirements

### Tier I (cert before 2011-01-01)
- Age 55 with ≥ 8 years service (age reduction applies)
- Age 62 with ≥ 5 years service
- Any age with ≥ 30 years service *(only if termination on or after 2002-08-02)*

### Tier II (cert on or after 2011-01-01)
- Age 62 with ≥ 10 years service (age reduction applies)
- Age 67 with ≥ 10 years service

---

## 3. Service Credit

### 3.1 Components

| Component | Notes |
|---|---|
| `surs_service` | Base SURS employment service credit |
| `sick_leave_credit` | Unused/unpaid sick leave converted to service (see table below). Only if retired within 60 days of termination. Max 1.0 year. |
| `surs_total_with_sick` | `surs_service + sick_leave_credit` |
| `ope_service` | Other Public Employment — purchased service credit. Used in MP formula separately (multiplier = 2x, not 2.4x). |
| `military_service` | Purchased. Used in MP formula separately (multiplier = 1x). |
| `reciprocal_service` | From reciprocal systems. Added for eligibility; used in General Formula if applicable. Not used in Police/Fire formula. |
| `total_service_with_reciprocal` | `surs_total_with_sick + reciprocal_service` |

### 3.2 Sick Leave Conversion Table

| Unused Unpaid Sick Days | Additional Service Credit |
|---|---|
| 20–59 days | 0.25 years |
| 60–119 days | 0.50 years |
| 120–179 days | 0.75 years |
| 180+ days | 1.00 year |

*Condition: Member must retire within 60 days of termination.*

### 3.3 OPE and Insurance Eligibility
OPE service credit determines `eligible_insurance_service_years`. This is a separate field from retirement benefit service — OPE service feeds both the MP formula (at 2x multiplier) and insurance eligibility tracking.

### 3.4 Service Waived
If member has contributed more than necessary to reach the 80% maximum benefit cap, excess service credit may be waived. Waiver order (last purchased first): OPE → Prior Service → Repay Refund → Military. FAE years are never waived.

### 3.5 Part-Time Adjustment
If member has more than 3 years at ≤ 50% time (effective 1991-07-01), benefit service credit and the benefit amount may be reduced. Vesting service (for eligibility) is not affected. First 3 years at lowest percentages are granted free. Remaining years adjusted by `(percentage_worked / FAE_average_percentage) × service_credit`.

---

## 4. Final Average Earnings (FAE / FRE)

The FAE is the salary basis for the General Formula. Take whichever method produces the **higher** result.

### 4.1 Tier I (cert before 2011-01-01, term on or after 1971-07-15)

**Method A — High 4 Consecutive Academic Years**
- Cannot skip partial years; can skip years with zero service
- If member works ≥ 6 months in final academic year, may assume full base pay for that year
- Sum the 4 years ÷ 4

**Method B — 48-Month Actual Earnings**
- Only applies if member has a 12-month contract
- Use earnings as *earned* (not paid) in the 48 months preceding termination
- Sum ÷ 4 for annual, ÷ 48 for monthly

**Method C — Actual Service/Earnings**
- Used only when member has fewer than 4 years of service

**Earnings cap:** Any academic year (after 1997-06-30) where earnings increased ≥ 20% over the prior year with the same employer are capped at the prior year's amount + 20%. This prevents salary spiking.

### 4.2 Tier II (cert on or after 2011-01-01)
- High 8 consecutive academic years within the last 10 years, **or**
- Highest 96 consecutive months within the last 120 months
- Whichever is higher

### 4.3 FAE for Police/Firefighter (Tier I)
Use the highest of:
- High 4 consecutive academic years
- Last 48 months
- Annual base rate of earnings on last day worked

### 4.4 Output
| Field | Formula |
|---|---|
| `fae_annual` | FAE per method above |
| `fae_monthly` | `fae_annual / 12` |
| `fae_maximum_pct` | 80% (standard for term on/after 1997-07-07); varies by age/term date for earlier terminations — see max benefit table |
| `fae_maximum_dollar` | `fae_annual × fae_maximum_pct` |

---

## 5. Retirement Benefit Calculations

The system calculates all applicable formulas and selects the **highest** result as the member's base unreduced annuity.

---

### 5.1 General Formula

**Eligibility:** All Traditional and Portable plan members.

**Formula (term date on or after 1997-07-07):**
```
total_service_credit × 2.2% × fae_annual = annual_general_benefit
annual_general_benefit / 12 = monthly_general_benefit
```

**Formula (term date before 1997-07-07 — Graduated):**
```
First 10 years  × 1.67%
Next 10 years   × 1.90%
Next 10 years   × 2.10%
Remaining years × 2.30%
Sum of all tiers × fae_annual = annual_general_benefit
```

**Maximum benefit cap:** 80% of FAE (for term on/after 1997-07-07). Earlier terminations have lower caps based on age at retirement — see Section 9.

**Age Reduction (if applicable):**
- Applies when member retires before normal retirement age and has fewer than 30 years service (Tier I) or any retirement before 67 (Tier II)
- Tier I normal retirement age: 60 (unless 30+ years service or disability)
- Tier II normal retirement age: 67
- Reduction: **0.5% per month** short of normal retirement age
- `age_reduction_factor = 1 - (months_short × 0.005)`
- `reduced_general_benefit = monthly_general_benefit × age_reduction_factor`

---

### 5.2 Money Purchase Formula

**Eligibility:** Member certified (participation began) **before 2005-07-01** (Tier I only). Members certified on or after 2005-07-01 are not eligible.

**Inputs required:**
- `normal_contributions_and_interest` (C&I) — employee + employer contributions in "normal" bucket, with interest
- `actuarial_factor` — life expectancy factor from actuarial table, based on member's age at retirement
- Contribution rate: 6.5% for standard members; 8% (or 9.5%) for police/firefighters

**Standard calculation (all service after 1969-09-01, non-OPE, non-Military):**
```
(normal_C_and_I × 2.4) / actuarial_factor = monthly_MP_benefit
```

**OPE time (separate calc, then sum):**
```
(ope_C_and_I × 2) / actuarial_factor = ope_MP_benefit
```

**Military time (separate calc, then sum):**
```
(military_C_and_I × 1) / actuarial_factor = military_MP_benefit
```

**Total MP benefit:**
```
total_MP_benefit = standard_MP_benefit + ope_MP_benefit + military_MP_benefit
```

Note: "Divided by factor" on the hand calc sheet refers to the actuarial factor lookup. This table is maintained by SURS and is age-based.

---

### 5.3 Minimum Annuity (HB2616)

**Eligibility:** All members with ≥ 50% time worked.

**Formula:**
```
min_benefit = $25.00 × min(years_service_credit, 30)
```
Maximum = $750.00/month.

**This is a floor, not a standalone formula.** If the member's total calculated benefit (General or MP, plus AAI, plus supplemental annuity, minus reversionary reduction) is less than this amount, the difference is paid as a monthly supplemental payment.

```
supplemental_payment = max(0, min_benefit - total_calculated_benefit)
```

Supplemental payment is recalculated annually after each AAI is applied, until it reaches zero.

---

### 5.4 Police/Firefighter Formula (Conditional)

**Eligibility (Tier I):**
- Contributed 9.5% to SURS, AND
- Age 50+ with ≥ 25 years P/F service, OR age 55+ with ≥ 20 but < 25 years P/F service

**Eligibility (Tier II):**
- Age 60+ with ≥ 20 years P/F service (no age reduction)

**Formula (graduated, capped at 80%):**
```
First 10 years  × 2.25%
Second 10 years × 2.50%
Third 10+ years × 2.75%
Sum (capped at 80%) × police_fire_FAE = annual_PF_benefit
```

**FAE for P/F:** Use highest of 4 consecutive academic years, 48 months, or base rate on last day worked (Tier I).

**Reciprocal service:** Not included in P/F formula. Non-P/F SURS service is calculated using General Formula and added.

**Cert date matters for service credit scope:**
- Certified on or after 1988-01-26: only P/F service used in P/F formula; other SURS service → General Formula
- Certified before 1988-01-26: all SURS service may be considered

**If P/F eligibility not met:**
- Terminated before 1998-08-14: additional 1.5% contributions refunded as lump sum or additional annuity
- Terminated on/after 1998-08-14 and highest formula = General: refund as lump sum or additional annuity
- Terminated on/after 1998-08-14 and highest formula = MP: 1.5% used in MP calc (no lump sum option)

---

## 6. Selecting the Final Annuity Formula

```
base_unreduced_annuity = max(
  reduced_general_benefit,  // after age reduction
  total_MP_benefit,          // if eligible
  police_fire_benefit        // if eligible
)
```

If `base_unreduced_annuity < min_benefit`, supplemental payment applies (Section 5.3).

---

## 7. Benefit Options / Reductions

### 7.1 Traditional Plan — Reversionary Annuity (Optional)

Member receives reduced annuity; beneficiary receives income after member's death in addition to normal survivor benefit.

**Two options:**
- **Option 1:** Member keeps reduced annuity even if beneficiary dies first
- **Option 2:** Member's annuity is restored to full amount if beneficiary dies first

**Calculation:**
```
reversionary_cost = lookup(reversionary_table, member_age, beneficiary_age)
reversionary_reduction = (base_unreduced_annuity / 100) × reversionary_cost
reduced_annuity = base_unreduced_annuity - reversionary_reduction
```

Reversionary amount payable to beneficiary is capped at: `reduced_annuity - monthly_survivor_benefit`

AAI for Traditional members with reversionary is calculated on the **unreduced** base annuity.

**Deadline:** Election of Reversionary Annuity form must be received ≥ 30 days before retirement effective date. Only one beneficiary allowed.

### 7.2 Portable Plan — Joint & Survivor Annuity (Default if Married)

**Default forms:**
- Married → Joint & Survivor 50% (spouse as contingent annuitant)
- Not married → Single-Life Annuity

**Optional forms (elected in writing within 180-day window):**
- J&S 50%, 75%, or 100%
- Lump-Sum Retirement (contributions + interest + equal employer contributions)

J&S amounts are actuarially equivalent to the single-life annuity. Factors are maintained in J&S tables (member age × beneficiary age → percentage of benefit member receives).

AAI for Portable J&S is calculated on the **reduced** annuity amount.

Spouse consent required (written and notarized) to elect any option other than J&S 50% with spouse.

---

## 8. Automatic Annual Increase (AAI / COLA)

### Tier I
- Rate: **3% compounded** annually
- First increase: January 1 following the month of retirement, prorated for months retired
- Applied to: base retirement annuity (not additional annuities)

### Tier II
- Rate: **lesser of 3% or ½ of CPI-U** from prior year (non-compounding)
- If CPI-U is zero or negative: no increase that year
- First increase: January 1 on or after the **later of** age 67 or first anniversary of annuity start
- Applied to: original (base) retirement annuity amount

---

## 9. Maximum Benefit Cap

Standard (term date on/after 1997-07-07): **80% of FAE**

For earlier terminations, cap varies by age at retirement and termination date period:

| Age at Retirement | Term before 8/15/1969 | Term 8/15/69–8/27/73 | Term 8/27/73–9/14/77 | Term 9/14/77–7/6/97 | Term on/after 7/7/97 |
|---|---|---|---|---|---|
| ≤ 60 | 60% | 70% | 70% | 75% | 80% |
| 61 | 61.67% | 71.67% | 72% | 75% | 80% |
| 62 | 63.33% | 73.33% | 74% | 75% | 80% |
| 63 | 65% | 75% | 76% | 76% | 80% |
| 64 | 66.67% | 76.67% | 78% | 78% | 80% |
| 65 | 68.33% | 78.33% | 80% | 80% | 80% |
| ≥ 66 | 70% | 80% | 80% | 80% | 80% |

Exception: Members certified on/after 1977-09-15 and terminated before 1997-07-07 → max 75% regardless of age.
Exception: May allow 85% if a reciprocal system allows it.
Exception: Public Act 91-395 members — maximum does not apply (requires manual review).

---

## 10. Income Tax / Previously Taxed Contributions

| Field | Notes |
|---|---|
| `previously_taxed_contributions` | Contributions made with after-tax dollars |
| `number_of_months` | Expected benefit payment period |
| `monthly_exclusion` | `previously_taxed_contributions / number_of_months` — excluded from taxable income each month |

---

## 11. Highest Annual Earnings (HAE)

Used to determine return-to-work earnings limits, not the retirement benefit itself.

- `hae` = highest annual earnings from any academic year prior to retirement (including reciprocal system earnings if applicable)
- `earnings_limitation_type` = age-based rule:
  - Annuity began before age 60: monthly earnings ≤ base monthly annuity
  - Annuity began at age 60+: annual earnings + annual base annuity ≤ HAE

---

## 12. Transfers (Page 2 — Balance Sheet Items)

These are accounting entries at retirement, not inputs to the benefit calculation:

- Employee accumulated contributions
- Reserve for funded retirement & reversionary annuities (employee + employer contributions)
- Reserve for survivors insurance benefits
- Reserve for automatic annual increase
- Interest Rate Difference

These are populated by the payment system at finalization and do not affect the output monthly annuity amount.

---

## 13. Preliminary Estimated Payment (PEP)

Issued while claim is being finalized. Target: 80–90% of projected final benefit.

**PEP calculation:**
- Non-reciprocal: 90% of the higher of MP or General Formula
- Reciprocal:
  - General Formula: 90% of MP, or if not MP-eligible, 80% of General Formula
  - MP: 80% of MP Formula
- HB2616 members: 80% of MP or $75.00, whichever is higher

**PEP excludes:** current year earnings, current year vacation payments, sick leave credit, reciprocal credits, service credit purchased after application received.

At finalization: member receives lump sum for underpayment (no interest). Overpayment recovered from future benefits (no interest).

---

## 14. Reciprocal Service (Conditional)

Only needed when member has service in one or more of the 13 Illinois reciprocal retirement systems.

- Combined service must meet the longest minimum service requirement of any participating system
- Only 1.0 year of service credit per academic year across all systems combined
- Benefit start date must be the same in all systems (exceptions: different backdating provisions, age minimums, payment date rules)
- SURS may use FAE from a reciprocal system if higher than SURS FAE (20% earnings cap and 4-year minimum still apply)
- Reciprocal service credit is **not** used in the Police/Firefighter Formula

---

## 15. Calculation Decision Tree (Summary)

```
1. Determine tier (cert_date)
2. Check eligibility (age + service)
3. Calculate service credit total (SURS + sick leave + OPE + military; add reciprocal if applicable)
4. Compute FAE using applicable method (Tier I: High 4 vs 48-month; Tier II: High 8 vs 96-month)
   → Apply 20% earnings cap
   → Apply part-time adjustment if applicable
5. Calculate General Formula benefit → apply age reduction if applicable
6. If cert_date < 2005-07-01: Calculate Money Purchase benefit
7. If P/F eligible: Calculate Police/Firefighter benefit
8. Select highest formula result
9. Apply benefit option reduction (Reversionary or J&S) if elected
10. Compute AAI (Tier I: 3% compound; Tier II: lesser of 3% or ½ CPI-U)
11. Check HB2616 minimum floor → compute supplemental payment if needed
12. Apply 80% (or applicable) maximum benefit cap
13. Output: monthly_annuity (unreduced), monthly_annuity (reduced if option elected), supplemental_payment, AAI_start_date, aai_amount
```

---

## 16. API Output Fields (Proposed)

```json
{
  "member_id": "...",
  "retirement_date": "YYYY-MM-DD",
  "tier": "I" | "II",
  "plan_type": "traditional" | "portable",
  "service_credit": {
    "surs_service": 0.00,
    "sick_leave_credit": 0.00,
    "ope_service": 0.00,
    "military_service": 0.00,
    "reciprocal_service": 0.00,
    "total": 0.00
  },
  "fae": {
    "method_used": "high_4" | "48_month" | "actual",
    "annual": 0.00,
    "monthly": 0.00
  },
  "formulas": {
    "general": {
      "applicable": true,
      "unreduced_monthly": 0.00,
      "age_reduction_months": 0,
      "age_reduction_factor": 1.00,
      "reduced_monthly": 0.00
    },
    "money_purchase": {
      "applicable": true | false,
      "standard_monthly": 0.00,
      "ope_monthly": 0.00,
      "military_monthly": 0.00,
      "total_monthly": 0.00
    },
    "police_fire": {
      "applicable": false,
      "monthly": 0.00
    }
  },
  "formula_selected": "general" | "money_purchase" | "police_fire",
  "base_unreduced_annuity_monthly": 0.00,
  "benefit_option": {
    "type": "single_life" | "reversionary" | "js_50" | "js_75" | "js_100" | "lump_sum",
    "reduction_amount": 0.00,
    "reduced_annuity_monthly": 0.00
  },
  "aai": {
    "rate_type": "3pct_compound" | "cpi_u_half",
    "first_increase_date": "YYYY-MM-DD",
    "basis_amount": 0.00
  },
  "hb2616_minimum": {
    "minimum_monthly": 0.00,
    "supplemental_payment": 0.00
  },
  "maximum_benefit_cap": {
    "percentage": 80,
    "capped": false
  },
  "final_monthly_annuity": 0.00,
  "eligible_insurance_service_years": 0.00
}
```

---

## 17. Fields That Are Conditional / Not Always Required

| Field | Condition |
|---|---|
| `sick_leave_credit` | Only if retired within 60 days of termination and unused sick days ≥ 20 |
| `reciprocal_service` | Only if member has service in a reciprocal Illinois system |
| `money_purchase` | Only if cert_date < 2005-07-01 |
| `police_fire` | Only if member meets P/F eligibility criteria |
| `age_reduction` | Only if retiring before normal age with < 30 years service |
| `reversionary` | Traditional plan only; must be elected ≥ 30 days before retirement |
| `joint_survivor` | Portable plan only |
| `hb2616_supplemental` | Only if computed benefit < minimum floor |
| `ope_service` / `ope_MP` | Only if member purchased OPE credit |
| `military_service` / `military_MP` | Only if member has purchased military credit |
| `part_time_adjustment` | Only if > 3 years at ≤ 50% time |
| `previously_taxed_contributions` | Only if member made after-tax contributions |
| `reciprocal_benefit_amount` | Only for reciprocal calculations |
| `hae_earnings_limitation` | Only relevant for return-to-work scenarios |
| `claim_number` | Internal tracking; not required for calculation |
| `member_id` | Internal tracking; not required for calculation logic |

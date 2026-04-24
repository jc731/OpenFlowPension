# Actuarial Tables

SURS actuarial factor tables used in benefit option calculations. Source Excel files are in `Docs/source/`.

## Files

| File | Description | Axes |
|---|---|---|
| `reversionary_value_{date}.csv` | Value of $1/month of reversionary annuity | row=beneficiary_age, col=member_age |
| `reversionary_reduction_{date}.csv` | Member pension reduction per $1/month of reversionary annuity | row=beneficiary_age, col=member_age |
| `js_50pct_{date}.csv` | Portable J&S 50% survivor factor | row=beneficiary_age, col=member_age |
| `js_75pct_{date}.csv` | Portable J&S 75% survivor factor | row=beneficiary_age, col=member_age |
| `js_100pct_{date}.csv` | Portable J&S 100% survivor factor | row=beneficiary_age, col=member_age |

## Usage

All tables are 120×120. The factor at `(bene_age, member_age)` is applied as:

- **Reversionary**: `reversionary_amount = desired_reversionary_monthly / reversionary_value_factor`, `member_reduction = reversionary_amount * reversionary_reduction_factor`
- **J&S**: member receives `base_annuity * js_factor`; survivor receives the elected percentage of that amount

## Updating

When SURS publishes a new experience review, convert the new Excel file using the same sheet structure (data starts row 10, ages 1–120 in rows 11–130 and columns B–DQ) and add new CSVs with the new effective date in the filename. The effective date is the date the new tables take effect, not the review publication date.

Current tables: **2024 Experience Review**, effective **2024-07-02**
Basis: 6.50% interest, Pub-2010 Healthy Retiree Mortality Tables, MP-2021 projection scale

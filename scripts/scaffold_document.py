"""Scaffold a new document template.

Usage:
    python scripts/scaffold_document.py <slug> <type> --context provider1 provider2 ...

    type: letter | form | statement | notice

Example:
    python scripts/scaffold_document.py annual_statement statement \\
        --context member_info service_credit_summary contribution_summary

Generates:
    app/templates/documents/<slug>.html   — starter Jinja2 template
    Prints the SQL / API call to register the DB row.

Available context providers:
    fund_info              Fund name, address, contact details (auto-included)
    member_info            Member demographics and mailing address
    employment_summary     Most recent employment record and employer name
    service_credit_summary Total service credit years
    contribution_summary   Total employee/employer contributions
    benefit_estimate       Runs benefit estimate (requires retirement_date param)
    tax_elections          Current federal/state withholding elections
    beneficiaries          Primary and contingent beneficiaries
"""

import argparse
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

TEMPLATE_DIR = Path(__file__).parent.parent / "app" / "templates" / "documents"

# Variables each provider exposes — shown as hints in the scaffold template
PROVIDER_VARS = {
    "fund_info": ["fund_name", "fund_short_name", "fund_address", "fund_phone", "fund_website", "fund_email", "document_date"],
    "member_info": ["member_number", "member_full_name", "member_first_name", "member_last_name", "member_dob", "member_status", "address_formatted"],
    "employment_summary": ["employer_name", "employment_type", "hire_date", "termination_date", "percent_time"],
    "service_credit_summary": ["total_service_credit_years", "total_service_credit_display"],
    "contribution_summary": ["total_employee_contributions", "total_employer_contributions", "total_contributions"],
    "benefit_estimate": ["estimate_retirement_date", "estimate_monthly_benefit", "estimate_annual_benefit", "estimate_fae", "estimate_service_years", "estimate_formula_used"],
    "tax_elections": ["tax_elections (list)"],
    "beneficiaries": ["primary_beneficiaries (list)", "contingent_beneficiaries (list)"],
}


def scaffold_template(slug: str, doc_type: str, context_providers: list[str]) -> Path:
    """Create a starter Jinja2 HTML template file."""
    out_path = TEMPLATE_DIR / f"{slug}.html"
    if out_path.exists():
        print(f"WARNING: {out_path} already exists — not overwriting.")
        return out_path

    all_providers = ["fund_info"] + [p for p in context_providers if p != "fund_info"]
    var_hints = []
    for p in all_providers:
        vars_for_p = PROVIDER_VARS.get(p, [])
        var_hints.append(f"  {p}: " + ", ".join(vars_for_p))

    content = f"""{{% extends "_base.html" %}}

{{#
  Template: {slug}
  Type:     {doc_type}
  Context providers: {', '.join(all_providers)}

  Available variables:
{chr(10).join(var_hints)}
#}}

{{% block content %}}

<h2 class="doc-subject"><!-- Document Subject --></h2>

<div class="doc-body">

  <p>Dear {{{{ member_full_name }}}},</p>

  <p><!-- Main body text here --></p>

  <!-- Example data table:
  <table class="data-table">
    <tr><th colspan="2">Section Title</th></tr>
    <tr><td>Label</td><td class="amount">{{{{ variable }}}}</td></tr>
  </table>
  -->

  <div class="notice">
    <!-- Any important notices or disclaimers -->
  </div>

</div>

<div class="signature-block">
  <p>Sincerely,</p>
  <div class="signature-line">
    {{{{ fund_name }}}}<br>
    Member Services
  </div>
</div>

{{% endblock %}}
"""

    out_path.write_text(content)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Scaffold a new document template")
    parser.add_argument("slug", help="Template slug (e.g. annual_benefit_statement)")
    parser.add_argument("type", choices=["letter", "form", "statement", "notice"])
    parser.add_argument("--context", nargs="*", default=[], help="Context provider names")
    parser.add_argument("--description", default="", help="Human-readable description")
    args = parser.parse_args()

    # Validate providers
    from app.services.document_context_providers import CONTEXT_PROVIDERS
    unknown = [p for p in args.context if p not in CONTEXT_PROVIDERS]
    if unknown:
        print(f"ERROR: Unknown context providers: {unknown}")
        print(f"Available: {sorted(CONTEXT_PROVIDERS)}")
        sys.exit(1)

    # Create template file
    out_path = scaffold_template(args.slug, args.type, args.context)
    print(f"✓ Template file created: {out_path}")

    # Print API call / DB instructions
    config_value = {
        "context": args.context,
        "title": args.slug.replace("_", " ").title(),
        "params_schema": {},
    }
    print()
    print("Next: register the template in the database.")
    print()
    print("Option 1 — API call (server must be running):")
    print(f"  POST /api/v1/document-templates")
    print(f"  Body: {json.dumps({'slug': args.slug, 'document_type': args.type, 'template_file': f'{args.slug}.html', 'description': args.description or args.slug, 'config_value': config_value}, indent=2)}")
    print()
    print("Option 2 — seed_mvp.py entry:")
    print(f"""  DocumentTemplate(
      slug="{args.slug}",
      document_type="{args.type}",
      template_file="{args.slug}.html",
      description="{args.description or args.slug}",
      config_value={json.dumps(config_value, indent=6)},
  )""")


if __name__ == "__main__":
    main()

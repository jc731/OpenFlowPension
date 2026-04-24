"""Actuarial table loader and lookup functions.

Tables live in data/actuarial_tables/ relative to the project root.
They are loaded once on first access and cached in memory.

Table format: CSV with row=beneficiary_age (1-120), col=member_age (1-120).
"""

from __future__ import annotations

import csv
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

_TABLES_DIR = Path(__file__).parents[3] / "data" / "actuarial_tables"

# Maps option_type → filename suffix
_JS_SUFFIXES = {
    "js_50": "js_50pct",
    "js_75": "js_75pct",
    "js_100": "js_100pct",
}


def _latest_csv(prefix: str) -> Path:
    """Return the CSV with the most recent date suffix matching `prefix_*.csv`."""
    candidates = sorted(_TABLES_DIR.glob(f"{prefix}_*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No actuarial table found for prefix '{prefix}' in {_TABLES_DIR}")
    return candidates[-1]


def _load_table(path: Path) -> dict[int, dict[int, Decimal]]:
    """Load a beneficiary_age × member_age CSV into a nested dict."""
    table: dict[int, dict[int, Decimal]] = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bene_age = int(row["beneficiary_age"])
            table[bene_age] = {
                int(col): Decimal(val)
                for col, val in row.items()
                if col != "beneficiary_age" and val
            }
    return table


@lru_cache(maxsize=None)
def _get_table(prefix: str) -> dict[int, dict[int, Decimal]]:
    return _load_table(_latest_csv(prefix))


def reversionary_reduction_factor(member_age: int, beneficiary_age: int) -> Decimal:
    """Member pension reduction per $1/month of reversionary annuity paid to beneficiary."""
    table = _get_table("reversionary_reduction")
    bene_age = max(1, min(120, beneficiary_age))
    mem_age = max(1, min(120, member_age))
    return table[bene_age][mem_age]


def reversionary_value_factor(member_age: int, beneficiary_age: int) -> Decimal:
    """Actuarial present value of $1/month of reversionary annuity."""
    table = _get_table("reversionary_value")
    bene_age = max(1, min(120, beneficiary_age))
    mem_age = max(1, min(120, member_age))
    return table[bene_age][mem_age]


def js_factor(option_type: str, member_age: int, beneficiary_age: int) -> Decimal:
    """J&S factor: member receives base_annuity * factor; survivor receives elected pct of that."""
    if option_type not in _JS_SUFFIXES:
        raise ValueError(f"Unknown J&S option: {option_type}")
    table = _get_table(_JS_SUFFIXES[option_type])
    bene_age = max(1, min(120, beneficiary_age))
    mem_age = max(1, min(120, member_age))
    return table[bene_age][mem_age]

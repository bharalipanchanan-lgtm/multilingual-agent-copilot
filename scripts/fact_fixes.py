"""Single-fact corrections found while checking answers in the chat, each verified on its page by apply().

    .venv/Scripts/python scripts/fact_fixes.py [--write]
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from quote_overrides import apply  # noqa: E402

FIXES = {
    # the old value said "no separate money limit"; the clause caps it at the amount in the Policy Schedule
    "care-health-care-freedom.cataract": dict(
        value="Paid up to the cataract amount set in the Policy Schedule (named ailment sub-limit).",
        unit="text", stated=True, pdf_page=8,
        section="Benefit 1 c) Conditions for payment of Medical Expenses, (iii) Named Ailments / Procedures, item i (Treatment of Cataract)",
        quote="The Company will indemnify the Insured Person for Expenses incurred in respect of the below mentioned "
              "Ailments / Procedures up to the amount specified against each and every Ailment / Procedure mentioned "
              "in the Policy Schedule in a Policy Year",
        note="The rupee amount is printed in the Policy Schedule, not in this wording."),
}

if __name__ == "__main__":
    apply(FIXES, "--write" in sys.argv)

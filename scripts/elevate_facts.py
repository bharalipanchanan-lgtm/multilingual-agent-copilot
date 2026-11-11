"""ICICI Lombard Elevate facts read from the full wording (UIN ICIHLIP27062V072627).

The auto builder picked optional-cover clauses (Room Modifier, Vital Essence)
for room rent and cataract, and missed the standard exclusions; these are the
Basic Cover / Standard Exclusion lines, each verified on its page by apply().

    .venv/Scripts/python scripts/elevate_facts.py [--write]
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from quote_overrides import apply  # noqa: E402

E = "icici-elevate."
S = {
    E + "ped_wait_months": dict(
        value=36, unit="months", stated=True, pdf_page=88, section="Standard Exclusion 1 Pre-Existing Diseases (Code-Excl01)",
        quote="Treatment of a Pre-existing Disease and its direct complications, until the expiry of 36 months of continuous coverage after the date of inception of the first Policy with Us.",
        note="An optional cover can cut this to 24 or 12 months if opted at inception (PDF page 61)."),
    E + "specified_disease_wait_months": dict(
        value=24, unit="months", stated=True, pdf_page=88,
        section="Standard Exclusion 2 Specified Disease / Procedure Waiting Period (Code-Excl02)",
        quote="Treatment of the below-listed conditions and surgeries/treatments, until the expiry of 24 months of continuous coverage after the date of inception of the first Policy with us.",
        note=None),
    E + "room_rent": dict(
        value="Room Rent up to a Single Private AC room", unit="text", stated=True, pdf_page=12, room_class="no_cap",
        section="Basic Cover 1 In-patient Treatment, i. Room Rent",
        quote="1. In-patient Treatment We will cover the Medical Expenses incurred in respect of Your Hospitalization:: i. Room Rent up to a Single Private AC room;",
        note="The Room Modifier optional cover (PDF page 62) can change this to any room, twin sharing or a % of Sum Insured cap."),
    E + "ayush": dict(
        value="AYUSH in-patient treatment is covered at a Government Recognized AYUSH Hospital or AYUSH Day Care Centre.",
        unit="text", stated=True, pdf_page=15, section="Basic Cover 6 In Patient AYUSH Hospitalization",
        quote="6. In Patient AYUSH Hospitalization We will cover the Medical Expenses incurred in respect of Your Hospitalisation for the AYUSH Treatment at a Government Recognized AYUSH Hospital or AYUSH Day Care Centre.",
        note=None),
    E + "cataract": dict(
        value="Cataract is in the listed-illness waiting list; no separate money limit is written for it.", unit="text", stated=True,
        pdf_page=89, section="Code-Excl02 list, item ix (Cataracts)",
        quote="viii. Surgery on ears / tonsils / adenoids / paranasal sinuses. ix. Cataracts.",
        note="A ₹30,000 per eye sub-limit applies only with the Vital Essence add-on (PDF page 70)."),
    E + "robotic_surgery": dict(
        value="Robotic surgery is covered as a listed Technological Advancement treatment, up to the Sum Insured and the Policy's sub-limits.",
        unit="text", stated=True, pdf_page=14, section="Basic Cover 3 Technological Advancements and Treatments, item 7 (Robotic surgeries)",
        quote="Balloon Sinuplasty Oral Chemotherapy Robotic surgeries Stereotactic radio Surgeries", note=None),
}

if __name__ == "__main__":
    apply(S, "--write" in sys.argv)

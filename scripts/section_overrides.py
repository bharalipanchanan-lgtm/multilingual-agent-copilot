"""Clause / section numbers for facts that had none, read from the PDF text
above each quote (same page or the page before). Quotes that change are
re-verified on their page by quote_overrides.apply.

    .venv/Scripts/python scripts/section_overrides.py [--write]
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from quote_overrides import apply  # noqa: E402

S = {
    "bajaj-allianz-health-guard.robotic_surgery": dict(
        section="Annexure III: Modern Treatment Methods and Advancement in Technologies, item G (Robotic surgeries)"),
    "generali-central-health-absolute.cataract": dict(section="Benefit table, Sub Limits row (Cataract)"),
    "hdfc-ergo-optima-secure-v06-2024-25-wording.cataract": dict(
        section="Section C.1.b Specified Disease/Procedure waiting period (Code-Excl02), list vi"),
    "hdfc-ergo-optima-secure-v06-2024-25-wording.ayush": dict(section="Section B-1.4 AYUSH Treatment"),
    "hdfc-ergo-optima-secure-v06-2024-25-wording.room_rent": dict(
        section="Section B-1.1 Hospitalization Expenses, 1.1.1 a (Room Rent)"),
    "hdfc-ergo-optima-secure-v08-2025-26-wording.cataract": dict(
        section="Section C.1.b Specified Disease/Procedure waiting period (Code-Excl02), list vi"),
    "hdfc-ergo-optima-secure-v08-2025-26-wording.ayush": dict(section="Section B-1.4 AYUSH Treatment"),
    "hdfc-ergo-optima-secure-v08-2025-26-wording.room_rent": dict(
        section="Section B-1.1 Hospitalization Expenses, 1.1.1 a (Room Rent)"),
    "iffco-tokio-individual-health-protector.robotic_surgery": dict(
        section="Clause 4 Modern Treatment Methods and Advancement in Technologies, item G (Robotic surgeries)"),
    "liberty-general-healthprime-connect.robotic_surgery": dict(
        section="Clause 25 Coverage for Modern Treatments, item G (Robotic surgeries)",
        quote="25. Coverage for Modern Treatments: The following procedures will be covered (wherever medically indicated) either as in patient or as part of domiciliary hospitalization or as day cafe treatment in a hospital upto 50% of Sum Insured, specified in the policy schedule, during the policy period:",
        value="Covered up to 50% of Sum Insured, as a listed modern treatment (item G, Robotic surgeries)."),
    "magma-hdi-onehealth.robotic_surgery": dict(section="Section 2.13 Modern treatment Procedures"),
    "manipalcigna-prohealth-prime.room_rent": dict(section="Annexure II: Your Coverage Details, Basic Cover"),
    "oriental-insurance-happy-family-floater.robotic_surgery": dict(
        section="Clause 3.1.15 Advanced Treatments, item G (Robotic surgeries)"),
    "sbi-general-arogya-supreme.ped_wait_months": dict(section="III) Pre-Existing Diseases (Code-Excl01)"),
    "sbi-general-arogya-supreme.room_rent": dict(section="Section C.1 In-patient Hospitalization Treatment, a) Room rent"),
    "star-health-smart-health-pro.robotic_surgery": dict(
        section="Clause 14 Coverage for Modern Treatment, item g (Robotic surgeries)"),
    "tata-aig-medicare-plus.cataract": dict(
        section="Section 3 Exclusions, List of Specific Diseases/procedures, item XXIII (Cataract)"),
    "universal-sompo-complete-healthcare.cataract": dict(section="Section E.2 Specific Waiting Period (Code-Excl02)"),
    "universal-sompo-complete-healthcare.ayush": dict(section="Section C9 AYUSH Benefit"),
    "zuno-health-insurance.entry_age_max": dict(section="Clause 4 (eligibility and maximum age of entry)"),
    "zurich-kotak-health-premier.cataract": dict(
        section="Section 3.3 Specified disease/procedure waiting period (Code-Excl02)"),
    "care-health-ultimate-care.ayush": dict(section="Base Benefits, (vi) AYUSH Treatment"),
    "care-health-ultimate-care.robotic_surgery": dict(
        section="Base Benefits, (iii) Advance Technology Methods, item G (Robotic surgeries)"),
    "niva-bupa-health-premia.robotic_surgery": dict(
        section="Section 3.25 Modern Treatments, special condition for robotic surgeries"),
    "tata-aig-health-supercharge.cataract": dict(
        section="Section 3 Exclusions, List of Specific disease/conditions/treatments, item XVIII"),
    "tata-aig-health-supercharge.robotic_surgery": dict(
        section="Table I: Mandatory Sub-Limits for Geo Plan, Robotic surgeries row",
        value="Robotic surgery has a mandatory sub-limit that rises with the sum insured: ₹1,25,000 on the lowest sum insured up to ₹5,00,000 on the highest (Geo Plan, Table I)."),
    "hdfc-ergo-optima-restore.ayush": dict(section="In-patient Treatment, Note pertaining specifically to AYUSH Treatments"),
    "hdfc-ergo-energy-health.ayush": dict(section="In-patient Treatment, Note pertaining specifically to AYUSH Treatments"),
    "star-health-comprehensive.cataract": dict(
        section="Clause 2 Specified disease / procedure waiting period (Code-Excl02), list item i"),
    "star-health-comprehensive.robotic_surgery": dict(section="Clause 4 Coverage for Modern Treatments (sub-limit table)"),
    "star-health-young-star.robotic_surgery": dict(
        section="Clause 4 Coverage for Modern Treatments (sub-limit table)",
        value="Robotic surgery has its own limit that rises with the sum insured, per the modern-treatment sub-limit table on this page (not the full sum insured)."),
    "aditya-birla-health-activ-one.cataract": dict(
        section="1.2 Specified disease / procedure Waiting Period (Code-Excl02), Eye"),
    "aditya-birla-health-activ-one.ayush": dict(section="Annexure III - Product Benefit Table, AYUSH Treatment"),
    "aditya-birla-health-activ-one.robotic_surgery": dict(
        section="Section C.1.1.1 e (Modern Procedures / Treatments)"),
    "aditya-birla-health-activ-one.room_rent": dict(section="Annexure III - Product Benefit Table, Room Rent"),
    "royal-sundaram-next-gen-health.cataract": dict(
        section="Specified disease waiting period (Code-Excl02), f) list item a) Cataract"),
    "royal-sundaram-next-gen-health.robotic_surgery": dict(section="Modern Treatments, item VII (Robotic surgeries)"),
    "care-health-care-freedom.robotic_surgery": dict(section="(a) Advance Technology Methods, item G (Robotic surgeries)"),
    "care-health-care-freedom.room_rent": dict(section="Section 3.1.1 Room Category"),
    "care-health-care-heart.room_rent": dict(
        section="Section 3.1.1 Benefit 1, i) In-patient Care (Room Rent / Room Category)",
        value="Room category is set in the Policy Schedule — for example a Single Private Room; above it, proportionate deduction applies."),
    "star-health-cardiac-care.cataract": dict(section="Clause 5.B Waiting Period for Section 1, item I"),
    "star-health-cardiac-care.ped_wait_months": dict(section="Clause 5.C Waiting Period for Section 1 (pre-existing diseases)"),
    "star-health-cardiac-care.room_rent": dict(
        section="Coverage Section 1, A (Room, Boarding and Nursing Expenses)",
        value="Up to 2% of the sum insured, maximum Rs.5,000 per day (room, boarding and nursing)."),
    "star-health-cancer-care-platinum.robotic_surgery": dict(section="Clause m) Coverage for Modern treatment"),
    "star-health-medi-classic.cataract": dict(section="Clause 3 (Cataract limits table)"),
    "star-health-medi-classic.robotic_surgery": dict(section="Clause 5 Coverage for Modern Treatments (sub-limit table)"),
    # auto-built sections that took the list marker after the quote, or cut mid-word
    "bajaj-allianz-health-guard.room_rent": dict(section="Clause i Room rent and Boarding expenses"),
    "generali-central-health-absolute.robotic_surgery": dict(section="Modern treatments list, item 7) Robotic surgeries"),
    "iffco-tokio-individual-health-protector.ayush": dict(
        section="Clause 3 (sub-limits for Room / Boarding / nursing and AYUSH hospitalization)"),
    "iffco-tokio-individual-health-protector.cataract": dict(
        section="f) List of specific diseases/procedures, item (i) Cataract"),
    "liberty-general-healthprime-connect.entry_age_max": dict(section="Clause 1 Entry Age"),
    "magma-hdi-onehealth.room_rent": dict(section="Room Rent and boarding charges (Single private AC room category)"),
    "magma-hdi-onehealth.ayush": dict(section="Exclusion 3.2.3 (AYUSH covered only under Section 2.8 Inpatient AYUSH)"),
    "magma-hdi-onehealth.cataract": dict(section="Specified disease waiting list, item 1 (Cataract)"),
    "manipalcigna-prohealth-prime.ayush": dict(section="Section D.I.9 AYUSH Treatment"),
    "manipalcigna-prohealth-prime.cataract": dict(section="Sub-limits by Base Sum Insured, Treatment of Cataract (Per Eye)"),
    "manipalcigna-prohealth-prime.robotic_surgery": dict(section="Modern treatments, item g (Robotic surgeries)"),
    "new-india-assurance-yuva-bharat-health.robotic_surgery": dict(section="Clause 3.12.7 Robotic surgeries"),
    "niva-bupa-reassure-3-0.cataract": dict(
        section="f. List of specific diseases/procedures, item ii (Cataract, glaucoma and retinal detachment)"),
    "niva-bupa-reassure-3-0.robotic_surgery": dict(section="Modern treatments, item 7 (Robotic surgeries)"),
    "star-health-smart-health-pro.cataract": dict(section="Specified disease list, item 1 (Treatment of Cataract)"),
    "universal-sompo-complete-healthcare.robotic_surgery": dict(
        section="Modern treatment sub-limit table, item 7 (Robotic Surgeries)",
        quote="7 Robotic Surgeries 50% of SI and maximum upto Rs 500,000",
        value="Robotic surgery: up to 50% of Sum Insured, maximum Rs 5,00,000."),
    "zuno-health-insurance.ayush": dict(section="Benefit 7: AYUSH"),
    "zuno-health-insurance.cataract": dict(section="Specified disease list, item iv (Cataract)"),
    "care-health-ultimate-care.room_rent": dict(section="Room Category, i) Single Private AC Room"),
    "hdfc-ergo-energy-health.ped_wait_months": dict(section="Pre-existing Diseases (Code-Excl01), a)"),
    "hdfc-ergo-optima-senior.ayush": dict(section="In-Patient Treatment, Note pertaining specifically to AYUSH Treatments"),
    "royal-sundaram-next-gen-health.ayush": dict(section="Benefit table, item 11 AYUSH Treatment"),
    "care-health-care-plus-plan-care-health-plus-care-plus.room_rent": dict(section="Room Category, ii) Single Private AC Room"),
    "care-health-care-plus-plan-care-health-plus-care-plus.ayush": dict(section="Section 3.1.9 Benefit: AYUSH Treatments"),
    "care-health-care-freedom.ayush": dict(section="Section 3.1.10 Benefit 10: AYUSH Treatments"),
    "care-health-care-freedom.cataract": dict(section="Sub-limit list, item i (Treatment of Cataract)"),
    "care-health-care-joy-plan-joy-today-joy-tomorrow-maternity-care-joy.room_rent": dict(section="(i) Room Category"),
    "care-health-care-joy-plan-joy-today-joy-tomorrow-maternity-care-joy.ayush": dict(section="Section 3.7 Benefit 7: AYUSH Treatments"),
    "care-health-care-joy-plan-joy-today-joy-tomorrow-maternity-care-joy.robotic_surgery": dict(
        section="Advance Technology Methods, item g (Robotic surgeries)"),
    "care-health-care-heart.ayush": dict(section="Section 3.1.3 Benefit 3: AYUSH Treatments"),
    "care-health-care-heart.robotic_surgery": dict(section="Advance Technology Methods, item g (Robotic surgeries)"),
    "niva-bupa-health-companion-family-floater.robotic_surgery": dict(section="Modern treatments, item vii (Robotic surgeries)"),
}

if __name__ == "__main__":
    apply(S, "--write" in sys.argv)

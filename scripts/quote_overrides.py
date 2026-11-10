"""Hand-picked quote fixes, each verified against data/pages before writing.

    .venv/Scripts/python scripts/quote_overrides.py [--write]

Every quote below is copied from the pdftotext page text of the cited page.
The script refuses to write if any quote is not on its page, or if a numeric
value is missing from its own quote.
"""
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from diag_quotes import CAT, PAGES, norm  # noqa: E402
from fix_quotes import has_value  # noqa: E402

OVERRIDES = {
    "star-family-health-optima.ayush": dict(
        quote="Ayurveda, Unani, Siddha and Homeopathy is payable up to the Sum Insured."),
    "star-family-health-optima.cataract": dict(
        quote="Cataract is subject to the limit as per the following table Limit per Policy Period (in Rs.) Sum Insured (Rs.) Limit per eye (in Rs.) 1,00,000/- Up to 12,000/- per eye, per Policy Period"),
    "tata-medicare-premier.cataract": dict(
        quote="Cataract (avrana Shukla), Retinal detachment, Glaucoma (abhishyandha)"),
    "bajaj-allianz-health-guard.robotic_surgery": dict(
        quote="Oral chemotherapy Immunotherapy- Monoclonal Antibody to be given as injection Intra vitreal injections Robotic surgeries Stereotactic radio surgeries Bronchical Thermoplasty"),
    "generali-central-health-absolute.cataract": dict(
        quote="Sub Limits Cataract 10% Of SI, 10% Of SI, Maximum Of ₹ Maximum Of ₹ 1, 75,000/- Per Eye. 50,000/- Per Eye.",
        value="Cataract has its own limit: 10% of SI, up to ₹75,000 per eye on the first plan column (₹1,50,000 and ₹2,00,000 per eye on the higher plan columns), as written in this table."),
    "iffco-tokio-individual-health-protector.robotic_surgery": dict(
        quote="Intra vitreal injections Robotic surgeries Stereotactic radio surgeries Bronchial Thermoplasty"),
    "liberty-general-healthprime-connect.ped_wait_months": dict(
        quote="Expenses related to the treatment of a Pre-Existing Disease LED) and its direct complications shall be excluded as pet the Plan mentioned in the Policy schedule i.e.unti1 the expiry of 36 months of 24 months of continuous coverage after the date of inception of the first policy with Us.",
        section="Standard Exclusion 1 (Pre-Existing Diseases, Code-Excl01)",
        note="36 or 24 months, as per the plan in the Policy Schedule; 36 is used here as the longer case."),
    "liberty-general-healthprime-connect.cataract": dict(
        quote="Sr. First Year (12 months) Two Year (24 months) Three Year (36 months) No Waiting Period Waiting Period Waiting Period 1. Cataract",
        section="List of specific diseases/procedures, Sr. 1 (First Year column)"),
    "manipalcigna-prohealth-prime.room_rent": dict(
        quote="Room Rent: Covered up to Single Private AC Room For ICU - Covered up to Sum Insured",
        value="Covered up to a Single Private AC Room; ICU covered up to Sum Insured."),
    "oriental-insurance-happy-family-floater.entry_age_max": dict(
        quote="5.28 ENTRY AGE: Maximum Entry Age under the Policy is 65years for all members.",
        pdf_page=37, section="Clause 5.28 (Entry Age)"),
    "oriental-insurance-happy-family-floater.robotic_surgery": dict(
        quote="Per policy period 10% of SI, subject to maximum INR 1,00,000.* maximum INR 2,00,000.* G. Robotic surgeries"),
    "sbi-general-arogya-supreme.room_rent": dict(
        quote="a) Room rent and boarding expenses as provided by the Hospital/Nursing home subject to below limits • 1% of base Sum Insured (excluding cumulative / enhanced cumulative bonus) OR • Single private Air-Conditioned room OR • At actuals up to Sum Insured",
        value="Depends on the option chosen: 1% of base Sum Insured, or a Single private AC room, or at actuals up to Sum Insured."),
    "sbi-general-arogya-supreme.cataract": dict(
        quote="We will pay Medical Expenses of Rs 50,000/- or Rs 1,00,000/incurred for treatment of Cataract as specified in the Policy Schedule, per eye including cost of lens during Policy Year, subject to claim admissible under the Policy.",
        section="Cataract Treatment"),
    "sbi-general-arogya-supreme.robotic_surgery": dict(
        quote="vii. Robotic Surgeries viii. Stereotactic Radio Surgeries ix. Bronchical Thermoplasty",
        section="Modern treatments, item vii (Robotic Surgeries)"),
    "care-health-ultimate-care.ayush": dict(
        quote="AYUSH Treatment The Company will indemnify the Insured Person, through Cashless or Reimbursement Facility, up to the Sum Insured, as specified in the Policy Schedule, towards Medical Expenses incurred with respect to the Insured Person’s medical treatment undergone at any AYUSH Hospitals or"),
    "niva-bupa-aspire.robotic_surgery": dict(
        quote="7. Robotic surgeries 8. Stereotactic radio Surgeries",
        section="Modern treatments, item 7 (Robotic surgeries)"),
    "tata-aig-health-supercharge.cataract": dict(
        quote="Cataract, Retinal detachment, Glaucoma Congenital Internal Diseases"),
    "tata-aig-health-supercharge.robotic_surgery": dict(
        quote="Robotic surgeries 125,000 500,000 0 0 0 Stem cell therapy",
        section=None),
    "hdfc-ergo-energy-health.ayush": dict(
        quote="Treatments only: Medical expenses pertaining only to In-patient care AYUSH treatment are also covered under"),
    "hdfc-ergo-energy-health.diabetes_wait": dict(
        quote="Any condition or illness, complication or ailment arising out of or connected to the below mentioned conditions shall not be considered as part of this waiting period. 2. a. Type 2 Diabetes Mellitus b. Impaired Fasting Glucose (IFG) c. Impaired Glucose Tolerance (IGT) d. Type 1 Diabetes e. Hypertension"),
    "star-health-comprehensive.robotic_surgery": dict(
        quote="Sum Insured on Individual Basis: Limit per person, per Policy Period for each treatment / procedure Sum Insured on Floater Basis: Limit per Policy Period for each treatment / procedure Rs. 5,00,000/- 2,50,000/-",
        value="Robotic surgery has its own limit that rises with the sum insured (₹2,50,000 at ₹5 lakh sum insured), per the modern-treatment sub-limit table on this page."),
    "aditya-birla-health-activ-one.room_rent": dict(
        quote="Room Rent Actuals up to Sum Insured ICU Charges Actuals up to Sum Insured",
        value="Actuals up to Sum Insured (no room-rent cap)."),
    "aditya-birla-health-activ-one.ayush": dict(
        quote="AYUSH Treatment Actuals up to Sum Insured"),
    "aditya-birla-health-activ-one.cataract": dict(
        quote="Body System Illness Treatment / Surgery Eye Cataract Cataract Surgery Glaucoma Glaucoma Surgery"),
    "aditya-birla-health-activ-one.robotic_surgery": dict(
        quote="Balloon Sinuplasty Oral Chemotherapy Robotic Surgeries Stereotactic Radio Surgeries"),
    "royal-sundaram-next-gen-health.ayush": dict(
        quote="11 AYUSH Treatment Covered up to Sum Insured"),
    "royal-sundaram-next-gen-health.robotic_surgery": dict(
        quote="Intra vitreal injection Robotic surgeries Stereotactic radio surgeries Bronchical Thermoplastic"),
    "care-health-care-plus-plan-care-health-plus-care-plus.ayush": dict(
        quote="Benefit : AYUSH Treatments The Company will indemnify the Insured Person, through Cashless or Reimbursement Facility, up to sum insured as specified in the Policy Schedule, towards Medical Expenses incurred with respect to the Insured Person’s medical treatment undergone at any AYUSH"),
    "care-health-care-plus-plan-care-health-plus-care-plus.cataract": dict(
        quote="3. Benign Prostatic Hypertrophy 4. Cataract 5. Dilatation and Curettage",
        section="Specified illness waiting list, item 4 (Cataract)"),
    "care-health-care-plus-plan-care-health-plus-care-plus.robotic_surgery": dict(
        quote="F. Intra vitreal injections G. Robotic surgeries H. Stereotactic radio surgeries",
        section="Modern treatments, item G (Robotic surgeries)"),
    "care-health-care-freedom.ped_wait_months": dict(
        quote="Pre-existing Disease – code – Excl01: i. Expenses related to the treatment of a pre-existing Disease (PED) and its direct complications shall be excluded until the expiry of 24 months of continuous coverage after the date of inception of the first policy with insurer.",
        pdf_page=12, section="Pre-existing Disease, Code-Excl01"),
    "care-health-care-freedom.ayush": dict(
        quote="Benefit 10: AYUSH Treatments The Company will indemnify the Insured Person, through Cashless or Reimbursement Facility, up to the Sum Insured, as specified in the Policy Schedule, towards Medical Expenses incurred with respect to the Insured Person's medical treatment undergone at any AYUSH"),
    "care-health-care-joy-plan-joy-today-joy-tomorrow-maternity-care-joy.cataract": dict(
        quote="III. Benign Prostatic Hypertrophy; IV. Cataract;",
        section="Specified illness waiting list, item IV (Cataract)"),
    "care-health-care-heart.ayush": dict(
        quote="Benefit 3: AYUSH Treatments: The Company will indemnify the Insured Person, through Cashless or Reimbursement Facility, up to theSum Insured specified in the Policy Schedule, towards in-patient Medical Expenses incurred with respect to the Insured Person's Medical treatment undergone at any"),
    "star-health-cancer-care-platinum.cataract": dict(
        quote="Cataract treatment: The company will pay the expenses incurred for treatment of cataract up to the limits mentioned below; Basic Sum Insured (Rs.) 5,00,000/7,50,000/- and 10,00,000/- i) Limit of Cataract Surgery (Rs.) 30,000/- per eye per person and not exceeding 40,000/- per person per policy period",
        section="Clause h) Cataract treatment"),
    "star-health-cancer-care-platinum.robotic_surgery": dict(
        quote="Robotic surgeries 2,50,000 2,75,000 3,00,000 Stereotactic radio surgeries",
        value="Robotic surgery has its own limit by sum insured: ₹2,50,000 / ₹2,75,000 / ₹3,00,000, as written in this table."),
    "star-health-medi-classic.robotic_surgery": dict(
        quote="Basic Sum Insured (Rs.) Robotic surgeries Stereotactic radio surgeries",
        value="Robotic surgery has its own limit that rises with the sum insured, per the modern-treatment sub-limit table on this page (not the full sum insured)."),
}


def main():
    apply(OVERRIDES, "--write" in sys.argv)


def apply(overrides, write):
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    byid = {p["id"]: p for p in cat["products"]}
    bad = 0
    for name, o in overrides.items():
        pid, key = name.split(".")
        p = byid[pid]
        f = p["facts"][key]
        doc = cat["documents"][pid]
        pages = {x["page"]: x["text"] for x in json.loads((PAGES / (doc["source"][:-4] + ".json")).read_text(encoding="utf-8"))["pages"]}
        f.update(o)
        if "pdf_page" in o:
            off = doc.get("page_offset")
            f["printed_page"] = None if off is None else f["pdf_page"] + off
        ok = norm(f["quote"]) in norm(pages.get(f["pdf_page"], ""))
        okv = has_value(f, norm(f["quote"]))
        if not (ok and okv):
            bad += 1
            print(f"FAIL {name}: on page={ok} value={okv}")
    print(f"{len(overrides)} overrides, {bad} failing")
    if write and not bad:
        CAT.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("written")


if __name__ == "__main__":
    main()

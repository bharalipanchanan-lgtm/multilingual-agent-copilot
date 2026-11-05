# Policy intake QA report (5 Nov 2026, revision 4)

## Correction: Royal Sundaram Surrosafe is removed

The Royal Sundaram file is not a general health policy. "Surrosafe" is a surrogacy product. Its only benefits are Surrogate Cover and Oocyte Donor Cover (section D, pages 7 and 8), and the words cataract and dialysis never appear. Maternity is excluded (page 10). It would give wrong answers next to mediclaim policies, so it is out of the demo set and out of the manifest rows. My first QA pass called it usable because I checked layout and key terms but did not read what the product covers. The fix going forward is that every policy is checked for what it covers before layout.

The set was three policies after that removal. The Royal Sundaram Multiplier Health brochure is now the fourth, which is a general health product.

## Demo set

| | Oriental Sampoorna | United India Individual | SBI General Retail | Royal Sundaram Multiplier |
|---|---|---|---|---|
| Document type | Full policy wording, 75 pages | Prospectus, 19 pages | Prospectus, 36 pages | Brochure, 13 pages (not the wording) |
| UIN | OICHLIP27035V022627 | UIIHLIP24089V052324 | SBIHLIP22138V042122 | RSAHLIP23030V012223 |
| Plans | PREMIUM, ELITE, ROYAL (benefits differ) | Platinum, Gold, Senior Citizen by entry age | A, B, C by city (benefits same) | One plan, sum insured 5 to 25 lakh |
| Pre-existing disease wait | 36, 24, 12 or 24 months by plan and age | 48 months | 48 months | 36 months (50% co-pay cover in years 2 and 3) |
| 30 day initial wait | Yes (clause 4.3, page 40) | Yes (page 5) | Yes (page 6) | Yes (page 11) |
| Moratorium | 60 months | Not stated | Not stated | Not stated |
| Co-pay | 10%, 5%, none for non-network treatment | Not applicable | 10% after deductible, non-network | None mandatory, optional 5 to 20% |
| Maternity | Elite and Royal only | Excluded | Excluded | Excluded |
| Mental illness | Covered, 20%, 50%, 100% of sum insured cap | Unclear (inpatient not addressed) | Covered, Rs 50,000 sub-limit | Not stated |
| Premium rate table | No (refers to a PED buyback chart not in the file) | Yes, pages 15 to 19 | Yes, pages 11 to 30 | No (zones and discounts only) |

My earlier version of this report said no 30 day wait was found for Oriental. That was wrong: my search missed "30days" without a space. It is clause 4.3 on page 40.

## Fact table

fact_table_review.csv has 86 rows (Oriental 34, United India 20, SBI 16, Royal Multiplier 16) across 16 attributes, one row per plan where values differ. Each row has the value, status (stated, not_stated or unclear), page, verbatim quotes and a blank verified column. All 135 quotes were checked by script against the text of the stated page, so quotes and page numbers are mechanically correct. The values are my reading and still need a person. 26 rows are marked needs_extra_care, mostly values I read from table images (Oriental pages 11, 13, 17, 18) or where the document is silent or ambiguous. fact_table_prefill.json holds the same rows for loading into your facts folder; map the fields to your schema.

## Per policy findings

### Oriental Sampoorna Swasthya Suraksha

Page 14 carries an older header block (UIN OICHLIP26035V012526, every other page shows OICHLIP27035V022627). Confirm that page against the insurer's current wording before verifying facts from it. The pre-existing disease clause on page 38 prints "24 (<45age)" for Royal above 45, a typo; the benefit table on page 18 says 2 years above 45. The specific coverage limit table (page 22 onward, Premium plan only) is long and only its first rows are in the fact table. Maternity, cumulative bonus and cataract values come from table images and need a visual check.

### United India Individual Health Insurance Policy

A prospectus. It says nothing about AYUSH as a benefit, a moratorium, a no claim bonus or inpatient mental illness, so those rows are not_stated or unclear. Do not let the system say these are not covered. Obtain the full wording if possible. Its premium tables on pages 15 to 19 are annual, per person, excluding GST, for Zones A, B and C.

### SBI General Health Insurance Policy Retail (prospectus)

SBI's own purchase page for this UIN does not say the product is discontinued, while a third party site labels the retail policy "Discontinued" without a date. Confirm with SBI before the demo. Premium tables on pages 11 to 30 have numbers that wrap inside narrow cells (1,471 printed as "1,4" over "71"), which will corrupt a naive table extraction. Each premium row needs a visual check.

### Royal Sundaram Multiplier Health Insurance Plan

A marketing brochure that states it is not a contract, so every row from it needs the full wording before it is trusted. The benefit table sits on a two-page spread (brochure pages 4 and 5) and was read from the image. Distinct features are the 4X Multiplier, Flexi Reload and 20% yearly no claim bonus up to 100%. The brochure is inconsistent on the bonus after a claim: page 4 says no reduction, page 10 says the bonus needs no paid or outstanding claims in the expiring year. Moratorium, mental illness and cashless procedure wording is absent, so those rows are not_stated or unclear and must never be answered as "not covered". Rupee amounts print as backticks and ligatures such as "benefit" print as one glyph, so the parser needs normalisation. There is no premium rate table, only zones and discounts, so premium comparison for this policy needs another source.

## Parser findings for the team

Section labels are unreliable across insurers: the Oriental moratorium clause was labelled "5.11 Withdrawal of policy", the United India pre-existing disease clause "1.2 Sub-limit", and the SBI mental health clause sat under "K. IONM". Oversized table rows can exceed the chunk limit. Numbers wrapped inside narrow cells need joining with no separator. Plan specific values need plan aware chunks or the model will blend plans.

## Manifest rows

manifest_additions.csv now has oriental_sampoorna.pdf, united_india.pdf, sbi_retail_health.pdf and royal_multiplier.pdf (strip_regex removes the repeated UIN line, tested on all 13 pages). No pages need skipping and page_offset is 0 for all. Each strip_regex was tested on the extracted text. These tests used pdftotext; run inspect_chunks.py on your Mac.

## Open decisions

Whether to obtain full wordings for United India, SBI and Royal Multiplier. A fifth policy with a published premium table is optional. Royal Multiplier has no premium table, so the premium comparison covers two or three policies unless more data is found. Confirmation of SBI product status.

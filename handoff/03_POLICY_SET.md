# Policy set

## The five policies

| policy_id | Insurer and product | Document | Pages | UIN | Plans | Status |
|---|---|---|---|---|---|---|
| oriental_sampoorna | Oriental Insurance, Sampoorna Swasthya Suraksha | Full policy wording | 75 | OICHLIP27035V022627 | PREMIUM, ELITE, ROYAL (benefits differ) | 34 fact rows |
| united_india | United India, Individual Health | Prospectus | 19 | UIIHLIP24089V052324 | Platinum, Gold, Senior Citizen by entry age | 20 fact rows, premium tables pp 15 to 19 |
| sbi_retail_health | SBI General, Health Insurance Policy Retail | Prospectus | 36 | SBIHLIP22138V042122 | A, B, C by city (benefits same) | 16 fact rows, premium tables pp 11 to 30 |
| royal_multiplier | Royal Sundaram, Multiplier Health Insurance Plan | Brochure, not the wording | 13 | RSAHLIP23030V012223 | One plan, sum insured 5 to 25 lakh | 16 fact rows, no premium table |
| national_mediclaim | National Insurance, Mediclaim | Policy wording (Phase 0) | see repo | see repo | see repo | Gold CSV pre-filled and unverified, no fact rows yet |

## Removed from the set

Royal Sundaram Surrosafe is a surrogacy product, not general health. SBI General 2010 wording was replaced by the SBI Retail prospectus. Do not add either back.

## Manifest rows

Copy these into data/policies/manifest.csv. strip_regex removes repeated headers and footers. They were tested with pdftotext; run inspect_chunks.py on the Mac to confirm with PyMuPDF.

```csv
file,policy_id,insurer,product,skip_pages,page_offset,strip_regex
oriental_sampoorna.pdf,oriental_sampoorna,The Oriental Insurance Company,"Oriental Sampoorna Swasthya Suraksha (Premium, Elite, Royal plans)",,0,The Oriental Insurance Co\. Ltd Oriental Sampoorna Swasthya Suraksha 2026- Policy Wordings|Page \d+ of 75 UIN: OICHLIP\w+|The Oriental Insurance Co\. Ltd\s*CIN No\.\S+\s*Oriental Sampoorna Swasthya Suraksha\s*UIN: OICHLIP\w+\s*Policy Wordings|(?m:^Page \d+ of 75\s*$)
united_india.pdf,united_india,United India Insurance,Individual Health Insurance Policy (prospectus),,0,United India Insurance Company Limited\s*Corporate Identity Number: \S+\s*Registered Office: [^\n]*\s*IRDAI REG NO\.545\s*\d+ \| P a g e\s*Individual Health Insurance Policy . Prospectus\s*UIN: UIIHLIP\w+
sbi_retail_health.pdf,sbi_retail_health,SBI General Insurance,"Health Insurance Policy Retail (prospectus, UIN SBIHLIP22138V042122)",,0,(?s)SBI General Insurance Company Limited\s*SBI General Insurance Company Limited - Prospectus \d+\s*Corporate & Registered Office:.*?SBIHLIP\w+ I IRDAI Reg No 144
royal_multiplier.pdf,royal_multiplier,Royal Sundaram General Insurance,"Multiplier Health Insurance Plan (brochure, UIN RSAHLIP23030V012223)",,0,UIN: RSAHLIP\w+
```

## Per policy findings

Oriental: page 14 carries an older header (OICHLIP26035V012526); confirm that page against the insurer's current wording before verifying facts from it. The PED clause on page 38 prints "24 (<45age)" for Royal above 45, a typo; the benefit table on page 18 says 2 years above 45. Maternity, cumulative bonus and cataract values come from table images on pages 11, 13, 17, 18 and need a visual check. The specific coverage limit table (page 22 onward, Premium plan only) is long and only its first rows are in the fact table. 30 day wait is clause 4.3 on page 40 (text reads "30days" without a space).

United India: prospectus says nothing on AYUSH as a benefit, moratorium, no claim bonus or inpatient mental illness. Those rows are not_stated or unclear. Obtain the full wording if possible.

SBI Retail: one third party site labels the retail policy "Discontinued" without a date, SBI's own page does not. Confirm product status with SBI before the demo.

Royal Multiplier: brochure inconsistent on no claim bonus after a claim (page 4 no reduction, page 10 needs no paid or outstanding claims). Moratorium, mental illness and cashless wording absent. Benefit table is a two-page spread read from an image. Joint replacement waits 24 months here.

## Parser findings (apply in the repo)

1. Section labels are unreliable across insurers. Oriental moratorium was labelled "5.11 Withdrawal of policy", United India PED "1.2 Sub-limit", SBI mental health under "K. IONM". Do not use the label for routing or citation text. Use page and clause number.
2. Oversized table rows can exceed the chunk max. Split by cell group but keep the row header with each piece.
3. Digits wrap inside narrow table cells. Join numeric fragments in a cell with no separator, then verify visually.
4. Plan specific values need plan aware chunks, otherwise the model blends plans.
5. Normalise ligatures (NFKC) and map the backtick rupee mark to the rupee sign.
6. Brochure PDFs can be two-page spreads. Page numbering and bounding boxes must follow physical pages.
7. National Mediclaim and SBI use garbled repeated headers; strip_regex values must be built from the exact raw lines.

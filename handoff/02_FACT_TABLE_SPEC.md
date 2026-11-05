# Fact table specification

## Record

One record per policy, plan and attribute. Where plans differ in value (Oriental PREMIUM, ELITE, ROYAL; United India PLATINUM, GOLD, SENIOR) there is one row per plan. Where all plans share a value the plan is ALL.

| Field | Meaning |
|---|---|
| policy_id | Matches manifest policy_id |
| plan | ALL or the plan name |
| attribute | One of the 19 attributes below |
| value | Plain language value a person can check at a glance |
| status | stated, not_stated or unclear |
| needs_extra_care | yes when read from a table image, ambiguous, or silent |
| pages | Physical PDF pages of the evidence |
| evidence_quotes | Verbatim fragments, each with its page. Every quote must exist on its page |
| note | Caveats, conflicts, what to check in the full wording |
| verified, verified_by, verified_on | Filled by a human. Blank means unverified |

## Status rules

stated: the document gives the value. not_stated: searched and nothing found; the full wording may say. unclear: partial or implied wording. Never convert not_stated or unclear into "not covered" or "no".

## Existing 16 attributes (86 rows done for four policies)

ped_waiting, specific_disease_waiting, initial_waiting, moratorium, room_rent, icu_limit, copay, maternity, ayush, daycare, pre_post_hospitalisation, no_claim_bonus, renewal, sublimits, cashless, mental_illness.

## Three new attributes (to add)

The recommendation needs prospect inputs such as age, family, sum insured and budget. These three attributes let the fit table test them.

| Attribute | What to record | Why the fit table needs it |
|---|---|---|
| entry_age | Minimum and maximum entry age for adults, minimum age for children, dependent child upper age, family members allowed (self, spouse, children, parents), floater or individual | Rules a policy out when the prospect or a family member is outside the range. United India plans are defined by entry age, so this also selects the plan |
| sum_insured_options | Available sum insured values or range, floater or individual, any plan-specific limits | Tests the prospect's cover target |
| restoration_reload | Restore, recharge, reload or multiplier benefits: trigger, amount, whether it applies to the same illness, whether it applies on first claim | Often the deciding feature at the same premium. Royal has Flexi Reload and 4X Multiplier, Oriental and others may have restore benefits |

Known hints, all unverified, to be checked against the PDFs: Royal Multiplier adults 18 to 65 with lifetime renewability, children 91 days to 25 years, sum insured 5, 7.5, 10, 15, 20, 25 lakh, Flexi Reload up to 100 percent of base sum insured not available on first claim in the policy year, 4X Multiplier four times in policy lifetime. United India plans Platinum 18 to 35, Gold 36 to 60, Senior Citizen 61 to 65. Others not yet read for these attributes.

## Premium (separate table, not an attribute)

Premium needs its own table: policy_id, plan, zone or city group, age band, sum insured, term, annual premium, tax included flag, page, effective date. Available for United India (pages 15 to 19, Zones A, B, C, annual, per person, excluding GST) and SBI Retail (pages 11 to 30, plans A, B, C by city). Not available in Oriental, Royal Multiplier and, as far as checked, National. SBI numbers wrap inside narrow cells (1,471 prints as "1,4" over "71"), so every parsed value needs a visual check against the page image.

## Verification flow

A person opens fact_table_review.csv, starts with needs_extra_care rows, compares value and quote with the page image, fixes the value if wrong, and fills verified, verified_by, verified_on. The comparison view should show an unverified badge for any row with verified blank. Run the quote validator again after any edit: every quote must be found on its page after whitespace, case, quote mark and ligature normalisation (NFKC).

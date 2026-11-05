# Handoff for Claude Code: policy set and fact table

Project: Multilingual Agent Copilot demo for Claviq, first meeting with Quickinsure. Audience is the founder and CEO.

This folder tells Claude Code what was prepared outside the repo and what to build next. Read the files in order.

| File | Purpose |
|---|---|
| 01_README.md | This file. Context, rules, order of work |
| 02_FACT_TABLE_SPEC.md | Schema, the 19 attributes, status rules, verification flow |
| 03_POLICY_SET.md | The five policies, manifest rows, per-policy findings, parser findings |
| 04_TASKS.md | Ordered tasks with acceptance checks |

Files to copy into the repo alongside these: fact_table_review.csv, fact_table_prefill.json, manifest_additions.csv, POLICY_QA_REPORT.md (from policy_intake). The PDFs are the ones the user attached: ORIENTAL_SAMPOORNA.pdf, United_India_Insurance.pdf, SBI_Retail_Health_Brochure, Royal_Sundaram_Multiplier_Health_Brochure, and National Mediclaim from Phase 0. Rename them to the file names in the manifest.

## Rules that must not be broken

Answers come only from the policy text. If the text is silent the system says "not stated in the document". It never says "not covered" for a silent policy.

Comparison and recommendation use the human verified fact table, not free text retrieval. A row with verified false may be shown only with an "unverified" marker.

The recommendation is a fit table (met, partly, not, unknown) per prospect input. It is never a single "best policy" verdict. Unknown is never counted as met. The agent decides.

Demo data is synthetic. No real customer data. The Sarvam API key lives in an environment variable and is never committed. Cloud voice is allowed in the demo only, with a typed fallback.

## Style for anything written for the user

Direct answer first. Short paragraphs. No bullet points in chat replies. No em dashes. No emojis. Challenge weak logic rather than agreeing.

## Page numbers

Fact files cite physical PDF pages. Printed page = physical page minus page_offset. All five policies currently use page_offset 0.

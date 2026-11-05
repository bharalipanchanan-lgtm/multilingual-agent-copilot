# Tasks for Claude Code

Do them in order. Each has an acceptance check. Ask before changing the architecture.

| # | Task | Acceptance check |
|---|---|---|
| 1 | Copy the four PDFs into data/policies with manifest names, merge manifest_additions.csv, run ingest and inspect_chunks.py | No chunk over the max size; no header or footer text inside chunks; page and printed_page present on every chunk |
| 2 | Apply the parser fixes from 03_POLICY_SET.md (NFKC, rupee mark, cell digit joins, plan aware chunks) | Spot check 10 chunks per policy by eye; SBI premium cells such as 1,471 parse whole |
| 3 | Load fact_table_prefill.json into facts/ and write the quote validator as a test | Every quote found on its page; test fails on any miss |
| 4 | Add the three new attributes (entry_age, sum_insured_options, restoration_reload) to the schema, then extract them for all five policies with page and quote | Same validator passes; not_stated used when absent |
| 5 | Build fact rows for national_mediclaim for all 19 attributes from the existing gold CSV | Same validator passes; rows start unverified |
| 6 | Premium table loader for United India and SBI Retail with visual check list | Each row has page and tax flag; a sample of 20 rows matches the page images |
| 7 | Comparison view reads only facts, shows plan rows, an unverified badge, and click through to the cited clause | An attribute across five policies renders in one table; not_stated rows are labelled "not stated in the document" |
| 8 | Visual citation: store word bounding boxes at ingest, render the page with the cited sentence highlighted | Highlight sits on the right sentence for 20 sample answers |
| 9 | Fit table: prospect inputs (age, family, sum insured, known conditions, wants maternity, budget) mapped to rules per policy | Output per policy per input is met, partly, not or unknown; unknown never counts as met; no single winner is printed |
| 10 | Synthetic lead list: 50 customers, fixed seed, fields customer id, fake name, age, city, masked phone, vehicle, motor insurer, motor renewal date, has health, has term, family size, last contact | Filter "no health or term cover" works; prospect inputs prefill the fit table |
| 11 | Voice input with Sarvam Saaras, typed fallback, key from environment variable | Hindi, English and Hinglish test clips transcribe; app works with no key |
| 12 | Hardening: number check must verify the number belongs to the asked attribute, add a covered versus excluded polarity check, and test that the refusal and not_stated controls actually fire | Adversarial question set where each control fires at least once |

## Eval targets

Retrieval hit at k=5 above 90 percent on the 20 question set across five policies. Zero answers that state a value absent from the cited clause. Every not_stated attribute answered as "not stated in the document".

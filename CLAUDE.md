# CLAUDE.md: Claviq Agent Copilot prototype

Read this first. It carries the context from the earlier chat so work can continue here without re-explaining.

## What this project is

A local, zero-cost prototype of Claviq's Multilingual Agent Copilot, built for a demo to the founder/CEO of Claviq to support a pitch to Quickinsure. An insurance agent types a question about a health policy in English, Hindi or Hinglish. The system answers in plain language, quotes the exact clause, shows the page number, and says "not stated in the document" when the policy does not answer. See PLAN.md for phases, architecture, risks and the demo script, and PITCH.md for the pitch storyline.

## Working style (the user's standing preferences)

Act as a senior software engineer. Lead with the direct answer. Use short paragraphs. Do not use bullet points in replies. No em dashes and no emojis. Ask clarifying questions before starting major tasks. Challenge weak logic instead of agreeing.

## Hard constraints

Everything runs locally on a MacBook Pro 16 inch 2021 (M1 Pro, 16 GB, macOS Sequoia). Nothing paid at this stage. No WhatsApp Business API: the front end will be a WhatsApp style web chat. Scope is health insurance only, typed English, Hindi and Hinglish, no voice. Stack: Python, FastAPI, Chroma, bge-m3 embeddings, a plain HTML front end. Generation sits behind one interface so a local Ollama model (Qwen2.5 7B or Llama 3.1 8B, 4 bit) and Claude can be compared and swapped. Claude API is paid per token and is not covered by a claude.ai subscription, so it stays optional.

## Current status

As of 2026-11-05 the prototype runs end to end on the laptop: parse, ingest, retrieval, grounded generation with Qwen2.5 7B on MLX, number check, polarity check, refusals, fact table comparison, FastAPI with streaming, WhatsApp style web chat. Five policies are loaded (handoff/ tasks 1 to 3 done). The policy is chosen in conversation, not from a dropdown (chat.py, policy_select.py). Fact table is format 2 in facts/ (fact_table.py), checked by tests/test_fact_quotes.py; values are still unverified by a human. See eval/RESULTS.md for measured results and DEMO.md for the demo script.

Models live in models/ (gitignored), fetched with fetch_models.sh because the Hugging Face Python downloader stalls on this network. HF_HUB_DISABLE_XET is set in config.py.

## Layout

| Path | Purpose |
|---|---|
| config.py | Paths, model names, chunk sizes, generation settings |
| answer.py | Router, retrieval, grounded generation, number check, citations |
| generate.py | Backends: mlx (default), ollama, claude (optional), extractive |
| compare.py, facts/ | Comparison from the fact table |
| server.py, web/index.html | FastAPI service and chat UI |
| eval_answers.py, demo_check.py | End to end answer eval, demo script check against the running server |
| parse.py | PDF to page aware chunks, boilerplate removal, tables |
| ingest.py | Reads manifest, embeds with bge-m3, stores in Chroma |
| retrieve.py | Semantic search with optional policy filter |
| inspect_chunks.py | Dumps extracted chunks to data/dumps for human review |
| eval_retrieval.py | Retrieval recall at 3 and 6 against gold labels, refusal threshold hint |
| eval/questions.yaml | 20 questions: English, Hinglish, Hindi, plus 2 trap questions |
| eval/gold/national_mediclaim.csv | Pre-filled gold labels, need human verification |
| data/policies/manifest.csv | One row per policy, with skip_pages, page_offset, strip_regex |
| eval/reference/national_mediclaim_pdftotext_dump.txt | Chunker output from the earlier sandbox run (pdftotext text), kept to diff against the real PyMuPDF run |

Generated and not committed: data/dumps/, data/chroma/, eval/reports/.

## Commands

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python ingest.py
python inspect_chunks.py national_mediclaim
python retrieve.py "room rent limit" --policy national_mediclaim
python eval_retrieval.py
```

## Decisions and findings worth remembering

Gold files use physical PDF page numbers. Printed page equals physical page minus page_offset (3 for National Mediclaim). Appendices have no printed numbers.

The National Mediclaim PDF draws its footer twice, which yields garbled fragments ("N Na at ti io") one per line. The manifest strip_regex removes them. Check for similar artefacts in every new policy with inspect_chunks.py.

Cover pages and tables of contents must be skipped through skip_pages, otherwise the TOC repeats every clause name and pollutes retrieval.

The National Mediclaim policy is version 07/2014 and is for pipeline testing only. The demo needs current wordings. Its mental illness exclusion is likely outdated against current regulation, which has not been verified.

Clause 4.3 (specific waiting periods) starts at the bottom of one page and its list is on the next. Retrieval should expand to neighbouring chunks.

Questions that need an absence answer (co-pay, premium, network hospital list) must produce "not stated". Never let the system infer "there is no co-pay".

Comparison across policies must come from a human verified fact table with page references, not from free text search.

## Next steps

Run Phase 0 on the real stack and fix bugs. Verify the pre-filled gold labels, especially q02, q08, q10, q12 and q17. Add two more current policies from private insurers with different layouts, build their gold files, and read recall by language. Then Phase 1: grounded generation with citations, a number check against the cited text, and refusal when evidence is weak.

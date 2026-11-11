# CLAUDE.md: Claviq Agent Copilot prototype

Read this first. It carries the context from the earlier chat so work can continue here without re-explaining.

## What this project is

A local, zero-cost prototype of Claviq's Multilingual Agent Copilot, built for a demo to the founder/CEO of Claviq to support a pitch to Quickinsure. An insurance agent types a question about a health policy in English, Hindi or Hinglish. The system answers in plain language, quotes the exact clause, shows the page number, and says "not stated in the document" when the policy does not answer. See PLAN.md for phases, architecture, risks and the demo script, and PITCH.md for the pitch storyline.

## Working style (the user's standing preferences)

Act as a senior software engineer. Lead with the direct answer. Use short paragraphs. Do not use bullet points in replies. No em dashes and no emojis. Ask clarifying questions before starting major tasks. Challenge weak logic instead of agreeing.

## Hard constraints

Everything runs locally on a MacBook Pro 16 inch 2021 (M1 Pro, 16 GB, macOS Sequoia). Nothing paid at this stage. No WhatsApp Business API: the front end will be a WhatsApp style web chat. Scope is health insurance only, typed English, Hindi and Hinglish, no voice. Stack: Python, FastAPI, Chroma, bge-m3 embeddings, a plain HTML front end. Generation sits behind one interface so a local Ollama model (Qwen2.5 7B or Llama 3.1 8B, 4 bit) and Claude can be compared and swapped. Claude API is paid per token and is not covered by a claude.ai subscription, so it stays optional.

## Current status

As of 2026-11-05 the prototype runs end to end on the laptop: parse, ingest, retrieval, grounded generation with Qwen2.5 7B on MLX, number check, polarity check, refusals, fact table comparison, FastAPI with streaming, WhatsApp style web chat. Five policies are loaded (handoff/ tasks 1 to 3 done). The policy is chosen in conversation, not from a dropdown (chat.py, policy_select.py). Fact table is format 2 in facts/ (fact_table.py), checked by tests/test_fact_quotes.py; values are still unverified by a human. Voice input (handoff task 11) uses Sarvam Saaras through stt.py with SARVAM_API_KEY from the environment or a gitignored .env; it is tested with a mock (tests/e2e_voice.py) and needs a real key for voice_check.py. See eval/RESULTS.md for measured results and DEMO.md for the demo script.

As of 2026-11-06 (branch feature/phase2-ranking-cloud; the version before it is tagged v1.0-base): WhatsApp style single conversation (the user rejected a chat list with one chat per policy: it does not scale to 300); other documents are reached through a "Browse all documents" search panel, and a pick is said in the chat. Dark mode. A best policy ranking (rank.py) uses only fact table rows plus the IRDAI health incurred claims ratio in data/insurers.json (Annual Report 2024-25, Statement 10, p142). IRDAI no longer publishes an insurer-wise claim settlement ratio, so never call ICR a settlement ratio. Design for 300 policies is in SCALING.md. Cloud: Dockerfile (bge-m3 on CPU, `api` backend for Sarvam, Groq or Gemini, rate limit, voice off in public) and deploy_hf.py for a Hugging Face Space. Hosted models phrase "not stated" in words, and ABSENCE_RE in answer.py catches that. The copilot is named Bima Saathi (by Claviq), set once as config.AGENT_NAME (COPILOT_NAME overrides it). The page opens on a welcome screen with the name. The copilot speaks only after the agent does: "Hi", "Hello" or "Namaste" get an introduction plus the document choice (policy_select.GREETING_RE, chat.converse). The name appears on the welcome screen and as a label on each reply, not in the top bar. As of 2026-11-08: 17 documents. Twelve policy wordings from 12 more insurers were downloaded via joinditto.in product pages (PDFs on Ditto's S3). ManipalCigna was dropped because its PDF text is garbled by its font encoding. They have no fact rows, so compare and rank add a coverage note. data/policies/leaks_reviewed.csv lists running-line matches that were read in context and found inside real sentences; check_chunks.py reports them as reviewed and still fails every other leak. The manifest has a label column (button text, which must be an alias). Messages list 5 documents and point to the browser for the rest. The UI is now a modern chatbot (Inter font, indigo and teal), still one conversation. share_link.sh gives a public link from the laptop (Cloudflare quick tunnel, Sarvam answers). New free Hugging Face Docker Spaces may need a PRO plan (community reports, mid 2026); this is not yet confirmed on the user's account.

As of 2026-11-10: 29 documents. Twelve more from joinditto.in so look-alike products exist (HDFC Optima Secure, Restore, Senior; Care Supreme, Care, Care Senior; Niva ReAssure 1.0, 2.0, 3.0; Star Super Star, Health Premier, Diabetes Safe, Super Surplus; Activ One Max and VIP; TATA MediCare Premier, MediSenior, Elder Care). Ditto's Optima Lite and Care Supreme VFM/Senior links served duplicate files and were dropped. The manifest has uin, status (active or withdrawn), replaced_by, status_source and differs columns. Withdrawn, per joinditto.in: ReAssure 1.0 (replaced by 2.0), MediSenior (replaced by Elder Care), SBI Retail (no replacement named, not confirmed by SBI). Insurer names are aliases shared by every product of that insurer, so "HDFC" asks which exact product and shows one line on how each differs (policy_select.differences, built from fact numbers). fit.py reads a customer description (age, member, condition, room rent, cover, start date), checks every product on sale, shows the best and second best with reasons, one line per reason the others fail, the date the condition is covered, and a sales kit (what to say, WhatsApp message, waiting end dates, papers, what not to promise). Naming one product with a customer description checks only that product. quick.py answers simple questions (room rent, waiting, age limit, co-pay, sum insured, bonus) from the fact row in milliseconds; anything with more content goes to clause search. Fact rows for all documents were drafted by extract_facts.py (Sarvam 105B over retrieved clauses, every quote checked verbatim against the PDF page, "numbers" for the ranking); they are unverified. Premium questions stay refused. The insurer-only filter for agents was left out at the user's request. IRDAI ICR for all 17 insurers is in data/insurers.json.

As of 2026-11-10 (later): 39 documents, 29 health and 10 term (ICICI Pru iProtect Smart Plus and Super, HDFC Life Click 2 Protect Super (withdrawn, replaced by Supreme Plus) and Supreme Plus, SBI Life eShield Insta, Bajaj Life eTouch II, ABSLI DigiShield, Axis Max Life Smart Term Plan Plus, Acko Flexi Term, LIC Digi Term). Term was added at the user's request; ranking, the customer finder, quick answers and comparison stay health only (fact rows are health facts), term documents are answered by clause search. The manifest has category (health or term) and solo_aliases ("star", "care", "royal", "max": they select only when the message is that word alone). Brand names are shared across a brand's health and term products ("ICICI" lists Lombard health and Prudential term), and the kind of cover narrows the list ("ICICI health policy", "HDFC term", or topic words such as room rent or death benefit). Every insurer's full name is an alias automatically. The page opens with one "Hi" button; the greeting asks which document, with "Browse the policy documents" and "Find a product for a customer" buttons and no document list. tests/e2e_all_docs.py checks every document (PDF, label, brand, a question that cites only that document, browser search and pick).

As of 2026-11-10 (night): extract_facts.py also scans every chunk for room rent, co-pay and entry age (SCAN), and a second hand review fixed the redrafts (facts/review/hand_review_2026_11_10b.py). Where a wording is silent on those three facts, data/web_facts.json (joinditto.in product pages, read 2026-11-10, hand-set numbers) fills them for fit.py and quick.py only; such rows carry web=True, a URL instead of a page, and every line that uses one says "from the product web page, not the wording". A fact the wording states always wins. rank.py and compare.py still use PDF rows only. Ditto uses template sentences, so these values are weaker than the wording and need confirming with the insurer. Voice on the share link needs COPILOT_PUBLIC_VOICE=1 (it spends Sarvam credits per spoken question). Restarting share_link.sh changes the link and breaks pages already open.

As of 2026-11-11: a question asked before any document is chosen (with or without "Hi") is answered from the nearest document (chat.nearest: best clause score across all documents, at least 0.45, products on sale only, health or term by the question's words, one per product family, never national_mediclaim). The answer carries a calm notice that says which document it used and that the customer's policy may differ, plus the next two documents as buttons; tapping one asks the same question there. Text with no real question words ("policy document", "kya hai") still gets the plain "which document?" with Browse and Find. The user chose answering from the nearest over only suggesting.

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

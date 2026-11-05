# Claviq Agent Copilot: local prototype

An insurance agent asks about a health policy in English, Hindi or Hinglish. The copilot answers from the policy wording only, quotes the clause, shows the page, and says "not stated in the document" when the policy does not answer.

Everything runs on the laptop. No paid services, and no network once the models are downloaded.

## Run the demo

    ./run_demo.sh            # then open http://localhost:8000

There is no policy dropdown. The copilot asks which policy document to inspect ("Kaunsa policy
document aapko dekhna hai?") and the agent answers in English, Hindi or Hinglish: "SBI dekhna hai",
"ओरिएंटल", a number from the list, or a question that names the insurer. The choice holds until the
agent names another policy. A comparison question needs no choice; it uses every policy.

The first start takes about 30 to 60 seconds while the embedding model and the local LLM load. The header shows "online" when it is ready.

To run without the LLM (quotes the best matching clauses verbatim, useful as a fallback):

    COPILOT_BACKEND=extractive ./run_demo.sh

## First time setup (macOS, Apple Silicon)

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    # fetch the models first (next block), then:
    python ingest.py

Fetch the models (resumable curl, about 8 GB in total) into models/:

    ./fetch_models.sh BAAI/bge-m3 mlx-community/Qwen2.5-7B-Instruct-4bit mlx-community/Qwen2.5-3B-Instruct-4bit

The 7B is used when present, otherwise the 3B. The 3B made a dangerous error in testing (it said pre-existing diabetes is covered without a waiting period), so do not demo with it.

## How it works

    PDF -> parse.py (page aware chunks, tables by cell, boilerplate removed)
        -> ingest.py (bge-m3 embeddings, Chroma on disk)
    question -> chat.py: choose or keep the policy (policy_select.py, aliases in the manifest)
             -> answer.py
        route: out of scope (premium, hospital list, claim status) -> refuse
               comparison -> compare.py, from the fact table in facts/*.json
               single policy -> retrieve.py (top 5 semantic + keyword matches + rest of each clause, max 6)
        generate.py: mlx (local) | ollama | claude (optional, paid) | extractive
        number check: every figure in the answer must appear in a cited clause, else the draft is blocked
        polarity check: a "covered" answer resting only on exclusion clauses is blocked
    server.py (FastAPI, streaming) -> web/index.html (WhatsApp style chat, clause cards linking to the PDF page)

## Adding a policy

1. Put the PDF in data/policies/ and add a row to data/policies/manifest.csv.
   skip_pages: physical pages to ignore (cover, table of contents), separated by semicolons.
   page_offset: physical page minus printed page number.
   strip_regex: text to remove, such as a repeated footer or masthead.
   plans: plan names whose columns the benefit table uses, separated by semicolons (PREMIUM;ELITE;ROYAL).
   aliases: names an agent may type for the policy, including Hindi, separated by semicolons.
2. `python inspect_chunks.py <policy_id>` and read data/dumps/<policy_id>.txt. Clauses intact, no footer leaks, tables readable. `python check_chunks.py --only <policy_id>` checks chunk size, header and footer leaks and page numbers.
3. `python ingest.py --only <policy_id>`
4. Add rows to facts/<policy_id>.json (format 2, see fact_table.py) with a verbatim quote and page for each value. `pytest tests/test_fact_quotes.py` checks every quote on its page. `python import_facts.py --export` writes facts/review/fact_table_review.csv for a person, and `--apply` writes their verification back.
5. `python eval_retrieval.py --init` creates eval/gold/<policy_id>.csv. Fill it by reading the PDF.

## Evaluation

    python eval_retrieval.py              # retrieval recall at 3 and 6 by language, refusal threshold hint
    python eval_answers.py                # end to end answers, refusals, blocked drafts, latency
    python eval_answers.py --backend extractive
    python demo_check.py 3                # runs the demo conversation 3 times against the running server
    pytest tests/                         # fact quotes, policy choice, polarity check (no model needed)
    python tests/e2e_ui.py                # the chat page in Google Chrome, whole demo flow, screenshots in eval/reports/ui_shots

Gold files use physical PDF page numbers. Reports go to eval/reports/.

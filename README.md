# Claviq Agent Copilot: local prototype

An insurance agent asks about a health policy in English, Hindi or Hinglish. The copilot answers from the policy wording only, quotes the clause, shows the page, and says "not stated in the document" when the policy does not answer.

Everything runs on the laptop. No paid services, and no network once the models are downloaded.

## Run the demo

    ./run_demo.sh            # then open http://localhost:8000

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
    question -> answer.py
        route: out of scope (premium, hospital list, claim status) -> refuse
               comparison -> compare.py, from the fact table in facts/*.json
               single policy -> retrieve.py (top 5 semantic + keyword matches + rest of each clause, max 6)
        generate.py: mlx (local) | ollama | claude (optional, paid) | extractive
        number check: every figure in the answer must appear in a cited clause, else the draft is blocked
    server.py (FastAPI, streaming) -> web/index.html (WhatsApp style chat, clause cards linking to the PDF page)

## Adding a policy

1. Put the PDF in data/policies/ and add a row to data/policies/manifest.csv.
   skip_pages: physical pages to ignore (cover, table of contents), separated by semicolons.
   page_offset: physical page minus printed page number.
   strip_regex: text to remove, such as a repeated footer or masthead.
2. `python inspect_chunks.py <policy_id>` and read data/dumps/<policy_id>.txt. Clauses intact, no footer leaks, tables readable.
3. `python ingest.py --only <policy_id>`
4. Add facts/<policy_id>.json for the comparison path and have a human verify each value against the PDF.
5. `python eval_retrieval.py --init` creates eval/gold/<policy_id>.csv. Fill it by reading the PDF.

## Evaluation

    python eval_retrieval.py              # retrieval recall at 3 and 6 by language, refusal threshold hint
    python eval_answers.py                # end to end answers, refusals, blocked drafts, latency
    python eval_answers.py --backend extractive
    python demo_check.py 3                # runs the demo script 3 times against the running server

Gold files use physical PDF page numbers. Reports go to eval/reports/.

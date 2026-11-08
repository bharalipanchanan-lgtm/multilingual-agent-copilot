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

Voice questions (optional, the one cloud service, demo only): copy .env.example to .env and set
SARVAM_API_KEY (from https://dashboard.sarvam.ai). run_demo.sh loads it. The mic button then records
up to 25 seconds, the server sends the audio to Sarvam Saaras (saaras:v3, mode translit, so Hindi and
Hinglish come back in Roman script), and the transcript lands in the box for the agent to check before
sending. The key stays on the server and out of git. Without a key the mic is off and typing works.
`python voice_check.py` checks the real service with the recorded clips in tests/voice/clips.

To run without the LLM (quotes the best matching clauses verbatim, useful as a fallback):

    COPILOT_BACKEND=extractive ./run_demo.sh

The agent has one conversation with the copilot, never a chat per policy. The greeting lists the first five documents as buttons with a "Browse all documents" button; the browser (also the search icon in the header) searches every loaded document by insurer, product or plan, so it works for 300 as well as 5. Picking a document is said in the chat and the copilot confirms it there. "Best policy finder" asks for a shortlist across all policies, for example "Which policy works best for a customer who wants no waiting period and a good claims record? Premium does not matter." The shortlist comes from rank.py (see SCALING.md).

The base version before the ranking and the new UI is tagged `v1.0-base`: `git checkout v1.0-base`.

## Public demo link from this laptop (free, no account)

    ./share_link.sh          # prints https://<random-words>.trycloudflare.com

It starts the copilot in public mode (Sarvam 105B answers, using the SARVAM_API_KEY in .env; 30 questions per visitor per 10 minutes; voice off for visitors) and opens a Cloudflare quick tunnel to it. tools/cloudflared is the official binary from github.com/cloudflare/cloudflared/releases, gitignored. The link works only while the script runs and the laptop is awake and online, and it changes on every run. Ctrl+C stops both. Visitors' questions and the matching clauses go to Sarvam, so no real customer data.

## Public demo link (cloud)

The Dockerfile builds the same app for a public URL: bge-m3 search on the CPU, answers from a hosted model (`COPILOT_BACKEND=api`, `COPILOT_LLM=sarvam|groq|gemini`, key from the host's secrets), 30 questions per visitor per 10 minutes, voice off unless `COPILOT_PUBLIC_VOICE=1`. It needs about 3 GB of memory. To put it on a Hugging Face Space:

    HF_TOKEN=hf_... python deploy_hf.py your-username/claviq-copilot

Any Docker host with 3 GB or more also works: `docker build -t claviq-copilot . && docker run -p 7860:7860 -e GROQ_API_KEY=... claviq-copilot`. To test the cloud setup on the laptop without Docker: `COPILOT_BACKEND=api COPILOT_LLM=sarvam COPILOT_DEVICE=cpu COPILOT_PUBLIC=1 COPILOT_PORT=8002 python server.py`, then `COPILOT_URL=http://localhost:8002/ python tests/e2e_ui.py`.

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
               best policy -> rank.py, from the fact table and IRDAI insurer figures (data/insurers.json)
               single policy -> retrieve.py (top 5 semantic + keyword matches + rest of each clause, max 6)
        generate.py: mlx (local) | ollama | claude (optional, paid) | api (hosted, cloud) | extractive
        number check: every figure in the answer must appear in a cited clause, else the draft is blocked
        polarity check: a "covered" answer resting only on exclusion clauses is blocked
    server.py (FastAPI, streaming) -> web/index.html (WhatsApp style chat, clause cards linking to the PDF page)

## Loaded documents

There are 17 documents. The first five (National, Oriental, United India, SBI, Royal Sundaram) have fact table rows and gold labels. Twelve full policy wordings, one per insurer, were added on 2026-11-08 from the policy wording links on joinditto.in product pages: HDFC ERGO my: Optima Secure, Aditya Birla Activ One, ICICI Lombard Elevate, Star Super Star, TATA AIG MediCare Premier, Care Supreme, Niva Bupa ReAssure 2.0, Bajaj Health Care Supreme, Acko Personal Health Policy, Digit Health Insurance Policy, New India Premier Mediclaim and IFFCO Tokio Health Protector. They are searchable and answerable, but they have no fact rows yet, so comparison and the best policy finder do not include them and say so. The ManipalCigna wording was dropped because its PDF text extracts as garbled characters.

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
    python tests/e2e_voice.py             # voice in a browser with a recorded clip and a mock Sarvam (no key, no cost)
    python voice_check.py                 # voice against the real Sarvam service (needs SARVAM_API_KEY)
    python tests/e2e_voice_real.py        # spoken clips through the page, real Sarvam and the running copilot

Gold files use physical PDF page numbers. Reports go to eval/reports/.

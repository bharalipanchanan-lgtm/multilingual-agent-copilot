# Quickinsure Copilot: ingestion and retrieval eval

Setup (macOS, Apple Silicon):

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

1. Put each policy PDF in data/policies/ and list it in data/policies/manifest.csv.
   Optional columns: skip_pages (physical pages to ignore, such as cover and table of contents, separated
   by semicolons), page_offset (physical page minus printed page number), strip_regex (text to remove,
   such as a repeated footer). A ready entry for National Mediclaim Policy is already in the manifest.
2. python ingest.py
   First run downloads bge-m3 (about 2.3 GB). Check the summary: pages, chunks, sparse pages.
3. python inspect_chunks.py national_mediclaim
   Read data/dumps/national_mediclaim.txt. Check that clauses are intact, no footer or garbled text leaks in,
   and tables look sensible. Then:
   python retrieve.py "room rent limit" --policy <policy_id>
   Eyeball the results before building the eval.
4. python eval_retrieval.py --init
   (national_mediclaim.csv is already pre-filled in eval/gold/. Verify it against the PDF. Pages in gold files
   are physical PDF pages.) For other policies, open eval/gold/<policy_id>.csv. For each question set answerable to yes or no, put the page number(s)
   in gold_pages (separate with semicolons), and 1 or 2 distinctive phrases from the clause in key_phrases
   (separate with a pipe), plus the correct answer in gold_answer. Leave a row blank to skip it.
5. python eval_retrieval.py

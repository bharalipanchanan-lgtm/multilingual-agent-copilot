# Claviq Agent Copilot: Prototype Build Plan

Status: draft for review. Nothing beyond Phase 0 is built yet.

## 1. Goal

Build a local, zero-cost prototype of the Claviq Multilingual Agent Copilot that a founder can run on a laptop in a CEO demo. An insurance agent types a question in English, Hindi or Hinglish about a health policy. The system replies in plain language, quotes the exact clause, shows the page number, and says "not stated in the document" when the policy does not answer the question.

The demo has to prove one thing: the agent gets a correct, checkable answer faster than reading a 120 page policy. Everything in this plan serves that.

## 2. Scope

| In scope | Out of scope for now |
|---|---|
| Health insurance policy wordings, 15 to 20 real PDFs from different insurers | Term insurance (structure differs, add later) |
| Typed English, Hindi (Devanagari) and Hinglish | Voice input and speech to text |
| Local hosting, local compute, no paid services | WhatsApp Business API |
| Single policy deep answers with clause citation | Premium quotes, network hospital lists, claim status |
| A limited cross policy comparison on a fixed set of attributes | Open ended comparison of any attribute |
| WhatsApp style web chat | Login, multi user, deployment, analytics |

## 3. Guiding principles

**Citation over fluency.** Every answer shows the source clause and page. An answer without a source is a bug.

**Refusal is a feature.** In a regulated market, a confident wrong waiting period is a mis-selling risk. The system must decline when evidence is weak, and the demo should show this on purpose.

**Measure retrieval before generation.** If the right clause is not retrieved, no model can answer correctly. We evaluate retrieval first and use a gold set built from the real PDFs.

**Swappable model.** Generation sits behind one interface so a local model and Claude can be compared on the same questions, and switched with a config change.

## 4. Architecture

```
Policy PDFs (local folder)
        |
        v
[1] Parse: page aware text and table extraction, header/footer removal, clause splitting
        |
        v
[2] Embed: bge-m3 (multilingual) running locally on Apple Silicon
        |
        v
[3] Store: Chroma (local, persistent), metadata = policy, insurer, page, section, type
        |
        +-------------------------------+
        |                               |
        v                               v
[4] Single policy path           [5] Comparison path
    retrieve top k clauses           lookup in a structured fact table
    -> LLM answers only from         (one row per policy, verified by a human,
       the clauses, cites page       each value carries its source page)
    -> refuses if evidence weak
        |                               |
        +---------------+---------------+
                        v
[6] FastAPI service: /ask, /policies, /compare
                        |
                        v
[7] WhatsApp style web chat: typed input, streamed reply, citation card with page number
```

## 5. Components

| Component | Choice | Why |
|---|---|---|
| PDF parsing | PyMuPDF with its table finder | Fast, local, keeps page numbers. Tables matter because room rent caps and sub-limits sit in benefit schedules. |
| Embeddings | BAAI/bge-m3 | Multilingual, so a Hinglish query can match English policy text. About 2.3 GB, runs on the M1 Pro GPU through MPS. |
| Vector store | Chroma, persistent, local | Free, simple, one collection with metadata filter per policy. |
| Generation | Ollama with Qwen2.5 7B or Llama 3.1 8B, 4 bit | Free and local. Fits comfortably in 16 GB. Claude API stays as an optional switch if quality demands it. |
| API | FastAPI | Matches the agreed stack. Supports streaming. |
| Front end | Plain HTML, CSS and JavaScript | No build step, easy to run live. Styled like WhatsApp. |
| Fact table | SQLite or a JSON file | Small and inspectable. Used only for the comparison path. |

## 6. Phases

| Phase | Deliverable | Exit criterion | Status |
|---|---|---|---|
| 0 | Ingestion pipeline, retrieval, 20 question set, retrieval eval harness | Code runs on 3 real PDFs; gold labels filled | Code written, tested only on synthetic text. Not yet run on real PDFs. |
| 1 | Grounded answer generation with citations and refusal | Zero invented numbers across the eval set; all trap questions refused | Not started |
| 2 | Language handling and query routing | Hinglish and Hindi questions match English recall within 10 points; router separates single policy, comparison and out of scope | Not started |
| 3 | FastAPI service | /ask streams an answer with citations; /policies lists loaded policies | Not started |
| 4 | WhatsApp style web chat | Agent picks a policy, asks, sees answer and clause card; works offline | Not started |
| 5 | Comparison across policies | Fixed attribute list answered from the verified fact table for all loaded policies | Not started |
| 6 | Demo hardening | Scripted demo runs 10 times without failure; fallback plan ready | Not started |

## 7. Phase detail

### Phase 0: Ingestion and retrieval evaluation

Load three policy wordings, chunk by clause with page numbers, embed and index them. Label the gold answer for each of the 20 questions per policy by reading the PDF. Run the evaluation and read recall at 3 and 6, split by English, Hinglish and Hindi.

The evaluation also compares top retrieval scores on answerable questions against trap questions. That tells us whether a score threshold alone can trigger refusals.

### Phase 1: Grounded generation

The prompt gives the model only the retrieved clauses and these rules: answer only from the clauses, quote the sentence that supports the answer, give the page number, and reply "not stated in the document" if the clauses do not answer the question.

A second check compares every number and duration in the answer against the cited text. If a figure does not appear in the source, the answer is blocked. This is cheap, and it directly addresses the mis-selling risk.

We run the same questions on two local models and, optionally, on Claude, then pick on evidence.

### Phase 2: Language and routing

Queries in Hinglish are written in many spellings, so we test whether the embedding model alone handles them. If recall drops, we add a query rewrite step that turns the question into clean English before retrieval. The answer is returned in the language the agent used.

A light router decides whether a question is about one policy, a comparison across policies, or something we cannot answer, such as premiums.

### Phase 5: Comparison

Searching text cannot answer "which policy waives the diabetes waiting period" across 20 documents reliably. Instead we extract a fixed set of attributes per policy, have a human verify each value against the PDF, and answer comparison questions from that table.

Proposed attributes: pre-existing disease waiting period, specific disease waiting period, initial waiting period, room rent cap, co-pay, maternity cover and waiting period, AYUSH cover, daycare cover, pre and post hospitalisation days, no claim bonus, renewal terms, sub-limits present or not.

Verification effort is roughly 12 attributes across 20 policies, which is real manual work, and it cannot be skipped if the comparison is shown to a CEO.

## 8. Evaluation plan

| Metric | Target for demo readiness |
|---|---|
| Retrieval recall at 3, answerable questions | 85 percent or better |
| Retrieval recall at 3, Hinglish and Hindi vs English | Within 10 points |
| Answers containing a number not found in the cited clause | Zero |
| Trap questions correctly refused | 100 percent |
| Time to first streamed token on the M1 Pro | Under 3 seconds |
| Full answer time | Measured, then stated honestly in the pitch |

Test set: 20 questions across 3 policies gives 60 cases, which is enough to catch systematic failures but not enough to claim accuracy. We report it as a demo readiness check.

## 9. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Scanned PDFs with no text layer | Policy cannot be indexed | Detect at ingest and swap the policy. Add OCR only if a needed policy is scanned. |
| Waiting period clause spans a page break | Answer misses an exception | Retrieve neighbouring chunks; check in the eval. |
| Small local model blends two clauses | Wrong answer shown live | Number check against the source, refusal rule, and compare with Claude on the same questions. |
| Weak Hinglish retrieval | Core pitch scenario fails | Measure in Phase 0; add query rewrite if needed. |
| Comparison answers wrong across insurers | Credibility loss | Human verified fact table with page references. |
| Live demo failure | Lost meeting | Everything local, no network dependency, rehearsed script, pre-tested questions. |

## 10. Claims to correct in the pitch

**"Scans the PDF in under 3 seconds."** The system indexes documents in advance and retrieves clauses at question time. A technical buyer will notice. Say "answers from the indexed policy document in seconds, with the clause shown".

**"Insurer X waives it after 36 months with a 10 percent co-pay."** Present answers with the quoted clause and page. The pitch should position verification as the product, because compliance teams care about it more than speed.

**Local model speed.** A 7B model on a laptop may take several seconds to finish a paragraph. We will measure it and stream the reply so it feels immediate.

## 11. Demo script (draft)

1. Agent picks a health policy and asks in Hinglish about diabetes and the waiting period.
2. The reply streams in, with a clause card showing the quoted text and page number.
3. Agent asks a follow up about room rent and ICU charges.
4. Agent asks a question the policy does not answer, such as the premium. The system declines and says why.
5. Agent asks a comparison question across the loaded policies, answered from the verified table.

## 12. Open decisions

| Decision | Options | Needed by |
|---|---|---|
| Which 3 policies for Phase 0 | Different insurers, one standard, one different structure, one table heavy | Now |
| Local model or Claude for generation | Decide after the Phase 1 comparison; Claude costs a few dollars per demo session | End of Phase 1 |
| Comparison attribute list | Confirm or edit the 12 proposed attributes | Before Phase 5 |
| Who labels gold answers and verifies the fact table | Needs someone who can read policy wording | Before Phase 0 evaluation |
| Whether the demo must work with no internet | Affects whether Claude can be a fallback | Before Phase 4 |

## 13. Rough effort

These are estimates for one engineer and will move once real PDFs are parsed.

| Phase | Estimate |
|---|---|
| 0 | 2 to 3 days, mostly gold labelling |
| 1 | 2 to 3 days |
| 2 | 1 to 2 days |
| 3 | 1 day |
| 4 | 2 days |
| 5 | 3 to 5 days, mostly verification |
| 6 | 1 to 2 days |

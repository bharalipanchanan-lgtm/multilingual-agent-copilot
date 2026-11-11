# Evaluation results

Policy: National Mediclaim Policy (07/2014). Gold labels are pre-filled and still need a human check.
Hardware: MacBook Pro M1 Pro, 16 GB. Model: Qwen2.5 7B Instruct 4 bit via MLX. Embeddings: bge-m3.

## Retrieval (eval_retrieval.py), 2026-11-05

17 answerable questions. Recall at 3: 100%. Recall at 6: 100%. English 12, Hinglish 4, Hindi 1, all 100%.
Top scores overlap between answerable (lowest 0.458) and not-stated questions (highest 0.561),
so a score threshold alone cannot gate refusals. Refusals come from the router and the model.

## Answers (eval_answers.py), 2026-11-05

Not-stated questions refused: 3 of 3 (premium, hospital list, co-pay).
Answerable questions answered: 17 of 17. Drafts blocked by the number check: 0.
Latency on the laptop, warm: median 5.3 s total, first word in about 3 to 4.5 s. The first question after start takes about 15 s.

Reading the answers (human judgement, not automated):

| Question | Verdict |
|---|---|
| q02 diabetes (Hinglish) | Correct: 2 years specific waiting period (4.3) and 48 months if pre-existing (4.1) |
| q05, q06 room rent, ICU | Correct figures |
| q09 maternity | Correct: not covered (4.7). Was wrong before chunks carried their "Exclusions" part |
| q12 mental illness | Correct per this 2014 wording (likely outdated against current regulation) |
| q17 lifetime renewable | Acceptable: does not claim lifetime renewal |
| q08 sub-limits | Partly right: lists 2.3 caps, misses the 25% caps of 2.1 and 2.2 |
| q13 permanent exclusions | Weak: mixes Appendix II consumables with clause 4 exclusions. Keep out of the demo |

Small model answers vary with wording. Treat these as demo readiness checks on 20 questions, not an accuracy claim.

## Retrieval across six policies (eval_retrieval.py), 2026-11-10

Added five health wordings: Star Family Health Optima, HDFC Optima Secure, Care Supreme,
Niva ReAssure 2.0, TATA AIG MediCare Premier. 743 new chunks, 590+133 indexed, no scanned pages.

32 answerable questions labelled so far (25 of 120 gold rows; the rest are blank and skipped).

Recall@3: 97%. Recall@6: 97%. English 27 at 96%, Hinglish 4 at 100%, Hindi 1 at 100%.

One miss: niva_reassure_2 q05 "What is the room rent limit?". Retrieval returned the Room Rent
definition (p5) and the proportionate-deduction formula (p25, p26) but not the entitlement clause
4.21 on p15, which is the one that says Single Private Room or Sharing Room. The gold label was
left as it is rather than widened to the pages retrieval happened to return.

Score ranges still overlap: lowest answerable 0.461, highest not-stated 0.642, medians 0.617 and
0.545. Same conclusion as the 2026-11-05 run on one policy, now confirmed across six: a score
threshold alone cannot gate refusals.

Page offsets differ per insurer and are recorded in manifest.csv: Star +1, Care Supreme +1, the
rest 0. Citing a PDF index where the footer prints a different number would send an agent to the
wrong page mid-call.

Caveat: 25 of 120 gold rows are labelled, so these numbers cover waiting periods, room rent, AYUSH
and the two traps. They are a demo-readiness check, not an accuracy claim.

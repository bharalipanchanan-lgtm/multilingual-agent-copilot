# Demo runbook

## Before the meeting

1. Plug in the laptop. Close heavy apps (the local model uses about 5 GB of memory).
2. `./run_demo.sh`, open http://localhost:8000, wait for "online" in the header.
3. Ask one warm-up question so the first real answer is fast.
4. Fallback if anything misbehaves: stop the server and run `COPILOT_BACKEND=extractive ./run_demo.sh`. Answers become verbatim clause quotes with page numbers; refusals and comparison still work.

Wi-Fi can be off. Nothing leaves the laptop.

## Script (about 5 minutes)

| Step | Ask | What to point at |
|---|---|---|
| 1 | Diabetes ke liye waiting period kitna hai? | Hinglish in, Hinglish out. Clause card shows clause 4.3 (2 years) and 4.1 (48 months if diabetes exists when the policy starts). Tap "Page" to open the PDF at that page. |
| 2 | Kya ICU charges par bhi room rent ka cap lagta hai? | Exact figures: 1% per day up to ₹5,000, ICU 2% up to ₹10,000. Badge: "Checked against the policy text". |
| 3 | What is the premium for a 45 year old for 10 lakh? | Declines and says why. This is the compliance story: it does not guess. |
| 4 | Is there any co-payment? | "Not stated in the document." It does not claim "no co-pay". |
| 5 | क्या इस पॉलिसी में पहले से मौजूद बीमारियों के लिए वेटिंग पीरियड है? | Devanagari Hindi works too. |
| 6 | Compare the diabetes waiting period across policies | Answered from the fact table, not free text. Today only one policy is loaded and the values are marked unverified. Say this out loud. |

## What to say, and what not to say

Say: "It answers from the indexed policy document in seconds, and shows the clause and page so the agent can verify it." Verification is the product.

Do not say: "It scans the PDF in under 3 seconds." The PDF is indexed in advance. Do not quote an answer without its clause.

Be honest about the current limits:
1. One policy is loaded (National Mediclaim, version 07/2014, used for pipeline testing). Its mental illness exclusion is likely outdated against current regulation.
2. Comparison values are pre-filled and not yet verified by a person.
3. Typed questions only. Voice notes and WhatsApp Business API are not part of this prototype.
4. Measured answer time on this laptop: about 5 seconds per answer (first words after 3 to 4.5 seconds). The first question after starting takes about 15 seconds, which is why the warm-up question matters.

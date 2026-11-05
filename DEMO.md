# Demo runbook

## Before the meeting

1. Plug in the laptop. Close heavy apps (the local model uses about 5 GB of memory).
2. `./run_demo.sh`, open http://localhost:8000, wait for "online" in the header.
3. Ask one warm-up question so the first real answer is fast, then reload the page so the chat starts clean.
4. `python demo_check.py 1` runs the script below against the server and should print 11/11.
5. Fallback if anything misbehaves: stop the server and run `COPILOT_BACKEND=extractive ./run_demo.sh`. Answers become verbatim clause quotes with page numbers; refusals and comparison still work.

Wi-Fi can be off. Nothing leaves the laptop.

## Script (about 5 minutes)

There is no policy dropdown. The copilot opens by asking which policy document to inspect, in English and Hinglish, and the agent answers in their own words. The header shows the policy in use; tap it to see the list again.

| Step | Ask | What to point at |
|---|---|---|
| 0 | Diabetes ke liye waiting period kitna hai? | No policy chosen yet, so it asks "Kaunsa policy document aapko dekhna hai?" and holds the question. |
| 0b | National Mediclaim policy dekhna hai | It confirms the policy in Hinglish and then answers the held question by itself. |
| 1 | (answered automatically) | Hinglish in, Hinglish out. Clause card shows clause 4.3 (2 years) and 4.1 (48 months if diabetes exists when the policy starts). Tap "Page" to open the PDF at that page. |
| 2 | Kya ICU charges par bhi room rent ka cap lagta hai? | Exact figures: 1% per day up to ₹5,000, ICU 2% up to ₹10,000. Badge: "Checked against the policy text". |
| 3 | What is the premium for a 45 year old for 10 lakh? | Declines and says why. This is the compliance story: it does not guess. |
| 4 | Is there any co-payment? | "Not stated in the document." It does not claim "no co-pay". |
| 5 | क्या इस पॉलिसी में पहले से मौजूद बीमारियों के लिए वेटिंग पीरियड है? | Devanagari Hindi works too. |
| 6 | ab SBI wali policy dekhni hai | Switches policy mid conversation and warns that this document is a prospectus, not the full wording. |
| 7 | Is maternity covered? | SBI excludes maternity (Code Excl 18). The answer says not covered. If the model ever calls an exclusion covered, the draft is blocked and the clause is shown instead. |
| 8 | Compare the diabetes waiting period across policies | Answered from the fact table across all five policies, not free text. The values are marked unverified. Say this out loud. |

## What to say, and what not to say

Say: "It answers from the indexed policy document in seconds, and shows the clause and page so the agent can verify it." Verification is the product.

Do not say: "It scans the PDF in under 3 seconds." The PDF is indexed in advance. Do not quote an answer without its clause.

Be honest about the current limits:
1. Five policies are loaded. National Mediclaim is version 07/2014, for pipeline testing. SBI and United India are prospectuses and Royal Sundaram is a brochure, not the full wordings; the copilot says so when one is chosen.
2. Comparison values are pre-filled and not yet verified by a person.
3. Single policy answers on the four new documents are less reliable than on National Mediclaim, which the eval set covers. Stay on National Mediclaim for the detailed questions and use the others for the switch and the comparison.
4. Typed questions only. Voice notes and WhatsApp Business API are not part of this prototype.
5. Measured answer time on this laptop: about 5 seconds per answer (first words after 3 to 4.5 seconds). The first question after starting takes about 15 seconds, which is why the warm-up question matters.

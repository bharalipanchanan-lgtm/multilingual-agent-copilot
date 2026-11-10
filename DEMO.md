# Demo runbook

## Before the meeting

1. Plug in the laptop. Close heavy apps (the local model uses about 5 GB of memory).
2. `./run_demo.sh`, open http://localhost:8000, wait for "online" in the header.
3. Ask one warm-up question so the first real answer is fast, then reload the page so the chat starts clean.
4. `python demo_check.py 1` runs the script below against the server and should print 11/11. `python tests/e2e_ui.py` clicks through the page itself in Chrome and should print "All 17 steps passed".
   If the page still shows a policy dropdown, the browser is showing an old copy: reload with Cmd+Shift+R.
5. Voice (optional): with SARVAM_API_KEY in .env, run `python voice_check.py` (should print 4/4) and allow the microphone when Chrome asks. On a Mac, Chrome also needs System Settings > Privacy & Security > Microphone. Voice needs internet; everything else does not. If the network is poor, type.
6. Fallback if anything misbehaves: stop the server and run `COPILOT_BACKEND=extractive ./run_demo.sh`. Answers become verbatim clause quotes with page numbers; refusals and comparison still work.

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
| 7b | (tap the mic) "Room rent kitna hai?" | Optional, needs the key and internet. The transcript appears in the box; the agent checks it and presses send. "How this was checked" says the question was spoken and which service transcribed it. |
| 8 | Compare the diabetes waiting period across policies | Answered from the fact table across all five policies, not free text. The values are marked unverified. Say this out loud. |
| 9 | Tap "Best policy finder", then send: "Which policy works best for a customer who wants no waiting period and a good claims record? Premium does not matter." | A ranked shortlist of policy plans with a score bar. Each line shows the figure it used and links to its page. It says that premium is left out, and that the claims figure is IRDAI's incurred claims ratio, not a claim settlement ratio. Tap "Ask about this policy" to switch to that policy. |

## What to say, and what not to say

Say: "It answers from the indexed policy document in seconds, and shows the clause and page so the agent can verify it." Verification is the product.

Do not say: "It scans the PDF in under 3 seconds." The PDF is indexed in advance. Do not quote an answer without its clause.

Be honest about the current limits:
1. Seventeen documents are loaded. Twelve of them (HDFC ERGO, Aditya Birla, ICICI Lombard, Star Health, TATA AIG, Care Health, Niva Bupa, Bajaj, Acko, Digit, New India, IFFCO Tokio) are full policy wordings, downloaded on 2026-11-08 from the links on joinditto.in product pages. They have no fact table rows yet, so comparison and the best policy finder cover only the original five, and the answer says so. Their single policy answers are spot checked, not evaluated against gold labels. The original five: National Mediclaim is version 07/2014, for pipeline testing. SBI and United India are prospectuses and Royal Sundaram is a brochure, not the full wordings; the copilot says so when one is chosen.
2. Comparison values are pre-filled and not yet verified by a person.
3. Single policy answers on the four new documents are less reliable than on National Mediclaim, which the eval set covers. Stay on National Mediclaim for the detailed questions and use the others for the switch and the comparison. Avoid plan specific limits on Oriental (for example ELITE maternity): the clause on page 23 says 10% up to 2 lakh while the benefit table gives ELITE 5% up to ₹50,000, and the copilot quotes the clause.
4. Voice questions use Sarvam's cloud service (the only part that leaves the laptop, and only the audio clip). WhatsApp Business API is not part of this prototype.
5. The shortlist is for the agent, not advice to the customer, and it cannot use premium. The claims record uses IRDAI's incurred claims ratio, because IRDAI no longer publishes a claim settlement ratio per insurer. Oriental scores highest on it, at 102.58%, which also means it paid out more in claims than it earned in premium; the card says so.
6. Measured answer time on this laptop: about 5 seconds per answer (first words after 3 to 4.5 seconds). The first question after starting takes about 15 seconds, which is why the warm-up question matters.

## Additions on 2026-11-10 (29 documents)

1. Type "HDFC". The copilot lists Optima Secure, Optima Restore and Optima Senior with one line on how each differs, and answers only after one is picked. It never mixes products.
2. Pick Optima Restore, ask "What is the waiting period?". The answer comes from the fact table in well under a second, with the exact line and page.
3. Type "ReAssure 1.0". The copilot warns that it is no longer sold (source: joinditto.in) and names ReAssure 2.0. Ask "Is robotic surgery covered?": the answer carries the warning and the policy's own line "A limit of maximum INR 1 Lac will apply to all robotic surgeries".
4. Type "Mother is 50, has diabetes, wants room rent more than 10,000 a day". The copilot checks 29 products, shows the best and second best with reasons, folds away why the others do not fit, says when diabetes cover starts, and opens the sales kit: words to say, a WhatsApp message to copy, waiting end dates, papers and what not to promise.
5. Add a product name to the same need ("... Check Diabetes Safe") and only that product is checked.

Say in the demo: fact values were drafted by a model and every quote was checked against the PDF, but no person has signed them off yet; entry ages are mostly in brochures, not wordings, so the copilot asks the agent to confirm age instead of guessing. Premium is still never quoted.

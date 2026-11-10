# QuickInsure Agent Copilot — Test Story

Use this file to test the chatbot, with the 5 features followed strictly, using one tier-3 family story.

Demo: QuickPolicy, simple.html, 49 policies, 44 active, 5 stopped.
Test on localhost: run `./run_demo.sh`, open `http://localhost:8000/simple.html`

This file follows the 5 features strictly, as written. Test each feature exactly as below.

---

## English Version

### Story: A tier-3 family, mother is 55

A family lives in a small town. The son works outside, his mother lives at home.

His mother is 55. She has diabetes. She has severe pain in her knees.

They tried insurance before. In every plan, the waiting period for a pre-existing disease was more than 3 years. That means diabetes would be covered only after 3 years. And they also want a low premium, because the family budget is limited.

The son thinks, can I put my mother in a health insurance plan where diabetes cover starts sooner, and the premium is also low?

Now the agent comes in. An agent cannot remember 500 products. The names also look alike, Optima, Optima Secure, Optima Restore. One company can have 3 products with almost the same name. If he says the wrong product, it becomes a wrong sale.

### This is where the copilot comes in

Test input, type this in the chatbot:

> "My mother is 55 years old. She has diabetes. She has severe pain in her knees. We tried insurance before, but in all of them the waiting period for a pre-existing disease was more than 3 years. Is there a health insurance plan where I can put my mother, and the premium is also low?"

### Feature 1 — Know exactly which product

Test input: type "Optima"

Expected: the copilot shows 2-3 options, with one small difference written under each, for example:
- HDFC Optima Restore — difference: its UIN
- HDFC Optima Secure V08, 2025-26 wording — difference: room rent at actuals
- HDFC Optima Senior — difference: 2020-21 wording

Expected: the copilot answers only after the agent picks one. It never mixes two products.

### Feature 2 — Two ways to use it

Way 1, need-first: the mother case above. The customer tells his need, the tool finds the product.

Way 2, name-first: test input "Optima Secure V08"

Expected: the tool checks only that product, no other product.

Test: set My insurers to ICICI Lombard only.

Expected: the tool shows ICICI Lombard products first (Elevate). Max Life is not in the catalogue — there is no health wording for it.

### Feature 3 — Show the best 1 or 2

Expected: the copilot checks age, diabetes wait, and room rent, then shows the best 1 and the second best only, not a long list. Money / premium is **not ranked** — premium is never in the wording.

Expected:
- Best: HDFC Optima Secure V08, diabetes wait 36 months, room rent at actuals, age 55 fits.
- Diabetes cover starts: **11 November 2029**
- Second best: Liberty HealthPrime Connect, 36 months, entry up to 65.
- Why best, in one line: "Shortest wait among plans where entry age is confirmed from the wording — 36 months."
- Money line: "Money was not compared. Premium is never written in a policy wording — the insurer sets it from its rate card after the health check."
- Why others do not fit, in one line each: for example, "PED wait 48 months, longer than 36".
- The date when diabetes cover will start: 11 November 2029.
- A shorter-wait plan with no entry age in the wording (e.g. Care Freedom 24 months) may appear as **not ranked**, with a prospectus warning — not as a second "shortest".

### Feature 4 — Simple answers, hard questions show the exact line

Simple questions, short answer in seconds:

Test input: "How much will the premium be?"
Expected: short answer, in seconds.

Test input: "What is the waiting time?"
Expected: short answer, in seconds.

Test input: "What is the room rent?"
Expected: short answer, in seconds: room rent at actuals.

Test input: "What is the age limit?"
Expected: short answer, in seconds.

Hard questions, exact line from the policy book, with page and rule number, plus one line in simple words:

Test input: "What is the cataract limit?"
Expected: exact line from the policy book, PDF page 31, with section and rule number, plus one line in simple words: "Cataract is in the listed-illness waiting list; no separate money limit is written for it."

Test input: "Is robotic surgery covered?"
Expected: exact line from the policy book, with page and rule number, plus one line in simple words. If it is not written, the tool says: "This is not written in this product."

Test input: "Is AYUSH covered?"
Expected: exact line from the policy book, with page and rule number, plus one line in simple words. If it is not written, the tool says: "This is not written in this product."

If the book does not say it, the tool says: "This is not written in this product."

### Feature 5 — Help the agent close the sale, and keep products up to date

Test: tap "Close the sale"

Expected:
- Words to say to the customer, in simple language: diabetes cover starts 11 November 2029, room rent at actuals, knee pain is treated as pre-existing, same wait.
- A short WhatsApp message to send, with the plan name, UIN, and diabetes cover from 11 November 2029.
- The date when waiting will end: 11 November 2029, 36 months, PDF page 30.
- Papers needed to buy (only if the wording names them, each with a page): for Optima Secure V08 — pre-policy medical check-up and previous medical / treatment records (PDF page 43). Do **not** invent Aadhaar, PAN, sugar reports or knee X-ray if the wording does not ask for them.
- Papers at claim time (separate list): claim form, discharge summary, hospital bills, diagnostic reports, etc., each with its wording page.
- What he should not promise: never say a pre-existing condition is covered from day one, never quote a premium before the medical underwriting result (premium is not in the wording), do not say diabetes is covered before 11 November 2029, do not promise knee surgery or joint replacement during the waiting period.

Test input: type "National Mediclaim"

Expected: "STOPPED — National Insurance National Mediclaim Policy 2014 Edition, was stopped for new sales on 1 Apr 2024. Renewals only — do not sell it to a new customer." Replacement shown: "Sell the current product instead: TATA AIG MediCare Premier" with difference **"PED wait 24 months"** (no word "shortest" — ranking already owns the only shortest-wait claim).

### End of the story

The mother gets a plan, the diabetes cover date is clear, the agent has no fear of selling the wrong product, and the family gets no false promise.

That is the 5 features, in one family's story, followed strictly.

---

## Hinglish Version

### Story: Ek tier-3 family, ma 55 saal ki

Ek chhote seher me ek family rehti hai. Beta bahar kaam karta hai, ghar me ma rehti hai.

Ma 55 saal ki hai. Unhe diabetes hai. Unke ghutno me bohot jyada dard rehta hai.

Unhone pehle insurance try kiya tha. Har plan me pre-existing disease ka waiting period 3 saal se zyada tha. Matlab diabetes ka cover 3 saal baad milega. Aur premium bhi kam chahiye, kyunki family ka budget limited hai.

Beta sochta hai, ma ko kisi health insurance plan me daal sake, jaha diabetes ka cover jaldi mile, aur paise bhi kam lage.

Ab agent ke paas aata hai. Agent ko 500 products yaad nahi rehte. Naam bhi ek jaise hote hain, Optima, Optima Secure, Optima Restore. Ek company ke 3 products ka naam lagbhag ek jaisa hota hai. Galat product bol diya, to galat sale ho jayegi.

### Yahi par copilot aata hai

Test input, chatbot me ye likho:

> "meri ma 55 years ki hai. unhe diabetes hai. unke ghutne meh bohot jyada dard rehta hai. humne pehle insurance pehle kuch try kiya tha. but unme pre existing disease ka jo waiting period hota hai, woh 3 saal se jyada ka hota hai. esa kuch hai kya jisse mummy ko hum ek health insurance plan meh dal sake. Esa koi health insurance plan hai kya, jaha peh mummy ko dal sake aur pese bhi kam lage."

### Feature 1 — Know exactly which product

Test input: "Optima" likho

Expected: copilot 2-3 options dikhata hai, har ek ke neeche ek chhota difference likha hota hai, jaise:
- HDFC Optima Restore — difference: uska UIN
- HDFC Optima Secure V08, 2025-26 wording — difference: room rent at actuals
- HDFC Optima Senior — difference: 2020-21 wording

Expected: copilot jawab sirf agent ke pick karne ke baad deta hai. Do products ko mix nahi karta.

### Feature 2 — Two ways to use it

Way 1, need-first: ma ka case upar. Customer apni need batata hai, tool product dhoondhta hai.

Way 2, name-first: test input "Optima Secure V08"

Expected: tool sirf wahi product check karta hai, koi aur product nahi.

Test: My insurers ko ICICI Lombard only set karo.

Expected: tool pehle ICICI Lombard (Elevate) dikhata hai. Max Life catalogue me nahi hai — uska health wording nahi mila.

### Feature 3 — Show the best 1 or 2

Expected: copilot age, diabetes wait, aur room rent check karta hai, phir best 1 aur second best dikhata hai, lambi list nahi. Money / premium rank **nahi** hota — premium wording me kabhi nahi hota.

Expected:
- Best: HDFC Optima Secure V08, diabetes wait 36 months, room rent at actuals, age 55 fits.
- Diabetes cover start hoga: **11 November 2029**
- Second best: Liberty HealthPrime Connect, 36 months, entry up to 65.
- Why best, ek line me: "Shortest wait among plans where entry age is confirmed from the wording — 36 months."
- Money line: "Paisa compare nahi kiya… premium rate card se aata hai."
- Why others nahi, ek line me har ek ke liye: jaise, "PED wait 48 months, longer than 36".
- Diabetes cover kab start hoga: 11 November 2029.
- Kam wait wala plan jiski wording me entry age nahi (jaise Care Freedom 24 months) **not ranked** dikhe — doosra "shortest" mat dikhao.

### Feature 4 — Simple answers, hard questions show the exact line

Simple questions, short answer seconds me:

Test input: "premium kitna hoga?"
Expected: short answer, seconds me.

Test input: "waiting time kitna hai?"
Expected: short answer, seconds me.

Test input: "room rent kya hai?"
Expected: short answer, seconds me: room rent at actuals.

Test input: "age limit kya hai?"
Expected: short answer, seconds me.

Hard questions, exact line policy book se, page aur rule number ke saath, plus ek line simple words me:

Test input: "cataract limit kya hai?"
Expected: exact line policy book se, PDF page 31, section aur rule number ke saath, plus ek line simple words me: "Cataract is in the listed-illness waiting list; no separate money limit is written for it."

Test input: "robotic surgery covered hai?"
Expected: exact line policy book se, page aur rule number ke saath, plus ek line simple words me. Agar likha nahi hai, to tool bolta hai: "This is not written in this product."

Test input: "AYUSH covered hai?"
Expected: exact line policy book se, page aur rule number ke saath, plus ek line simple words me. Agar likha nahi hai, to tool bolta hai: "This is not written in this product."

Agar book me likha nahi hai, to tool bolta hai: "This is not written in this product."

### Feature 5 — Help the agent close the sale, and keep products up to date

Test: "Close the sale" dabao

Expected:
- Customer ko kya bolna hai, simple language me: diabetes cover 11 November 2029 se start hoga, room rent at actuals, knee pain pre-existing hai, same wait.
- Ek short WhatsApp message, plan name, UIN, aur diabetes cover 11 November 2029 ke saath.
- Waiting kab khatm hogi: 11 November 2029, 36 months, PDF page 30.
- Papers needed to buy (sirf wording me jo likha ho, page ke saath): Optima Secure V08 — pre-policy medical check-up aur previous medical records (PDF page 43). Aadhaar / PAN / sugar / knee X-ray mat invent karo agar wording me nahi hai.
- Papers at claim time (alag list): claim form, discharge, bills, reports, wagaira — har ek page ke saath.
- Kya promise nahi karna hai: kabhi mat bolo pre-existing pehle din se covered hai, medical underwriting se pehle premium mat bolo (premium wording me nahi), diabetes 11 November 2029 se pehle covered mat bolo, waiting me knee / joint replacement ka promise mat karo.

Test input: "National Mediclaim" likho

Expected: STOPPED notice + replacement TATA AIG MediCare Premier with **"PED wait 24 months"** (bina "shortest" ke).

### Story ka end

Ma ko plan mil gaya, diabetes ka cover date clear hai, agent ko galat product bechne ka dar nahi hai, aur family ko jhootha promise nahi mila.

Yehi hai 5 features, ek family ki story me, strictly followed.

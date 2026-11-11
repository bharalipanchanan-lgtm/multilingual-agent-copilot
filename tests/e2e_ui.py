"""End to end test of the chat page in a real browser (Google Chrome, driven by Playwright).

  python tests/e2e_ui.py [--headed] [--shots DIR]

Needs the server running (./run_demo.sh). Opens the page as an agent would, with no policy
chosen, and goes through the whole demo flow: the greeting, a question held until a policy is
chosen, choosing by typing, a clause card and its page link, a refusal, a not-stated answer,
Hindi, switching by tapping the header and an option button, a spelling slip, an insurer that is
not loaded, and a comparison. Every step checks what is on screen, not just the API status.
Prints one line per step and exits 1 on the first failure, with a screenshot.
"""
import argparse
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

import os
URL = os.environ.get("COPILOT_URL", "http://localhost:8000/")
ROOT = Path(__file__).resolve().parents[1]


class Fail(Exception):
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--shots", default=str(ROOT / "eval" / "reports" / "ui_shots"))
    a = ap.parse_args()
    shots = Path(a.shots)
    shots.mkdir(parents=True, exist_ok=True)
    errors, results = [], []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=not a.headed)
        page = browser.new_page(viewport={"width": 480, "height": 900})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("response", lambda r: errors.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)

        def shot(name):
            page.screenshot(path=str(shots / f"{len(results):02d}_{name}.png"), full_page=False)

        def bot_texts():
            return page.locator(".msg.bot").all_inner_texts()

        def finals():
            return page.locator(".msg.bot .meta").count()

        def send(text, expect_finals=1, tap=None, timeout=150):
            before = finals()
            if tap:
                tap()
            else:
                page.fill("#q", text)
                page.press("#q", "Enter")
            deadline = time.time() + timeout
            while finals() < before + expect_finals:
                if time.time() > deadline:
                    raise Fail(f"no answer within {timeout}s after {text!r}")
                page.wait_for_timeout(250)
            page.wait_for_timeout(300)
            return bot_texts()[-1]

        def step(name, fn):
            t0 = time.time()
            try:
                detail = fn() or ""
                results.append(name)
                shot(re.sub(r"\W+", "_", name.lower())[:40])
                print(f"OK   {name} ({time.time() - t0:.1f}s) {detail}")
            except Exception as e:
                shot("FAILED")
                print(f"FAIL {name}: {e}")
                print("Last bot message:", (bot_texts() or [""])[-1][:400])
                browser.close()
                sys.exit(1)

        def check(cond, msg):
            if not cond:
                raise Fail(msg)

        page.goto(URL, wait_until="networkidle")

        def greeting():
            # the page opens on a welcome screen with the copilot's name; it speaks once the agent does
            page.wait_for_selector("#hero", timeout=10000)
            check("Bima Saathi" in page.inner_text("#hero"), "welcome screen does not name the copilot")
            check(page.locator(".msg").count() == 0, "the copilot spoke before the agent did")
            check(page.locator("select").count() == 0, "a dropdown is still on the page")
            check("No policy chosen yet" in page.inner_text("#cur"), "header does not say no policy is chosen")
            check(page.locator("#hero button").count() == 1 and page.inner_text("#hiBtn") == "Hi",
                  "the welcome screen should have exactly one button, Hi")
            check(page.locator(".chip").count() == 0, "suggestion chips are back")
            for _ in range(120):  # wait for the models
                if "online" in page.inner_text("#status"):
                    break
                page.wait_for_timeout(1000)
            check("online" in page.inner_text("#status"), "server not online")
            t = send("", tap=lambda: page.click("#hiBtn"))
            check(not page.locator("#hero").is_visible(), "welcome screen still shown after the first message")
            check("Bima Saathi" in t and "Which policy document are you looking for?" in t, f"no greeting: {t[:160]!r}")
            last = page.locator(".msg.bot").last
            check(last.locator(".opt").count() == 0, "the greeting should not list documents")
            acts = [b.inner_text() for b in last.locator(".act-btn").all()]
            check(acts == ["Browse the policy documents", "Find a product for a customer"], f"greeting buttons: {acts}")
        step("Welcome screen has one Hi button; Hi asks which document, with Browse and Find", greeting)

        def held_question():
            t = send("Diabetes ke liye waiting period kitna hai?")
            last = page.locator(".msg.bot").last
            check("koi policy chuni nahi gayi" in t.lower(), "no note that it answered from the nearest document")
            check(last.locator(".notice.info").count() == 1, "the nearest-document note is not in the calm style")
            check(1 <= last.locator(".opt").count() <= 2, "no other documents offered for the same question")
            check("national" not in page.inner_text("#cur").lower(), "answered from the 2014 test wording")
            return page.inner_text("#cur")
        step("Question before choosing: answered from the nearest document, says so, offers others", held_question)

        def choose_by_typing():
            send("National Mediclaim policy dekhna hai", expect_finals=2)
            texts = bot_texts()
            sel, ans = texts[-2], texts[-1]
            check("Theek hai" in sel and "National Mediclaim" in sel, f"no Hinglish confirmation: {sel[:120]!r}")
            check("National Mediclaim" in page.inner_text("#cur"), "header does not show the policy")
            check("Checked against the policy text" in ans, f"held question not answered: {ans[:160]!r}")
            check(re.search(r"2 saal|two years|2 years", ans, re.I), "diabetes answer lacks the 2 year rule")
            quotes = page.locator(".msg.bot").last.locator(".cardc q").all_inner_texts()
            check(any("diabet" in q.lower() for q in quotes), f"no clause card quotes the diabetes line: {quotes}")
            check(page.locator(".chip").count() == 0, "suggestion chips came back after choosing")
            return ans.splitlines()[1][:90]
        step("Typing 'National Mediclaim policy dekhna hai' chooses it and answers the held question", choose_by_typing)

        def clause_card():
            last = page.locator(".msg.bot").last
            check(last.locator(".cardc").count() >= 1, "no clause card")
            href = last.locator(".cardc a").first.get_attribute("href")
            check(re.match(r"/pdf/national_mediclaim#page=\d+", href or ""), f"bad page link {href}")
            r = page.request.get(URL.rstrip("/") + href.split("#")[0])
            check(r.status == 200 and r.headers.get("content-type", "").startswith("application/pdf"), "PDF not served")
            if last.locator(".ref").count():
                last.locator(".ref").first.click()
                page.wait_for_timeout(200)
            return href
        step("Clause card links to the PDF page", clause_card)

        def icu():
            t = send("Kya ICU charges par bhi room rent ka cap lagta hai?")
            check("Checked against the policy text" in t, t[:160])
            check("2%" in t or "10,000" in t, "ICU figure missing")
        step("ICU question answered with figures", icu)

        def premium():
            t = send("What is the premium for a 45 year old for 10 lakh?")
            check("Outside the policy wording" in t, t[:160])
        step("Premium question refused", premium)

        def copay():
            t = send("Is there any co-payment?")
            check(re.search(r"not written in this product|Not stated in the document", t, re.I), t[:160])
            check(not re.search(r"no co-?pay", t, re.I), "claims there is no co-pay")
        step("Co-pay answered as not stated", copay)

        def hindi():
            t = send("क्या इस पॉलिसी में पहले से मौजूद बीमारियों के लिए वेटिंग पीरियड है?")
            check(re.search(r"[ऀ-ॿ]", t.split("\n", 1)[-1]), "answer not in Hindi")
            check("Checked against the policy text" in t, t[:160])
        step("Hindi question answered in Hindi", hindi)

        def switch_by_tap():
            t = send("", tap=lambda: page.click("#cur"))
            check("Which policy document" in t or "Kaunsa" in t or "kaunsa" in t, f"tapping the header did not ask: {t[:120]!r}")
            last = page.locator(".msg.bot").last
            check(last.locator(".act-btn").count() == 2, "no Browse and Find buttons")
            t = send("Royal")   # the short name alone selects Royal Sundaram, a brochure
            check("Royal Sundaram" in page.inner_text("#cur"), "header did not switch to Royal Sundaram")
            check("brochure" in t, "no brochure warning")
            check("me" in page.locator(".msg").nth(-2).get_attribute("class"), "the tap did not show as the agent's message")
        step("Tap header asks which document; 'Royal' switches with a brochure warning", switch_by_tap)

        def sbi_maternity():
            t = send("SBI health policy")   # "SBI" alone lists SBI General (health) and SBI Life (term)
            check("no longer sold" in t, f"SBI Retail is marked withdrawn but no warning: {t[:200]!r}")
            t = send("Is maternity covered?")
            check("no longer sold" in t, "answer from a withdrawn product carries no warning")
            body = t.lower()
            check("not covered" in body or "excluded" in body or "does not" in body or "blocked" in body,
                  f"SBI maternity not answered as excluded: {t[:200]!r}")
            check(not re.search(r"maternity (expenses )?(is|are) covered", body), "says maternity is covered")
            href = page.locator(".msg.bot").last.locator(".cardc a").first.get_attribute("href")
            check(href and href.startswith("/pdf/sbi_retail_health#page="), f"card links to {href}")
        step("SBI (withdrawn) warns; maternity excluded, cites the SBI PDF", sbi_maternity)

        def typo_switch():
            t = send("ab oriantal wali policy dekhni hai")
            check("Oriental" in page.inner_text("#cur") and "Theek hai" in t, t[:160])
        step("Spelling slip 'oriantal' switches to Oriental", typo_switch)

        def plan_question():
            t = send("ELITE plan mein maternity cover hai kya?")
            check(any(b in t for b in ["Checked against the policy text", "Draft blocked", "Not stated", "Not written", "Quick answer"]), t[:160])
            return t.splitlines()[1][:100] if "\n" in t else t[:100]
        step("Plan question on Oriental gets a checked answer", plan_question)

        def not_loaded():
            t = send("ManipalCigna ka room rent kitna hai?")
            check("ManipalCigna" in t and "loaded nahi" in t, t[:200])
            check("Oriental" in page.inner_text("#cur"), "policy changed after an unloaded insurer")
        step("Unloaded insurer ManipalCigna is refused, policy unchanged", not_loaded)

        def compare():
            t = send("Compare the diabetes waiting period across policies")
            check("From the policy fact table" in t, t[:160])
            n = page.locator(".msg.bot").last.locator("table.cmp tr").count() - 1
            on_sale = sum(1 for p in page.request.get(URL.rstrip("/") + "/api/policies").json() if p["status"] != "withdrawn" and p["category"] == "health")
            check(n == on_sale, f"comparison table has {n} policies, {on_sale} health products are on sale")
            check("no longer sold" not in t, "a withdrawn product is in the comparison")
            check("Not yet verified" in t or "unverified" in t, "no unverified marker")
        step("Comparison covers every product on sale, marked unverified", compare)

        def two_named():
            t = send("SBI ya United India, room rent kitna hai?")
            check("Kaunsi use karun" in t or "Which one" in t, t[:160])
            last = page.locator(".msg.bot").last
            check(last.locator(".opt").count() == 2, "should offer the two named policies")
            send("", tap=lambda: last.locator(".opt", has_text="United India").click(), expect_finals=2)
            texts = bot_texts()
            check("United India" in page.inner_text("#cur"), "did not switch to United India")
            check(texts[-2].startswith("Policy document chosen") and "Theek hai" in texts[-2],
                  f"confirmation not in Hinglish: {texts[-2][:120]!r}")
            check("Checked against the policy text" in texts[-1] and "1%" in texts[-1],
                  f"United India room rent (1% of sum insured, page 2) not answered: {texts[-1][:200]!r}")
            check("Answering your earlier question" in page.inner_text("#chat"), "no note that the earlier question is answered")
        step("Two policies named: asks which, then answers the held question", two_named)

        def shortlist():
            t = send("Which policy works best for a customer who wants no waiting period and a good claims record? "
                     "Premium does not matter.")
            check("Shortlist from the policy fact table" in t, t[:200])
            last = page.locator(".msg.bot").last
            n = last.locator(".rk").count()
            check(n >= 3, f"only {n} ranked policies shown")
            first = last.locator(".rk").first.inner_text()
            check("Oriental" in first, f"unexpected first place: {first[:120]!r}")
            check("ICR" in first, "claims record (IRDAI ICR) not used")
            check("not a claim settlement ratio" in t, "ICR not explained as different from a settlement ratio")
            check("Premium is left out" in t, "premium preference not acknowledged")
            href = last.locator(".rk a").first.get_attribute("href")
            check(href and href.startswith("/pdf/oriental_sampoorna#page="), f"ranking evidence links to {href}")
            return first.splitlines()[1] if "\n" in first else first[:80]
        step("Best policy finder ranks on waiting periods and claims record, with evidence", shortlist)

        def which_product():
            t = send("HDFC")
            check("Which exact product" in t, t[:160])
            last = page.locator(".msg.bot").last
            check(last.locator(".opt").count() == 5, "should offer HDFC ERGO's three health and HDFC Life's two term documents")
            check(last.locator(".opt .cat.term").count() == 2, "term plans are not marked as term")
            t = send("HDFC health policy")
            last = page.locator(".msg.bot").last
            check(last.locator(".opt").count() == 3, "HDFC health should list only the three health documents")
            check(last.locator(".opt .cat.term").count() == 0, "a term plan was listed for HDFC health")
            check(last.locator(".opt small.diff").count() == 3, "each product needs a line on how it differs")
            t = send("", tap=lambda: last.locator(".opt", has_text="Optima Restore").click())
            check("Optima Restore" in page.inner_text("#cur"), "did not switch to Optima Restore")
        step("HDFC lists 5 (health and term); HDFC health lists only the 3 health, each with how it differs", which_product)

        def quick():
            t0 = time.time()
            t = send("What is the waiting period?")
            check("Quick answer from the fact table" in t, t[:160])
            check(page.locator(".msg.bot").last.locator(".cardc").count() >= 1, "no exact line shown")
            return f"{time.time() - t0:.1f}s in the browser"
        step("Simple question: quick answer from the fact table with the exact line", quick)

        def need_fit():
            t = send("Mother is 50, has diabetes, wants room rent more than 10,000 a day")
            check("against the customer" in t, t[:160])
            last = page.locator(".msg.bot").last
            n = last.locator(".fc").count()
            check(1 <= n <= 2, f"{n} product cards; the best one or two are wanted")
            check("BEST" in last.locator(".fc").first.inner_text().upper(), "no best product card")
            check(last.locator(".fc").first.locator("li").count() >= 1, "best product has no reasons")
            check("Diabetes cover starts" in t, "no date when diabetes cover starts")
            check("products are not shown" in t, "no reasons for the others")
            kit = last.locator("details.kit")
            check(kit.count() == 1, "no sales kit")
            k = kit.inner_text()
            for part in ("Say to the customer", "WhatsApp message", "When the waiting ends", "Papers to keep ready", "Do not promise"):
                check(part.lower() in k.lower(), f"sales kit lacks {part}")
            check(not re.search(r"Rs\.?\s?[\d,]+\s*(premium|per year)", k, re.I), "sales kit quotes a premium")
            return last.locator(".fc").first.locator(".nm").inner_text()
        step("Customer need: best and second best, reasons, diabetes date and a sales kit", need_fit)

        def browse_documents():
            # one conversation, never a chat per policy; other documents are found by search
            page.set_viewport_size({"width": 1280, "height": 860})
            page.wait_for_timeout(300)
            check(page.locator(".side, #plist, .pitem").count() == 0, "a chat list of policies is on the page")
            browse = page.locator(".msg.bot").first.locator(".act-btn[data-act=browse]")
            check(browse.count() == 1, "greeting has no Browse the policy documents button")
            browse.click()
            check(page.locator("#sheet").is_visible(), "document browser did not open")
            n_docs = len(page.request.get(URL.rstrip("/") + "/api/policies").json())
            check(n_docs >= 15, f"only {n_docs} documents loaded")
            check(page.locator("#doclist .doc").count() == n_docs, "browser does not list every loaded document")
            page.fill("#docsearch", "royal sund")
            check(page.locator("#doclist .doc").count() == 1, "search did not narrow to one document")
            page.fill("#docsearch", "icici term")
            check(page.locator("#doclist .doc").count() == 2, "searching 'icici term' should find the two ICICI term plans")
            page.fill("#docsearch", "star")
            check(page.locator("#doclist .doc").count() == 4, "searching 'star' should find the four Star Health products")
            page.fill("#docsearch", "manipal")
            check("No loaded document matches" in page.inner_text("#doclist"), "no message for a document that is not loaded")
            page.fill("#docsearch", "multiplier")
            send("", tap=lambda: page.locator("#doclist .doc").first.click(), expect_finals=1)
            check(not page.locator("#sheet").is_visible(), "browser stayed open after picking")
            check("Royal Sundaram" in page.inner_text("#cur"), "picking in the browser did not switch the policy")
            check("me" in page.locator(".msg").nth(-2).get_attribute("class"), "the pick was not shown as the agent's message")
            check("Policy document chosen" in bot_texts()[-1], "copilot did not confirm the document in the chat")
            page.click("#browseTop")
            check(page.locator("#doclist .doc.sel", has_text="Royal Sundaram").count() == 1, "browser does not mark the document in use")
            page.keyboard.press("Escape")
            check(not page.locator("#sheet").is_visible(), "Escape did not close the browser")
            page.set_viewport_size({"width": 480, "height": 900})
        step("Browse all documents: search, pick, the copilot confirms in the same chat", browse_documents)

        browser.close()

    real_errors = [e for e in errors if "favicon" not in e]
    if real_errors:
        print("Browser console errors:", real_errors)
        sys.exit(1)
    print(f"\nAll {len(results)} steps passed. Screenshots in {shots}")


if __name__ == "__main__":
    main()

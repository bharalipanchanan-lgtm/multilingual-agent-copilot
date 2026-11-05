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

URL = "http://localhost:8000/"
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
            page.wait_for_selector("text=Kaunsa policy document aapko dekhna hai?", timeout=10000)
            check(page.locator("select").count() == 0, "a dropdown is still on the page")
            check(page.locator(".opt").count() == 5, f"expected 5 option buttons, saw {page.locator('.opt').count()}")
            check("No policy chosen yet" in page.inner_text("#cur"), "header does not say no policy is chosen")
            check(not page.locator("#chips").is_visible(), "suggestions shown before a policy is chosen")
            for _ in range(120):  # wait for the models
                if "online" in page.inner_text("#status"):
                    break
                page.wait_for_timeout(1000)
            check("online" in page.inner_text("#status"), "server not online")
        step("Greeting asks which policy, no dropdown", greeting)

        def held_question():
            t = send("Diabetes ke liye waiting period kitna hai?")
            check("Kaunsa policy document aapko dekhna hai?" in t, "did not ask which policy")
            check("Choose a policy document" in t, "badge missing")
        step("Question before choosing is held, copilot asks which policy", held_question)

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
            check(page.locator("#chips").is_visible(), "suggestions not shown after choosing")
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
            check("Not stated in the document" in t, t[:160])
            check(not re.search(r"no co-?pay", t, re.I), "claims there is no co-pay")
        step("Co-pay answered as not stated", copay)

        def hindi():
            t = send("क्या इस पॉलिसी में पहले से मौजूद बीमारियों के लिए वेटिंग पीरियड है?")
            check(re.search(r"[ऀ-ॿ]", t.split("\n", 1)[-1]), "answer not in Hindi")
            check("Checked against the policy text" in t, t[:160])
        step("Hindi question answered in Hindi", hindi)

        def switch_by_tap():
            t = send("", tap=lambda: page.click("#cur"))
            check("Which policy document" in t or "Kaunsa" in t, f"tapping the header did not show the list: {t[:120]!r}")
            last = page.locator(".msg.bot").last
            check(last.locator(".opt").count() == 5, "no option buttons in the list")
            t = send("", tap=lambda: last.locator(".opt", has_text="SBI").click())
            check("SBI" in page.inner_text("#cur"), "header did not switch to SBI")
            check("prospectus" in t, "no prospectus warning")
            check("me" in page.locator(".msg").nth(-2).get_attribute("class"), "the tap did not show as the agent's message")
        step("Tap header, tap SBI: switches with a prospectus warning", switch_by_tap)

        def sbi_maternity():
            t = send("Is maternity covered?")
            body = t.lower()
            check("not covered" in body or "excluded" in body or "does not" in body or "blocked" in body,
                  f"SBI maternity not answered as excluded: {t[:200]!r}")
            check(not re.search(r"maternity (expenses )?(is|are) covered", body), "says maternity is covered")
            href = page.locator(".msg.bot").last.locator(".cardc a").first.get_attribute("href")
            check(href and href.startswith("/pdf/sbi_retail_health#page="), f"card links to {href}")
        step("SBI maternity: excluded, cites the SBI PDF", sbi_maternity)

        def typo_switch():
            t = send("ab oriantal wali policy dekhni hai")
            check("Oriental" in page.inner_text("#cur") and "Theek hai" in t, t[:160])
        step("Spelling slip 'oriantal' switches to Oriental", typo_switch)

        def plan_question():
            t = send("ELITE plan mein maternity cover hai kya?")
            check(any(b in t for b in ["Checked against the policy text", "Draft blocked", "Not stated"]), t[:160])
            return t.splitlines()[1][:100] if "\n" in t else t[:100]
        step("Plan question on Oriental gets a checked answer", plan_question)

        def not_loaded():
            t = send("HDFC Ergo ka room rent kitna hai?")
            check("HDFC ERGO" in t and "loaded nahi" in t, t[:200])
            check("Oriental" in page.inner_text("#cur"), "policy changed after an unloaded insurer")
        step("Unloaded insurer HDFC ERGO is refused, policy unchanged", not_loaded)

        def compare():
            t = send("Compare the diabetes waiting period across policies")
            check("From the policy fact table" in t, t[:160])
            n = page.locator(".msg.bot").last.locator("table.cmp tr").count() - 1
            check(n == 5, f"comparison table has {n} policies")
            check("Not yet verified" in t or "unverified" in t, "no unverified marker")
        step("Comparison table covers all five policies, marked unverified", compare)

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

        browser.close()

    real_errors = [e for e in errors if "favicon" not in e]
    if real_errors:
        print("Browser console errors:", real_errors)
        sys.exit(1)
    print(f"\nAll {len(results)} steps passed. Screenshots in {shots}")


if __name__ == "__main__":
    main()

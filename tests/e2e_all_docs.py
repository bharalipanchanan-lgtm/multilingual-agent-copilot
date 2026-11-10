"""Every loaded document, end to end, against the running copilot.

  COPILOT_URL=http://localhost:8002/ python tests/e2e_all_docs.py            API checks and browser search
  COPILOT_URL=http://localhost:8002/ python tests/e2e_all_docs.py --no-ask   skip the model questions

For each document in /api/policies:
  pdf        /pdf/<id> serves a PDF
  label      typing its button label selects exactly this document
  brand      typing its insurer's short name selects it or lists it among the choices
  ask        a typical question is answered (or honestly not stated) from this document only: every
             cited clause belongs to it, never to a look-alike
  browse     in the page, searching the document browser for its label finds it, and picking it
             makes it the policy in use
Exit code 1 if anything fails. Failures are listed with the document.
"""
import argparse
import json
import os
import re
import sys
import urllib.request

URL = os.environ.get("COPILOT_URL", "http://localhost:8000/").rstrip("/")

QUESTION = {"health": "What is the waiting period for pre-existing diseases?",
            "term": "What is the death benefit and is suicide excluded?"}
# a short name an agent would type for the brand
BRAND_WORDS = ["icici", "hdfc", "sbi", "bajaj", "aditya birla", "acko", "star", "care", "niva", "tata", "lic", "max life",
               "national", "oriental", "united india", "royal", "digit", "new india", "iffco", "life insurance corporation"]


def get(path):
    with urllib.request.urlopen(URL + path, timeout=60) as r:
        return r.status, r.headers.get("content-type", ""), r.read()


def ask(question, policy_id=None):
    body = json.dumps({"question": question, "policy_id": policy_id}).encode()
    req = urllib.request.Request(URL + "/api/ask", body, {"Content-Type": "application/json"})
    events = []
    with urllib.request.urlopen(req, timeout=120) as r:
        for raw in r:
            line = raw.decode("utf-8").strip()
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ask", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    _, _, raw = get("/api/policies")
    docs = json.loads(raw)
    fails = []

    def fail(doc, what):
        fails.append(f"{doc['label']} ({doc['policy_id']}): {what}")
        print(f"FAIL {doc['label']:34} {what}", flush=True)

    for d in docs:
        pid = d["policy_id"]
        st, ctype, body = get(f"/pdf/{pid}")
        if st != 200 or "pdf" not in ctype or not body.startswith(b"%PDF"):
            fail(d, f"PDF not served ({st} {ctype})")
        fin = ask(d["label"])[-1]
        if fin.get("status") != "selected" or fin.get("policy_id") != pid:
            fail(d, f"label {d['label']!r} gave {fin.get('status')} {fin.get('policy_id')} {[o['label'] for o in fin.get('options', [])]}")
        insurer = d["name"].split(", ")[0].lower()   # the brand is in the insurer's name, as a whole word
        brand = next((b for b in BRAND_WORDS if re.search(rf"\b{re.escape(b)}\b", insurer)), None)
        if brand:
            fin = ask(brand)[-1]
            offered = [o["policy_id"] for o in fin.get("options", [])]
            if not (fin.get("policy_id") == pid or pid in offered):
                fail(d, f"brand {brand!r} neither selects nor lists it ({fin.get('status')}, {offered[:5]})")
        if not a.no_ask:
            q = QUESTION.get(d.get("category") or "health")
            fin = ask(q, pid)[-1]
            cites = fin.get("citations") or []
            if fin.get("status") not in ("answered", "not_stated", "blocked"):
                fail(d, f"question gave {fin.get('status')}: {fin.get('answer', '')[:120]}")
            elif any(c.get("policy_id") not in (pid, None) for c in cites):
                fail(d, f"answer cites another document: {sorted({c.get('policy_id') for c in cites})}")
            else:
                print(f"ok   {d['label']:34} {fin['status']:10} {fin.get('ms', 0):>6} ms  {fin['answer'][:70]!r}", flush=True)

    if not a.no_browser:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(channel="chrome")
            page = b.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(URL + "/", wait_until="networkidle")
            page.click("#hiBtn")
            page.wait_for_selector(".act-btn[data-act=browse]")
            for d in docs:
                n = page.locator(".msg.bot .meta").count()
                if page.locator("#sheet.open").count() == 0:
                    page.click("#browseTop")
                page.fill("#docsearch", d["label"])
                hit = page.locator("#doclist .doc", has_text=d["label"])
                if hit.count() == 0:
                    fail(d, "browser search for its label finds nothing")
                    page.keyboard.press("Escape")
                    continue
                if "sel" in (hit.first.get_attribute("class") or ""):
                    page.keyboard.press("Escape")
                    continue
                hit.first.click()
                for _ in range(120):
                    if page.locator(".msg.bot .meta").count() > n:
                        break
                    page.wait_for_timeout(250)
                cur = page.inner_text("#cur")
                if d["name"].split(", ")[1].split(" (")[0][:20] not in cur:
                    fail(d, f"picking it in the browser shows {cur!r}")
            for word, expect in (("star", "Super Star"), ("term", "iProtect"), ("stopped", "ReAssure 1.0")):
                page.click("#browseTop")
                page.fill("#docsearch", word)
                t = page.inner_text("#doclist")
                if expect not in t:
                    fails.append(f"browser search {word!r} does not list {expect}")
                    print(f"FAIL browser search {word!r} does not list {expect}")
                page.keyboard.press("Escape")
            if errors:
                fails.append(f"console errors: {errors[:3]}")
            b.close()

    print(f"\n{len(docs)} documents checked. " + (f"{len(fails)} failures." if fails else "All checks passed."))
    for f in fails:
        print("  -", f)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()

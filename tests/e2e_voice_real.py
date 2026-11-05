"""Voice end to end against the REAL Sarvam service and the running copilot (uses a few seconds
of Sarvam credit, well under one rupee).

  ./run_demo.sh            (with SARVAM_API_KEY in .env)
  python tests/e2e_voice_real.py

For each clip, Chrome's fake microphone plays the recorded question into the page, the page
records it, the server sends it to Sarvam, the transcript lands in the box, the test presses
send as an agent would, and the answer is checked on screen.
"""
import json
import re
import sys
import time
import urllib.request
import wave
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = "http://localhost:8000/"
CLIPS = ROOT / "tests" / "voice" / "clips"

# clip, policy typed first (None = choose by voice), words the transcript must hold, check on the answer
CASES = [
    ("hinglish_select_sbi", None, ["sbi"], lambda t, cur: "SBI" in cur and "Policy document chosen" in t),
    ("hinglish_diabetes", "National Mediclaim dekhna hai", ["diabetes", "waiting"],
     lambda t, cur: "Checked against the policy text" in t and re.search(r"2 saal|two years|2 years", t, re.I)),
    ("hi_ped", "National Mediclaim dekhna hai", ["waiting", "policy"],
     lambda t, cur: "Checked against the policy text" in t and "48" in t),
    ("en_room_rent", "National Mediclaim dekhna hai", ["room rent"],
     lambda t, cur: "Checked against the policy text" in t and "1%" in t),
]


def main():
    v = json.load(urllib.request.urlopen(URL + "api/voice"))
    if not v["enabled"]:
        sys.exit("Voice is off on the running server (no SARVAM_API_KEY). Start it with ./run_demo.sh after adding the key to .env.")
    shots = ROOT / "eval" / "reports" / "voice_real_shots"
    shots.mkdir(parents=True, exist_ok=True)
    fails = 0
    with sync_playwright() as pw:
        for clip, typed, words, ok in CASES:
            wav = CLIPS / f"{clip}_48k.wav"
            with wave.open(str(wav)) as w:
                secs = w.getnframes() / w.getframerate()
            browser = pw.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                                               f"--use-file-for-fake-audio-capture={wav}%noloop"])
            page = browser.new_page(viewport={"width": 480, "height": 900})
            page.goto(URL, wait_until="networkidle")
            page.wait_for_selector("text=Kaunsa policy document")
            page.wait_for_timeout(800)

            def finals():
                return page.locator(".msg.bot .meta").count()

            def send(k=1):
                before = finals()
                page.press("#q", "Enter")
                end = time.time() + 150
                while finals() < before + k and time.time() < end:
                    page.wait_for_timeout(250)
                page.wait_for_timeout(300)
                return page.locator(".msg.bot").last.inner_text()

            t0 = time.time()
            try:
                if typed:
                    page.fill("#q", typed)
                    send()
                page.click("#mic")
                page.wait_for_selector("#mic.rec", timeout=10000)
                page.wait_for_timeout(int(secs * 1000) + 500)
                page.click("#mic")
                end = time.time() + 30
                while not page.input_value("#q") and time.time() < end:
                    if "Could not" in page.inner_text("#vnote") or "rejected" in page.inner_text("#vnote"):
                        break
                    page.wait_for_timeout(200)
                heard = page.input_value("#q")
                if not heard:
                    raise AssertionError(f"no transcript; note: {page.inner_text('#vnote')!r}")
                missing = [w for w in words if w not in heard.lower()]
                if missing:
                    raise AssertionError(f"transcript {heard!r} lacks {missing}")
                t = send()
                if not ok(t, page.inner_text("#cur")):
                    raise AssertionError(f"answer not as expected: {t[:220]!r}")
                spoken = "spoken" in page.locator(".msg.me").last.inner_text()
                if not spoken:
                    raise AssertionError("question not marked spoken")
                page.screenshot(path=str(shots / f"{clip}.png"))
                body = t.split("\n", 1)[-1].replace("\n", " ")
                print(f"OK   {clip:20} heard {heard!r}\n     answer ({time.time() - t0:.1f}s): {body[:160]!r}")
            except Exception as e:
                fails += 1
                page.screenshot(path=str(shots / f"{clip}_FAILED.png"))
                print(f"FAIL {clip:20} {e}")
            browser.close()
    print(f"\n{len(CASES) - fails}/{len(CASES)} spoken questions passed end to end. Screenshots in {shots}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()

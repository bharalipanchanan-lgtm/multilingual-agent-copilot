"""End to end test of voice input in a real browser, with no network, key or cost.

  python tests/e2e_voice.py [--headed]

Starts its own copy of the server on port 8001 (extractive backend, so it does not need a second
LLM in memory) pointed at a mock of Sarvam's endpoint (tests/voice/mock_sarvam.py). Chrome's
fake microphone plays a recorded clip, so the page records real audio exactly as it would from
a person. Checks: the recording reaches the speech service as WebM with the key, model and mode;
the transcript lands in the box and is not sent until the agent presses send; a spoken policy
choice and a spoken question both work; an edited transcript is labelled as edited; the "How this
was checked" panel names the speech service; a speech service outage shows a plain message and
typing still works; and with no key the mic is off and typing works.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CLIP = ROOT / "tests" / "voice" / "clips" / "hinglish_diabetes_48k.wav"
PORT, MOCK_PORT = 8001, 8765
URL = f"http://localhost:{PORT}/"
PY = sys.executable
TMP = Path(tempfile.mkdtemp(prefix="voice_e2e_"))
LOG, TEXT = TMP / "mock_log.json", TMP / "transcript.txt"
procs = []


def start_server(with_key: bool):
    env = {**os.environ, "COPILOT_PORT": str(PORT), "COPILOT_BACKEND": "extractive", "HF_HUB_OFFLINE": "1",
           "SARVAM_STT_URL": f"http://127.0.0.1:{MOCK_PORT}/speech-to-text"}
    env.pop("SARVAM_API_KEY", None)
    if with_key:
        env["SARVAM_API_KEY"] = "test-key"
    p = subprocess.Popen([PY, "-W", "ignore", "server.py"], cwd=ROOT, env=env,
                         stdout=open(TMP / "server.log", "a"), stderr=subprocess.STDOUT)
    procs.append(p)
    for _ in range(180):
        try:
            if json.load(urllib.request.urlopen(f"{URL}api/status", timeout=2)).get("ready"):
                return p
        except Exception:
            pass
        time.sleep(1)
    raise SystemExit("test server did not start; see " + str(TMP / "server.log"))


def start_mock():
    env = {**os.environ, "MOCK_TRANSCRIPT_FILE": str(TEXT)}
    p = subprocess.Popen([PY, str(ROOT / "tests" / "voice" / "mock_sarvam.py"), str(MOCK_PORT), str(LOG)], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(p)
    time.sleep(2)
    return p


def stop(p):
    p.send_signal(signal.SIGTERM)
    try:
        p.wait(10)
    except subprocess.TimeoutExpired:
        p.kill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    shots = ROOT / "eval" / "reports" / "voice_shots"
    shots.mkdir(parents=True, exist_ok=True)
    n = [0]
    mock = start_mock()
    server = start_server(with_key=True)
    try:
        with sync_playwright() as pw:
            # Playwright's own Chromium: installed Chrome on macOS waits on the OS microphone
            # permission even with a fake device (python -m playwright install chromium)
            browser = pw.chromium.launch(headless=not a.headed, args=[
                "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                f"--use-file-for-fake-audio-capture={CLIP}"])
            ctx = browser.new_context(viewport={"width": 480, "height": 900})
            ctx.grant_permissions(["microphone"], origin=URL.rstrip("/"))
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            def step(name, fn):
                t0 = time.time()
                try:
                    detail = fn() or ""
                    n[0] += 1
                    page.screenshot(path=str(shots / f"{n[0]:02d}.png"))
                    print(f"OK   {name} ({time.time() - t0:.1f}s) {detail}")
                except Exception as e:
                    page.screenshot(path=str(shots / "FAILED.png"))
                    print(f"FAIL {name}: {e}\n  voice note: {page.inner_text('#vnote')!r}")
                    raise SystemExit(1)

            def check(c, m):
                if not c:
                    raise AssertionError(m)

            def finals():
                return page.locator(".msg.bot .meta").count()

            def record(text, seconds=3.0):
                TEXT.write_text(text, encoding="utf-8")
                if LOG.exists():
                    LOG.unlink()
                page.click("#mic")
                page.wait_for_selector("#mic.rec", timeout=5000)
                page.wait_for_timeout(int(seconds * 1000))
                page.click("#mic")

            def wait_box(text, timeout=20):
                end = time.time() + timeout
                while page.input_value("#q") != text:
                    if time.time() > end:
                        raise AssertionError(f"box shows {page.input_value('#q')!r}, expected {text!r}")
                    page.wait_for_timeout(200)

            def send_and_wait(k=1, timeout=120):
                before = finals()
                page.press("#q", "Enter")
                end = time.time() + timeout
                while finals() < before + k:
                    if time.time() > end:
                        raise AssertionError("no answer")
                    page.wait_for_timeout(250)
                page.wait_for_timeout(300)
                return page.locator(".msg.bot").last.inner_text()

            page.goto(URL, wait_until="networkidle")
            page.wait_for_selector("text=Kaunsa policy document")
            page.wait_for_timeout(800)

            step("Mic is on when the server has a key",
                 lambda: check("off" not in page.get_attribute("#mic", "class"), "mic shows as off"))

            def spoken_choice():
                record("mujhe SBI wali policy dekhni hai")
                wait_box("mujhe SBI wali policy dekhni hai")
                check(finals() == 0, "transcript was sent without the agent pressing send")
                check("Check it" in page.inner_text("#vnote"), "no 'check before sending' note")
                rec = json.loads(LOG.read_text())
                check(rec["key"] == "test-key", "key not sent in api-subscription-key")
                check(rec["model"] == "saaras:v3" and rec["mode"] == "translit", f"model/mode {rec['model']}/{rec['mode']}")
                check(rec["language_code"] == "unknown", "language not left to auto detect")
                check(rec["bytes"] > 3000 and rec["magic"] == "1a45dfa3", f"audio is not a WebM recording: {rec}")
                t = send_and_wait()
                check("SBI" in page.inner_text("#cur") and "Policy document chosen" in t, t[:120])
                check("spoken" in page.locator(".msg.me").last.inner_text(), "user bubble not marked spoken")
                return f"{rec['bytes']} bytes {rec['content_type']}"
            step("Spoken policy choice: WebM audio, key, model and mode reach the service; agent sends", spoken_choice)

            def spoken_question():
                record("room rent kitna hai")
                wait_box("room rent kitna hai")
                t = send_and_wait()
                check("Policy document chosen" not in t and ("policy" in t.lower()), t[:120])
                page.locator(".msg.bot").last.locator("details.how summary").click()
                how = page.locator(".msg.bot").last.locator("details.how").inner_text()
                check("Question was spoken" in how and "sarvam" in how and "sent as heard" in how, how)
            step("Spoken question is answered and the panel names the speech service", spoken_question)

            def edited():
                record("diabetes ka waiting period")
                wait_box("diabetes ka waiting period")
                page.fill("#q", "diabetes ka waiting period kitna hai?")
                send_and_wait()
                check("spoken, edited" in page.locator(".msg.me").last.inner_text(), "edit not shown")
            step("Edited transcript is labelled 'spoken, edited'", edited)

            def typed_after_voice():
                page.fill("#q", "Is maternity covered?")
                send_and_wait()
                check("spoken" not in page.locator(".msg.me").last.inner_text(), "typed question marked spoken")
            step("A typed question after voice is not marked spoken", typed_after_voice)

            def outage():
                stop(mock)
                record("anything")
                end = time.time() + 30
                while "Could not reach" not in page.inner_text("#vnote"):
                    if time.time() > end:
                        raise AssertionError("no outage message")
                    page.wait_for_timeout(200)
                page.fill("#q", "Is there any co-payment?")
                t = send_and_wait()
                check(t, "typing failed during the outage")
            step("Speech service down: plain message, typing still works", outage)

            check(not errors, f"page errors: {errors}")
            browser.close()

        stop(server)
        start_server(with_key=False)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not a.headed)
            page = browser.new_page(viewport={"width": 480, "height": 900})
            page.goto(URL, wait_until="networkidle")
            page.wait_for_selector("text=Kaunsa policy document")
            page.wait_for_timeout(800)

            def no_key():
                if "off" not in page.get_attribute("#mic", "class"):
                    raise AssertionError("mic not marked off without a key")
                page.click("#mic")
                if "SARVAM_API_KEY" not in page.inner_text("#vnote"):
                    raise AssertionError(f"no reason shown: {page.inner_text('#vnote')!r}")
                page.fill("#q", "SBI dekhna hai")
                page.press("#q", "Enter")
                page.wait_for_selector("text=Policy document chosen", timeout=30000)
            t0 = time.time()
            no_key()
            page.screenshot(path=str(shots / "no_key.png"))
            print(f"OK   No key: mic is off with the reason, typing works ({time.time() - t0:.1f}s)")
            browser.close()
        print(f"\nAll voice steps passed. Screenshots in {shots}")
    finally:
        for p in procs:
            if p.poll() is None:
                stop(p)


if __name__ == "__main__":
    main()

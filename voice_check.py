"""Check voice input against the real Sarvam service with the recorded test clips.

  SARVAM_API_KEY=... python voice_check.py          (or put the key in .env)

Uses a few seconds of audio in total (well under ₹1 at ₹30 per hour). Each clip in
tests/voice/clips is transcribed, and the transcript must carry what the copilot needs:
the key words of the question, and for the policy choice clip, the right policy.
Exit code 0 if every clip passes, 1 if any fails, 2 if no key is set.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
env = ROOT / ".env"
if env.exists() and not os.environ.get("SARVAM_API_KEY"):
    for line in env.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import stt  # noqa: E402
from answer import detect_lang  # noqa: E402
from policy_select import mentioned, selection_only  # noqa: E402

CLIPS = [
    # file, words that must appear (any one of each group, case-insensitive), expected policy if any
    ("en_room_rent.wav", [["room rent", "room-rent"], ["limit"]], None),
    ("hinglish_diabetes.wav", [["diabetes", "diabetis", "डायबिटीज"], ["waiting", "वेटिंग"]], None),
    ("hi_ped.wav", [["waiting", "वेटिंग"], ["policy", "polisi", "पॉलिसी"]], None),
    ("hinglish_select_sbi.wav", [["sbi", "s b i", "एसबीआई"]], "sbi_retail_health"),
]


def main():
    if not stt.status()["enabled"]:
        print("No SARVAM_API_KEY set. Get one at https://dashboard.sarvam.ai, then run:\n"
              "  SARVAM_API_KEY=... python voice_check.py   (or add it to .env)")
        sys.exit(2)
    fails = 0
    for name, groups, policy in CLIPS:
        path = ROOT / "tests" / "voice" / "clips" / name
        try:
            out = stt.transcribe(path.read_bytes(), name, "audio/wav")
        except stt.STTError as e:
            print(f"FAIL {name}: {e}")
            fails += 1
            continue
        text = out["text"]
        missing = [g for g in groups if not any(w in text.lower() for w in g)]
        problems = [f"missing {'/'.join(g)}" for g in missing]
        if policy:
            found, rest = mentioned(text)
            if found != [policy] or not selection_only(rest):
                problems.append(f"policy choice gave {found} (selection only: {selection_only(rest)})")
        ok = not problems
        fails += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {name:26} {out['ms']:5} ms  lang {out['language_code']}  "
              f"answer language {detect_lang(text):8}  {text!r}" + ("" if ok else f"  <- {'; '.join(problems)}"))
    print(f"\n{len(CLIPS) - fails}/{len(CLIPS)} clips usable ({stt.status()['model']}, mode {stt.status()['mode']})")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()

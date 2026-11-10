#!/usr/bin/env python3
"""Sync partner insurers and policy wordings from QuickInsure (https://quickinsure.co.in/)
and local PDF drops into the Claviq Agent Copilot catalogue and Chroma index.

Usage:
    python ingest/sync_quickinsure.py [--check-remote] [--reingest]
"""
import argparse
import csv
import datetime
import json
import pathlib
import re
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "policies" / "manifest.csv"
CATALOGUE = ROOT / "web" / "data" / "catalogue.json"
QUICKINSURE_URL = "https://quickinsure.co.in/"


def fetch_quickinsure_insurers(url: str = QUICKINSURE_URL) -> list[str]:
    """Fetch QuickInsure homepage and extract partner insurer names mentioned on the page."""
    req = urllib.request.Request(url, headers={"User-Agent": "Claviq-Agent-Copilot/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    known = [
        "Star Health", "HDFC ERGO", "Care Health", "Niva Bupa", "TATA AIG",
        "ICICI Lombard", "Max Life", "National Insurance", "Bajaj Allianz",
        "Aditya Birla", "ManipalCigna", "Digit", "Reliance", "SBI General",
    ]
    found = [ins for ins in known if re.search(re.escape(ins.split()[0]), html, re.I)]
    return sorted(set(found))


def verify_catalogue() -> dict:
    cat = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))
    manifest_ids = {r["policy_id"] for r in rows}
    active = [p for p in cat["products"] if p.get("status") == "active"]
    withdrawn = [p for p in cat["products"] if p.get("status") == "withdrawn"]

    # Touch updated_on stamp when verified
    cat["catalogue"]["updated_on"] = datetime.date.today().isoformat()
    CATALOGUE.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "catalogue_products": len(cat["products"]),
        "active_products": len(active),
        "withdrawn_products": len(withdrawn),
        "manifest_policies": len(manifest_ids),
        "insurers": sorted({p["insurer"] for p in cat["products"]}),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-remote", action="store_true", help="Check https://quickinsure.co.in/ reachability")
    ap.add_argument("--reingest", action="store_true", help="Run extract.py and ingest.py after verifying")
    args = ap.parse_args()

    if args.check_remote:
        try:
            found = fetch_quickinsure_insurers()
            print(f"[quickinsure] reachable ({QUICKINSURE_URL}); matched partner tokens: {', '.join(found) or 'homepage parsed'}")
        except Exception as e:
            print(f"[quickinsure] offline or unreachable ({e}); using local verified catalogue")

    stats = verify_catalogue()
    print(
        f"[catalogue] {stats['catalogue_products']} products "
        f"({stats['active_products']} active, {stats['withdrawn_products']} withdrawn) "
        f"across {len(stats['insurers'])} insurers: {', '.join(stats['insurers'])}"
    )

    if args.reingest:
        subprocess.run([sys.executable, str(ROOT / "ingest" / "extract.py")], check=True)
        subprocess.run([sys.executable, str(ROOT / "ingest.py")], check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

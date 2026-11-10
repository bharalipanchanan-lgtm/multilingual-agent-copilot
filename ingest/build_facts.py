#!/usr/bin/env python3
"""Build verified catalogue facts for the QuickInsure wordings.

    python ingest/build_facts.py            # report only
    python ingest/build_facts.py --write    # merge into web/data/catalogue.json + manifest.csv

Every stated value carries a verbatim quote taken from the extracted page
text (data/pages/*.json), the PDF page, the printed page and the clause it
sits under. When no clear sentence is found the fact is recorded as not
stated, with a reason — nothing is inferred from another product.
test/catalogue.test.mjs re-checks every quote against its page.
"""
import argparse
import collections
import csv
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGES = ROOT / "data" / "pages"
POLICIES = ROOT / "data" / "policies"
QI_MANIFEST = POLICIES / "quickinsure_manifest.csv"
MANIFEST = POLICIES / "manifest.csv"
CATALOGUE = ROOT / "web" / "data" / "catalogue.json"

INSURER = {
    "Tata AIG": "TATA AIG",
    "Generali Central (formerly Future Generali)": "Generali Central",
    "Zuno (formerly Edelweiss)": "Zuno",
    "Zurich Kotak (formerly Kotak)": "Zurich Kotak",
}
NAME = {
    "08": ("Optima Secure", "V06 · 2024-25 wording"),
    "29": ("Optima Secure", "V08 · 2025-26 wording"),
    "35": ("MediCare", None),
    "26": ("Health Insurance", None),
}
UIN_RE = re.compile(r"\b[A-Z]{3,5}HLIP\d{5}V\d{6}\b")
WORDNUM = {"twelve": 12, "twenty four": 24, "twenty-four": 24, "thirty six": 36, "thirty-six": 36,
           "forty eight": 48, "forty-eight": 48, "one": 1, "two": 2, "three": 3, "four": 4}


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def norm(s: str) -> str:
    """Same comparison the provenance test uses: letters and digits only."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s).replace("‘", "'").replace("’", "'")
    return re.sub(r"[^a-z0-9]", "", s.lower())


# ── page numbers ───────────────────────────────────────────────────────

FOOT_RE = re.compile(r"^(?:page\s*\|?\s*)?(\d{1,3})(?:\s*(?:of|/)\s*\d{1,3})?$", re.I)


def page_offset(pages: list[dict]) -> int | None:
    """printed = pdf + offset, read from page footers/headers. None if no clear pattern."""
    diffs = collections.Counter()
    for p in pages:
        lines = [x.strip() for x in p["text"].splitlines() if x.strip()]
        seen = set()
        for x in lines[:6] + lines[-6:]:
            m = FOOT_RE.match(x)
            if m:
                d = int(m.group(1)) - p["page"]
                if d not in seen and -6 <= d <= 3:
                    diffs[d] += 1
                    seen.add(d)
    if not diffs:
        return None
    off, n = diffs.most_common(1)[0]
    return off if n >= 0.4 * len(pages) else None


# ── clause label for a quote ───────────────────────────────────────────

CODE_RE = re.compile(r"Code\s*[-–—]?\s*Ex[ce][l1I]\.?\s*0?\s*(\d{1,2})", re.I)
CLAUSE_RE = re.compile(
    r"(?:^|\s)((?:[A-Z]\.){0,1}\d{1,2}(?:\.\d{1,2}){0,3}\.?\)?|[ivx]{1,4}[.)]|\([ivx]{1,4}\)|[A-Z]\.\d{1,2}(?:\.\d{1,2})*)"
    r"\s+([A-Z][A-Za-z/&’'\- ]{2,48})")


HEAD_BAD = re.compile(r"^(?:Years?|Months?|Days?|Lakhs?|Lacs?|Crores?|Policy Wording|Page)\b|Insurance\b|Health Insurance|"
                      r"\bUIN\b|Company|Limited|^\d+ (?:Years?|Lakhs?|Lacs?)|GLUCOMETER|STRIPS", re.I)


def clause_label(text: str, pos: int) -> str | None:
    win = text[max(0, pos - 220):pos + 60]
    code = None
    for m in CODE_RE.finditer(win):
        code = f"Code-Excl{int(m.group(1)):02d}"
    num = None
    for m in CLAUSE_RE.finditer(win):
        head = re.split(r"\s*(?:Code\b|\(|:|–|—| - )", m.group(2))[0].strip(" -")
        if HEAD_BAD.search(head) or HEAD_BAD.search(m.group(1) + " " + head):
            continue
        if len(head) >= 3:
            num = f"{m.group(1).rstrip('.)')} {head}"
    if num and code:
        return f"Clause {num} ({code})"
    if num:
        return f"Clause {num}"
    return code


# ── sentence windows ───────────────────────────────────────────────────

FOOTER_RE = re.compile(r"(?:\s[A-Z][\w&]*){1,5}\s-\s*Policy Wording\b|\((?i:Effective from) [\d./]+\)|\bU[Il1]N\s*[-:]\s*[A-Z]{5}|\b(?i:Page) \d+ (?i:of) \d+\b")


def window(text: str, start: int, end: int, before: int = 40, max_len: int = 320) -> tuple[str, int]:
    """A quote around [start, end): back to the sentence start (bounded), forward to its end."""
    floor = max(0, start - before)
    cut = max(text.rfind(". ", floor, start), text.rfind("; ", floor, start), text.rfind(" • ", floor, start))
    if cut >= 0:
        a = cut + 2
    else:
        a = floor
        if a > 0:
            sp = text.find(" ", a)
            a = sp + 1 if 0 <= sp < start else a
    stop = len(text)
    for mark in (". ", "; ", " • "):
        k = text.find(mark, max(end, a + 30))
        if k >= 0:
            stop = min(stop, k + 1)
    b = min(stop, a + max_len)
    if b < stop:
        b = text.rfind(" ", a, b)
    q = text[a:b]
    foot = FOOTER_RE.search(q, 25)
    if foot:
        q = q[:foot.start()]
    return q.strip(" ;,•"), a


def months_in(s: str) -> list[int]:
    out = []
    for m in re.finditer(r"(\d{1,2})\s*\)?\s*(?:\(\s*\w+\s*\))?\s*(months?|years?)", s, re.I):
        n = int(m.group(1))
        out.append(n * 12 if m.group(2).lower().startswith("year") else n)
    for w, n in WORDNUM.items():
        for m in re.finditer(rf"\b{w}\b\s*\(?\d*\)?\s*(months?|years?)", s, re.I):
            out.append(n * 12 if m.group(1).lower().startswith("year") else n)
    return out


def fact(pages, pg, text, q, pos, value, unit, offset, note=None, **extra):
    page = next(p for p in pages if p["page"] == pg)
    assert norm(q) in norm(page["text"]), f"quote drift p{pg}: {q[:60]}"
    return {"value": value, "unit": unit, "section": clause_label(text, pos), "pdf_page": pg,
            "printed_page": pg + offset if offset is not None else None, "quote": q, "note": note,
            "stated": True, **extra}


def missing(note: str) -> dict:
    return {"value": None, "unit": None, "pdf_page": None, "printed_page": None, "quote": None,
            "note": note, "stated": False}


# ── facts ──────────────────────────────────────────────────────────────

CARVE_RE = re.compile(r"(?:Any condition or illness[^.]{0,120}?)?(?:shall not be considered as part of this waiting period|"
                      r"(?:waiting period|exclusion) shall not (?:be )?appl(?:y|icable) (?:to|for))", re.I)
INITIAL_RE = re.compile(r"initial waiting period of 30 days|first 30 days", re.I)


def condition_carveout(pages, offset):
    """Plans built for diabetics/hypertensives that lift the PED wait for those conditions."""
    initial = any(INITIAL_RE.search(squash(p["text"])) for p in pages)
    for p in pages:
        t = squash(p["text"])
        for m in CARVE_RE.finditer(t):
            tail = t[m.end():m.end() + 220]
            if not re.search(r"diabetes", tail, re.I) or re.search(r"specific to these|are mentioned in|own waiting", tail, re.I):
                continue
            conds = ["diabetes"] + (["high BP"] if re.search(r"hypertension", tail, re.I) else [])
            stop = re.search(r"\b\d+\.\s+[A-Z][a-z]+ Exclusions|\b2\.\s+Standard", tail)
            end = m.end() + (stop.start() if stop else len(tail))
            q = t[m.start():end].strip().rstrip(".") + ""
            q = q if len(q) <= 360 else q[:360].rsplit(" ", 1)[0]
            months = 1 if initial else 0
            value = ("Covered after the 30-day initial wait — no pre-existing wait for " if initial
                     else "Covered from the start — no pre-existing wait for ") + " and ".join(conds)
            return fact(pages, p["page"], t, q, m.start(), value, "text", offset,
                        "Other pre-existing illnesses still follow the normal PED wait.",
                        months=months, conditions=conds, source_kind="prose")
    return None

PED_RE = re.compile(r"(?:Expenses related to the )?treatment of an?\s+pre-?\s?existing\s+(?:Disease|Condition)s?\b.{0,60}?"
                    r"(?:excluded|not be covered|shall not be (?:payable|covered))\s+(?:as\s+\w+\s+the\s+Plan[^.]{0,60}?)?(?:until|till|for)\s+(?:the\s+)?(?:expiry\s+of\s+)?",
                    re.I)
OPTIONAL_CTX = re.compile(r"buy[- ]?back|shall read as follows|if opted|optional cover|reduction in (?:pre-?existing|PED)|opt(?:ed)? for", re.I)


PED_ALT_RE = re.compile(r"pre-?\s?existing disease/?s?\b.{0,120}?(?:shall not be covered|excluded)\s+until\s+", re.I)
SEG_END = re.compile(r"In case of enhancement|enhancement of (?:the )?sum insured|after the date of inception|"
                     r"\b[b-c][.)]\s+(?:In case|If|The)|Coverage under the policy after", re.I)


PED_REV_RE = re.compile(r"waiting period of (\d{2}) (?:consecutive )?months[^.]{0,80}?in respect of pre-?\s?existing diseases?", re.I)
PED_SCHED_RE = re.compile(r"pre-?\s?existing disease[^.]{0,200}?(?:as specified in the Policy Schedule|as opted by you|mentioned in (?:the )?policy schedule)", re.I)


def ped(pages, offset):
    found = []
    for p in pages:
        t = squash(p["text"])
        for m in list(PED_RE.finditer(t)) or list(PED_ALT_RE.finditer(t)):
            seg = t[m.end():m.end() + 360]
            cut = SEG_END.search(seg)
            seg = seg[:cut.start()] if cut else seg[:160]
            ms = [x for x in months_in(seg) if 6 <= x <= 60]
            if not ms:
                continue
            q, a = window(t, m.start(), m.end() + len(seg), before=10, max_len=420)
            optional = bool(OPTIONAL_CTX.search(t[max(0, m.start() - 400):m.start()]))
            found.append((optional, p["page"], t, q, a, ms))
    if not found:
        for p in pages:
            t = squash(p["text"])
            m = PED_REV_RE.search(t)
            if m:
                q, a = window(t, m.start(), m.end(), before=10, max_len=320)
                return fact(pages, p["page"], t, q, a, int(m.group(1)), "months", offset)
        if any(PED_SCHED_RE.search(squash(p["text"])) for p in pages):
            return missing("The PED wait is chosen with the plan and printed in the Policy Schedule — this wording gives no fixed number.")
        return missing("No pre-existing disease waiting clause found in this wording.")
    primary = [f for f in found if not f[0]] or found
    _, pg, t, q, a, ms = primary[0]
    others = sorted({m for f in found for m in f[5]} - set(ms))
    note = None
    if len(set(ms)) > 1:
        note = f"Depends on the plan or sum insured chosen: {', '.join(str(x) for x in sorted(set(ms)))} months. The longest is used for ranking."
    elif others:
        note = f"Another option in this wording reads {', '.join(str(x) for x in others)} months — check the plan in the schedule."
    return fact(pages, pg, t, q, a, max(ms), "months", offset, note)


SPEC_RE = re.compile(r"treatment of (?:the\s+)?(?:following\s+)?listed\s+conditions.{0,120}?excluded\s+until\s+the\s+expiry\s+of\s+", re.I)


def specified(pages, offset):
    for p in pages:
        t = squash(p["text"])
        m = SPEC_RE.search(t)
        if m:
            seg = t[m.end():m.end() + 80].split("continuous coverage")[0]
            ms = months_in(seg)
            if ms:
                q, a = window(t, m.start(), m.end() + len(seg) + 25, before=10, max_len=300)
                return fact(pages, p["page"], t, q, a, max(ms), "months", offset)
    return missing("No specified-disease waiting clause found in this wording.")


AGE_PATTERNS = [
    re.compile(r"no (?:limit on |upper |bar on )?maximum entry age|no maximum entry age(?: limit)?|maximum entry age[^.]{0,40}?no limit|no upper age limit", re.I),
    re.compile(r"maximum (?:entry )?age(?: of entry)?(?: in the policy| under the policy)?(?: is| will be|:|-|–)?\s*(\d{2})\s*years", re.I),
    re.compile(r"maximum entry age\s*:?\s*(\d{2})\s*years", re.I),
]


def entry_age(pages, offset):
    for p in pages:
        t = squash(p["text"])
        for i, rx in enumerate(AGE_PATTERNS):
            m = rx.search(t)
            if not m:
                continue
            q, a = window(t, m.start(), m.end(), before=60, max_len=260)
            if i == 0:
                return fact(pages, p["page"], t, q, a, "No upper limit", "text", offset,
                            "The wording sets no maximum entry age for adults.")
            n = int(m.group(1))
            if 45 <= n <= 99:
                extra = t[m.end():m.end() + 160]
                note = "Some variants differ — see the quote." if re.search(r"no maximum|variant|platinum", extra + q, re.I) else None
                return fact(pages, p["page"], t, q, a, n, "years", offset, note)
    return missing("Not stated in this wording. See the prospectus.")


ROOM_GOOD = [
    (re.compile(r"single (?:standard |private )?(?:a\.?c\.?|air[- ]conditioned)?\s*(?:private )?room", re.I), 4),
    (re.compile(r"at actuals?", re.I), 3),
    (re.compile(r"any room(?: category)?", re.I), 4),
    (re.compile(r"no (?:room rent )?(?:capping|cap|sub-?limit|restriction|limit)", re.I), 3),
    (re.compile(r"\d+(?:\.\d+)?\s*%\s*of (?:the )?(?:base )?sum insured", re.I), 3),
    (re.compile(r"per day", re.I), 2),
    (re.compile(r"(?:Rs\.?|₹|INR)\s*[\d,]{3,}", re.I), 1),
    (re.compile(r"room category", re.I), 1),
    (re.compile(r"policy schedule", re.I), 1),
]
ROOM_BAD = re.compile(r"means the amount|proportionate|formula|Associated Medical Expenses shall include|"
                      r"difference in room rent|bears to the actual|rate per day of room|in proportion to the room|"
                      r"discount|wellness|shared accommodation|daily cash|hospital cash|modification|upgrade|"
                      r"\boption(?:al)?\b|\bopt(?:ed|s)?\b|enhancement|co-?payment|Optima Select|\bNote\b|\d{8,}|"
                      r"^Page \d+|Page \d+ of \d+|(\b\w+\b)(?: \1\b){2,}", re.I)
NO_CAP_RE = re.compile(r"at actuals?|any room(?: category)?|without any room rent[^.]{0,30}capping|no (?:room rent )?(?:capping|cap|sub-?limit|restriction)|"
                       r"single (?:standard |private )?(?:a\.?c\.?|air[- ]conditioned)?\s*(?:private )?room", re.I)
PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*of (?:the )?(?:base )?sum insured", re.I)
DAY_RE = re.compile(r"(?:Rs\.?|₹|INR)\s*(\d[\d,]{3,})\s*(?:/-)?\s*(?:per day|/day|a day)", re.I)


def room_class(q: str) -> tuple[str, int | None]:
    """no_cap | per_day | pct_si | depends | schedule — what the ranking can rely on."""
    kinds = set()
    if NO_CAP_RE.search(q):
        kinds.add("no_cap")
    day = DAY_RE.search(q)
    if day:
        kinds.add("per_day")
    if PCT_RE.search(q):
        kinds.add("pct_si")
    sched = re.search(r"policy schedule|plan chosen|as specified|unless otherwise|subject to (?:the )?(?:below |following )?limits", q, re.I)
    if len(re.findall(r"(?:Rs\.?|₹|INR)\s*\d", q)) >= 3 or re.search(r"cumulative bonus\)|sum insured (?:of|above|below|upto|up to) (?:Rs|₹|INR)", q, re.I):
        kinds.add("si_band")
    if len(kinds) > 1 or (sched and kinds - {"no_cap"}):
        return "depends", None
    if sched and "no_cap" in kinds and not re.search(r"at actuals?[’'‘]?\s*unless otherwise", q, re.I):
        return "depends", None
    if not kinds:
        return "schedule", None
    k = kinds.pop()
    return k, int(day.group(1).replace(",", "")) if k == "per_day" else None


def room_rent(pages, offset):
    best = None
    for p in pages:
        t = squash(p["text"])
        for m in re.finditer(r"room rent|room,? boarding|room category|eligible room", t, re.I):
            q, a = window(t, m.start(), m.end(), before=140, max_len=300)
            if ROOM_BAD.search(q) or len(q) < 40:
                continue
            score = sum(w for rx, w in ROOM_GOOD if rx.search(q))
            if score < 3:
                continue
            if best is None or score > best[0]:
                best = (score, p["page"], t, q, a)
    if not best:
        return missing("Room rent is set in the Policy Schedule; the wording gives no per-day figure.")
    _, pg, t, q, a = best
    kind, cap = room_class(q)
    value = q if len(q) <= 240 else q[:240].rsplit(" ", 1)[0] + " …"
    note = {
        "depends": "The room limit depends on the plan or sum insured in the Policy Schedule.",
        "schedule": "The room category is set in the Policy Schedule.",
        "pct_si": "A share of the sum insured per day — the rupee figure depends on the sum insured chosen.",
        "si_band": "The room limit changes with the sum insured chosen.",
    }.get(kind)
    return fact(pages, pg, t, q, a, value, "text", offset, note, max_per_day=cap, room_class=kind, source_kind="prose")


def _best_sentence(pages, rx, score_fn, bad=None, min_score=1):
    best = None
    for p in pages:
        t = squash(p["text"])
        for m in rx.finditer(t):
            q, a = window(t, m.start(), m.end(), before=120, max_len=300)
            if bad and bad.search(q):
                continue
            s = score_fn(q)
            if s >= min_score and (best is None or s > best[0]):
                best = (s, p["page"], t, q, a)
    return best


DEF_BAD = re.compile(r"\bmeans\b|is defined|shall mean|definition", re.I)
AMOUNT = re.compile(r"(?:Rs\.?|₹|INR)\s*\d[\d,.]*(?:\s*(?:lakh|lac|crore)s?)?|\d+(?:\.\d+)?\s*%(?:\s*of (?:the )?(?:base )?sum insured)?", re.I)


def ayush(pages, offset):
    best = _best_sentence(
        pages, re.compile(r"\bAYUSH\b", re.I),
        lambda q: (3 if re.search(r"in-?patient|hospitali[sz]ation", q, re.I) else 0)
        + (3 if re.search(r"up\s?to (?:the )?(?:basic |base )?sum insured", q, re.I) else 0)
        + (2 if AMOUNT.search(q) else 0) + (1 if re.search(r"covered|payable|indemnify|pay", q, re.I) else 0),
        bad=re.compile(DEF_BAD.pattern + r"|AYUSH Hospital is|AYUSH Day Care Centre|qualified AYUSH|registered", re.I), min_score=4)
    if not best:
        return missing("AYUSH cover is not written in this wording.")
    _, pg, t, q, a = best
    if re.search(r"up\s?to (?:the )?(?:basic |base )?sum insured", q, re.I):
        plain = "AYUSH in-patient treatment is covered up to the sum insured."
    elif (m := AMOUNT.search(q)):
        plain = f"AYUSH in-patient treatment is covered, capped at {m.group(0).strip()} as written."
    else:
        plain = "AYUSH in-patient treatment is covered, subject to the conditions in this clause."
    return fact(pages, pg, t, q, a, plain, "text", offset)


def cataract(pages, offset):
    best = _best_sentence(
        pages, re.compile(r"\bcataract\b", re.I),
        lambda q: (4 if AMOUNT.search(q) else 0) + (2 if re.search(r"per eye|each eye|limit|sub-?limit|up to", q, re.I) else 0),
        bad=DEF_BAD, min_score=4)
    if best:
        _, pg, t, q, a = best
        eye = re.search(r"(?:Rs\.?|₹|INR)?\s*(\d[\d,]{3,})\s*/?-?\s*(?:per|each) eye", q, re.I)
        amt = f"₹{eye.group(1)}" if eye else AMOUNT.search(q).group(0).strip()
        per_eye = " per eye" if re.search(r"per eye|each eye", q, re.I) else ""
        if eye and len(re.findall(r"(?:per|each) eye", q, re.I)) > 1:
            per_eye += " (the limit rises with the sum insured — see the table)"
        return fact(pages, pg, t, q, a, f"Cataract has its own limit: {amt}{per_eye}, as written in this clause.", "text", offset)
    for p in pages:
        t = squash(p["text"])
        m = re.search(r"\bcataract\b", t, re.I)
        if m and re.search(r"listed conditions|specified disease|named ailment|waiting", t[max(0, m.start() - 2500):m.start()], re.I):
            q, a = window(t, m.start(), m.end(), before=60, max_len=200)
            return fact(pages, p["page"], t, q, a,
                        "Cataract is in the listed-illness waiting list; no separate money limit is written for it.", "text", offset)
    return missing("Cataract is not written in this wording.")


def robotic(pages, offset):
    best = _best_sentence(
        pages, re.compile(r"robotic", re.I),
        lambda q: 2 + (3 if AMOUNT.search(q) else 0) + (2 if re.search(r"sum insured|limit|covered|payable", q, re.I) else 0),
        bad=DEF_BAD, min_score=2)
    if not best:
        return missing("Robotic surgery is not written in this wording.")
    _, pg, t, q, a = best
    if re.search(r"not covered|excluded|shall not", q, re.I):
        plain = "Robotic surgery is not covered as per this clause."
    elif (m := AMOUNT.search(q)):
        plain = f"Robotic surgery is covered with a limit of {m.group(0).strip()} as written."
    elif re.search(r"sum insured", q, re.I):
        plain = "Robotic surgery is covered up to the sum insured as written."
    else:
        plain = "Robotic surgery is named under modern treatments in this wording; read the clause for its limit."
    return fact(pages, pg, t, q, a, plain, "text", offset, source_kind="prose")


def build_one(row: dict) -> dict | None:
    stem = pathlib.Path(row["file"]).stem
    pf = PAGES / f"{stem}.json"
    if not row["file"] or not pf.exists() or not (POLICIES / row["file"]).exists():
        return None
    doc = json.loads(pf.read_text(encoding="utf-8"))
    pages = doc["pages"]
    offset = page_offset(pages)

    counts = collections.Counter(UIN_RE.findall(" ".join(p["text"] for p in pages)))
    man = (UIN_RE.findall(row.get("uin") or "") or [None])[0]
    uin = man if man and counts.get(man) else (counts.most_common(1)[0][0] if counts else man)

    num = row["#"].zfill(2)
    insurer = INSURER.get(row["insurer"], row["insurer"])
    name, variant = NAME.get(num, (None, None))
    if not name:
        name = re.sub(r"\s+(?:Insurance\s+)?(?:Plan|Policy)\s*$", "", row["policy"]).strip()
        name = re.sub(r"\s*\(base\)$", "", name)
    pid = "qi_" + re.sub(r"[^a-z0-9]+", "_", stem[3:]).strip("_")
    slug = re.sub(r"[^a-z0-9]+", "-", f"{insurer} {name} {variant or ''}".lower()).strip("-")

    facts = {
        "ped_wait_months": ped(pages, offset),
        "specified_disease_wait_months": specified(pages, offset),
        "room_rent": room_rent(pages, offset),
        "entry_age_max": entry_age(pages, offset),
        "ayush": ayush(pages, offset),
        "cataract": cataract(pages, offset),
        "robotic_surgery": robotic(pages, offset),
        "premium_inr": missing("Not stated in policy wordings. See the rate card."),
    }
    if (d := condition_carveout(pages, offset)):
        facts["diabetes_wait"] = d
    return {
        "doc": {"source": row["file"], "pdf_pages": doc["page_count"], "page_offset": offset, "uin": uin},
        "manifest": {"file": row["file"], "policy_id": pid, "insurer": insurer, "product": f"{name}{f' ({variant})' if variant else ''}",
                     "skip_pages": "", "page_offset": str(-offset) if offset is not None else "0", "strip_regex": ""},
        "product": {"id": slug, "policy_id": pid, "insurer": insurer, "name": name, "variant": variant,
                    "status": "active", "uin": uin, "source_url": row.get("url") or None, "facts": facts},
    }


def differentiator(p: dict) -> str:
    f = p["facts"]
    bits = []
    if f.get("diabetes_wait", {}).get("stated"):
        bits.append("no PED wait for " + " / ".join(c.replace("high BP", "BP") for c in f["diabetes_wait"]["conditions"]))
    if f["ped_wait_months"]["stated"]:
        bits.append(f"PED {f['ped_wait_months']['value']} months")
    r = f["room_rent"]
    if r["stated"]:
        v, kind = r["value"], r.get("room_class")
        if kind == "per_day":
            bits.append(f"room up to ₹{r['max_per_day']:,}/day")
        elif kind == "no_cap":
            bits.append("room at actuals" if re.search(r"at actuals?", v, re.I) else
                        "any room category" if re.search(r"any room", v, re.I) else "single private room")
        elif kind == "pct_si" and (m := PCT_RE.search(v)):
            bits.append(f"room {m.group(1)}% of SI/day")
        else:
            bits.append("room depends on plan")
    a = f["entry_age_max"]
    if a["stated"]:
        bits.append("no max entry age" if isinstance(a["value"], str) else f"entry up to {a['value']}")
    return "; ".join(bits) or "Policy wording on file"


SUPERSEDE = {
    # older Optima Secure wordings -> the 2025-26 revision (UIN version 08)
    "hdfc-optima-secure": "hdfc-ergo-optima-secure-v08-2025-26-wording",
    "hdfc-optima-super-secure": "hdfc-ergo-optima-secure-v08-2025-26-wording",
    "hdfc-optima-suraksha": "hdfc-ergo-optima-secure-v08-2025-26-wording",
    "hdfc-ergo-optima-secure-v06-2024-25-wording": "hdfc-ergo-optima-secure-v08-2025-26-wording",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(QI_MANIFEST, encoding="utf-8")))
    built = [b for b in (build_one(r) for r in rows) if b]

    for b in built:
        p = b["product"]
        p["differentiator"] = differentiator(p)
        f = p["facts"]
        print(f"\n## {p['insurer']} — {p['name']}{' · ' + p['variant'] if p['variant'] else ''}  [{p['uin']}]  offset={b['doc']['page_offset']}")
        for k in ("ped_wait_months", "diabetes_wait", "specified_disease_wait_months", "room_rent", "entry_age_max", "ayush", "cataract", "robotic_surgery"):
            if k not in f:
                continue
            x = f[k]
            if x["stated"]:
                v = x["value"] if not isinstance(x["value"], str) else x["value"][:90]
                tag = f" [{x.get('room_class')}{' ₹' + str(x['max_per_day']) if x.get('max_per_day') else ''}]" if k == "room_rent" else ""
                tag += f" NOTE: {x['note'][:70]}" if x.get("note") and k == "ped_wait_months" else ""
                print(f"  {k:30} {v!s:<60} p{x['pdf_page']} {x['section'] or ''}{tag}")
            else:
                print(f"  {k:30} — {x['note']}")

    if not args.write:
        return 0

    cat = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    existing_uins = {d["uin"] for d in cat["documents"].values()}
    by_id = {p["id"]: p for p in cat["products"]}
    for b in built:
        p = b["product"]
        if p["uin"] in existing_uins and p["id"] not in by_id:
            print(f"skip duplicate of an existing product: {p['id']} ({p['uin']})")
            continue
        cat["documents"][p["id"]] = b["doc"]
        by_id[p["id"]] = p

    for old, new in SUPERSEDE.items():
        if old in by_id and new in by_id:
            o = by_id[old]
            o["status"] = "withdrawn"
            o["replaced_by"] = new
            o["withdrawn_on"] = None
            o["stop_reason"] = f"Revised wording UIN {by_id[new]['uin']} replaces UIN {o['uin']}."

    cat["products"] = list(by_id.values())
    cat["catalogue"]["source"] = f"{len(cat['documents'])} insurer policy wordings + plan variants, verified page by page."
    cat["_provenance"]["built_from"] = f"{len(cat['documents'])} policy wordings (PDF) in data/policies/"
    CATALOGUE.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    man = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))
    have = {r["policy_id"] for r in man}
    fields = list(man[0].keys())
    for b in built:
        if b["manifest"]["policy_id"] not in have and b["product"]["id"] in by_id:
            man.append(b["manifest"])
    with open(MANIFEST, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(man)
    print(f"\ncatalogue: {len(cat['products'])} products, {len(cat['documents'])} documents; manifest: {len(man)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

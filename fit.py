"""Find the product that fits a customer, or check one named product against the customer.

  python fit.py "mother is 50, has diabetes, wants room rent more than 10,000"
  python fit.py "mother 50 diabetes room rent 10000" --policy care_supreme

Two ways in, one engine:
  need first     the agent describes the customer; every product on sale is checked and the best
                 one and the second best are shown, with one line on why, and one line on why
                 each of the others does not fit.
  product first  the agent names the product; only that product is checked against the customer.

Rules that keep it honest (same as rank.py):
  1. Every check reads the fact table ("numbers" on each row, with its verbatim quote and page) or
     the IRDAI insurer figure. Nothing comes from a model or from free text search.
  2. A fact that is missing is never read as a pass. It is shown as "not in the fact table" and
     the product scores nothing for it.
  3. Withdrawn products and top-ups are never offered for a new sale.
  4. Premium is not in the wordings; it is never used or quoted.
  5. Dates are worked out from the policy start date the agent gives (today if none) and the
     waiting period in the wording, and assume renewal without a break and full disclosure.
"""
import calendar
import datetime as dt
import re
import sys

from fact_table import load_facts, manifest

# ------------------------------------------------------------------ reading the customer

MEMBER = [
    ("mother", r"\b(mother|mom|mum|mummy|maa|ma|mata\s*ji|mataji|ammi)\b|माँ|मां|माता|मम्मी"),
    ("father", r"\b(father|dad|papa|pitaji|pita\s*ji|abbu)\b|पिता|पापा"),
    ("parents", r"\b(parents|mata\s*pita|maa\s*baap)\b|माता[- ]पिता"),
    ("spouse", r"\b(wife|husband|spouse|patni|pati)\b|पत्नी|पति"),
    ("self", r"\b(myself|for me|self|khud)\b"),
]
CONDITIONS = [
    ("diabetes", r"diabet|\bsugar\b|madhumeh|मधुमेह|डायबिटीज|शुगर"),
    ("hypertension", r"hypertension|blood\s*pressure|\bb\.?p\.?\b|उच्च रक्तचाप|बीपी"),
    ("heart disease", r"\bheart\b|cardiac|दिल|हृदय"),
    ("thyroid", r"thyroid|थायराइड"),
    ("asthma", r"asthma|दमा"),
]
AGE_RE = [
    re.compile(r"\b(\d{1,2})\s*(?:years?|yrs?|yr|y/?o|saal|sal|baras|varsh)\b(?:\s*old)?", re.I),
    re.compile(r"(\d{1,2})\s*(?:वर्ष|साल)"),
    re.compile(r"\b(?:age|aged|umar|umr|ayu)\s*(?:is|of|:|hai)?\s*(\d{1,2})\b", re.I),
    re.compile(r"(?:उम्र|आयु)\s*(\d{1,2})"),
    re.compile(r"\b(?:is|hai|hain)\s+(\d{2})\b(?!\s*(?:lakh|lac|k\b|,\d|000|thousand|hazaar|%))", re.I),
    re.compile(r"\b(?:mother|father|mom|maa|mummy|papa|wife|husband)\s*,?\s*(\d{2})\b(?!\s*(?:lakh|lac|k\b|,\d|000|%))", re.I),
]
AMOUNT = r"(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|hazaar|hazar|हज़ार|हजार|lakh|lac|lakhs|crore|cr)?"
ROOM_RE = [
    re.compile(r"(?:room|kamra|kamre|कमरा|कमरे|रूम)[^\d]{0,40}?" + AMOUNT, re.I),
    re.compile(AMOUNT + r"[^\d]{0,25}?(?:room|kamra|kamre|कमरा|कमरे|रूम)", re.I),
]
SI_RE = re.compile(r"(?:cover|sum\s*insured|\bsi\b|bima\s*rashi|कवर)[^\d]{0,20}?(\d+(?:\.\d+)?)\s*(lakh|lac|lakhs|crore|cr|लाख|करोड़)"
                   r"|(\d+(?:\.\d+)?)\s*(lakh|lac|lakhs|crore|cr|लाख|करोड़)\s*(?:ka|ki|का|की)?\s*(?:cover|sum\s*insured|\bsi\b|कवर|policy|plan)", re.I)
PRIVATE_ROOM = re.compile(r"(single|private)\s+(ac\s+)?room|private kamra|प्राइवेट रूम|सिंगल रूम", re.I)
START_RE = re.compile(r"(?:start|starts|starting|from|se shuru|शुरू)\D{0,12}(\d{1,2})[\s/-]*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*[\s/-]*(\d{4})?", re.I)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _rupees(num: str, unit: str | None) -> float:
    n = float(num.replace(",", ""))
    u = (unit or "").lower()
    if u in ("k", "thousand", "hazaar", "hazar", "हज़ार", "हजार"):
        n *= 1000
    elif u in ("lakh", "lac", "lakhs", "लाख"):
        n *= 1e5
    elif u in ("crore", "cr", "करोड़"):
        n *= 1e7
    return n


def profile(text: str, today: dt.date | None = None) -> dict:
    t = text.lower()
    p: dict = {"age": None, "member": None, "conditions": [], "room_rent": None, "private_room": bool(PRIVATE_ROOM.search(text)),
               "sum_insured": None, "start": today or dt.date.today(), "start_given": False,
               "premium": bool(re.search(r"premium|budget|sasta|sasti|cheap|प्रीमियम|बजट|money|paisa|paise", t))}
    for name, rx in MEMBER:
        if re.search(rx, t, re.I):
            p["member"] = name
            break
    for name, rx in CONDITIONS:
        if re.search(rx, t, re.I):
            p["conditions"].append(name)
    room_span = None
    for rx in ROOM_RE:
        m = rx.search(text)
        if m:
            v = _rupees(m.group(1), m.group(2))
            if 500 <= v <= 200000:
                p["room_rent"], room_span = v, m.span(1)
                break
    m = SI_RE.search(text)
    if m:
        p["sum_insured"] = _rupees(m.group(1) or m.group(3), m.group(2) or m.group(4))
    for rx in AGE_RE:
        for m in rx.finditer(text):
            if room_span and room_span[0] <= m.start(1) < room_span[1]:  # the room amount is not an age
                continue
            a = int(m.group(1))
            if 0 < a < 100:
                p["age"] = a
                break
        if p["age"]:
            break
    m = START_RE.search(text)
    if m:
        year = int(m.group(3)) if m.group(3) else p["start"].year
        try:
            d = dt.date(year, MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
            if not m.group(3) and d < p["start"]:
                d = d.replace(year=year + 1)
            p["start"], p["start_given"] = d, True
        except ValueError:
            pass
    return p


def is_need(text: str) -> bool:
    """A customer description rather than a question about one clause: at least two of age,
    family member, condition, room rent amount or sum insured, with an age or member among them."""
    p = profile(text)
    signals = sum(bool(x) for x in (p["age"], p["member"], p["conditions"], p["room_rent"] or p["private_room"], p["sum_insured"]))
    return signals >= 2 and bool(p["age"] or p["member"])


# ------------------------------------------------------------------ dates

def add_months(d: dt.date, months: float) -> dt.date:
    if months < 1:
        return d + dt.timedelta(days=round(months * 30))
    m = int(round(months))
    y, mo = divmod(d.month - 1 + m, 12)
    y, mo = d.year + y, mo + 1
    return dt.date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))


def fmt_date(d: dt.date) -> str:
    return f"{d.day} {calendar.month_abbr[d.month]} {d.year}"


# ------------------------------------------------------------------ the products

def products() -> list[dict]:
    """Every product with a fact file, its rows by attribute (plan ALL), and manifest status."""
    man = manifest()
    out = []
    for f in load_facts():
        r = man.get(f["policy_id"])
        if not r:
            continue
        rows = {x["attribute"]: x for x in f["rows"] if x["plan"] == "ALL"}
        # plan only rows (Oriental PREMIUM, ELITE, ROYAL): the first plan in the manifest is the base plan
        base = next((pl.strip() for pl in (r.get("plans") or "").split(";") if pl.strip()), None)
        for x in f["rows"]:
            if base and x["plan"].upper() == base.upper() and x["attribute"] not in rows:
                rows[x["attribute"]] = {**x, "value": f"{x['value']} ({base.title()} plan)"}
        prod = r["product"].lower()
        short = re.sub(r"^The |\s+(General Insurance|Health Insurance|Insurance Company|Insurance|Assurance Company|and Allied Insurance)$", "",
                       r["insurer"]).replace(" and Allied", "")
        prod_name = re.sub(r"\s*\((?:prospectus|brochure)[^)]*\)|,\s*top-up", "", r["product"]).strip()
        out.append({"policy_id": f["policy_id"], "insurer": short, "product": r["product"], "label": r.get("label") or r["insurer"],
                    "display": prod_name if any(prod_name.lower().startswith(x.lower()) for x in short.split()) else f"{short} {prod_name}",
                    "status": r.get("status") or "active", "replaced_by": r.get("replaced_by") or "",
                    "top_up": "top-up" in prod or "top up" in prod, "brochure": "brochure" in prod or "prospectus" in prod,
                    "offset": int(r.get("page_offset") or 0), "rows": rows})
    return out


def num(prod: dict, attribute: str) -> dict:
    r = prod["rows"].get(attribute)
    return (r.get("numbers") or {}) if r and r["status"] == "stated" else {}


def evidence(prod: dict, attribute: str) -> dict | None:
    r = prod["rows"].get(attribute)
    if not r or r["status"] != "stated" or not r["evidence"]:
        return None
    e = r["evidence"][0]
    return {"attribute": attribute, "value": r["value"], "page": e["page"], "printed_page": e["page"] - prod["offset"],
            "quote": e["quote"], "clause": e.get("clause"), "verified": r["verified"]}


# ------------------------------------------------------------------ checking one product

def _months(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def condition_wait(prod: dict) -> tuple[float | None, list[str]]:
    """Months before a condition the customer already has (declared at entry) is covered: the
    pre-existing disease wait, or a longer specific wait for that disease if the wording lists one."""
    ped = _months(num(prod, "ped_waiting").get("months"))
    sp = num(prod, "specific_disease_waiting")
    spec = _months(sp.get("diabetes_months"))
    if sp.get("diabetes_overrides_ped") and spec is not None:  # a diabetes product: its own section, not the PED rule
        return spec, ["specific_disease_waiting"]
    used = [a for a, v in (("ped_waiting", ped), ("specific_disease_waiting", spec)) if v is not None]
    vals = [v for v in (ped, spec) if v is not None]
    return (max(vals) if vals else None), used


def room_check(prod: dict, need: float | None, private: bool, si: float | None) -> tuple[str, float, str, str | None]:
    """(result, score, reading, condition) with result "pass" | "fail" | "unknown"."""
    rr = num(prod, "room_rent")
    kind = rr.get("kind")
    if not kind:
        return "unknown", 0.0, "room rent not in the fact table (the wording may leave it to the policy schedule)", None
    if kind == "no_limit":
        return "pass", 1.0, "no room rent limit", None
    if kind == "category":
        cat = (rr.get("category") or "").lower()
        if re.search(r"shared|twin|general ward|multi", cat) and not re.search(r"single|private", cat):
            return ("fail" if (need or private) else "pass"), 0.3, f"room limited to {cat}", None
        return "pass", 0.9, f"{(rr.get('category') or 'room category').split('/')[0].strip()} at the hospital's rate", None
    if kind == "rupees" and rr.get("rupees_per_day"):
        cap = float(rr["rupees_per_day"])
        ok = need is None or cap >= need
        return ("pass" if ok else "fail"), (0.7 if ok else 0.1), f"room rent capped at Rs {cap:,.0f} a day", None
    if kind == "percent_si" and rr.get("percent_of_si"):
        pct = float(rr["percent_of_si"])
        cap = float(rr["max_rupees_per_day"]) if rr.get("max_rupees_per_day") else None
        reading = f"room rent capped at {pct:g}% of sum insured a day" + (f", at most Rs {cap:,.0f}" if cap else "")
        if need is None:
            return "pass", 0.5, reading, None
        if cap and cap < need:
            return "fail", 0.1, reading, None
        if si:
            ok = si * pct / 100 >= need
            return ("pass" if ok else "fail"), (0.6 if ok else 0.1), reading + f" (Rs {si * pct / 100:,.0f} on the cover asked for)", None
        need_si = need * 100 / pct
        return "pass", 0.4, reading, f"needs a sum insured of at least Rs {need_si / 1e5:g} lakh for Rs {need:,.0f} a day"
    return "unknown", 0.0, "room rent rule could not be read: " + prod["rows"]["room_rent"]["value"][:60], None


def check(prod: dict, p: dict) -> dict:
    """Does this product fit the customer? Returns the reasons it fails (each a short line), the
    readings that make it good, a score for products that fit, and the facts used."""
    fails, good, cautions, used, gaps = [], [], [], set(), []
    score, weight = 0.0, 0.0
    if prod["status"] == "withdrawn":
        new = next((x for x in products() if x["policy_id"] == prod["replaced_by"]), None)
        fails.append("no longer sold" + (f"; the new product is {new['label']}" if new else ""))
    if prod["top_up"]:
        fails.append("a top-up: it pays only above a deductible, so it needs a base policy first")
    age = p["age"]
    ea = num(prod, "entry_age")
    lo, hi = ea.get("adult_min_years"), ea.get("adult_max_years")
    if ea:
        used.add("entry_age")
    if age is not None:
        if lo and age < lo:
            fails.append(f"takes new customers from {lo} years only")
        elif hi and age > hi:
            fails.append(f"takes new customers only up to {hi} years")
        elif not ea:
            cautions.append("entry age is not in the fact table; confirm the customer can join")
            gaps.append("entry age")
        elif not hi:
            cautions.append("the wording states no upper entry age; confirm with the insurer")
    si = p["sum_insured"]
    sio = num(prod, "sum_insured_options")
    if si and sio.get("max_rupees") and si > float(sio["max_rupees"]):
        fails.append(f"covers up to Rs {float(sio['max_rupees']) / 1e5:g} lakh only")
        used.add("sum_insured_options")

    wait = None
    if p["conditions"]:
        wait, w_used = condition_wait(prod)
        used |= set(w_used)
        weight += 3
        if wait is None:
            cautions.append(f"{p['conditions'][0]} waiting period is not in the fact table")
            gaps.append(f"{p['conditions'][0]} waiting period")
        else:
            score += 3 * max(0.0, 1 - wait / 48)
            good.append(f"{p['conditions'][0]} covered after {wait:g} months")
    res, s, reading, cond = room_check(prod, p["room_rent"], p["private_room"], si)
    weight += 2 if (p["room_rent"] or p["private_room"]) else 1
    if res == "fail":
        fails.append(reading)
    elif res == "pass":
        score += (2 if (p["room_rent"] or p["private_room"]) else 1) * s
        good.append(reading)
    else:
        cautions.append(reading)
        gaps.append("room rent")
    if res != "unknown":
        used.add("room_rent")
    if cond:
        cautions.append(cond)
    cp = num(prod, "copay")
    weight += 1.5
    if cp:
        used.add("copay")
        pct = _months(cp.get("percent"))
        if pct is None:
            cautions.append("co-pay " + (cp.get("condition") or "depends on the plan; read the clause"))
        elif pct == 0:
            score += 1.5
            good.append("no co-pay")
        elif cp.get("mandatory") is False:
            score += 1.2
            good.append(f"no compulsory co-pay ({pct:g}% {cp.get('condition') or 'if chosen'})")
        else:
            score += 1.5 * max(0.0, 1 - pct / 50)
            cautions.append(f"{pct:g}% co-pay" + (f" ({cp['condition']})" if cp.get("condition") else ""))
    from rank import claims_reading
    cr = claims_reading(prod["insurer"])
    weight += 1
    if cr:
        score += cr[0]
    return {"policy_id": prod["policy_id"], "label": prod["label"], "insurer": prod["insurer"], "product": prod["product"],
            "display": prod["display"],
            "fits": not fails, "fails": fails, "gaps": gaps, "good": good, "cautions": cautions, "wait_months": wait,
            "score": round(100 * score / weight, 1) if weight else 0.0, "claims": cr[1] if cr else None,
            "brochure": prod["brochure"], "facts": [e for a in sorted(used) if (e := evidence(prod, a))]}


# ------------------------------------------------------------------ dates and the sales kit

SPECIFIC_NAMES = [("cataract_months", "cataract")]


def waiting_dates(prod: dict, p: dict) -> list[dict]:
    start = p["start"]
    out = []
    iw = _months(num(prod, "initial_waiting").get("days"))
    if iw:
        out.append({"what": "illness", "note": "accidents are covered from day one", "months": iw / 30,
                    "date": fmt_date(start + dt.timedelta(days=int(iw))), "attribute": "initial_waiting"})
    if p["conditions"]:
        w, _ = condition_wait(prod)
        if w is not None:
            out.append({"what": p["conditions"][0], "note": "declared in the proposal form", "months": w,
                        "date": fmt_date(add_months(start, w)), "attribute": "ped_waiting"})
    for key, name in SPECIFIC_NAMES:
        m = _months(num(prod, "specific_disease_waiting").get(key))
        if m:
            out.append({"what": f"{name} surgery", "note": None, "months": m, "date": fmt_date(add_months(start, m)),
                        "attribute": "specific_disease_waiting"})
    return out


WHO = {"mother": ("your mother", "mummy ji", "माँ"), "father": ("your father", "papa ji", "पिताजी"),
       "parents": ("your parents", "mummy-papa", "माता-पिता"), "spouse": ("your family member", "aapke parivaar", "आपके परिवार"),
       "self": ("you", "aap", "आप"), None: ("the customer", "aap", "आप")}


def sales_kit(best: dict, prod: dict, p: dict, lang: str) -> dict:
    """Words for the agent, a WhatsApp message, waiting end dates, papers and what not to promise.
    Built from the same fact rows as the check; nothing is added that the rows do not say."""
    dates = waiting_dates(prod, p)
    cond = p["conditions"][0] if p["conditions"] else None
    cond_date = next((d for d in dates if d["attribute"] == "ped_waiting"), None)
    who = WHO.get(p["member"], WHO[None])
    li = {"en": 0, "hinglish": 1, "hi": 2}[lang]
    good = "; ".join(best["good"][:3])
    if lang == "en":
        say = [f"For {who[0]}, I suggest {best['display']}.",
               f"Why: {good}." if good else "",
               f"{cond.capitalize()} claims are covered from {cond_date['date']}, as long as the policy is renewed every year without a break." if cond_date else "",
               "Till then, other illnesses and accidents are covered as per the policy terms." if cond_date else "",
               "Please declare every illness in the proposal form; hiding one can lead to a claim being refused."]
        wa = (f"Namaste! As discussed, {best['display']} suits {who[0]}: {good}. "
              + (f"{cond.capitalize()} cover starts {cond_date['date']} (policy start {fmt_date(p['start'])}, renewed without a break). " if cond_date else "")
              + "Premium will be shared from the insurer's quote. Please keep ID, address proof and recent medical reports ready.")
    elif lang == "hinglish":
        say = [f"{who[1].capitalize()} ke liye main {best['display']} suggest karta hoon.",
               f"Kyunki: {good}." if good else "",
               f"{cond.capitalize()} ka claim {cond_date['date']} se milega, agar policy har saal bina break ke renew ho." if cond_date else "",
               "Tab tak baaki bimariyan aur accident policy terms ke hisaab se cover hain." if cond_date else "",
               "Proposal form mein har bimari batana zaroori hai; chhupane par claim reject ho sakta hai."]
        wa = (f"Namaste! Jaisa baat hui, {best['display']} {who[1]} ke liye sahi hai: {good}. "
              + (f"{cond.capitalize()} cover {cond_date['date']} se shuru hoga (policy start {fmt_date(p['start'])}, bina break renew). " if cond_date else "")
              + "Premium insurer ke quote se bhejunga. ID, address proof aur recent medical reports tayyar rakhiye.")
    else:
        say = [f"{who[2]} के लिए मैं {best['display']} सुझाता हूँ।",
               f"क्यों: {good}।" if good else "",
               f"{cond} का क्लेम {cond_date['date']} से मिलेगा, अगर पॉलिसी हर साल बिना रुकावट रिन्यू हो।" if cond_date else "",
               "तब तक बाकी बीमारियाँ और दुर्घटना पॉलिसी की शर्तों के अनुसार कवर हैं।" if cond_date else "",
               "प्रपोज़ल फॉर्म में हर बीमारी बताना ज़रूरी है; छिपाने पर क्लेम रिजेक्ट हो सकता है।"]
        wa = (f"नमस्ते! जैसा बात हुई, {best['display']} {who[2]} के लिए सही है: {good}। "
              + (f"{cond} कवर {cond_date['date']} से शुरू होगा (पॉलिसी शुरू {fmt_date(p['start'])}, बिना रुकावट रिन्यू)। " if cond_date else "")
              + "प्रीमियम बीमा कंपनी के कोटेशन से भेजूँगा। पहचान पत्र, पते का प्रमाण और हाल की मेडिकल रिपोर्ट तैयार रखिए।")
    papers = PAPERS[lang] + ([PAPERS_COND[lang].format(c=cond)] if cond else [])
    dont = []
    for d in dates:
        line = DONT["before"][lang].format(what=d["what"], date=d["date"])
        dont.append(line[:-1] + f" ({d['note']})" + line[-1] if d.get("note") and lang == "en" else line)
    cp = num(prod, "copay")
    if cp and (_months(cp.get("percent")) or 0) > 0 and cp.get("mandatory") is not False:
        dont.append(DONT["copay"][lang].format(v=prod["rows"]["copay"]["value"][:120]))
    rr = num(prod, "room_rent")
    if rr.get("kind") in ("percent_si", "rupees", "category"):
        dont.append(DONT["room"][lang].format(v=prod["rows"]["room_rent"]["value"][:120]))
    dont += [DONT["premium"][lang], DONT["approval"][lang]]
    if best["brochure"]:
        dont.append(DONT["brochure"][lang])
    return {"say": [s for s in say if s], "whatsapp": wa, "dates": dates, "papers": papers, "dont": dont,
            "start": fmt_date(p["start"]), "start_given": p["start_given"]}


PAPERS = {
    "en": ["Photo ID and address proof (Aadhaar, PAN, passport or voter ID)", "Age proof", "Passport size photo",
           "Proposal form filled and signed, with every illness declared"],
    "hinglish": ["Photo ID aur address proof (Aadhaar, PAN, passport ya voter ID)", "Age proof", "Passport size photo",
                 "Proposal form bhar kar sign kiya hua, har bimari ke saath"],
    "hi": ["फोटो पहचान पत्र और पते का प्रमाण (आधार, पैन, पासपोर्ट या वोटर आईडी)", "उम्र का प्रमाण", "पासपोर्ट साइज़ फोटो",
           "भरा और साइन किया हुआ प्रपोज़ल फॉर्म, हर बीमारी बताते हुए"],
}
PAPERS_COND = {
    "en": "Recent {c} reports and current prescriptions; the insurer may also ask for a medical check-up before it accepts",
    "hinglish": "{c} ki recent reports aur current prescriptions; insurer policy dene se pehle medical check-up bhi maang sakta hai",
    "hi": "{c} की हाल की रिपोर्ट और मौजूदा पर्चे; बीमा कंपनी पॉलिसी देने से पहले मेडिकल जाँच भी माँग सकती है",
}
DONT = {
    "before": {"en": "Do not promise {what} claims before {date}.", "hinglish": "{date} se pehle {what} ke claim ka vaada mat kijiye.",
               "hi": "{date} से पहले {what} के क्लेम का वादा मत कीजिए।"},
    "copay": {"en": "Do not say there is no co-pay. The policy says: {v}", "hinglish": "Yeh mat kahiye ki co-pay nahi hai. Policy kehti hai: {v}",
              "hi": "यह मत कहिए कि को-पे नहीं है। पॉलिसी कहती है: {v}"},
    "room": {"en": "Do not promise any room. The policy says: {v}", "hinglish": "Kisi bhi room ka vaada mat kijiye. Policy kehti hai: {v}",
             "hi": "किसी भी कमरे का वादा मत कीजिए। पॉलिसी कहती है: {v}"},
    "premium": {"en": "Do not quote a premium from memory; send the insurer's quote.",
                "hinglish": "Premium yaad se mat bataiye; insurer ka quote bhejiye.",
                "hi": "प्रीमियम याद से मत बताइए; बीमा कंपनी का कोटेशन भेजिए।"},
    "approval": {"en": "Do not promise the policy will be issued; the insurer decides after reading the proposal and reports.",
                 "hinglish": "Policy milne ka vaada mat kijiye; insurer proposal aur reports dekh kar decide karta hai.",
                 "hi": "पॉलिसी मिलने का वादा मत कीजिए; बीमा कंपनी प्रपोज़ल और रिपोर्ट देखकर तय करती है।"},
    "brochure": {"en": "These facts come from a brochure; check the full policy wording before you commit.",
                 "hinglish": "Yeh facts brochure se hain; vaada karne se pehle poori policy wording dekhiye.",
                 "hi": "ये तथ्य ब्रोशर से हैं; वादा करने से पहले पूरी पॉलिसी वर्डिंग देखिए।"},
}

# ------------------------------------------------------------------ the answer

TEXT = {
    "en": {"for": "Customer: {who}.", "best": "Best: {name}. Why: {why}.", "second": "Second: {name}. Why: {why}.",
           "none": "No product on sale fits all of this. Closest reasons below.",
           "not_fit": "Why the others do not fit:", "more": "and {n} more for the same reasons", "fits_but": "fits, but {why}",
           "date": "{cond} cover starts {date} with {name}, if the policy starts {start} and is renewed without a break.",
           "today": " (today; tell me the start date if it is different)",
           "caution": "Check: {c}.", "unverified": "Fact values are drafts not yet checked by a person; the quotes below are checked against the PDF.",
           "premium": "Premium is not in the policy documents, so it is not used here. Get the insurer's quote.",
           "coverage": "{k} of {n} loaded products have fact rows and were checked.",
           "one_fit": "{name} fits this customer. Why: {why}.", "one_nofit": "{name} does not fit this customer: {why}.",
           "advice": "A shortlist for the agent, not advice to the customer. The insurer decides acceptance and premium."},
    "hinglish": {"for": "Customer: {who}.", "best": "Best: {name}. Kyunki: {why}.", "second": "Doosra: {name}. Kyunki: {why}.",
                 "none": "Koi bhi product jo abhi bik raha hai, yeh sab poora nahi karta. Kaaran neeche hain.",
                 "not_fit": "Baaki kyun fit nahi:", "more": "aur {n} isi wajah se", "fits_but": "fit hai, lekin {why}",
                 "date": "{name} mein {cond} cover {date} se shuru hoga, agar policy {start} se shuru ho aur bina break renew ho.",
                 "today": " (aaj; alag date ho to bataiye)",
                 "caution": "Check karein: {c}.", "unverified": "Fact values draft hain, kisi ne abhi check nahi kiye; neeche ke quotes PDF se match kiye gaye hain.",
                 "premium": "Premium policy document mein nahi hota, isliye yahan use nahi kiya. Insurer ka quote lijiye.",
                 "coverage": "{n} loaded products mein se {k} ke fact rows hain aur check kiye gaye.",
                 "one_fit": "{name} is customer ke liye fit hai. Kyunki: {why}.", "one_nofit": "{name} is customer ke liye fit nahi: {why}.",
                 "advice": "Yeh agent ke liye shortlist hai, customer ke liye salah nahi. Policy dena aur premium insurer tay karta hai."},
    "hi": {"for": "ग्राहक: {who}।", "best": "सबसे अच्छा: {name}। क्यों: {why}।", "second": "दूसरा: {name}। क्यों: {why}।",
           "none": "अभी बिकने वाला कोई प्रोडक्ट यह सब पूरा नहीं करता। कारण नीचे हैं।",
           "not_fit": "बाकी क्यों फिट नहीं:", "more": "और {n} इसी कारण से", "fits_but": "फिट है, लेकिन {why}",
           "date": "{name} में {cond} कवर {date} से शुरू होगा, अगर पॉलिसी {start} से शुरू हो और बिना रुकावट रिन्यू हो।",
           "today": " (आज; अलग तारीख हो तो बताइए)",
           "caution": "जाँचें: {c}।", "unverified": "फैक्ट मान ड्राफ्ट हैं, किसी व्यक्ति ने अभी जाँचे नहीं; नीचे के उद्धरण PDF से मिलाए गए हैं।",
           "premium": "प्रीमियम पॉलिसी दस्तावेज़ में नहीं होता, इसलिए यहाँ इस्तेमाल नहीं हुआ। बीमा कंपनी का कोटेशन लीजिए।",
           "coverage": "{n} लोड किए गए प्रोडक्ट में से {k} की फैक्ट पंक्तियाँ हैं और जाँची गईं।",
           "one_fit": "{name} इस ग्राहक के लिए फिट है। क्यों: {why}।", "one_nofit": "{name} इस ग्राहक के लिए फिट नहीं: {why}।",
           "advice": "यह एजेंट के लिए शॉर्टलिस्ट है, ग्राहक के लिए सलाह नहीं। पॉलिसी देना और प्रीमियम बीमा कंपनी तय करती है।"},
}


def lower_reason(r: dict, best: dict, p: dict) -> str:
    """Why a product that fits still ranks below the best one, in a few words."""
    if p["conditions"] and r["wait_months"] is not None and best["wait_months"] is not None and r["wait_months"] > best["wait_months"]:
        return f"{p['conditions'][0]} covered only after {r['wait_months']:g} months"
    if r["gaps"]:
        g = r["gaps"]
        return (" and ".join(g) if len(g) <= 2 else ", ".join(g[:-1]) + " and " + g[-1]) + (" are" if len(g) > 1 else " is") + \
            " not stated in its wording"
    if r["cautions"]:
        return r["cautions"][0]
    return "a lower IRDAI claims ratio" if r.get("claims") else "fewer facts in its favour"


def who_line(p: dict) -> str:
    bits = []
    if p["member"]:
        bits.append(p["member"])
    if p["age"]:
        bits.append(f"{p['age']} years")
    bits += p["conditions"]
    if p["room_rent"]:
        bits.append(f"room rent above Rs {p['room_rent']:,.0f} a day")
    elif p["private_room"]:
        bits.append("private room")
    if p["sum_insured"]:
        bits.append(f"cover Rs {p['sum_insured'] / 1e5:g} lakh")
    return ", ".join(bits) or "no details given"


def _cites(results: list[dict], prods: dict) -> list[dict]:
    cites = []
    for r in results:
        for e in r["facts"]:
            cites.append({"n": len(cites) + 1, "policy_id": r["policy_id"], "product": r["label"],
                          "section": f"{r['label']}: {e['attribute'].replace('_', ' ')}" + (f" (clause {e['clause']})" if e.get("clause") else ""),
                          "page": e["page"], "printed_page": e["printed_page"], "quote": e["quote"], "text": e["value"]})
    return cites


def fit_answer(question: str, lang: str = "en", policy_id: str | None = None, today: dt.date | None = None,
               only: list[str] | None = None) -> dict:
    """only: rank within these products (the agent named an insurer with several products)."""
    p = profile(question, today)
    w = TEXT[lang]
    prods = {x["policy_id"]: x for x in products()}
    total = sum(1 for r in manifest().values() if (r.get("category") or "health") == "health")
    lines = [w["for"].format(who=who_line(p))]
    if policy_id:  # product first: check this one only
        prod = prods.get(policy_id)
        if not prod:
            return {"status": "not_stated", "answer": w["coverage"].format(k=len(prods), n=total) + " " +
                    "This product has no fact rows yet, so I cannot check it against the customer.", "citations": []}
        r = check(prod, p)
        why = "; ".join(r["good"]) if r["fits"] else "; ".join(r["fails"])
        lines.append(w["one_fit" if r["fits"] else "one_nofit"].format(name=r["display"], why=why or "-"))
        best, results, others = (r if r["fits"] else None), [r], []
    else:  # need first: every product
        results = [check(x, p) for x in prods.values() if not only or x["policy_id"] in only]
        fit = sorted([r for r in results if r["fits"]], key=lambda r: (-r["score"], len(r["cautions"]), r["label"]))
        others = [r for r in results if not r["fits"]]
        best = fit[0] if fit else None
        if best:
            lines.append(w["best"].format(name=best["display"], why="; ".join(best["good"]) or "-"))
            if len(fit) > 1:
                s = fit[1]
                lines.append(w["second"].format(name=s["display"], why="; ".join(s["good"]) or "-"))
        else:
            lines.append(w["none"])
        rest = fit[2:]
        if others or rest:
            lines.append(w["not_fit"])
            groups: dict[str, list[str]] = {}
            for r in others:
                groups.setdefault(r["fails"][0], []).append(r["label"])
            shown = 0
            for reason, names in sorted(groups.items(), key=lambda kv: -len(kv[1])):
                if shown >= 6:
                    break
                lines.append(f"- {', '.join(names[:4])}" + (f" ({w['more'].format(n=len(names) - 4)})" if len(names) > 4 else "") + f": {reason}.")
                shown += 1
            if rest:
                low: dict[str, list[str]] = {}
                for r in rest:
                    low.setdefault(lower_reason(r, best, p), []).append(r["label"])
                for reason, names in sorted(low.items(), key=lambda kv: -len(kv[1]))[:5]:
                    lines.append(f"- {', '.join(names[:4])}" + (f" ({w['more'].format(n=len(names) - 4)})" if len(names) > 4 else "")
                                 + f": {w['fits_but'].format(why=reason)}.")
        results = (fit[:2] if fit else []) + others
    if best:
        prod = prods[best["policy_id"]]
        cd = next((d for d in waiting_dates(prod, p) if d["attribute"] == "ped_waiting"), None)
        if cd:
            lines.append(w["date"].format(cond=p["conditions"][0].capitalize(), date=cd["date"], name=best["label"],
                                          start=fmt_date(p["start"]) + ("" if p["start_given"] else w["today"])))
        for c in best["cautions"][:3]:
            lines.append(w["caution"].format(c=c))
    if p["premium"]:
        lines.append(w["premium"])
    lines.append(w["unverified"])
    if not policy_id and len(prods) < total:
        lines.append(w["coverage"].format(k=len(prods), n=total))
    lines.append(w["advice"])
    shown = [r for r in results if r["fits"]][:2] if not policy_id else results
    kit = sales_kit(best, prods[best["policy_id"]], p, lang) if best else None
    return {"status": "ranked", "answer": "\n".join(lines), "citations": _cites(shown, prods),
            "fit": {"profile": {**p, "start": fmt_date(p["start"])}, "mode": "product" if policy_id else "need",
                    "best": shown, "others": [{"label": r["label"], "reason": r["fails"][0]} for r in others],
                    "checked": len(prods), "total": total, "kit": kit}}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="+")
    ap.add_argument("--policy")
    ap.add_argument("--lang", default="en")
    a = ap.parse_args()
    out = fit_answer(" ".join(a.question), a.lang, a.policy)
    print(out["answer"])
    if out.get("fit") and out["fit"]["kit"]:
        k = out["fit"]["kit"]
        print("\nSAY:", *k["say"], sep="\n  ")
        print("\nWHATSAPP:\n ", k["whatsapp"])
        print("\nDATES:", *[f"{d['what']}: {d['date']}" for d in k["dates"]], sep="\n  ")
        print("\nPAPERS:", *k["papers"], sep="\n  ")
        print("\nDO NOT PROMISE:", *k["dont"], sep="\n  ")

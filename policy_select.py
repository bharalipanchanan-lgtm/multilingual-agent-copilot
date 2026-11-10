"""Choose the policy document from what the agent types, instead of a dropdown.

The agent says which policy to inspect ("SBI health policy dekhna hai", "ओरिएंटल", "2") or
names it inside a question ("United India mein room rent kitna hai?"). The choice is kept by
the client and sent back with every question until the agent names another policy.

Matching is deterministic: aliases from the manifest (insurer, product and an aliases column
with Hindi and short forms), plus close spelling matches for longer words. No model call,
so the choice is instant and never guessed. If the text names more than one policy (outside
a comparison) or a policy that is not loaded, the copilot asks instead of picking one.
"""
import difflib
import re

from fact_table import manifest

# Insurers whose policies are not loaded. If the agent names one, say so rather than answer
# from whichever policy happens to be selected.
# Insurers with no document loaded: naming one gets a clear "not loaded", never another insurer's answer.
# Insurers that are loaded are matched by their manifest aliases before this list is consulted.
OTHER_INSURERS = {"manipal cigna": "ManipalCigna", "manipalcigna": "ManipalCigna", "reliance general": "Reliance General",
                  "future generali": "Future Generali", "cholamandalam": "Cholamandalam MS", "chola ms": "Cholamandalam MS",
                  "liberty general": "Liberty General", "kotak": "Kotak General", "magma": "Magma HDI",
                  "universal sompo": "Universal Sompo", "galaxy health": "Galaxy Health", "narayana": "Narayana Health",
                  "zuno": "Zuno", "navi": "Navi General"}

# Words that carry no content in "I would like to review the SBI policy" style requests. The last
# Roman line holds the spellings Sarvam's transliteration uses ("Mujhe SBI vali policy dekhni hai").
FILLER = set("""
i i'd id me my we us let lets let's would like want wanna to the a an of about for on in with and please pls kindly
review inspect check see look open use select choose show switch change go start load read study discuss
policy policies document documents doc wording wordings plan plans health insurance insurer company mediclaim
now ok okay yes sure thanks thank you this that one term life cover products product
mujhe mujhko humein hume hum main mai mein ko ka ki ke se par pe wala wali wale ab abhi chalo theek thik haan han
dekhna dekhni dekhne dekho dikhao dikhaiye kholo kholiye karna karni karo kariye chahta chahti chahte chahiye hai hain
hoon hu hun ho jao jaaye baat batao bataiye policy polisi document dastavez bima
vali vala vale chahie chaahie chahiye chaahiye dekhani dekhana mujhko iss is us uss vo woh ye yeh
""".split()) | {"मुझे", "मैं", "हमें", "को", "का", "की", "के", "से", "पर", "वाली", "वाला", "अब", "ठीक", "है", "हैं",
                "हूँ", "हूं", "देखना", "देखनी", "देखिए", "दिखाओ", "दिखाइए", "खोलो", "चाहता", "चाहती", "चाहिए",
                "पॉलिसी", "पालिसी", "दस्तावेज़", "दस्तावेज", "बीमा", "हेल्थ", "इंश्योरेंस", "कंपनी", "प्लान"}

TEXT = {
    "choose": {
        "en": "Which policy document are you looking for? Type the insurer or product name (for example ICICI or Star Health), or browse the documents.",
        "hinglish": "Aapko kaunsa policy document chahiye? Insurer ya product ka naam likhiye (jaise ICICI ya Star Health), ya documents browse kijiye.",
        "hi": "आपको कौन सा पॉलिसी दस्तावेज़ चाहिए? बीमा कंपनी या प्रोडक्ट का नाम लिखिए (जैसे ICICI या Star Health), या दस्तावेज़ ब्राउज़ कीजिए।",
    },
    "greet": {
        "en": "Hello! I'm {agent}, your insurance policy copilot. I answer only from the policy document, with the clause and page.",
        "hinglish": "Namaste! Main {agent} hoon, aapka insurance policy copilot. Main sirf policy document se jawab deta hoon, clause aur page ke saath.",
        "hi": "नमस्ते! मैं {agent} हूँ, आपका इंश्योरेंस पॉलिसी कोपायलट। मैं केवल पॉलिसी दस्तावेज़ से, क्लॉज़ और पेज के साथ जवाब देता हूँ।",
    },
    "greet_again": {
        "en": "Hello again! I'm answering from {name}. Ask your question, or name another policy to switch.",
        "hinglish": "Namaste! Abhi main {name} se jawab de raha hoon. Apna sawaal poochiye, ya doosri policy ka naam lijiye.",
        "hi": "नमस्ते! अभी मैं {name} से जवाब दे रहा हूँ। अपना सवाल पूछिए, या दूसरी पॉलिसी का नाम लीजिए।",
    },
    "more": {
        "en": "{n} more documents are loaded. Find them with Browse all documents.",
        "hinglish": "{n} aur documents loaded hain. Unhe Browse all documents mein dhundhiye.",
        "hi": "{n} और दस्तावेज़ लोड हैं। उन्हें Browse all documents में खोजिए।",
    },
    "choose_hint": {
        "en": "Type the insurer's name or its number.",
        "hinglish": "Insurer ka naam ya number likhiye.",
        "hi": "बीमा कंपनी का नाम या नंबर लिखिए।",
    },
    "selected": {
        "en": "Okay. I will answer from {name}. What would you like to know?",
        "hinglish": "Theek hai. Ab main {name} se jawab dunga. Aap kya jaanna chahte hain?",
        "hi": "ठीक है। अब मैं {name} से जवाब दूँगा। आप क्या जानना चाहते हैं?",
    },
    "not_wording": {
        "en": "Note: this document is a {kind}, not the full policy wording. The policy wording governs.",
        "hinglish": "Dhyan dein: yeh document {kind} hai, poori policy wording nahi. Policy wording hi maanya hai.",
        "hi": "ध्यान दें: यह दस्तावेज़ {kind} है, पूरी पॉलिसी वर्डिंग नहीं। पॉलिसी वर्डिंग ही मान्य है।",
    },
    "ambiguous": {
        "en": "You mentioned more than one policy. Which one should I use?",
        "hinglish": "Aapne ek se zyada policy ka naam liya. Kaunsi use karun?",
        "hi": "आपने एक से अधिक पॉलिसी का नाम लिया। मैं कौन सी इस्तेमाल करूँ?",
    },
    "which_product": {
        "en": "I have {n} {insurer} documents loaded. Which exact product do you mean?",
        "hinglish": "Mere paas {insurer} ke {n} documents loaded hain. Aap kaunsa product dekhna chahte hain?",
        "hi": "मेरे पास {insurer} के {n} दस्तावेज़ लोड हैं। आप ठीक कौन सा प्रोडक्ट देखना चाहते हैं?",
    },
    "which_hint": {
        "en": "Tap one, or type its name. I answer from one product only, never a mix.",
        "hinglish": "Ek chuniye ya uska naam likhiye. Main sirf ek product se jawab deta hoon, kabhi mila kar nahi.",
        "hi": "एक चुनिए या उसका नाम लिखिए। मैं केवल एक प्रोडक्ट से जवाब देता हूँ, कभी मिलाकर नहीं।",
    },
    "stopped": {
        "en": "Warning: {name} is no longer sold ({source}). Use it only for a customer who already holds it.",
        "hinglish": "Dhyan dein: {name} ab nahi bika jaata ({source}). Ise sirf us customer ke liye dekhein jiske paas yeh pehle se hai.",
        "hi": "ध्यान दें: {name} अब नहीं बेचा जाता ({source})। इसे केवल उस ग्राहक के लिए देखें जिसके पास यह पहले से है।",
    },
    "stopped_new": {
        "en": "For a new sale, the current product is {new}. Say \"{label}\" to switch.",
        "hinglish": "Nayi sale ke liye current product {new} hai. Badalne ke liye \"{label}\" likhiye.",
        "hi": "नई बिक्री के लिए मौजूदा प्रोडक्ट {new} है। बदलने के लिए \"{label}\" लिखिए।",
    },
    "not_loaded": {
        "en": "I do not have a {insurer} policy loaded, so I cannot answer from it.",
        "hinglish": "Mere paas {insurer} ki koi policy loaded nahi hai, isliye main usse jawab nahi de sakta.",
        "hi": "मेरे पास {insurer} की कोई पॉलिसी लोड नहीं है, इसलिए मैं उससे जवाब नहीं दे सकता।",
    },
}
KIND = {"brochure": {"en": "brochure", "hinglish": "brochure", "hi": "ब्रोशर"},
        "prospectus": {"en": "prospectus", "hinglish": "prospectus", "hi": "प्रॉस्पेक्टस"}}


def policies() -> list[dict]:
    """Loaded policies in manifest order, numbered from 1 for the agent to pick by number."""
    from config import POLICY_DIR
    out = []
    for r in manifest().values():
        if not (POLICY_DIR / r["file"]).exists():
            continue
        # aliases in the same form as the text they are matched against ("ReAssure 2.0" -> "reassure 2 0")
        # the insurer's full name ("Life Insurance Corporation of India", "The New India Assurance Company")
        # always names its products, with and without a leading "The"
        full = _norm(r["insurer"]).strip()
        short = re.sub(r"( of india| limited| ltd| company| insurance| assurance| general)+$", "", re.sub(r"^the ", "", full))
        names = (r.get("aliases") or "").split(";") + [full, re.sub(r"^the ", "", full)] + ([short] if len(short) > 3 else [])
        aliases = list(dict.fromkeys(_norm(a).strip() for a in names if a.strip()))
        out.append({"n": len(out) + 1, "policy_id": r["policy_id"], "insurer": r["insurer"],
                    "product": r["product"], "name": display_name(r), "aliases": aliases,
                    "label": r.get("label") or "", "uin": r.get("uin") or "",
                    "status": (r.get("status") or "active").strip(), "replaced_by": (r.get("replaced_by") or "").strip(),
                    "status_source": r.get("status_source") or "", "differs": (r.get("differs") or "").strip(),
                    "category": (r.get("category") or "health").strip(),
                    "solo": [_norm(a).strip() for a in (r.get("solo_aliases") or "").split(";") if a.strip()]})
    return out


def by_id(policy_id: str) -> dict | None:
    return next((p for p in policies() if p["policy_id"] == policy_id), None)


def withdrawn(policy_id: str) -> bool:
    p = by_id(policy_id)
    return bool(p and p["status"] == "withdrawn")


def display_name(r: dict) -> str:
    return f"{r['insurer']}, {r['product']}"


def doc_kind(product: str) -> str | None:
    p = product.lower()
    return "brochure" if "brochure" in p else "prospectus" if "prospectus" in p else None


def _norm(text: str) -> str:
    return " " + re.sub(r"[^\wऀ-ॿ']+", " ", text.lower()).strip() + " "


def _spans(text: str, alias: str) -> list[tuple[int, int]]:
    # word boundaries via the padded, punctuation free form; Devanagari matches as a substring
    return [(m.start(), m.end()) for m in re.finditer(re.escape(f" {alias} "), text)]


def mentioned(text: str) -> tuple[list[str], str]:
    """Policy ids named in the text, and the text with those names removed.

    An alias can belong to several products: "HDFC" or "Care" names every product of that insurer,
    "Optima Secure" names one. Longer aliases are matched first. A name shared by several products
    is narrowed by a more specific one in the same text ("HDFC Optima Restore" is one product), and
    left as the whole family when nothing narrows it, so the copilot asks which exact product.
    """
    t = _norm(text)
    cut = t
    pols = policies()
    owners: dict[str, list[str]] = {}
    for p in pols:
        for a in p["aliases"]:
            owners.setdefault(a, []).append(p["policy_id"])
    sets: list[list[str]] = []
    for a in sorted(owners, key=len, reverse=True):
        while _spans(cut, a):
            if owners[a] not in sets:
                sets.append(owners[a])
            cut = cut.replace(f" {a} ", " ")
    if not sets:  # close spelling, e.g. "oriantal", "sundram"; only words of 5+ letters
        single = {a: ids for a, ids in owners.items() if " " not in a and len(a) >= 5}
        for w in cut.split():
            if len(w) >= 5 and w not in FILLER:
                hit = difflib.get_close_matches(w, single, n=1, cutoff=0.84)
                if hit and single[hit[0]] not in sets:
                    sets.append(single[hit[0]])
                    cut = cut.replace(f" {w} ", " ")
    if not sets:
        # "Star", "Care", "Royal", "Max": too common to match inside a sentence ("star rating", "day
        # care"), so they name their products only when the message is that word and nothing else
        words = [w for w in cut.split() if w not in FILLER]
        if len(words) == 1:
            ids = [p["policy_id"] for p in pols if words[0] in p["solo"]]
            if ids:
                sets.append(ids)
                cut = cut.replace(f" {words[0]} ", " ")
    found: list[str] = []
    for s_ in sets:
        if any(set(o) < set(s_) for o in sets):  # a more specific name narrows this one
            continue
        found += [i for i in s_ if i not in found]
    return found, cut


def one_family(ids: list[str]) -> bool:
    """True when the ids share a name the agent can use for all of them ("ICICI" names ICICI Lombard's
    health policy and ICICI Prudential's term plans; "Star" names four Star Health products): the agent
    named a brand, not two policies to choose between."""
    pols = [p for p in policies() if p["policy_id"] in ids]
    if len(pols) < 2:
        return False
    common = set(pols[0]["aliases"] + pols[0]["solo"])
    for p in pols[1:]:
        common &= set(p["aliases"] + p["solo"])
    return bool(common)


# "ICICI health policy", "HDFC term plan": the kind of cover narrows a brand's list
CATEGORY_RE = {
    "health": re.compile(r"\b(health|mediclaim|medical|hospital\w*|swasthya|sehat|room rent|kamra|icu|maternity|co-?pay\w*"
                         r"|pre-?existing|cashless|day ?care|ayush|cataract|surgery)\b|स्वास्थ्य|हेल्थ|मेडिक्लेम|अस्पताल|रूम रेंट", re.I),
    "term": re.compile(r"\b(term|life cover|life insurance|jeevan bima|death (cover|benefit)|sum assured|maturity|suicide"
                         r"|return of premium)\b|टर्म|जीवन बीमा|मृत्यु", re.I),
}
CATEGORY_NAME = {"health": {"en": "health", "hinglish": "health", "hi": "हेल्थ"},
                 "term": {"en": "term", "hinglish": "term", "hi": "टर्म"}}


def category_in(text: str) -> str | None:
    hits = [c for c, rx in CATEGORY_RE.items() if rx.search(text)]
    return hits[0] if len(hits) == 1 else None


def narrow_by_category(ids: list[str], rest: str) -> list[str]:
    """Keep the products of the kind the agent asked for. The words are read from the text left after
    the policy names are removed, so "Star Health" (a name) does not count as asking for health."""
    cat = category_in(rest)
    if not cat or len(ids) < 2:
        return ids
    kept = [i for i in ids if (by_id(i) or {}).get("category") == cat]
    return kept or ids


def group_name(ids: list[str]) -> str:
    """What the agent called the group: the insurer when there is one, else the shared name (ICICI)."""
    pols = [p for p in policies() if p["policy_id"] in ids]
    ins = {p["insurer"] for p in pols}
    if len(ins) == 1:
        return pols[0]["insurer"]
    common = set(pols[0]["aliases"] + pols[0]["solo"])
    for p in pols[1:]:
        common &= set(p["aliases"] + p["solo"])
    latin = sorted((a for a in common if a.isascii()), key=len)
    return latin[0].upper() if latin and len(latin[0]) <= 5 else (latin[0].title() if latin else pols[0]["insurer"])


def strip_names(text: str) -> str:
    """The question without policy names, for retrieval and the answer prompt.

    "SBI ya United India, room rent kitna hai?" -> "room rent kitna hai?". The names chose the
    policy already; left in, they pull premium and discount pages into the search.
    """
    out = text
    for a in sorted({a for p in policies() for a in p["aliases"]}, key=len, reverse=True):
        pat = r"[\W_]+".join(re.escape(w) for w in a.split())
        out = re.sub(rf"(?<![\wऀ-ॿ]){pat}(?![\wऀ-ॿ])", " ", out, flags=re.I)
    out = re.sub(r"\b(?:policy|policies|insurance|health)\b(?=\s+(?:mein|me|ki|ka|ke|में|की|का|के)\b)", " ", out, flags=re.I)
    # leading connectors left behind ("ya", "mein", "में"); \b does not work after Devanagari vowel signs
    out = re.sub(r"^[\s,;:/-]*(?:(?:ya|or|aur|and|vs|या|और|mein|me|में|ki|ka|ke|की|का|के|wali|wala|वाली|वाला)"
                 r"(?=[\s,;:/-]|$)[\s,;:/-]*)*", "", out, flags=re.I)
    out = re.sub(r"\s+", " ", out).strip(" ,;:-")
    return out if len(re.findall(r"[\wऀ-ॿ]+", out)) >= 2 else text


def other_insurer(text: str) -> str | None:
    t = _norm(text)
    for key, name in OTHER_INSURERS.items():
        if f" {key} " in t:
            return name
    return None


def selection_only(rest: str) -> bool:
    """True when nothing but filler is left after removing the policy name, e.g. "SBI dekhna hai"."""
    return not [w for w in rest.split() if w not in FILLER and not w.isdigit()]


def by_number(text: str) -> str | None:
    m = re.fullmatch(r"\s*(?:no\.?|number|#)?\s*(\d{1,2})\s*[.)]?\s*", text.lower())
    if m:
        n = int(m.group(1))
        return next((p["policy_id"] for p in policies() if p["n"] == n), None)
    return None


def _label(p: dict) -> str:
    """Short name for buttons; tapping one sends it as the agent's message, so it must be an alias.
    The manifest "label" column sets it; without one it is derived from the insurer's name."""
    return (p.get("label") or "").strip() or (p["insurer"].replace(" General Insurance", "")
                                              .replace(" Insurance Company", "").replace(" Insurance", "").replace("The ", ""))


def options(only: list[str] | None = None) -> list[dict]:
    out = [{"n": p["n"], "policy_id": p["policy_id"], "name": p["name"], "label": _label(p),
            "status": p["status"], "replaced_by": p["replaced_by"], "category": p["category"]}
           for p in policies() if not only or p["policy_id"] in only]
    if only and len(out) > 1:
        notes = differences([o["policy_id"] for o in out])
        for o in out:
            o["differs"] = notes.get(o["policy_id"], "")
    # products still on sale first; a withdrawn one is shown last, marked, never as the default
    return sorted(out, key=lambda o: (o["status"] == "withdrawn", o["n"]))


# ------------------------------------------------------------------ telling look-alike products apart

def _fact_numbers(policy_id: str) -> dict:
    from fact_table import load_facts
    for f in load_facts():
        if f["policy_id"] == policy_id:
            return {r["attribute"]: (r.get("numbers") or {}) for r in f["rows"]
                    if r["plan"] == "ALL" and r["status"] == "stated"}
    return {}


def _lakh(n) -> str:
    n = float(n)
    return f"{n / 1e7:g} crore" if n >= 1e7 else f"{n / 1e5:g} lakh"


def _features(p: dict) -> list[tuple[str, str]]:
    """(feature, short text) pairs in priority order; the first ones that differ between sibling
    products are shown next to each option."""
    num = _fact_numbers(p["policy_id"])
    prod = p["product"].lower()
    out = []   # health or term is shown as a tag on the card, not repeated here
    if p["status"] == "withdrawn":
        rep = by_id(p["replaced_by"]) if p["replaced_by"] else None
        out.append(("status", "stopped" + (f", replaced by {_label(rep)}" if rep else "")))
    if "top-up" in prod or "top up" in prod:
        out.append(("kind", "top-up cover over a deductible"))
    elif "brochure" in prod or "prospectus" in prod:
        out.append(("kind", "brochure only" if "brochure" in prod else "prospectus only"))
    age = num.get("entry_age", {})
    lo, hi = age.get("adult_min_years"), age.get("adult_max_years")
    if lo and lo >= 45:
        out.append(("age", f"for ages {lo}+"))
    elif hi:
        out.append(("age", f"entry up to {hi} years"))
    elif lo:
        out.append(("age", f"adults from {lo} years"))
    sp = num.get("specific_disease_waiting", {})
    if sp.get("diabetes_overrides_ped") and sp.get("diabetes_months") is not None:
        out.append(("diabetes", f"diabetes complications covered after {sp['diabetes_months']} months"))
    if num.get("ped_waiting", {}).get("months"):
        out.append(("ped", f"pre-existing disease wait {num['ped_waiting']['months']} months"))
    rr = num.get("room_rent", {})
    if rr.get("kind") == "no_limit":
        out.append(("room", "no room rent limit"))
    elif rr.get("kind") == "percent_si" and rr.get("percent_of_si"):
        out.append(("room", f"room rent {rr['percent_of_si']:g}% of sum insured a day"))
    elif rr.get("kind") == "rupees" and rr.get("rupees_per_day"):
        out.append(("room", f"room rent up to Rs {rr['rupees_per_day']:,.0f} a day"))
    elif rr.get("kind") == "category" and rr.get("category"):
        out.append(("room", rr["category"].split("/")[0].strip().lower()))
    cp = num.get("copay", {})
    if cp.get("percent") == 0:
        out.append(("copay", "no co-pay"))
    elif cp.get("percent"):
        out.append(("copay", f"{cp['percent']:g}% co-pay" + (f" {cp['condition']}" if cp.get("condition") and len(cp["condition"]) < 45 else "")))
    if num.get("restoration_reload", {}).get("available"):
        out.append(("restore", "sum insured restored after a claim"))
    si = num.get("sum_insured_options", {})
    if si.get("max_rupees"):
        out.append(("si", f"cover up to {_lakh(si['max_rupees'])}"))
    if p["uin"]:
        out.append(("uin", f"UIN {p['uin']}"))
    return out


def differences(ids: list[str], most: int = 2) -> dict[str, str]:
    """One short line per product saying how it differs from the others named with it.
    The manifest "differs" column overrides; otherwise it is built from the fact table, so it
    works for 500 products without writing each line by hand."""
    pols = [p for p in policies() if p["policy_id"] in ids]
    feats = {p["policy_id"]: dict(_features(p)) for p in pols}
    keys = [k for k, _ in _features(pols[0])] + [k for p in pols for k, _ in _features(p)]
    keys = list(dict.fromkeys(keys))
    varying = [k for k in keys if len({feats[i].get(k) for i in feats}) > 1]
    out = {}
    for p in pols:
        if p["differs"]:
            out[p["policy_id"]] = p["differs"]
            continue
        mine = feats[p["policy_id"]]
        # first what only this product has, then anything else that varies; the UIN only as a last resort
        unique = [k for k in varying if k in mine and k != "uin" and all(feats[o].get(k) != mine[k] for o in feats if o != p["policy_id"])]
        rest = [k for k in varying if k in mine and k not in unique and k != "uin"]
        keys_ = (unique + rest)[:most] or (["uin"] if "uin" in mine else [])
        out[p["policy_id"]] = "; ".join(mine[k] for k in keys_)
    return out


LIST_IN_MESSAGE = 5  # documents written out in a message; the rest are reached by name or the browser


def option_lines(opts: list[dict]) -> str:
    return "\n".join(f"{o['n']}. {o['name']}" + (f": {o['differs']}" if o.get("differs") else "") for o in opts)


def stopped_note(policy_id: str, lang: str) -> str | None:
    """The warning shown with every answer from a withdrawn product, naming the product that replaced it."""
    p = by_id(policy_id)
    if not p or p["status"] != "withdrawn":
        return None
    src = re.sub(r"^joinditto\.in[^:]*:\s*", "", p["status_source"]).strip() or "marked withdrawn in the manifest"
    src = "source: joinditto.in" if "joinditto" in p["status_source"] else src
    msg = TEXT["stopped"][lang].format(name=p["name"], source=src)
    new = by_id(p["replaced_by"]) if p["replaced_by"] else None
    if new:
        msg += " " + TEXT["stopped_new"][lang].format(new=new["name"], label=_label(new))
    return msg


def which_product_message(lang: str, ids: list[str]) -> tuple[str, list[dict]]:
    opts = options(ids)
    head = TEXT["which_product"][lang].format(insurer=group_name(ids), n=len(opts))
    return f"{head}\n{option_lines(opts)}\n{TEXT['which_hint'][lang]}", opts


def selected_message(policy_id: str, lang: str) -> str:
    p = next(p for p in policies() if p["policy_id"] == policy_id)
    msg = TEXT["selected"][lang].format(name=p["name"])
    kind = doc_kind(p["product"])
    if kind:
        msg += "\n" + TEXT["not_wording"][lang].format(kind=KIND[kind][lang])
    stop = stopped_note(policy_id, lang)
    if stop:
        msg += "\n" + stop
    return msg


# "hi", "hello there", "namaste ji", "good morning", "नमस्ते": a greeting with nothing else in it
GREETING_RE = re.compile(
    r"^\s*(hi+|hello+|hey+|helo|hallo|hii+|namaste|namaskar|namaskaar|namastey|pranam|good\s+(morning|afternoon|evening)|"
    r"नमस्ते|नमस्कार|हेलो|हाय|प्रणाम)(?:[\s,!.]+(there|ji|sir|madam|team|everyone|bima\s+saathi|saathi|copilot))?[\s,!.?]*$", re.I)


def greeting_only(text: str) -> bool:
    return bool(GREETING_RE.match(text or ""))


def greeting_lang(text: str) -> str:
    if re.search(r"[ऀ-ॿ]", text):
        return "hi"
    return "hinglish" if re.search(r"namas|pranam|\bji\b", text, re.I) else "en"


def greet_message(lang: str, policy_id: str | None = None) -> str:
    from config import AGENT_NAME
    if policy_id:
        p = next((p for p in policies() if p["policy_id"] == policy_id), None)
        if p:
            return TEXT["greet_again"][lang].format(name=p["name"])
    return TEXT["greet"][lang].format(agent=AGENT_NAME) + "\n" + TEXT["choose"][lang]


def choose_message(lang: str, opts: list[dict] | None = None, key: str = "choose", **fmt) -> str:
    """Asking which document: no list when nothing narrows it (the agent types a name or browses, which
    works for 300 documents as well as 5); a short list when a name matched several."""
    if opts is None:
        head = TEXT[key][lang].format(**fmt)
        return head if key == "choose" else head.rstrip(":：") + "\n" + TEXT["choose"][lang]
    return f"{TEXT[key][lang].format(**fmt)}\n{option_lines(opts)}\n{TEXT['choose_hint'][lang]}"

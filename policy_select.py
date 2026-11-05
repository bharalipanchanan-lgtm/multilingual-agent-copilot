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
OTHER_INSURERS = {"hdfc ergo": "HDFC ERGO", "hdfc": "HDFC ERGO", "star health": "Star Health",
                  "care health": "Care Health", "niva bupa": "Niva Bupa", "max bupa": "Niva Bupa",
                  "icici lombard": "ICICI Lombard", "bajaj allianz": "Bajaj Allianz", "tata aig": "Tata AIG",
                  "aditya birla": "Aditya Birla", "manipal cigna": "ManipalCigna", "new india": "New India Assurance",
                  "go digit": "Go Digit", "digit": "Go Digit", "acko": "Acko", "reliance general": "Reliance General",
                  "future generali": "Future Generali", "cholamandalam": "Cholamandalam MS",
                  "iffco tokio": "IFFCO Tokio", "liberty general": "Liberty General", "kotak": "Kotak General",
                  "magma": "Magma HDI", "universal sompo": "Universal Sompo", "galaxy health": "Galaxy Health",
                  "narayana": "Narayana Health", "lic": "LIC"}

# Words that carry no content in "I would like to review the SBI policy" style requests.
FILLER = set("""
i i'd id me my we us let lets let's would like want wanna to the a an of about for on in with and please pls kindly
review inspect check see look open use select choose show switch change go start load read study discuss
policy policies document documents doc wording wordings plan plans health insurance insurer company mediclaim
now ok okay yes sure thanks thank you this that one
mujhe mujhko humein hume hum main mai mein ko ka ki ke se par pe wala wali wale ab abhi chalo theek thik haan han
dekhna dekhni dekhne dekho dikhao dikhaiye kholo kholiye karna karni karo kariye chahta chahti chahte chahiye hai hain
hoon hu hun ho jao jaaye baat batao bataiye policy polisi document dastavez bima
""".split()) | {"मुझे", "मैं", "हमें", "को", "का", "की", "के", "से", "पर", "वाली", "वाला", "अब", "ठीक", "है", "हैं",
                "हूँ", "हूं", "देखना", "देखनी", "देखिए", "दिखाओ", "दिखाइए", "खोलो", "चाहता", "चाहती", "चाहिए",
                "पॉलिसी", "पालिसी", "दस्तावेज़", "दस्तावेज", "बीमा", "हेल्थ", "इंश्योरेंस", "कंपनी", "प्लान"}

TEXT = {
    "choose": {
        "en": "Which policy document would you like to inspect?",
        "hinglish": "Kaunsa policy document aapko dekhna hai?",
        "hi": "आप कौन सा पॉलिसी दस्तावेज़ देखना चाहते हैं?",
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
    "not_loaded": {
        "en": "I do not have a {insurer} policy loaded, so I cannot answer from it. These are the policies I have:",
        "hinglish": "Mere paas {insurer} ki koi policy loaded nahi hai, isliye main usse jawab nahi de sakta. Yeh policies hain:",
        "hi": "मेरे पास {insurer} की कोई पॉलिसी लोड नहीं है, इसलिए मैं उससे जवाब नहीं दे सकता। ये पॉलिसी उपलब्ध हैं:",
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
        aliases = [a.strip().lower() for a in (r.get("aliases") or "").split(";") if a.strip()]
        out.append({"n": len(out) + 1, "policy_id": r["policy_id"], "insurer": r["insurer"],
                    "product": r["product"], "name": display_name(r), "aliases": aliases})
    return out


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
    """Policy ids named in the text, and the text with those names removed."""
    t = _norm(text)
    found, cut = [], t
    pols = policies()
    for p in pols:
        # remove every alias of the policy ("Oriental Sampoorna Swasthya Suraksha" holds three)
        for a in sorted(p["aliases"], key=len, reverse=True):
            while _spans(cut, a):
                if p["policy_id"] not in found:
                    found.append(p["policy_id"])
                cut = cut.replace(f" {a} ", " ")
    if not found:  # close spelling, e.g. "oriantal", "sundram"; only words of 5+ letters
        single = {a: p["policy_id"] for p in pols for a in p["aliases"] if " " not in a and len(a) >= 5}
        for w in cut.split():
            if len(w) >= 5 and w not in FILLER:
                hit = difflib.get_close_matches(w, single, n=1, cutoff=0.84)
                if hit and single[hit[0]] not in found:
                    found.append(single[hit[0]])
                    cut = cut.replace(f" {w} ", " ")
    return found, cut


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


def options(only: list[str] | None = None) -> list[dict]:
    return [{"n": p["n"], "policy_id": p["policy_id"], "name": p["name"],
             "label": p["insurer"].replace(" General Insurance", "").replace(" Insurance Company", "")
                                  .replace(" Insurance", "").replace("The ", "")}
            for p in policies() if not only or p["policy_id"] in only]


def option_lines(opts: list[dict]) -> str:
    return "\n".join(f"{o['n']}. {o['name']}" for o in opts)


def selected_message(policy_id: str, lang: str) -> str:
    p = next(p for p in policies() if p["policy_id"] == policy_id)
    msg = TEXT["selected"][lang].format(name=p["name"])
    kind = doc_kind(p["product"])
    if kind:
        msg += "\n" + TEXT["not_wording"][lang].format(kind=KIND[kind][lang])
    return msg


def choose_message(lang: str, opts: list[dict] | None = None, key: str = "choose", **fmt) -> str:
    opts = opts or options()
    return f"{TEXT[key][lang].format(**fmt)}\n{option_lines(opts)}\n{TEXT['choose_hint'][lang]}"

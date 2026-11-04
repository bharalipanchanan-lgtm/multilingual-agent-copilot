"""Question -> grounded answer with clause citations, or a refusal.

Pipeline
  1. detect language (English, Hindi in Devanagari, Hinglish in Roman script)
  2. route: out of scope (premium, hospital lists, claim status) -> refuse without guessing
            comparison across policies -> answered from the verified fact table (compare.py)
            otherwise single policy
  3. retrieve top k clauses for the chosen policy, expand to the rest of each clause
  4. generate from those clauses only (generate.py backends), citing [n]
  5. check every number in the answer against the cited text; block the answer if one is missing
  6. return answer + clause cards (quoted sentence, page, section)

ask_stream() yields events so the API can stream tokens:
  {"type": "meta", ...} {"type": "token", "text": ...} {"type": "final", ...}
"""
import re
import time
from typing import Iterator

from config import CLAUSE_CHARS, MAX_CLAUSES, NEIGHBOURS, RETRIEVE_K
from generate import ExtractiveGenerator, Generator, get_generator

MIN_SCORE = 0.40  # lowest answerable top score was 0.458 in eval_retrieval; traps overlap, so the LLM and router also gate

NOT_STATED = {
    "en": "This is not stated in the policy document.",
    "hi": "यह जानकारी पॉलिसी दस्तावेज़ में नहीं दी गई है।",
    "hinglish": "Yeh jaankari policy document mein nahi di gayi hai.",
}
OUT_OF_SCOPE = {
    "premium": {
        "en": "Premium amounts are not part of the policy wording, so I cannot quote them. Please use the insurer's premium calculator or quote system.",
        "hi": "प्रीमियम की राशि पॉलिसी वर्डिंग में नहीं होती, इसलिए मैं इसे नहीं बता सकता। कृपया बीमा कंपनी का प्रीमियम कैलकुलेटर देखें।",
        "hinglish": "Premium ki amount policy wording mein nahi hoti, isliye main yeh nahi bata sakta. Insurer ka premium calculator ya quote system use karein.",
    },
    "hospitals": {
        "en": "The list of network hospitals is not in the policy document. It is maintained by the insurer or TPA and changes over time.",
        "hi": "नेटवर्क अस्पतालों की सूची पॉलिसी दस्तावेज़ में नहीं है। यह बीमा कंपनी या TPA के पास रहती है।",
        "hinglish": "Network hospitals ki list policy document mein nahi hai. Yeh insurer ya TPA ke paas hoti hai aur badalti rehti hai.",
    },
    "claim_status": {
        "en": "I cannot check claim status. I only answer from the policy wording.",
        "hi": "मैं क्लेम की स्थिति नहीं देख सकता। मैं केवल पॉलिसी वर्डिंग से जवाब देता हूँ।",
        "hinglish": "Main claim status check nahi kar sakta. Main sirf policy wording se jawab deta hoon.",
    },
}
BLOCKED_NOTE = {
    "en": "I could not verify a figure in the draft answer against the policy text, so here are the relevant clauses as written.",
    "hi": "उत्तर का एक आंकड़ा पॉलिसी के पाठ से मेल नहीं खाया, इसलिए यहाँ संबंधित क्लॉज़ जैसे लिखे हैं वैसे दिए गए हैं।",
    "hinglish": "Draft answer ka ek figure policy text se match nahi hua, isliye relevant clauses jaise likhe hain waise de raha hoon.",
}
EXTRACTIVE_NOTE = {
    "en": "Here is what the policy says:",
    "hi": "पॉलिसी में यह लिखा है:",
    "hinglish": "Policy mein yeh likha hai:",
}

HINGLISH_WORDS = {"kya", "hai", "hain", "ke", "ki", "ka", "liye", "mein", "kitna", "kitne", "kaunsi", "kaun",
                  "nahi", "nahin", "milta", "milega", "bhi", "par", "yeh", "ye", "kab", "kaise", "agar", "toh",
                  "jata", "jaata", "hota", "hoti", "lagta", "lagti", "wala", "wali", "kisi", "sakte", "chahiye", "mera",
                  "meri", "mere", "batao", "bataiye"}

ROUTES = [
    ("premium", re.compile(r"premium\s*(for|of|kitna|kitni|amount|kya hoga|kya hai)|how much .*premium|premium .*(year|lakh|sum insured|age)|प्रीमियम|quote for", re.I)),
    ("hospitals", re.compile(r"(which|list of|kaun\s?se|kaunse|konse)\s.*hospitals?|hospitals?\s+(in|near|list)|network hospital list|अस्पतालों की सूची", re.I)),
    ("claim_status", re.compile(r"claim status|status of (my )?claim|claim ka status", re.I)),
]
COMPARE_RE = re.compile(r"\bcompare\b|\bcomparison\b|which polic(y|ies)|kaun\s?si polic|kaunsi polic|konsi polic|sabse (accha|achha|best)|\bvs\.?\b|versus|कौन सी पॉलिसी", re.I)


def detect_lang(q: str) -> str:
    if re.search(r"[ऀ-ॿ]", q):
        return "hi"
    words = set(re.findall(r"[a-z]+", q.lower()))
    return "hinglish" if len(words & HINGLISH_WORDS) >= 2 else "en"


def route(q: str) -> str:
    for name, rx in ROUTES:
        if rx.search(q):
            return name
    if COMPARE_RE.search(q):
        return "compare"
    return "single"


SYSTEM_PROMPT = """You help Indian insurance agents answer customer questions about a health insurance policy.
You are given numbered clauses from the policy wording. Rules:
1. Answer ONLY from the clauses. Do not use outside knowledge and do not guess.
2. After each sentence, cite the clause numbers it comes from in square brackets, like [1] or [2][3].
3. Copy every number, percentage, amount and time period exactly as written in the clauses.
4. If the clauses do not answer the question, reply with exactly: NOT_STATED
   Never conclude that something does not exist just because no clause mentions it.
5. Write 2 to 4 short sentences an agent can say to a customer. Include conditions and exceptions that change the answer.
   For a named disease, check every clause: if it appears in a specific waiting period list AND the pre-existing disease rule could apply, state both periods and when each applies.
6. Clauses under an "Exclusions" part list what the policy does NOT pay for. A treatment listed there is not covered (unless the clause itself states an exception).
   Clauses under a "Definition" part only define words; they do not by themselves grant cover.
   An appendix "List of Expenses Generally Excluded" is a list of non-medical items such as consumables, not the policy's main exclusions.
7. Never use words like "lifetime", "guaranteed", "always", "all hospitals" or "no limit" unless that exact idea is written in a clause.
8. Write in the language you are told to use. Keep terms like "waiting period", "sum insured" and "pre-existing disease" in English.

Example
Clauses:
[1] (page 4, 4 Exclusions > 4.1 Pre-existing diseases) All pre-existing diseases ... until 48 months of continuous coverage has elapsed.
[2] (page 5, 4 Exclusions > 4.3 Specific waiting period) ii. Two years waiting period ... c. Hernia ...
Question: Hernia ka waiting period kitna hai?
Language: Hinglish (Hindi words in Roman script)
Answer: Hernia par 2 saal (two years) ka specific waiting period hai [2]. Agar hernia policy lene se pehle se hai, toh woh pre-existing disease hai aur 48 months of continuous coverage tak cover nahi hoga [1]."""

LANG_LINE = {
    "en": "English",
    "hi": "Hindi in Devanagari script",
    "hinglish": "Hinglish (Hindi words in Roman script)",
}


SUBHEAD_RE = re.compile(r"\b([ivx]{1,4})\.\s+([A-Z][A-Za-z ]{3,50}?(?:period|cover|limit|benefit)s?)\b")


def list_notes(question: str, text: str) -> list[str]:
    """For list clauses laid out in columns, say which sub-heading a matched item sits under.

    e.g. 'Diabetes' in clause 4.3 sits under 'ii. Two years waiting period'. Extracted text of
    two column lists interleaves items, which small models misread.
    """
    from retrieve import STOP
    notes = []
    for w in sorted({w for w in re.findall(r"[A-Za-z]{5,}", question) if w.lower() not in STOP}):
        m = re.search(rf"\b[a-z]\.\s+([^.]*?\b{re.escape(w)}\w*[^.]*?)(?=\s+[a-z]\.\s|$)", text, re.I)
        if not m:
            continue
        heads = [h for h in SUBHEAD_RE.finditer(text) if h.start() < m.start()]
        if heads:
            h = heads[-1]
            notes.append(f'Note: "{m.group(1).strip()[:60]}" is listed under "{h.group(1)}. {h.group(2)}".')
    return notes


def build_prompt(question: str, clauses: list[dict], product: str, lang: str = "en") -> str:
    parts = [f"Policy: {product}", "", "Clauses:"]
    for i, c in enumerate(clauses, 1):
        part = c.get("part") or ""
        tag = f"{part} > {c['section']}" if part and part != c["section"] else c["section"]
        notes = list_notes(question, c["text"])
        text = c["text"] if len(c["text"]) <= CLAUSE_CHARS else c["text"][:CLAUSE_CHARS].rsplit(" ", 1)[0] + " ..."
        parts.append(f"[{i}] (page {c['printed_page']}, {tag})\n{text}" + ("\n" + "\n".join(notes) if notes else ""))
    parts += ["", f"Question: {question}", f"Language: {LANG_LINE[lang]}", "Answer:"]
    return "\n".join(parts)


# ---------- number check ----------

NUM_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
             "nine": "9", "ten": "10", "twelve": "12", "fifteen": "15", "twenty": "20", "thirty": "30",
             "forty": "40", "forty-five": "45", "sixty": "60", "ninety": "90", "hundred": "100"}
DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    t = text.translate(DEV_DIGITS).lower()
    for w, d in NUM_WORDS.items():
        t = re.sub(rf"\b{w}\b", d, t)
    out = set()
    for m in NUM_RE.findall(t):
        n = m.replace(",", "").rstrip(".")
        if n:
            out.add(n.lstrip("0") or "0")
    return out


def check_numbers(answer: str, sources: list[str]) -> list[str]:
    """Numbers in the answer that appear in none of the cited sources."""
    body = re.sub(r"\[\d+\]", " ", answer)
    ans = _numbers(body)
    src = set()
    for s in sources:
        src |= _numbers(s)
    return sorted(n for n in ans if n not in src)


# ---------- quoting ----------

def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2}


def _clip(s: str, n: int = 400) -> str:
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " ..."


def best_sentence(chunk_text: str, answer: str, question: str) -> str:
    """The sentence (or pair of sentences) in the clause that best supports the answer."""
    # split at real sentence ends, not list markers like "a." or "ii."
    sents = [s.strip() for s in re.split(r"(?<=[a-z0-9)%]{3}[.;])\s+(?=[A-Z(\d])|\n", chunk_text) if s.strip()]
    windows = [s for s in sents if len(s) >= 40]
    windows += [sents[i] + " " + sents[i + 1] for i in range(len(sents) - 1)]
    windows = [w for w in windows if 40 <= len(w) <= 500] or [chunk_text]
    target = _tokens(answer) | _tokens(question)
    target_nums = _numbers(answer)
    def score(s):
        return (len(_tokens(s) & target) + 3 * len(_numbers(s) & target_nums), -len(s))
    best = max(windows, key=score)
    if best is chunk_text or len(best) > 400:
        # long list with no sentence breaks: centre a window on the most specific matching term
        low = chunk_text.lower()
        terms = sorted(target_nums, key=len, reverse=True) + sorted(target, key=len, reverse=True)
        pos = next((low.find(t) for t in terms if len(t) > 3 and low.find(t) >= 0), -1)
        if pos >= 0:
            a = max(0, pos - 150)
            a = chunk_text.rfind(" ", 0, a) + 1 if a else 0
            snippet = chunk_text[a:a + 320].rsplit(" ", 1)[0]
            return ("... " if a else "") + snippet + " ..."
    if score(best)[0] == 0:  # nothing overlaps (e.g. Hindi question, no answer): show the clause opening
        return _clip(chunk_text, 350)
    return best if len(best) <= 400 else best[:400].rsplit(" ", 1)[0] + " ..."


def card(c: dict, n: int, answer: str, question: str) -> dict:
    return {"n": n, "page": c["page"], "printed_page": c["printed_page"], "section": c["section"],
            "quote": best_sentence(c["text"], answer, question), "text": c["text"], "score": c.get("score"),
            "policy_id": c["policy_id"], "product": c.get("product", "")}


# ---------- pipeline ----------

def _retrieve(question: str, policy_id: str) -> list[dict]:
    from retrieve import expand_sections, keyword_hits, search
    hits = search(question, policy_id, RETRIEVE_K)
    kw = keyword_hits(question, policy_id, {h["id"] for h in hits})
    for k in kw:
        k["score"] = hits[0]["score"] if hits else 0.5
    hits = hits[:1] + kw + hits[1:]  # keyword matches right after the best semantic hit
    if NEIGHBOURS:
        hits = expand_sections(hits, max_extra=2)
    return hits[:MAX_CLAUSES]


def _extractive(question, lang, clauses, note=None) -> tuple[str, list[dict]]:
    direct = [c for c in clauses if not c.get("expanded_from")] or clauses
    top = sorted(direct, key=lambda c: -(c.get("score") or 0))[:2]
    cards = [card(c, i, "", question) for i, c in enumerate(top, 1)]
    lines = [note or EXTRACTIVE_NOTE[lang]]
    for cd in cards:
        lines.append(f"“{cd['quote']}” [{cd['n']}]")
    return "\n".join(lines), cards


def ask_stream(question: str, policy_id: str, gen: Generator | None = None) -> Iterator[dict]:
    t0 = time.time()
    gen = gen or get_generator()
    lang = detect_lang(question)
    r = route(question)
    yield {"type": "meta", "lang": lang, "route": r, "backend": gen.name}

    if r in OUT_OF_SCOPE:
        yield {"type": "final", "status": "refused", "reason": r, "answer": OUT_OF_SCOPE[r][lang],
               "citations": [], "lang": lang, "backend": gen.name, "ms": int((time.time() - t0) * 1000)}
        return
    if r == "compare":
        from compare import compare_answer
        yield {"type": "final", **compare_answer(question, lang), "lang": lang, "backend": "fact_table",
               "ms": int((time.time() - t0) * 1000)}
        return

    clauses = _retrieve(question, policy_id)
    top = max((c["score"] for c in clauses), default=0)
    t_ret = int((time.time() - t0) * 1000)
    if not clauses or top < MIN_SCORE:
        yield {"type": "final", "status": "not_stated", "answer": NOT_STATED[lang], "citations": [],
               "lang": lang, "backend": gen.name, "top_score": top, "ms": t_ret}
        return

    if isinstance(gen, ExtractiveGenerator):
        ans, cards = _extractive(question, lang, clauses)
        yield {"type": "final", "status": "answered", "answer": ans, "citations": cards, "lang": lang,
               "backend": gen.name, "top_score": top, "ms": int((time.time() - t0) * 1000)}
        return

    product = clauses[0].get("product", "")
    prompt = build_prompt(question, clauses, product, lang)
    buf, first_tok = "", None
    for tok in gen.stream(SYSTEM_PROMPT, prompt):
        if first_tok is None:
            first_tok = int((time.time() - t0) * 1000)
        buf += tok
        if not buf.lstrip().startswith("NOT_STATED"[: len(buf.lstrip())]):  # do not stream the sentinel
            yield {"type": "token", "text": tok}
    answer = buf.strip()
    ms = int((time.time() - t0) * 1000)
    common = {"lang": lang, "backend": gen.name, "top_score": top, "ms": ms, "first_token_ms": first_tok,
              "retrieval_ms": t_ret}

    if answer.startswith("NOT_STATED") or not answer:
        yield {"type": "final", "status": "not_stated", "answer": NOT_STATED[lang], "citations": [], **common}
        return

    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer) if 0 < int(n) <= len(clauses)})
    if not cited:  # model forgot to cite: attach the clauses that best overlap the answer
        ranked = sorted(range(len(clauses)), key=lambda i: -len(_tokens(clauses[i]["text"]) & _tokens(answer)))
        cited = [i + 1 for i in ranked[:2]]
    src = lambda i: clauses[i - 1]["text"] + " " + clauses[i - 1]["section"]
    missing = check_numbers(answer, [src(i) for i in cited])
    if missing:  # citation repair: the figure may be right but cited against the wrong clause
        for n in list(missing):
            holder = next((i for i in range(1, len(clauses) + 1) if n in _numbers(src(i))), None)
            if holder and holder not in cited and len(cited) < 5:
                cited.append(holder)
        cited.sort()
        missing = check_numbers(answer, [src(i) for i in cited])
    if missing:
        ans, cards = _extractive(question, lang, clauses, note=BLOCKED_NOTE[lang])
        yield {"type": "final", "status": "blocked", "answer": ans, "draft": answer, "unsupported_numbers": missing,
               "citations": cards, **common}
        return

    cards = [card(clauses[i - 1], i, answer, question) for i in cited]
    yield {"type": "final", "status": "answered", "answer": answer, "citations": cards, **common}


def ask(question: str, policy_id: str, gen: Generator | None = None) -> dict:
    final = {}
    for ev in ask_stream(question, policy_id, gen):
        if ev["type"] == "final":
            final = ev
    return final


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--policy", default="national_mediclaim")
    ap.add_argument("--backend")
    a = ap.parse_args()
    res = ask(a.question, a.policy, get_generator(a.backend))
    print(json.dumps({k: v for k, v in res.items() if k != "citations"}, ensure_ascii=False, indent=2))
    for c in res.get("citations", []):
        print(f"  [{c['n']}] p{c['printed_page']} (pdf {c['page']}) {c['section']}: {c['quote']}")

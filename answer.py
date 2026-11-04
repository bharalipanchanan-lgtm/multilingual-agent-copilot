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

from config import NEIGHBOURS, RETRIEVE_K
from generate import ExtractiveGenerator, Generator, get_generator

MIN_SCORE = 0.45  # below this top retrieval score we do not attempt an answer (tune with eval_retrieval.py)

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
1. Answer ONLY from the clauses. Do not use outside knowledge, do not guess, do not generalise from other policies.
2. Cite the clause numbers you used in square brackets, like [1] or [2][3], right after the sentence they support.
3. Copy every number, percentage, amount and time period exactly as it appears in the clauses.
4. If the clauses do not answer the question, reply with exactly: NOT_STATED
   Never infer that something does not exist because it is missing (for example, never say "there is no co-pay" unless a clause says so).
5. Be short: 2 to 4 sentences in plain language an agent can repeat to a customer. Mention conditions and exceptions that change the answer.
6. Reply in the same language and script as the question: English, Hindi in Devanagari, or Hinglish in Roman script. Keep policy terms like "waiting period" and "sum insured" in English."""


def build_prompt(question: str, clauses: list[dict], product: str) -> str:
    parts = [f"Policy: {product}", "", "Clauses:"]
    for i, c in enumerate(clauses, 1):
        parts.append(f"[{i}] (page {c['printed_page']}, {c['section']})\n{c['text']}")
    parts += ["", f"Question: {question}", "Answer:"]
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


def best_sentence(chunk_text: str, answer: str, question: str) -> str:
    sents = [s.strip() for s in re.split(r"(?<=[.;])\s+|\n", chunk_text) if len(s.strip()) > 15]
    if not sents:
        return chunk_text[:300]
    target = _tokens(answer) | _tokens(question)
    target_nums = _numbers(answer)
    def score(s):
        return len(_tokens(s) & target) + 3 * len(_numbers(s) & target_nums)
    best = max(sents, key=score)
    return best if len(best) <= 400 else best[:400].rsplit(" ", 1)[0] + " ..."


def card(c: dict, n: int, answer: str, question: str) -> dict:
    return {"n": n, "page": c["page"], "printed_page": c["printed_page"], "section": c["section"],
            "quote": best_sentence(c["text"], answer, question), "text": c["text"], "score": c.get("score"),
            "policy_id": c["policy_id"], "product": c.get("product", "")}


# ---------- pipeline ----------

def _retrieve(question: str, policy_id: str) -> list[dict]:
    from retrieve import expand_sections, search
    hits = search(question, policy_id, RETRIEVE_K)
    if NEIGHBOURS:
        hits = expand_sections(hits)
    return hits


def _extractive(question, lang, clauses, note=None) -> tuple[str, list[dict]]:
    top = sorted(clauses, key=lambda c: -(c.get("score") or 0))[:2]
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
    prompt = build_prompt(question, clauses, product)
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
    cited_clauses = [clauses[i - 1] for i in cited]
    missing = check_numbers(answer, [c["text"] + " " + c["section"] for c in cited_clauses])
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

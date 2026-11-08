"""One chat turn: pick or keep the policy from what the agent typed, then answer.

Events are those of answer.ask_stream plus:
  {"type": "policy", "policy_id", "name", "insurer", "product"}   the policy in use changed
  final status "selected"        the agent only chose a policy; the copilot confirms and asks what to look at
  final status "choose_policy"   no policy chosen yet, more than one named, or one that is not loaded;
                                 "options" lists the loaded policies, "pending" says the text was a real
                                 question the client may re-send once a policy is chosen
"""
import re
import time
from typing import Iterator

from answer import OUT_OF_SCOPE, ask_stream, detect_lang, route
from policy_select import (FILLER, _norm, by_number, choose_message, greet_message, greeting_lang, greeting_only,
                           mentioned, options, other_insurer, policies, selected_message, selection_only, strip_names)

# "Which policy document can I inspect?", "policy badlo", "switch policy": the agent wants the list,
# not a comparison (COMPARE_RE also matches "which policy").
CHOOSE_RE = re.compile(r"(which|what|konsa|kaunsa|kaun sa|konsi|kaunsi|कौन सा|कौन सी).{0,25}(policy|policies|पॉलिसी).{0,25}"
                       r"(document|inspect|available|loaded|dekh|देख|उपलब्ध|hai\b|है)"
                       r"|\b(change|switch)\b.{0,12}\bpolic|polic\w*\s+(badlo|badliye|badalna|change)"
                       r"|\b(dusri|doosri|another|other)\s+polic|पॉलिसी\s+बदल", re.I)

CHOOSE_WORDS = {"which", "what", "konsa", "kaunsa", "konsi", "kaunsi", "kaun", "sa", "si", "can", "could", "may",
                "available", "loaded", "list", "options", "dekh", "dekhe", "dekhen", "dekhu", "inspect", "documents", "sakte", "sakta", "sakti", "hain", "another", "other",
                "dusri", "doosri", "badlo", "badliye", "badalna", "are", "is", "there", "do", "you", "have",
                "कौन", "सा", "सी", "उपलब्ध", "बदलो", "बदलनी", "बदलना", "दूसरी", "सकते"}

HINGLISH_SELECT = {"mujhe", "dekhna", "dekhni", "dikhao", "kholo", "chahiye", "chahta", "chahti", "wali", "wala",
                   "kaunsa", "konsa", "karo", "karna", "abhi", "chalo", "vali", "vala", "chahie", "mujhko"}


def chat_lang(text: str) -> str:
    lang = detect_lang(text)
    if lang == "en" and set(re.findall(r"[a-z]+", text.lower())) & HINGLISH_SELECT:
        return "hinglish"
    return lang


def converse(question: str, policy_id: str | None, gen, held: bool = False,
             prev_lang: str | None = None) -> Iterator[dict]:
    """held: the page is re-sending a question it held while the agent chose a policy, so the
    policy just chosen is used and policy names inside the question are not read again (the
    question may name two policies, which is why it was held).
    prev_lang: language of the conversation so far, used when the text is only a name or a number."""
    t0 = time.time()
    lang = chat_lang(question)
    r = route(question)
    num = by_number(question)
    found, rest = ([num], "") if num else mentioned(question)
    if not rest.split() and prev_lang in ("en", "hi", "hinglish"):
        lang = prev_lang  # "SBI", "2" or a tapped name carry no language of their own
    if held and policy_id:
        found, rest = [], question
    known = {p["policy_id"]: p for p in policies()}
    if policy_id not in known:
        policy_id = None

    def final(status, answer, **extra):
        return {"type": "final", "status": status, "answer": answer, "citations": [], "lang": lang,
                "backend": "policy_select", "ms": int((time.time() - t0) * 1000), "policy_id": policy_id, **extra}

    if greeting_only(question):
        # "Hi" opens the conversation: introduce the copilot, then ask which document (or, if one is
        # already in use, say which). Nothing is retrieved or generated.
        glang = greeting_lang(question) if not prev_lang or greeting_lang(question) != "en" else prev_lang
        yield {"type": "meta", "lang": glang, "route": "greeting", "backend": "policy_select"}
        if policy_id:
            yield {**final("greeting", greet_message(glang, policy_id)), "lang": glang}
        else:
            yield {**final("choose_policy", greet_message(glang), options=options(), pending=False), "lang": glang,
                   "greeting": True}
        return

    other = None if held else other_insurer(question)
    if other and not found:
        yield {"type": "meta", "lang": lang, "route": "choose_policy", "backend": "policy_select"}
        yield final("choose_policy", choose_message(lang, key="not_loaded", insurer=other),
                    options=options(), pending=False)
        return

    wants_list = CHOOSE_RE.search(question) and not [
        w for w in _norm(question).split() if w not in FILLER and w not in CHOOSE_WORDS]
    if not found and wants_list:
        yield {"type": "meta", "lang": lang, "route": "choose_policy", "backend": "policy_select"}
        yield final("choose_policy", choose_message(lang), options=options(), pending=False)
        return

    if r == "recommend":
        # a shortlist across every loaded policy; no policy needs to be chosen first
        from rank import rank_answer
        yield {"type": "meta", "lang": lang, "route": "recommend", "backend": "fact_table"}
        yield {"type": "final", **rank_answer(question, lang), "lang": lang, "backend": "fact_table",
               "ms": int((time.time() - t0) * 1000), "policy_id": policy_id}
        return

    if r == "compare":
        from compare import compare_answer
        yield {"type": "meta", "lang": lang, "route": "compare", "backend": "fact_table"}
        only = found if len(found) >= 2 else None
        yield {"type": "final", **compare_answer(question, lang, only=only), "lang": lang, "backend": "fact_table",
               "ms": int((time.time() - t0) * 1000), "policy_id": policy_id}
        return

    if len(found) > 1:
        yield {"type": "meta", "lang": lang, "route": "choose_policy", "backend": "policy_select"}
        yield final("choose_policy", choose_message(lang, options(found), key="ambiguous"),
                    options=options(found), pending=not selection_only(rest))
        return

    if found:
        if found[0] != policy_id:
            policy_id = found[0]
            p = known[policy_id]
            yield {"type": "policy", "policy_id": policy_id, "name": p["name"], "insurer": p["insurer"],
                   "product": p["product"]}
        if selection_only(rest):
            yield {"type": "meta", "lang": lang, "route": "select", "backend": "policy_select"}
            yield final("selected", selected_message(policy_id, lang))
            return

    if policy_id is None and r not in OUT_OF_SCOPE:
        yield {"type": "meta", "lang": lang, "route": "choose_policy", "backend": "policy_select"}
        yield final("choose_policy", choose_message(lang), options=options(), pending=True)
        return

    for ev in ask_stream(strip_names(question), policy_id, gen):
        if ev.get("type") == "final":
            ev["policy_id"] = policy_id
        yield ev

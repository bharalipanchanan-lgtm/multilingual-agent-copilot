"""Short answers to simple questions, straight from the fact table, in well under a second.

"Room rent kitna hai?", "waiting period?", "age limit kya hai?", "co-pay hai?" are answered from the
policy's fact row: the value, the verbatim line, its page and clause. No retrieval, no model.

A question is simple only when nothing is left after removing the topic words and filler. "Cataract
ka waiting period" keeps "cataract", so it goes to the full clause search instead, where the exact
line for cataract is found and quoted. Premium is refused earlier (answer.route), never answered here.
"""
import re

from fact_table import ATTRIBUTES, load_facts, manifest

# topic -> fact attributes it answers, and the words that name it
TOPICS = [
    (["ped_waiting"], r"pre[- ]?existing(?: diseases?| illness(?:es)?| conditions?)?|\bped\b|pehle se (?:wali |ki )?bimari(?:yon|yan)?|पहले से (?:मौजूद )?बीमारी"),
    (["initial_waiting"], r"initial waiting(?: period)?|first 30 days|30 days? waiting|shuru(?:aati)? ka waiting|शुरुआती वेटिंग"),
    (["initial_waiting", "ped_waiting", "specific_disease_waiting"], r"waiting periods?|waiting time|wait(?:ing)?|intez?aa?r|प्रतीक्षा(?: अवधि)?|वेटिंग(?: पीरियड)?"),
    (["room_rent"], r"room rent(?: limit| cap)?|room limit|room category|kamre? ka kiraya|kamra|रूम रेंट|कमरे? का किराया"),
    (["icu_limit"], r"\bicu\b(?: limit| charges)?"),
    (["entry_age"], r"(?:entry|maximum|minimum|max|min) age|age limit|age (?:criteria|eligibility)|umr?a?r? (?:seema|limit)|kitni umr?a?r?|kitne saal tak|उम्र(?: सीमा)?|आयु(?: सीमा)?"),
    (["copay"], r"co[- ]?pay(?:ment)?s?|सह[- ]?भुगतान|को[- ]?पे"),
    (["sum_insured_options"], r"sum insured(?: options?)?|cover amount|kitne (?:lakh|ka) cover|बीमा राशि"),
    (["no_claim_bonus"], r"no claim bonus|cumulative bonus|\bncb\b"),
    (["moratorium"], r"moratorium(?: period)?"),
]
FILLER = set("""what whats what's is are the a an of for in on this policy plan product its it does do there any how much many
long kya kitna kitni kitne hai hain h ka ki ke mein me main batao bataiye bata please pls tell me about limit period
options option available allowed maximum minimum max min upto up to hota hoti milta milega and or with under i we
details detail rule rules ok okay so then""".split()) | {"क्या", "है", "हैं", "का", "की", "के", "में", "कितना", "कितनी", "कितने", "बताइए", "बताओ", "इस", "पॉलिसी"}

LABEL = {"en": "{label}", "hinglish": "{label}", "hi": "{label}"}
TEXT = {
    "line": {"en": "Policy line, page {page}{clause}", "hinglish": "Policy ki line, page {page}{clause}", "hi": "पॉलिसी की पंक्ति, पेज {page}{clause}"},
    "not_written": {"en": "{label}: this is not written in this product's document.",
                    "hinglish": "{label}: yeh is product ke document mein likha nahi hai.",
                    "hi": "{label}: यह इस प्रोडक्ट के दस्तावेज़ में लिखा नहीं है।"},
    "draft": {"en": "From the fact table (a draft, not yet checked by a person; the line is checked against the PDF).",
              "hinglish": "Fact table se (draft, kisi ne abhi check nahi kiya; line PDF se match ki gayi hai).",
              "hi": "फैक्ट टेबल से (ड्राफ्ट, किसी व्यक्ति ने अभी जाँचा नहीं; पंक्ति PDF से मिलाई गई है)।"},
    "verified": {"en": "From the fact table, verified by a person.", "hinglish": "Fact table se, verified.",
                 "hi": "फैक्ट टेबल से, व्यक्ति द्वारा जाँचा गया।"},
}


def topic(question: str) -> list[str] | None:
    """The attributes a simple question asks for, or None when it asks about anything more."""
    from policy_select import mentioned
    _, rest = mentioned(question)            # policy names do not count as content
    t = " " + re.sub(r"[^\wऀ-ॿ' -]+", " ", rest.lower()) + " "
    attrs: list[str] = []
    for a, rx in TOPICS:
        if re.search(rx, t, re.I):
            attrs += [x for x in a if x not in attrs]
            t = re.sub(rx, " ", t, flags=re.I)
            if a == ["ped_waiting"] or a == ["initial_waiting"]:
                t = re.sub(TOPICS[2][1], " ", t, flags=re.I)  # "PED waiting period" is one topic
                break
    if not attrs:
        return None
    left = [w for w in t.split() if w not in FILLER and not w.isdigit()]
    return attrs if not left else None


def quick_answer(question: str, policy_id: str, lang: str) -> dict | None:
    attrs = topic(question)
    if not attrs:
        return None
    f = next((f for f in load_facts() if f["policy_id"] == policy_id and not f["legacy"]), None)
    if not f:
        return None
    rows = {r["attribute"]: r for r in f["rows"] if r["plan"] == "ALL"}
    plan_rows = [r for r in f["rows"] if r["plan"] != "ALL" and r["attribute"] in attrs]
    if plan_rows or any(a not in rows or rows[a]["status"] == "unclear" for a in attrs):
        return None  # plan specific or unclear: the full clause search answers it
    off = int(manifest()[policy_id].get("page_offset") or 0)
    lines, cites = [], []
    for a in attrs:
        r = rows[a]
        label = ATTRIBUTES[a]
        if r["status"] == "not_stated":
            lines.append(TEXT["not_written"][lang].format(label=label))
            continue
        e = r["evidence"][0]
        cites.append({"n": len(cites) + 1, "policy_id": policy_id, "product": f["product"],
                      "section": e.get("clause") or label, "page": e["page"], "printed_page": e["page"] - off,
                      "quote": e["quote"], "text": r["value"]})
        lines.append(f"{label}: {r['value']} [{len(cites)}]")
    verified = all(rows[a]["verified"] for a in attrs)
    if cites:  # a "not written" answer shows no line, so it does not claim one was checked
        lines.append(TEXT["verified" if verified else "draft"][lang])
    return {"status": "answered", "answer": "\n".join(lines), "citations": cites, "quick": True}

/* QuickPolicy agent core — the five agent rules, no DOM.
   Data: data/catalogue.json (verified facts, page + rule per value) and the
   close-kit copy. Policy chat drives a conversation on top of this.

   1  Exact product before any answer; never mix two products.
   2  Need path (customer need → product) and name path (product → check);
      the agent's own insurers come first.
   3  Best one and second best, one line why; one line why others miss;
      the date diabetes cover starts.
   4  Simple questions answered from facts in milliseconds; hard ones quote
      the exact line with page and rule; "not written" when it is not.
   5  Close kit: words to say, WhatsApp text, wait end date, papers, what not
      to promise. Stopped products point to their replacement. */

(() => {
  const fullName = (p) => (p.variant ? `${p.name} ${p.variant}` : p.name);
  const label = (p) => `${p.insurer} ${fullName(p)}`;
  const isUpload = (p) => p.source === "upload" || String(p.policy_id || p.id).startsWith("upload_");
  const policyIdOf = (p) => p.policy_id || p.id.replace(/-/g, "_");
  const rupees = (n) => `₹${Number(n).toLocaleString("en-IN")}`;

  function citePage(f) {
    if (!f) return null;
    if (f.printed_page != null) return { n: f.printed_page, pdf: f.pdf_page ?? f.printed_page, kind: "printed" };
    if (f.pdf_page != null) return { n: f.pdf_page, pdf: f.pdf_page, kind: "pdf" };
    return null;
  }
  const pageLabel = (c) => (!c ? "page not recorded" : c.kind === "printed" ? `Page ${c.n}` : `PDF page ${c.n}`);

  function waitEndDate(months, from = new Date()) {
    const d = new Date(from);
    d.setMonth(d.getMonth() + months);
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" });
  }
  const fmtMonths = (m) => (m % 12 === 0 ? `${m / 12} year${m === 12 ? "" : "s"}` : `${m} months`);
  function fmtDate(iso) {
    const d = new Date(`${iso}T00:00:00`);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  }

  const words = (s) => s.toLowerCase().normalize("NFKC").split(/[^a-z0-9\u0900-\u097f+]+/).filter(Boolean);
  const has = (text, list) => list.some((w) => (/^[a-z0-9 .+-]+$/.test(w) ? new RegExp(`\\b${w.replace(/[.+]/g, "\\$&")}\\b`).test(text) : text.includes(w)));

  /* ── feature 2: read the need from a plain Hinglish sentence ─────────── */

  const RELATION = {
    mother: ["mother", "mom", "mummy", "mumma", "maa", "ma", "mata", "amma", "मम्मी", "माँ", "मां"],
    father: ["father", "dad", "papa", "pitaji", "pita", "पापा", "पिता"],
    wife: ["wife", "biwi", "patni", "पत्नी"],
    husband: ["husband", "pati", "पति"],
    son: ["son", "beta", "bete", "ladka", "बेटा"],
    daughter: ["daughter", "beti", "ladki", "बेटी"],
    self: ["myself", "mujhe", "mere liye", "khud"],
  };
  const CONDITION = {
    diabetes: ["diabetes", "diabetic", "sugar", "madhumeh", "शुगर", "मधुमेह", "डायबिटीज"],
    "high BP": ["bp", "b.p", "blood pressure", "hypertension", "बीपी"],
    heart: ["heart", "cardiac", "dil ki", "dil ki bimari", "dil ki problem", "bypass", "हृदय"],
    "knee / joint pain": ["knee", "knees", "ghutna", "ghutne", "ghutno", "ghutnon", "joint", "joints", "jodon", "jodo", "arthritis", "gathiya", "घुटन", "जोड़"],
    thyroid: ["thyroid"],
    asthma: ["asthma", "dama", "saans", "breathing"],
  };
  const YOUTH_NAME = /young|yuva|youth|junior|activ one/i;
  const WAIT_WORDS = ["waiting", "wait", "ped", "pre existing", "pre-existing", "preexisting", "pehle se", "intezaar", "intezar", "वेटिंग"];
  const LOW_COST = ["sasta", "sasti", "saste", "cheap", "cheaper", "affordable", "low premium", "kam premium", "pese kam", "paise kam",
    "kam pese", "kam paise", "kam lage", "kam kharcha", "budget friendly", "पैसे कम", "सस्ता"];

  function parseMoney(text) {
    const out = [];
    const re = /(\d[\d,]*\.?\d*)\s*(lakh|lakhs|lac|l|k|thousand|hazaar|hazar)?\b/gi;
    let m;
    while ((m = re.exec(text))) {
      let n = parseFloat(m[1].replace(/,/g, ""));
      if (Number.isNaN(n)) continue;
      const unit = (m[2] || "").toLowerCase();
      if (["k", "thousand", "hazaar", "hazar"].includes(unit)) n *= 1000;
      else if (["lakh", "lakhs", "lac", "l"].includes(unit)) n *= 100000;
      out.push({ value: n, index: m.index, end: m.index + m[0].length });
    }
    return out;
  }

  function parseNeed(text) {
    const t = ` ${text.toLowerCase().normalize("NFKC")} `;
    const need = {
      relation: null, age: null, conditions: [], roomRentMin: null, budgetMax: null,
      pedMaxMonths: null, lowCost: false, text,
    };
    for (const [rel, list] of Object.entries(RELATION)) if (has(t, list)) { need.relation = rel; break; }
    for (const [cond, list] of Object.entries(CONDITION)) if (has(t, list)) need.conditions.push(cond);
    need.lowCost = has(t, LOW_COST);

    const nums = parseMoney(t);
    const ageCtx = /\b(age|umar|umr|saal|sal|years?|yrs?|yr|varsh|ki hai|ka hai|ke hai)\b|साल|वर्ष/;
    for (const n of nums) {
      if (!Number.isInteger(n.value) || n.value < 18 || n.value > 99) continue;
      const after = t.slice(n.end, n.end + 14);
      if (/^\s*(months?|mahine|mahina|din|days?|%|lakh|k\b|000)/.test(after)) continue;
      const around = t.slice(Math.max(0, n.index - 26), n.end + 18);
      if (ageCtx.test(around) || (need.relation && has(around, RELATION[need.relation]))) {
        need.age = n.value;
        break;
      }
    }

    let prevEnd = 0;
    for (const n of nums) {
      const before = t.slice(prevEnd, n.index);
      prevEnd = n.end;
      if (/\b(room|rent|kamra|kamre|bed)\b/.test(before) && n.value >= 1000) {
        need.roomRentMin = Math.max(need.roomRentMin ?? 0, n.value);
      } else if (/\b(budget|premium|afford|under|within|upto|up to|max|tak)\b/.test(before) && n.value >= 1000) {
        need.budgetMax = need.budgetMax === null ? n.value : Math.min(need.budgetMax, n.value);
      }
    }

    /* "waiting 3 saal se jyada hota hai" = those were too long → cap at 3 years */
    if (has(t, WAIT_WORDS)) {
      const longer = t.match(/(\d+(?:\.\d+)?)\s*(saal|sal|years?|yrs?|months?|mahine|mahina)\s*(se\s*)?(jyada|zyada|jada|ziada|zada|more|above|longer|upar|adhik)/);
      const shorter = t.match(/(?:less than|under|within|max(?:imum)?|at most)\s*(\d+(?:\.\d+)?)\s*(saal|sal|years?|yrs?|months?|mahine)|(\d+(?:\.\d+)?)\s*(saal|sal|years?|yrs?|months?|mahine)\s*(se\s*)?(kam|less|tak|ke andar)/);
      const pick = longer ? [longer[1], longer[2]] : shorter ? [shorter[1] || shorter[3], shorter[2] || shorter[4]] : null;
      if (pick) {
        const v = parseFloat(pick[0]);
        need.pedMaxMonths = Math.round(/mon|mah/.test(pick[1]) ? v : v * 12);
      }
    }

    const shopping = /\b(plan|policy|insurance|bima)\b/.test(t) &&
      /\b(chahiye|chahie|suggest|recommend|best|kaunsa|konsa|kaun sa|which|koi|dal sake|daal sake|le sake|batao|bataye)\b/.test(t);
    need.signals =
      (need.relation ? 1 : 0) + (need.age !== null ? 1 : 0) + (need.roomRentMin !== null ? 1 : 0) +
      (need.budgetMax !== null ? 1 : 0) + (need.pedMaxMonths !== null ? 1 : 0) + (need.lowCost ? 1 : 0) + (shopping ? 1 : 0);
    return need;
  }

  /* a need beats a question unless a product is already pinned and the only
     signal is a condition word inside a question about that product */
  function isNeed(need, productPinned) {
    if (need.signals > 0) return true;
    return !productPinned && need.conditions.length > 0;
  }

  function needSummary(need) {
    const out = [];
    if (need.relation) out.push(need.relation === "self" ? "self" : need.relation);
    if (need.age !== null) out.push(`age ${need.age}`);
    for (const c of need.conditions) out.push(c);
    if (need.pedMaxMonths !== null) out.push(`PED wait ≤ ${fmtMonths(need.pedMaxMonths)}`);
    if (need.roomRentMin !== null) out.push(`room rent ${rupees(need.roomRentMin)}+`);
    if (need.budgetMax !== null) out.push(`budget ${rupees(need.budgetMax)}`);
    if (need.lowCost) out.push("low premium");
    return out;
  }

  /* match the customer's language — Hindi script, Hinglish roman, or English */
  function detectLang(text) {
    const t = String(text || "");
    if (/[\u0900-\u097f]/.test(t)) return "hi";
    const hits = (t.toLowerCase().match(/\b(hai|hain|hoga|hogi|mein|meh|meri|mera|mere|mummy|maa|ma|unhe|unke|humne|chahiye|chahie|kitna|kitni|kya|koi|batao|bataye|saal|sal|pese|paise|sasta|jyada|zyada|pehle|dal|sake|woh|yeh|aur|lekin|but|ke|ki|ka)\b/g) || []).length;
    if (hits >= 2) return "hinglish";
    return "en";
  }

  const WHO_EN = { mother: "your mother", father: "your father", wife: "your wife", husband: "your husband", son: "your son", daughter: "your daughter", self: "you" };
  const WHO_HI = { mother: "mummy", father: "papa", wife: "aapki wife", husband: "aapke husband", son: "beta", daughter: "beti", self: "aap" };

  /* first bubble: speak in the language they used, then the cards follow */
  function needAnswer(need, r, lang) {
    const who = need.relation ? (lang === "en" ? WHO_EN : WHO_HI)[need.relation] : (lang === "en" ? "the customer" : "customer");
    const ageBit = need.age != null ? (lang === "en" ? ` (${need.age})` : ` (${need.age} saal)`) : "";
    const best = r.best?.product;
    const second = r.second?.product;
    const third = r.third?.product;
    const w = best ? waitFor(best, need) : null;
    const ped = w ? { stated: true, value: w.months } : null;
    const end = w ? waitEndDate(w.months) : null;
    const carved = w?.carved
      ? { en: `This plan's wording lifts the pre-existing wait for ${w.carvedFor} — covered from the start.`,
          hi: `इस प्लान की वर्डिंग में ${w.carvedFor} का PED वेट नहीं है — शुरू से कवर।`,
          hinglish: `Is plan ki wording mein ${w.carvedFor} ka PED wait nahi hai — start se cover.` }[lang]
      : null;
    const diabetes = need.conditions.includes("diabetes");
    const knee = need.conditions.includes("knee / joint pain");

    if (!best) {
      if (lang === "en") return [`I checked the catalogue — nothing fits all of that together.`, `Relax one need (age, waiting period, room rent or budget) and ask again.`];
      if (lang === "hi") return [`कैटलॉग में ऐसा कोई प्लान नहीं मिला जो सब ज़रूरतें एक साथ पूरी करे।`, `एक शर्त हल्की करके फिर पूछें।`];
      return [`Catalogue mein aisa plan nahi mila jo saari zaruratein ek saath poori kare.`, `Ek condition thodi soft karke phir poochho.`];
    }

    if (lang === "en") {
      const lines = [
        `Yes — there is a plan that can cover ${who}${ageBit}.`,
        diabetes && need.pedMaxMonths != null
          ? `They already have diabetes, and earlier policies waited more than ${fmtMonths(need.pedMaxMonths)}. I kept only plans whose pre-existing wait is ${fmtMonths(need.pedMaxMonths)} or less.`
          : diabetes
            ? `They already have diabetes, so the pre-existing waiting period is the deciding check.`
            : need.pedMaxMonths != null
              ? `I kept only plans whose pre-existing wait is ${fmtMonths(need.pedMaxMonths)} or less.`
              : `I ranked the plans that fit the need you described.`,
        `Best: ${label(best)}${ped?.stated ? ` — pre-existing wait ${ped.value} months${end ? `, cover from ${end}` : ""}` : ""}.`,
      ];
      if (second) lines.push(`Second: ${label(second)}${r.second.pedMonths ? ` — ${r.second.pedMonths} months wait` : ""}.`);
      if (third) lines.push(`Third: ${label(third)}${r.third.pedMonths ? ` — ${r.third.pedMonths} months wait` : ""}.`);
      if (knee) lines.push(`Knee / joint pain already diagnosed waits like any pre-existing condition; joint replacement may have its own listed-illness wait.`);
      if (r.cannotPremium) lines.push(`Premium is not written in any policy wording — quote it from the insurer rate card after the health check.`);
      if (need.roomRentMin != null) lines.push(`Room rent of ${rupees(need.roomRentMin)}+ was checked where the wording states it.`);
      return lines.filter(Boolean);
    }

    if (lang === "hi") {
      const lines = [
        `हाँ — ${who}${ageBit} के लिए प्लान मिल सकता है।`,
        diabetes && need.pedMaxMonths != null
          ? `डायबिटीज पहले से है, और पहले पॉलिसियों में वेटिंग ${fmtMonths(need.pedMaxMonths)} से ज़्यादा थी। मैंने सिर्फ उन्हीं प्लान को रखा जहाँ PED वेट ${fmtMonths(need.pedMaxMonths)} या उससे कम है।`
          : diabetes
            ? `डायबिटीज पहले से है, इसलिए PED वेटिंग सबसे ज़रूरी चेक है।`
            : `आपकी ज़रूरत के हिसाब से प्लान छांटे हैं।`,
        `सबसे अच्छा: ${label(best)}${ped?.stated ? ` — PED वेट ${ped.value} महीने${end ? `, कवर ${end} से` : ""}` : ""}।`,
      ];
      if (second) lines.push(`दूसरा: ${label(second)}${r.second.pedMonths ? ` — ${r.second.pedMonths} महीने वेट` : ""}।`);
      if (third) lines.push(`तीसरा: ${label(third)}${r.third.pedMonths ? ` — ${r.third.pedMonths} महीने वेट` : ""}।`);
      if (knee) lines.push(`घुटने का दर्द अगर पहले से है तो PED वेट ही लगेगी; जॉइंट रिप्लेसमेंट की अलग लिस्टेड वेट भी हो सकती है।`);
      if (r.cannotPremium) lines.push(`प्रीमियम किसी भी पॉलिसी वर्डिंग में नहीं लिखा — हेल्थ चेक के बाद रेट कार्ड से बताएँ।`);
      return lines.filter(Boolean);
    }

    /* hinglish */
    const lines = [
      `Haan — ${who}${ageBit} ke liye plan mil sakta hai.`,
      diabetes && need.pedMaxMonths != null
        ? `Diabetes pehle se hai, aur pehle wale plans mein waiting ${fmtMonths(need.pedMaxMonths)} se zyada thi. Maine sirf un plans ko rakha jahan PED wait ${fmtMonths(need.pedMaxMonths)} ya usse kam hai.`
        : diabetes
          ? `Diabetes pehle se hai, isliye PED waiting sabse important check hai.`
          : `Aapki zarurat ke hisaab se plans chhante hain.`,
      `Sabse behtar: ${label(best)}${ped?.stated ? ` — PED wait ${ped.value} months${end ? `, cover ${end} se start` : ""}` : ""}.`,
    ];
    if (second) lines.push(`Doosra: ${label(second)}${r.second.pedMonths ? ` — ${r.second.pedMonths} months wait` : ""}.`);
    if (third) lines.push(`Teesra: ${label(third)}${r.third.pedMonths ? ` — ${r.third.pedMonths} months wait` : ""}.`);
    if (knee) lines.push(`Ghutne ka dard agar pehle se hai toh PED wait hi lagti hai; joint replacement ki alag listed wait bhi ho sakti hai.`);
    if (r.cannotPremium) lines.push(`Premium kisi bhi wording mein likha nahi hai — health check ke baad rate card se quote dena.`);
    if (need.roomRentMin != null) lines.push(`Room rent ${rupees(need.roomRentMin)}+ jahan wording mein likha hai, wahan check kiya.`);
    return lines.filter(Boolean);
  }

  /* ── feature 3: check each product against the need ─────────────────── */

  const NO_CAP = /actuals|no room rent|any room|private|single|up to (the )?si|up to sum insured/i;

  /* the wait that applies to this customer's conditions: a plan built for
     diabetics can lift the PED wait for diabetes / BP only */
  function waitFor(p, need) {
    const ped = p.facts?.ped_wait_months;
    const dw = p.facts?.diabetes_wait;
    const conds = need?.conditions || [];
    if (dw?.stated && conds.length && conds.every((c) => (dw.conditions || []).includes(c))) {
      return { months: dw.months, fact: dw, carved: true, carvedFor: conds.join(" and ") };
    }
    return ped?.stated ? { months: ped.value, fact: ped, carved: false } : null;
  }

  function assess(p, need, byId) {
    const f = p.facts || {};
    const fails = [];
    const wins = [];
    const cannot = [];
    if (p.status === "withdrawn") {
      const next = byId.get(p.replaced_by);
      fails.push(`Stopped for new sales${next ? ` — sell ${label(next)} instead` : ""}`);
    }
    let ageUnknown = false;
    if (need.age !== null) {
      const a = f.entry_age_max;
      if (a?.stated && typeof a.value === "number") {
        if (need.age > a.value) fails.push(`Entry age stops at ${a.value}; customer is ${need.age}`);
        else wins.push(`Entry age up to ${a.value}`);
      } else if (a?.stated && /no (upper )?(age )?limit/i.test(String(a.value))) {
        wins.push("No upper entry age");
      } else {
        cannot.push("entry age (check the prospectus)");
        ageUnknown = true;
      }
    }
    const w = waitFor(p, need);
    if (need.pedMaxMonths !== null && w && w.months > need.pedMaxMonths) {
      fails.push(`PED wait ${w.months} months — longer than ${fmtMonths(need.pedMaxMonths)}`);
    }
    if (need.roomRentMin !== null) {
      const r = f.room_rent;
      const kind = r?.room_class;
      if (!r?.stated) cannot.push("room rent (set by the policy schedule)");
      else if (typeof r.max_per_day === "number" && r.max_per_day < need.roomRentMin) {
        fails.push(`Room rent capped at ${rupees(r.max_per_day)}/day; needs ${rupees(need.roomRentMin)}+`);
      } else if (r.unit === "si-band" || kind === "si_band" || kind === "pct_si" || kind === "depends") {
        cannot.push(`room rent depends on plan / sum insured (${r.note || r.value})`);
      } else if (kind === "schedule") {
        cannot.push("room rent limit (read the schedule)");
      } else if (kind === "no_cap" || typeof r.max_per_day === "number" || (!kind && NO_CAP.test(String(r.value)))) {
        wins.push(`Room: ${r.value}`);
      } else cannot.push("room rent limit (read the schedule)");
    }
    if (need.budgetMax !== null || need.lowCost) {
      if (!(f.premium_inr?.stated && typeof f.premium_inr.value === "number")) cannot.push("premium");
      else if (need.budgetMax !== null && f.premium_inr.value > need.budgetMax) {
        fails.push(`Premium ${rupees(f.premium_inr.value)} above budget ${rupees(need.budgetMax)}`);
      }
    }
    const pedMonths = w ? w.months : 999;
    return { product: p, fails, wins, cannot, pedMonths, ageUnknown, carved: !!w?.carved, carvedFor: w?.carvedFor,
      eligible: fails.length === 0 };
  }

  function recommend(products, need, mine, byId) {
    const sellable = products.filter((p) => !isUpload(p));
    let pool = sellable;
    let scope = "all";
    if (mine.size) {
      const own = sellable.filter((p) => mine.has(p.insurer));
      const ownOk = own.map((p) => assess(p, need, byId)).filter((a) => a.eligible);
      if (ownOk.length) { pool = own; scope = "mine"; } else scope = "mine-none";
    }
    const assessed = pool.map((p) => assess(p, need, byId));
    /* a plan whose age limit the wording confirms beats one we cannot check */
    const ok = assessed.filter((a) => a.eligible).sort((a, b) =>
      (a.ageUnknown ? 1 : 0) - (b.ageUnknown ? 1 : 0) ||
      a.pedMonths - b.pedMonths ||
      a.cannot.filter((c) => c !== "premium").length - b.cannot.filter((c) => c !== "premium").length ||
      label(a.product).localeCompare(label(b.product)));
    const best = ok[0] || null;
    const second = ok[1] || null;
    const third = ok[2] || null;
    /* a much shorter wait whose age limit the wording does not state: name it, never rank it blind.
       never float a youth-only sounding plan for a 40+ customer */
    const watch = best && !best.ageUnknown
      ? ok.filter((a) => a.ageUnknown && a.pedMonths <= best.pedMonths - 12 &&
          !(need.age != null && need.age > 40 && YOUTH_NAME.test(`${a.product.name} ${a.product.variant || ""}`)))
        .sort((a, b) => a.pedMonths - b.pedMonths || (a.carved ? -1 : 0))[0] || null
      : null;
    const top = new Set([best, second, third, watch].filter(Boolean));

    /* one line for every other product; identical reasons are grouped */
    const lines = new Map();
    const push = (reason, p) => { if (!lines.has(reason)) lines.set(reason, []); lines.get(reason).push(p); };
    for (const a of assessed) {
      if (top.has(a)) continue;
      if (!a.eligible) push(a.fails[0], a.product);
      else if (best && a.ageUnknown && !best.ageUnknown) push(`Entry age is not written in the wording — cannot confirm age ${need.age} is accepted`, a.product);
      else if (best && a.pedMonths > best.pedMonths) push(`${a.pedMonths}-month PED wait — ${a.pedMonths - best.pedMonths} months longer than the best`, a.product);
      else push("Fits too, but ranks lower on the same wait", a.product);
    }
    const others = [...lines].map(([reason, ps]) => ({ reason, products: ps }));
    const cannotPremium = (need.budgetMax !== null || need.lowCost) && assessed.some((a) => a.cannot.includes("premium"));
    return { best, second, third, watch, others, scope, cannotPremium, need };
  }

  function whyLine(a, rank, best) {
    const p = a.product;
    const ped = p.facts?.ped_wait_months;
    const roomWin = a.wins.find((w) => w.startsWith("Room"))?.replace(/\.+$/, "");
    if (a.carved) return `Built for this: the wording lifts the pre-existing wait for ${a.carvedFor} — covered from the start${roomWin ? `; ${roomWin.toLowerCase()}` : ""}.`;
    if (rank === 1) {
      const base = ped?.stated ? `Shortest pre-existing wait of the plans that fit — ${ped.value} months` : "Fits every check that the wording can answer";
      return roomWin ? `${base}; ${roomWin.toLowerCase()}.` : `${base}.`;
    }
    const parts = (p.differentiator || "").split(";").map((s) => s.trim().replace(/\.$/, "")).filter(Boolean);
    const extra = parts.find((s) => !/\bped\b|pre-existing/i.test(s)) || parts[0] || "";
    if (ped?.stated && best && best.pedMonths === ped.value) return `Same ${ped.value}-month wait${extra ? ` — ${extra}` : ""}.`;
    return ped?.stated ? `Next shortest wait at ${ped.value} months.` : "Fits, but the wording states no wait to rank on.";
  }

  function conditionLines(p, need) {
    const out = [];
    const w = waitFor(p, need);
    if (need.conditions.length) {
      if (w) {
        out.push({ k: need.conditions.includes("diabetes") ? "Diabetes cover starts" : "Declared condition cover starts",
          v: `${waitEndDate(w.months)}${w.carved ? " — no pre-existing wait for it in this wording" : ""}`,
          cite: pageLabel(citePage(w.fact)), section: w.fact.section });
      } else out.push({ k: "Pre-existing wait", v: "not written in this product" });
    }
    if (need.conditions.includes("knee / joint pain")) {
      const s = p.facts?.specified_disease_wait_months;
      out.push({
        k: "Knee / joint",
        v: s?.stated
          ? `if already diagnosed, it waits like any PED; joint replacement also has a ${s.value}-month listed-illness wait`
          : "if already diagnosed, it is a pre-existing condition and waits the same; joint-replacement rules are not written here",
        cite: s?.stated ? pageLabel(citePage(s)) : null,
      });
    }
    if (need.conditions.includes("heart") || need.conditions.includes("high BP")) {
      out.push({
        k: need.conditions.includes("heart") ? "Heart / BP" : "High BP",
        v: w
          ? (w.carved ? `wording lifts the wait for ${w.carvedFor} — covered from ${waitEndDate(w.months)}`
            : `treated as a pre-existing condition — cover from ${waitEndDate(w.months)}`)
          : "pre-existing wait is not written in this product",
        cite: w ? pageLabel(citePage(w.fact)) : null,
      });
    }
    return out;
  }

  /* ── feature 1: which exact product? ─────────────────────────────────── */

  const NAME_NOISE = new Set(["health", "insurance", "plan", "plans", "policy", "policies", "product", "cover", "the", "for", "and",
    "mera", "meri", "mere", "koi", "hai", "kya", "ka", "ki", "ke", "me", "mein", "batao", "about", "tell", "check", "is", "in", "of",
    "what", "kitna", "kitni", "how", "does", "do", "on", "it", "this", "that", "with"]);

  function matchProducts(query, products, mine) {
    const qt = words(query).filter((w) => w.length > 1 && !NAME_NOISE.has(w));
    if (!qt.length) return [];
    const scored = products.map((p) => {
      const hay = words(`${p.insurer} ${p.name} ${p.variant || ""} ${isUpload(p) ? "upload" : ""}`);
      let s = 0;
      for (const w of qt) {
        if (hay.includes(w)) s += 2;
        else if (w.length >= 4 && hay.some((h) => h.length >= 4 && (h.startsWith(w) || w.startsWith(h)))) s += 1;
      }
      return { p, s };
    }).filter((r) => r.s >= 2);
    if (!scored.length) return [];
    const top = Math.max(...scored.map((r) => r.s));
    return scored
      .filter((r) => r.s >= top - 1)
      .sort((a, b) =>
        b.s - a.s ||
        (isUpload(a.p) ? 1 : 0) - (isUpload(b.p) ? 1 : 0) ||
        (mine.has(b.p.insurer) ? 1 : 0) - (mine.has(a.p.insurer) ? 1 : 0) ||
        (a.p.status === "withdrawn" ? 1 : 0) - (b.p.status === "withdrawn" ? 1 : 0) ||
        label(a.p).localeCompare(label(b.p)))
      .map((r) => r.p);
  }

  /* the one small difference written next to each look-alike */
  function difference(p) {
    if (p.status === "withdrawn") return `Stopped ${p.withdrawn_on ? fmtDate(p.withdrawn_on) : ""} — renewals only`.trim();
    return (p.differentiator || "").split(";")[0].trim();
  }

  /* the difference that actually separates the options on screen: the first
     trait each one does not share with the others */
  function differences(list) {
    const traits = (p) => {
      if (p.status === "withdrawn") return [difference(p)];
      const f = p.facts || {};
      const t = (p.differentiator || "").split(";").map((s) => s.trim().replace(/\.$/, "")).filter(Boolean);
      if (p.variant) t.push(p.variant);
      const sd = f.specified_disease_wait_months;
      if (sd?.stated) t.push(`listed-illness wait ${sd.value} months`);
      const ea = f.entry_age_max;
      if (ea?.stated) t.push(typeof ea.value === "number" ? `entry up to ${ea.value}` : String(ea.value).toLowerCase());
      for (const [k, name] of [["cataract", "cataract"], ["ayush", "AYUSH"], ["robotic_surgery", "robotic surgery"]]) {
        if (f[k]?.stated && /\d/.test(String(f[k].value))) t.push(`${name}: ${String(f[k].value).replace(/\.$/, "")}`);
      }
      const fy = /(\d{2})(\d{2})$/.exec(p.uin || "");
      if (fy && +fy[2] === +fy[1] + 1) t.push(`20${fy[1]}-${fy[2]} wording`);
      if (p.uin) t.push(`UIN ${p.uin}`);
      return t;
    };
    const all = list.map(traits);
    const out = new Map();
    list.forEach((p, i) => {
      const others = new Set(all.filter((_, j) => j !== i).flat().map((s) => s.toLowerCase()));
      out.set(p.id, all[i].find((s) => !others.has(s.toLowerCase())) || all[i][0] || "");
    });
    return out;
  }

  /* ── feature 4: simple vs hard questions ─────────────────────────────── */

  const STOP = new Set(["kitna", "kitne", "kitni", "hai", "hoga", "hogi", "milega", "milegi", "ka", "ki", "ke", "mein", "kya", "much",
    "many", "what", "how", "the", "is", "for"]);
  const INTENTS = [
    { id: "close", kind: "close", words: ["close", "whatsapp", "sale", "pitch", "bolu", "bolna", "message", "papers", "documents", "kit"] },
    { id: "premium", kind: "premium", words: ["premium", "price", "cost", "quote", "paisa", "paise", "pese", "rupaye", "rupees", "rate", "lagega", "kharcha"] },
    { id: "ped-wait", kind: "fast", words: ["waiting", "wait", "ped", "pre", "existing", "preexisting", "intezaar", "intezar", "diabetes", "bp", "sugar", "pehle"] },
    { id: "room-rent", kind: "fast", words: ["room", "rent", "icu", "kamra", "kamre", "bed"] },
    { id: "entry-age", kind: "fast", words: ["age", "umar", "umr", "entry", "senior", "limit"] },
    { id: "copay", kind: "fast", words: ["copay", "co-pay", "deduction"] },
    { id: "robotic-surgery", kind: "hard", words: ["robotic", "robot"] },
    { id: "cataract", kind: "hard", words: ["cataract", "motiyabind", "motiyabindu", "aankh"] },
    { id: "ayush", kind: "hard", words: ["ayush", "ayurveda", "ayurvedic", "homeopathy", "unani", "siddha"] },
  ];
  const FAST_FIELD = { "ped-wait": "ped_wait_months", "room-rent": "room_rent", "entry-age": "entry_age_max", copay: "copay" };
  const HARD_FIELD = { ayush: "ayush", cataract: "cataract", "robotic-surgery": "robotic_surgery" };

  function classify(q) {
    const qt = words(q).filter((w) => !STOP.has(w));
    const scored = INTENTS.map((i) => ({ i, hits: i.words.filter((w) => qt.includes(w)).length })).filter((r) => r.hits);
    if (!scored.length) return null;
    /* a named treatment (cataract, robotic, AYUSH) is the topic; "limit" or "kitna" only frames it */
    const rank = { hard: 0, close: 1, premium: 2, fast: 3 };
    scored.sort((a, b) => b.hits - a.hits || rank[a.i.kind] - rank[b.i.kind]);
    if (scored.some((s) => s.i.kind === "hard")) return scored.find((s) => s.i.kind === "hard").i;
    return scored[0].i;
  }

  /* simple: one short line from a verified fact; null → send to retrieval */
  function simpleAnswer(p, intentId) {
    const f = p.facts?.[FAST_FIELD[intentId]];
    if (!f) return null;
    if (!f.stated) return { notWritten: true, note: f.note };
    const cite = citePage(f);
    let lead;
    if (intentId === "ped-wait") lead = `Pre-existing wait (diabetes, BP…): ${f.value} months. Cover starts ${waitEndDate(f.value)} if the policy starts today.`;
    else if (intentId === "room-rent") lead = `Room rent: ${f.value}.`;
    else if (intentId === "entry-age") lead = `Maximum entry age: ${f.value}${f.unit === "years" ? " years" : ""}.`;
    else lead = `${f.value}.`;
    return { lead, note: f.note || null, cite, section: f.section || null, quote: f.quote || null };
  }

  function hardFact(p, intentId) {
    const f = p.facts?.[HARD_FIELD[intentId]];
    if (!f) return null;
    if (!f.stated) return { notWritten: true, note: f.note };
    return { quote: f.quote, cite: citePage(f), section: f.section || null, plain: f.value, note: f.note || null, table: f.source_kind === "table" };
  }

  /* ── feature 5: close the sale ───────────────────────────────────────── */

  function closeKit(p, kit, need, lang = "en") {
    const w = waitFor(p, need);
    const ped = w ? { value: w.months } : null;
    const end = w ? waitEndDate(w.months) : null;
    const room = p.facts?.room_rent;
    const roomLine = room?.stated ? String(room.value) : (lang === "en" ? "as per the policy schedule" : "policy schedule ke hisaab se");
    const who = need?.relation
      ? (lang === "en" ? WHO_EN : WHO_HI)[need.relation]
      : (lang === "en" ? "the customer" : "customer");
    const conds = need?.conditions || [];
    const condWord = conds.includes("diabetes") ? "diabetes" : conds[0] || (lang === "en" ? "a declared illness" : "declared illness");
    const L = lang === "hi" ? "hi" : lang === "hinglish" ? "hinglish" : "en";

    let say, wa;
    if (L === "en") {
      say = [
        `${fullName(p)} from ${p.insurer} covers new illnesses for ${who} once the policy starts.`,
        end ? `For ${condWord}, cover starts on ${end} — after ${ped.value} months of continuous cover.` : "The pre-existing wait is not written in this wording — confirm it before you decide.",
        `Hospital room: ${roomLine}.`,
        "The premium comes from the insurer after the health check — I will share the exact quote.",
      ];
      wa = [
        "Namaste,",
        `Here is the plan for ${who}: ${p.insurer} ${fullName(p)} (UIN ${p.uin}).`,
        "• New illnesses: covered once the policy starts",
        end ? `• ${condWord[0].toUpperCase() + condWord.slice(1)}: covered from ${end}` : "• Pre-existing wait: confirming with the insurer",
        `• Room: ${roomLine}`,
        "Please keep Aadhaar, PAN and the last 2 years of medical reports ready.",
        "Shall I start the proposal?",
      ].join("\n");
    } else if (L === "hi") {
      say = [
        `${p.insurer} का ${fullName(p)} पॉलिसी शुरू होते ही ${who} की नई बीमारी कवर करता है।`,
        end ? `${condWord} के लिए कवर ${end} से शुरू — ${ped.value} महीने continuous cover के बाद।` : "PED वेटिंग इस वर्डिंग में नहीं लिखी — कन्फ़र्म करके बताएँ।",
        `रूम: ${roomLine}।`,
        "प्रीमियम हेल्थ चेक के बाद इंश्योरर से आएगा — मैं exact quote दूँगा/दूँगी।",
      ];
      wa = [
        "नमस्ते,",
        `${who} के लिए प्लान: ${p.insurer} ${fullName(p)} (UIN ${p.uin})।`,
        "• नई बीमारी: पॉलिसी शुरू होते ही कवर",
        end ? `• ${condWord}: ${end} से कवर` : "• PED वेट: इंश्योरर से कन्फ़र्म",
        `• रूम: ${roomLine}`,
        "आधार, पैन और पिछले 2 साल के मेडिकल रिकॉर्ड तैयार रखें।",
        "प्रपोजल शुरू करें?",
      ].join("\n");
    } else {
      say = [
        `${p.insurer} ka ${fullName(p)} policy start hote hi ${who} ki nayi bimari cover karta hai.`,
        end ? `${condWord} ke liye cover ${end} se start — ${ped.value} months continuous cover ke baad.` : "PED waiting is wording mein nahi likhi — confirm karke batao.",
        `Room: ${roomLine}.`,
        "Premium health check ke baad insurer se aayega — main exact quote dunga/dungi.",
      ];
      wa = [
        "Namaste,",
        `${who} ke liye plan: ${p.insurer} ${fullName(p)} (UIN ${p.uin}).`,
        "• Nayi bimari: policy start hote hi cover",
        end ? `• ${condWord}: ${end} se cover` : "• PED wait: insurer se confirm",
        `• Room: ${roomLine}`,
        "Aadhaar, PAN aur last 2 years ke medical records ready rakhein.",
        "Proposal start karein?",
      ].join("\n");
    }

    const papers = [...(kit?.documents || [])];
    if (conds.includes("diabetes")) papers.push(L === "hi" ? "नवीनतम शुगर रिपोर्ट (HbA1c / fasting) और वर्तमान दवा" : L === "hinglish" ? "Latest sugar reports (HbA1c / fasting) aur current prescription" : "Latest sugar reports (HbA1c / fasting) and current prescription");
    if (conds.includes("knee / joint pain")) papers.push(L === "hi" ? "घुटने का X-ray या ऑर्थोपेडिक नोट्स, अगर हों" : L === "hinglish" ? "Knee X-ray ya orthopaedic notes, agar hain" : "Knee X-ray or orthopaedic consultation notes, if any");
    if (conds.includes("high BP")) papers.push(L === "hi" ? "BP की दवा का प्रिस्क्रिप्शन" : "BP medication prescription");

    const dont = (kit?.never_promise || []).map((line) => (w?.carved && /pre-existing condition is covered from day one/i.test(line)
      ? (L === "hi" ? `${w.carvedFor} के अलावा कोई भी पुरानी बीमारी पहले दिन से कवर न बताएँ।`
        : L === "hinglish" ? `${w.carvedFor} ke alawa koi bhi purani bimari day one se cover mat bolo.`
          : `Never say any pre-existing illness other than ${w.carvedFor} is covered from day one.`)
      : line));
    if (conds.length && end) {
      dont.push(L === "hi" ? `${end} से पहले ${condWord} कवर मत बोलें।` : L === "hinglish" ? `${end} se pehle ${condWord} cover mat bolo.` : `Do not say ${condWord} is covered before ${end}.`);
    }
    if (conds.includes("knee / joint pain")) {
      dont.push(L === "hi" ? "वेटिंग में घुटने की सर्जरी या जॉइंट रिप्लेसमेंट कवर का वादा न करें।" : L === "hinglish" ? "Waiting mein knee surgery ya joint replacement cover ka promise mat karo." : "Do not promise knee surgery or joint replacement is covered during the waiting period.");
    }
    if (!room?.stated) {
      dont.push(L === "hi" ? "शेड्यूल चेक किए बिना रूम कैटेगरी का वादा न करें।" : L === "hinglish" ? "Schedule check kiye bina room category ka promise mat karo." : "Do not promise a room category until the schedule is checked.");
    }

    const labels = L === "hi"
      ? { say: "ग्राहक से यह कहें", wa: "WhatsApp मैसेज", wait: "वेटिंग खत्म", papers: "कागज़ात", dont: "यह वादा न करें", pitch: "कैसे पिच करें", pick: "यह चुनें" }
      : L === "hinglish"
        ? { say: "Customer se yeh bolo", wa: "WhatsApp message", wait: "Waiting khatam", papers: "Papers chahiye", dont: "Yeh promise mat karo", pitch: "Kaise pitch karein", pick: "Yeh choose karein" }
        : { say: "Say this to the customer", wa: "WhatsApp message", wait: "Waiting ends", papers: "Papers needed", dont: "Do not promise", pitch: "How to pitch", pick: "Pick this" };

    if (w?.carved) {
      say[1] = L === "hi" ? `${condWord}: वर्डिंग के अनुसार इसका PED वेट नहीं है — पॉलिसी शुरू होते ही कवर।`
        : L === "hinglish" ? `${condWord}: wording ke hisaab se iska PED wait nahi hai — policy start hote hi cover.`
          : `For ${condWord}, the wording lifts the pre-existing wait — covered from the start.`;
    }
    return { say, whatsapp: wa, waitEnd: end ? { date: end, months: w.months, cite: pageLabel(citePage(w.fact)) } : null, papers, dont, labels };
  }

  window.QPCore = {
    fullName, label, isUpload, policyIdOf, citePage, pageLabel, waitEndDate, fmtDate, fmtMonths,
    parseNeed, isNeed, needSummary, detectLang, needAnswer, assess, recommend, whyLine, conditionLines,
    matchProducts, difference, differences, classify, simpleAnswer, hardFact, closeKit,
  };
})();

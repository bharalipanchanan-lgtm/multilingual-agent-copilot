/* QuickPolicy by Claviq — product picker.
   Feature 1: never answer until the agent has named one exact product.

   Scope note: matching here is a literal token score over names and
   differentiators. It exists to prove the screen, not to rank products.
   Real need-based matching lands with retrieval in Phase 0/2. */

/* Real data, extracted from five insurer policy wordings and verified
   page by page. See data/catalogue.json and test/catalogue.test.mjs.
   Facts are objects, not bare values:
     {value, unit, pdf_page, printed_page, quote, note, stated}
   `stated: false` means the wording does not answer it — premiums and
   entry-age limits are never in a wording, so they are null on purpose. */
const CATALOGUE_URL = "data/catalogue.json";
const MAX_SHOWN = 3;

/* page to cite to the agent: the printed number when the document has
   one, otherwise the PDF index, labelled so nobody confuses them */
function citePage(f) {
  if (f.printed_page != null) return { n: f.printed_page, kind: "printed" };
  if (f.pdf_page != null) return { n: f.pdf_page, kind: "pdf" };
  return null;
}

/* Feature 4 — two tiers.
   FAST: answered from the structured fact table, no clause needed.
   CITED: must quote the wording, with page and section.
   Anything matching neither is refused. Refusal is a feature. */
/* Generic quantity words. They belong to no intent — "kitna" appears in
   "waiting period kitna hai" AND "premium kitna hoga". Leaving them on an
   intent makes an out-of-scope question match a confident answer. */
const STOPWORDS = new Set([
  "kitna", "kitne", "kitni", "hai", "hoga", "hogi", "milega", "milegi",
  "ka", "ki", "ke", "mein", "kya", "much", "many", "what", "how", "the",
]);

const INTENTS = [
  { id: "premium",   kind: "out",   words: ["premium", "price", "cost", "quote", "paisa", "rupaye", "rupees"] },
  { id: "ped-wait",  kind: "fast",  words: ["waiting", "wait", "ped", "pre", "existing", "preexisting", "intezaar", "diabetes", "bp", "sugar"] },
  { id: "room-rent", kind: "fast",  words: ["room", "rent", "icu", "kamra", "bed"] },
  { id: "entry-age", kind: "fast",  words: ["age", "umar", "entry", "senior", "saal"] },
  { id: "copay",     kind: "fast",  words: ["copay", "deduction"] },
  { id: "robotic-surgery", kind: "cited", words: ["robotic", "robot", "surgery"] },
  { id: "cataract",        kind: "cited", words: ["cataract", "motiyabind", "aankh"] },
  { id: "ayush",           kind: "cited", words: ["ayush", "ayurveda", "homeopathy", "unani", "siddha"] },
];

/* ── Feature 2, need-first entry ──────────────────────────
   Pulls structured constraints out of a plain sentence such as
   "mother 50, diabetes, room rent 10000, budget 25000".
   Deliberately conservative: a number it cannot label is ignored
   rather than guessed at. */

const CONDITION_WORDS = {
  diabetes: ["diabetes", "diabetic", "sugar", "madhumeh"],
  hypertension: ["bp", "hypertension", "pressure"],
  heart: ["heart", "cardiac", "dil"],
};

/* "10,000" / "10000" / "10k" / "1 lakh" / "1.5L" → rupees */
function parseMoney(text) {
  const out = [];
  const re = /(\d[\d,]*\.?\d*)\s*(lakh|lakhs|lac|l|k|thousand)?/gi;
  let m;
  while ((m = re.exec(text))) {
    let n = parseFloat(m[1].replace(/,/g, ""));
    if (Number.isNaN(n)) continue;
    const unit = (m[2] || "").toLowerCase();
    if (unit === "k" || unit === "thousand") n *= 1000;
    else if (["lakh", "lakhs", "lac", "l"].includes(unit)) n *= 100000;
    out.push({ value: n, index: m.index, end: m.index + m[0].length });
  }
  return out;
}

function parseNeed(text) {
  const lower = text.toLowerCase();
  const need = { age: null, conditions: [], roomRentMin: null, budgetMax: null };

  for (const [cond, words] of Object.entries(CONDITION_WORDS)) {
    if (words.some((w) => new RegExp(`\\b${w}\\b`).test(lower))) {
      need.conditions.push(cond);
    }
  }

  const nums = parseMoney(lower);

  // a bare 2-digit number near a person word is an age, not money
  const agePattern = /\b(?:age|umar|saal|years?|yrs?)\b|\b(?:mother|father|mom|dad|maa|papa|wife|husband|self)\b/;
  for (const n of nums) {
    const around = lower.slice(Math.max(0, n.index - 24), n.index + 24);
    if (n.value >= 18 && n.value <= 99 && Number.isInteger(n.value) && agePattern.test(around)) {
      if (need.age === null) need.age = n.value;
    }
  }

  /* Label a figure by the words between the PREVIOUS figure and this one.
     A fixed-width lookbehind leaks: in "room rent 10k budget 25000" the
     25000 would still see "room rent" and claim it. */
  let prevEnd = 0;
  for (const n of nums) {
    const before = lower.slice(prevEnd, n.index);
    prevEnd = n.end;
    if (/\b(room|rent|kamra|bed)\b/.test(before) && n.value >= 1000) {
      need.roomRentMin = Math.max(need.roomRentMin ?? 0, n.value);
    } else if (/\b(budget|premium|afford|under|within|upto|up to|max)\b/.test(before) && n.value >= 1000) {
      need.budgetMax = need.budgetMax === null ? n.value : Math.min(need.budgetMax, n.value);
    }
  }

  need.isNeedQuery =
    need.age !== null ||
    need.conditions.length > 0 ||
    need.roomRentMin !== null ||
    need.budgetMax !== null;

  return need;
}

/* ── Feature 3, eligibility ───────────────────────────────
   Every product is checked against the stated need. A product that
   fails a hard rule is out, with the reason recorded. Survivors are
   ranked, and the reasons are what the UI prints. */

/* Ranking on real data can only use what the wordings actually state.
   Premium and entry age are NOT in any policy wording, so a budget or
   age constraint cannot be checked here — it is reported as unanswerable
   rather than silently ignored or guessed. */
function assess(p, need) {
  const f = p.facts;
  const fails = [];
  const wins = [];
  const cannotCheck = [];

  if (p.status === "withdrawn") fails.push("Withdrawn — cannot be sold fresh");

  let ageUnknown = false;
  if (need.age !== null) {
    if (!f.entry_age_max?.stated) {
      cannotCheck.push("Entry age is not in the wording — check the prospectus");
      ageUnknown = true;
    } else if (typeof f.entry_age_max.value !== "number") {
      wins.push(`Entry age: ${f.entry_age_max.value}`);
    } else if (need.age > f.entry_age_max.value) {
      fails.push(`Entry age stops at ${f.entry_age_max.value}, customer is ${need.age}`);
    } else {
      wins.push(`Entry age up to ${f.entry_age_max.value} years (customer is ${need.age})`);
    }
  }

  if (need.budgetMax !== null) {
    if (f.premium_inr?.stated && typeof f.premium_inr.value === "number") {
      if (f.premium_inr.value > need.budgetMax) {
        fails.push(`Indicative premium ₹${f.premium_inr.value.toLocaleString("en-IN")} exceeds budget ₹${need.budgetMax.toLocaleString("en-IN")}`);
      } else {
        wins.push(`Within budget at ₹${f.premium_inr.value.toLocaleString("en-IN")}`);
      }
    } else {
      cannotCheck.push("Money not compared — premium comes from the insurer rate card after the health check, never from the wording");
    }
  }

  if (need.roomRentMin !== null) {
    if (!f.room_rent?.stated) {
      cannotCheck.push("Room rent is set by the Policy Schedule — ask which plan");
    } else if (typeof f.room_rent.max_per_day === "number" && f.room_rent.max_per_day < need.roomRentMin) {
      fails.push(
        `Room rent capped at ₹${f.room_rent.max_per_day.toLocaleString("en-IN")}/day, customer needs ₹${need.roomRentMin.toLocaleString("en-IN")}+`
      );
    } else if (["depends", "si_band", "pct_si", "schedule"].includes(f.room_rent.room_class)) {
      cannotCheck.push(`Room rent depends on the plan in the Policy Schedule — ${f.room_rent.note || "ask which plan"}`);
    } else {
      wins.push(`Room rent: ${f.room_rent.value}`);
    }
  }

  const ped = f.ped_wait_months;
  const dw = f.diabetes_wait;
  const carved = dw?.stated && need.conditions.length && need.conditions.every((c) => (dw.conditions || []).includes(c === "hypertension" ? "high BP" : c));
  const months = carved ? dw.months : ped?.stated ? ped.value : 999;
  if (carved) wins.push(`${dw.value} (p.${dw.pdf_page})`);
  else if (need.conditions.length && ped?.stated) wins.push(`Pre-existing cover starts after ${ped.value} months`);

  // a confirmed age limit beats one we cannot check; then the shorter wait
  // for this customer's conditions — the one thing every wording states
  const score = (ageUnknown ? 1e6 : 0) + months * 1000;

  return {
    product: p,
    fails,
    wins,
    cannotCheck,
    score,
    ageUnknown,
    eligible: fails.length === 0,
  };
}

function recommend(need) {
  let pool = state.products;
  if (state.myInsurers.size) {
    const mine = pool.filter((p) => state.myInsurers.has(p.insurer));
    if (mine.length) pool = mine;
  }

  const assessed = pool.map((p) => assess(p, need));
  const eligible = assessed.filter((a) => a.eligible).sort((a, b) => a.score - b.score);
  const rejected = assessed.filter((a) => !a.eligible).sort((a, b) => a.score - b.score);

  return {
    best: eligible[0] || null,
    second: eligible[1] || null,
    eligibleCount: eligible.length,
    rejected,
    need,
  };
}

/* one line saying why the winner wins */
function whyBest(a) {
  if (a.wins.length) return a.wins.join(". ") + ".";
  const ped = a.product.facts.ped_wait_months;
  if (!ped?.stated) return "Eligible, but the wording states no waiting period to rank on.";
  return a.ageUnknown
    ? `Shortest pre-existing wait at ${ped.value} months, but entry age is not written in the wording — confirm it from the prospectus first.`
    : `Shortest wait among plans where entry age is confirmed from the wording — ${ped.value} months.`;
}

const el = {
  q: document.getElementById("q"),
  filters: document.getElementById("filters"),
  results: document.getElementById("results"),
  resultsSection: document.getElementById("results-section"),
  count: document.getElementById("count"),
  pinnedSlot: document.getElementById("pinned-slot"),
};

const state = {
  products: [],
  clauses: {},
  thread: [],
  byId: new Map(),
  insurers: [],
  myInsurers: new Set(), // feature 2: agent's own insurers float to the top
  query: "",
  selected: null,
  hasPainted: false,
  uploading: false,
};

function rememberProduct(p) {
  const i = state.products.findIndex((x) => x.id === p.id);
  if (i >= 0) state.products[i] = p;
  else state.products.unshift(p);
  state.byId.set(p.id, p);
  if (p.insurer && !state.insurers.includes(p.insurer)) {
    state.insurers = [...state.insurers, p.insurer].sort();
  }
}

/* ── helpers ─────────────────────────────────────────────── */

const fullName = (p) => (p.variant ? `${p.name} ${p.variant}` : p.name);
const label = (p) => `${p.insurer} ${fullName(p)}`;

const tokens = (s) =>
  s.toLowerCase().split(/[^a-z0-9+]+/).filter((t) => t.length > 1);

function fmtDate(iso) {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", {
    day: "numeric", month: "short", year: "numeric",
  });
}

function textNode(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

/* ── scoring ─────────────────────────────────────────────── */

function score(p, queryTokens) {
  if (!queryTokens.length) return 0;
  const hay = tokens(`${label(p)} ${p.differentiator}`);
  let hits = 0;
  for (const t of queryTokens) {
    if (hay.some((h) => h === t)) hits += 2;
    else if (hay.some((h) => h.startsWith(t) || t.startsWith(h))) hits += 1;
  }
  return hits;
}

function rank() {
  const qt = tokens(state.query);
  let list = state.products.map((p) => ({ p, s: score(p, qt) }));

  if (qt.length) list = list.filter((r) => r.s > 0);

  list.sort((a, b) => {
    // agent's own uploads float to the top so the new PDF is findable
    const upA = a.p.uploaded || a.p.source === "upload" ? 1 : 0;
    const upB = b.p.uploaded || b.p.source === "upload" ? 1 : 0;
    if (upA !== upB) return upB - upA;
    // agent's own insurers first — feature 2
    const mineA = state.myInsurers.has(a.p.insurer) ? 1 : 0;
    const mineB = state.myInsurers.has(b.p.insurer) ? 1 : 0;
    if (mineA !== mineB) return mineB - mineA;
    if (b.s !== a.s) return b.s - a.s;
    // active before withdrawn, but withdrawn is never hidden
    const wA = a.p.status === "withdrawn" ? 1 : 0;
    const wB = b.p.status === "withdrawn" ? 1 : 0;
    if (wA !== wB) return wA - wB;
    return label(a.p).localeCompare(label(b.p));
  });

  return list.map((r) => r.p);
}

/* ── render: recommendation (feature 3) ──────────────────── */

function recCard(a, rank, need) {
  const p = a.product;
  const li = document.createElement("li");

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "card rec" + (rank === 1 ? " rec--best" : "");
  btn.addEventListener("click", () => select(p.id));

  btn.append(
    textNode("span", "rec__rank", rank === 1 ? "Best fit" : "Second choice")
  );
  btn.append(textNode("span", "card__insurer", p.insurer));

  const name = textNode("span", "card__name", p.name);
  if (p.variant) {
    name.append(" ");
    name.append(textNode("span", "card__variant", p.variant));
  }
  btn.append(name);

  const why = textNode("p", "rec__why");
  why.append(textNode("b", null, rank === 1 ? "Why this: " : "Why second: "));
  why.append(document.createTextNode(whyBest(a)));
  btn.append(why);

  const pedF = p.facts.ped_wait_months;
  if (need.conditions.length && pedF?.stated) {
    const d = textNode("p", "rec__date");
    d.append(textNode("b", null, "Declared condition covered from "));
    d.append(document.createTextNode(waitEndDate(pedF.value)));
    d.append(textNode("span", "rec__cite", ` · ${pageLabel(citePage(pedF))}`));
    btn.append(d);
  }
  if (a.cannotCheck.length) {
    const cc = textNode("p", "rec__cannot");
    cc.append(textNode("b", null, "Cannot check here: "));
    cc.append(document.createTextNode(a.cannotCheck.join(". ") + "."));
    btn.append(cc);
  }

  li.append(btn);
  return li;
}

function rejectRow(a) {
  const li = textNode("li", "reject");
  li.append(textNode("span", "reject__name", label(a.product)));
  li.append(textNode("span", "reject__why", a.fails[0]));
  return li;
}

function recommendationView(need) {
  const r = recommend(need);
  const wrap = textNode("section", "recos");

  const read = [];
  if (need.age !== null) read.push(`age ${need.age}`);
  for (const c of need.conditions) read.push(c);
  if (need.roomRentMin !== null)
    read.push(`room rent ₹${need.roomRentMin.toLocaleString("en-IN")}+`);
  if (need.budgetMax !== null)
    read.push(`budget ₹${need.budgetMax.toLocaleString("en-IN")}`);

  const heard = textNode("p", "recos__heard");
  heard.append(textNode("b", null, "Checking against: "));
  heard.append(document.createTextNode(read.join(" · ")));
  wrap.append(heard);

  if (!r.best) {
    const none = textNode("div", "empty");
    none.append(textNode("p", null, "Nothing in the catalogue fits all of that."));
    none.append(
      textNode("p", null, "Relax one constraint, or check the reasons below.")
    );
    wrap.append(none);
  } else {
    const ul = textNode("ul", "results");
    ul.append(recCard(r.best, 1, need));
    if (r.second) ul.append(recCard(r.second, 2, need));
    wrap.append(ul);
  }

  const alsoEligible = Math.max(0, r.eligibleCount - (r.best ? 1 : 0) - (r.second ? 1 : 0));
  if (alsoEligible) {
    wrap.append(
      textNode(
        "p",
        "recos__also",
        `${alsoEligible} more also qualify but rank lower. Narrow the need to see them.`
      )
    );
  }

  if (r.rejected.length) {
    const det = document.createElement("details");
    det.className = "rejects";
    const sum = document.createElement("summary");
    sum.textContent = `Why ${r.rejected.length} were ruled out`;
    det.append(sum);
    const ul = textNode("ul", "reject__list");
    for (const a of r.rejected) ul.append(rejectRow(a));
    det.append(ul);
    wrap.append(det);
  }

  return wrap;
}

/* ── render: candidate card ──────────────────────────────── */

function card(p) {
  const li = document.createElement("li");

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className =
    "card" +
    (p.status === "withdrawn" ? " card--withdrawn" : "") +
    (p.uploaded || p.source === "upload" ? " card--upload" : "");
  btn.addEventListener("click", () => select(p.id));

  btn.append(textNode("span", "card__insurer", p.insurer));

  const name = textNode("span", "card__name", p.name);
  if (p.variant) {
    name.append(" ");
    name.append(textNode("span", "card__variant", p.variant));
  }
  if (p.uploaded || p.source === "upload") {
    name.append(textNode("span", "badge-upload", "Your upload"));
  }
  btn.append(name);

  btn.append(textNode("p", "card__diff", p.differentiator));

  if (p.status === "withdrawn") {
    const flag = textNode("p", "flag");
    flag.append(textNode("b", null, "Withdrawn"));
    flag.append(
      document.createTextNode(
        ` ${fmtDate(p.withdrawn_on)}. Renewals only — cannot be sold fresh.`
      )
    );
    const next = state.byId.get(p.replaced_by);
    if (next) {
      flag.append(document.createTextNode(` Sell ${fullName(next)} instead.`));
    }
    btn.append(flag);
  }

  btn.append(textNode("p", "card__uin", `UIN ${p.uin}`));

  li.append(btn);
  return li;
}

/* ── render: pinned selection ────────────────────────────── */

function pinnedView(p) {
  const box = textNode("section", "pinned");
  box.setAttribute("aria-label", "Selected product");

  box.append(
    textNode(
      "p",
      "pinned__label",
      p.uploaded || p.source === "upload"
        ? "Answering about your upload"
        : "Answering about"
    )
  );

  const head = textNode("div", "pinned__head");
  const pinnedName = textNode("h2", "pinned__name", `${p.insurer} ${fullName(p)}`);
  if (p.uploaded || p.source === "upload") {
    pinnedName.append(textNode("span", "badge-upload", "Your upload"));
  }
  head.append(pinnedName);

  const change = textNode("button", "pinned__change", "Change product");
  change.type = "button";
  change.addEventListener("click", () => select(null));
  head.append(change);
  box.append(head);

  if (p.status === "withdrawn") {
    const flag = textNode("p", "flag");
    flag.append(textNode("b", null, "Withdrawn"));
    flag.append(
      document.createTextNode(
        ` ${fmtDate(p.withdrawn_on)}. Do not quote this to a new customer.`
      )
    );
    const next = state.byId.get(p.replaced_by);
    if (next) {
      flag.append(document.createTextNode(" "));
      const switchBtn = textNode(
        "button",
        "pinned__change",
        `Switch to ${next.insurer} ${fullName(next)} →`
      );
      switchBtn.type = "button";
      switchBtn.addEventListener("click", () => select(next.id));
      flag.append(switchBtn);
    }
    box.append(flag);
  }

  const facts = textNode("dl", "pinned__facts");
  const LABEL = {
    ped_wait_months: "PED waiting",
    specified_disease_wait_months: "Specified disease",
    named_ailment_wait_months: "Named ailment",
    room_rent: "Room rent",
    ayush: "AYUSH",
  };
  let shown = 0;
  for (const [key, f] of Object.entries(p.facts)) {
    if (!f.stated || !LABEL[key]) continue;
    const cite = citePage(f);
    const wrap = document.createElement("div");
    wrap.append(textNode("dt", null, LABEL[key]));
    const v = f.unit === "months" ? `${f.value} months` : String(f.value);
    wrap.append(textNode("dd", null, v));
    if (cite) wrap.append(textNode("p", "pinned__cite", pageLabel(cite)));
    facts.append(wrap);
    shown++;
  }
  if (shown) box.append(facts);

  box.append(
    textNode(
      "p",
      "pinned__unverified",
      `${p.uin} · every value above was read from the cited page of the wording.`
    )
  );

  return box;
}

/* ── answering ───────────────────────────────────────────── */

function classify(q) {
  const qt = tokens(q).filter((t) => !STOPWORDS.has(t));

  const scored = INTENTS.map((intent) => ({
    intent,
    hits: intent.words.filter((w) => qt.includes(w)).length,
  })).filter((r) => r.hits > 0);

  if (!scored.length) return null;

  // Refusal wins ties. A wrong confident number costs more than a decline,
  // so an out-of-scope match is never outranked by an equal in-scope one.
  scored.sort((a, b) => {
    if (b.hits !== a.hits) return b.hits - a.hits;
    const outA = a.intent.kind === "out" ? 0 : 1;
    const outB = b.intent.kind === "out" ? 0 : 1;
    return outA - outB;
  });

  return scored[0].intent;
}

/* Feature 3/5 — an absolute date, never only a duration. */
function waitEndDate(months) {
  const d = new Date();
  d.setMonth(d.getMonth() + months);
  return d.toLocaleDateString("en-IN", {
    day: "numeric", month: "long", year: "numeric",
  });
}

const FAST_FIELD = {
  "ped-wait": "ped_wait_months",
  "room-rent": "room_rent",
  "entry-age": "entry_age_max",
  copay: "copay",
};

function fastAnswer(p, intentId) {
  const key = FAST_FIELD[intentId];
  const f = key && p.facts[key];
  if (!f) return { kind: "refusal", reason: "not-in-wording" };

  // the wording does not answer it — say where it is answered instead
  if (!f.stated) return { kind: "refusal", reason: "not-in-wording", detail: f.note };

  const cite = citePage(f);
  const who = p.insurer;
  if (key === "ped_wait_months") {
    return {
      kind: "fast",
      /* Pitch Act III: marketing line first, clause + page underneath. */
      lead: `${who}: declared PED waiting is ${f.value} months.`,
      note: `Cover for a declared condition starts on ${waitEndDate(
        f.value
      )} if the policy begins today.`,
      cite,
      section: f.section || null,
      quote: f.quote,
    };
  }
  if (key === "room_rent") {
    return {
      kind: "fast",
      lead: `${who}: room rent — ${f.value}.`,
      note: f.note || "",
      cite,
      section: f.section || null,
      quote: f.quote,
    };
  }
  if (key === "entry_age_max") {
    return {
      kind: "fast",
      lead: `${who}: maximum entry age is ${f.value}.`,
      note: f.note || "",
      cite,
      section: f.section || null,
      quote: f.quote,
    };
  }
  return {
    kind: "fast",
    lead: `${who}: ${f.value}.`,
    note: f.note || "",
    cite,
    section: f.section || null,
    quote: f.quote,
  };
}

/* Cited answers come from verified facts that carry a quote. A fact with
   no quote (a table page) is still citable — we send the agent to the
   page rather than inventing a sentence. */
const CITED_FIELD = { ayush: "ayush", cataract: "cataract", "robotic-surgery": "robotic_surgery" };

function findClause(productId, topic) {
  const p = state.byId.get(productId);
  const f = p?.facts?.[CITED_FIELD[topic]];
  if (!f || !f.stated) return null;
  return {
    quote: f.quote,
    cite: citePage(f),
    section: f.section || null,
    plain: f.value,
    note: f.note,
    sourceKind: f.source_kind || "prose",
  };
}

function answer(p, question) {
  const intent = classify(question);

  if (!intent) {
    return { kind: "refusal", reason: "unmatched" };
  }
  if (intent.kind === "out") {
    return { kind: "refusal", reason: "out-of-scope" };
  }
  if (intent.kind === "fast") return fastAnswer(p, intent.id);

  const clause = findClause(p.id, intent.id);
  return clause
    ? { kind: "cited", clause }
    : { kind: "refusal", reason: "not-in-wording" };
}

/* ── thread rendering ────────────────────────────────────── */

function pageLabel(cite) {
  if (!cite) return "page not recorded";
  return cite.kind === "printed"
    ? `Page ${cite.n}`
    : `PDF page ${cite.n} (wording has no printed numbers)`;
}

function clauseCard(c, p) {
  const card = textNode("div", "clause");

  const ref = textNode("p", "clause__ref");
  ref.append(textNode("span", null, pageLabel(c.cite)));
  if (c.section) ref.append(textNode("span", null, c.section));
  ref.append(textNode("span", null, p.uin));
  card.append(ref);

  if (c.quote) {
    card.append(textNode("blockquote", "clause__quote", `“${c.quote}”`));
  } else {
    const t = textNode("p", "clause__table");
    t.append(textNode("b", null, "This sits in a table. "));
    t.append(
      document.createTextNode(
        "Open the page and read it with the customer rather than quoting a line."
      )
    );
    card.append(t);
  }

  if (c.plain) {
    const plain = textNode("p", "clause__plain");
    plain.append(textNode("b", null, "In plain words: "));
    plain.append(document.createTextNode(String(c.plain)));
    card.append(plain);
  }
  if (c.cite?.n) {
    const a = document.createElement("a");
    a.className = "clause__open";
    a.href = `/pdf/${policyIdOf(p)}#page=${c.cite.n}`;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = "Open this page in the wording";
    card.append(a);
  }
  return card;
}

function agentTurn(text) {
  const li = textNode("li", "turn turn--agent");
  li.append(textNode("div", "bubble", text));
  return li;
}

function copilotTurn(p, result, ms) {
  const li = textNode("li", "turn turn--copilot");
  const bubble = textNode("div", "bubble");

  if (result.kind === "pending") {
    const live = textNode("p", "bubble__lead");
    live.id = "live-answer";
    live.textContent = result.text || "Reading the wording…";
    bubble.append(live);
    bubble.append(textNode("p", "bubble__src", "Matching your question to the cited clauses."));
    li.append(bubble);
    return li;
  }

  if (result.kind === "rag") {
    const ev = result.ev;

    if (ev.status === "not_stated" || ev.status === "refused") {
      const box = textNode("div", "refusal");
      box.append(textNode("b", null,
        ev.status === "refused" ? "Outside this wording." : "Not written in this product."));
      box.append(textNode("p", null, ev.answer || ""));
      bubble.append(box);
    } else {
      if (ev.status === "blocked") {
        const warn = textNode("div", "refusal");
        warn.append(textNode("b", null, "Answer held. "));
        warn.append(textNode("p", null,
          `A figure (${(ev.unsupported_numbers || []).join(", ")}) was not found in the cited clause. Showing the clauses as written.`));
        bubble.append(warn);
      }
      const raw = (ev.answer || "").trim();
      const firstStop = raw.search(/[.!?\n]/);
      const market =
        firstStop > 12 && firstStop < 180 ? raw.slice(0, firstStop + 1).trim() : raw.split("\n")[0];
      const rest =
        market && raw.startsWith(market) ? raw.slice(market.length).trim() : "";
      if (market) bubble.append(textNode("p", "bubble__market", market));
      if (rest) bubble.append(textNode("p", "bubble__answer", rest));
      for (const c of ev.citations || []) {
        const card = textNode("div", "clause");
        const ref = textNode("p", "clause__ref");
        ref.append(textNode("span", null, `Page ${c.printed_page}`));
        if (c.printed_page !== c.page) ref.append(textNode("span", null, `PDF ${c.page}`));
        if (c.section) ref.append(textNode("span", null, c.section));
        card.append(ref);
        card.append(textNode("blockquote", "clause__quote", `\u201C${c.quote}\u201D`));
        const a = document.createElement("a");
        a.className = "clause__open";
        a.href = `/pdf/${policyIdOf(p)}#page=${c.page}`;
        a.target = "_blank";
        a.rel = "noopener";
        a.textContent = "Open this page in the wording";
        card.append(a);
        bubble.append(card);
      }
    }
    const src = [ev.backend, ev.top_score != null ? `top score ${ev.top_score}` : null]
      .filter(Boolean).join(" · ");
    if (src) bubble.append(textNode("p", "bubble__src", src));
    const scanMs = ev.first_token_ms ?? ev.ms;
    bubble.append(textNode("p", "latency",
      scanMs != null && scanMs < 3000
        ? `Scanned the policies in under 3 seconds (${scanMs} ms)`
        : `Scanned the policies · ${ev.ms} ms${ev.first_token_ms ? `, first word ${ev.first_token_ms} ms` : ""}`));
    li.append(bubble);
    return li;
  }

  if (result.kind === "fast") {
    bubble.append(textNode("p", "bubble__market", result.lead));
    if (result.note) bubble.append(textNode("p", "bubble__src", result.note));
    /* Clause + page sit under the marketing line — pitch Act III shape. */
    const clause = {
      cite: result.cite,
      section: result.section,
      quote: result.quote,
    };
    bubble.append(clauseCard(clause, p));
  } else if (result.kind === "cited") {
    bubble.append(
      textNode("p", "bubble__market", `${p.insurer}: ${result.clause.plain}.`)
    );
    bubble.append(clauseCard({ ...result.clause, plain: null }, p));
  } else {
    const box = textNode("div", "refusal");
    if (result.reason === "out-of-scope") {
      box.append(textNode("b", null, "Outside this wording."));
      box.append(
        textNode(
          "p",
          null,
          "Premium depends on underwriting. Quote it from the rate sheet, not from QuickPolicy."
        )
      );
    } else if (result.reason === "not-in-wording") {
      box.append(textNode("b", null, "Not written in this product."));
      box.append(
        textNode(
          "p",
          null,
          result.detail ||
            `The wording for ${fullName(p)} has no clause on this. Do not infer it from another product.`
        )
      );
    } else {
      box.append(textNode("b", null, "Not enough to go on."));
      box.append(
        textNode("p", null, "Ask about waiting period, room rent, entry age, co-pay, robotic surgery, cataract or AYUSH.")
      );
    }
    bubble.append(box);
  }

  bubble.append(
    textNode(
      "p",
      "latency",
      ms < 3000
        ? `Scanned the policies in under 3 seconds (${ms} ms)`
        : `Scanned the policies · ${ms} ms`
    )
  );
  li.append(bubble);
  return li;
}

/* ── close kit (feature 5) ───────────────────────────────── */

function closeKitView(p) {
  const kit = textNode("div", "kit");
  const pedK = p.facts.ped_wait_months;
  const end = pedK?.stated ? waitEndDate(pedK.value) : null;

  const room = p.facts.room_rent;
  const roomLine = room?.stated
    ? String(room.value)
    : "Set by the Policy Schedule — confirm the plan before promising a room";

  const say = textNode("div", "kit__block");
  say.append(textNode("p", "kit__title", "Say this to the customer"));
  say.append(
    textNode(
      "p",
      null,
      end
        ? `${fullName(p)} covers anything new from day one. For a condition already declared, cover starts on ${end}. Room rent: ${roomLine}.`
        : `${fullName(p)}. The waiting period is not stated in this wording — confirm it before quoting one.`
    )
  );
  kit.append(say);

  const wa = textNode("div", "kit__block");
  wa.append(textNode("p", "kit__title", "WhatsApp message"));
  const msg = `${p.insurer} — ${fullName(p)}
UIN ${p.uin}

Declared pre-existing cover starts: ${end ?? "not stated in the wording"}
Room rent: ${roomLine}

Shall I start the proposal?`;
  wa.append(textNode("pre", "kit__wa", msg));
  const copy = textNode("button", "kit__copy", "Copy message");
  copy.type = "button";
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(msg);
      copy.textContent = "Copied";
    } catch {
      copy.textContent = "Copy failed — select it by hand";
    }
    setTimeout(() => (copy.textContent = "Copy message"), 2000);
  });
  wa.append(copy);
  kit.append(wa);

  /* sale papers and claim papers stay separate; each line cites its wording page */
  const k = window.QPCore.closeKit(p, null, "en");
  const item = (d) => textNode("li", null, d.cite ? `${d.text} (${d.cite})` : d.text);

  const buy = textNode("div", "kit__block");
  buy.append(textNode("p", "kit__title", k.labels.papers));
  const ulBuy = document.createElement("ul");
  for (const d of k.papers) ulBuy.append(item(d));
  if (!k.papers.length) ulBuy.append(textNode("li", null, "This wording does not list sale papers — ask the insurer."));
  buy.append(ulBuy);
  kit.append(buy);

  const claim = textNode("div", "kit__block");
  claim.append(textNode("p", "kit__title", k.labels.claimPapers));
  const ulClaim = document.createElement("ul");
  for (const d of k.claimPapers || []) ulClaim.append(item(d));
  if (!(k.claimPapers || []).length) ulClaim.append(textNode("li", null, "This wording does not list claim papers — ask the insurer."));
  claim.append(ulClaim);
  kit.append(claim);

  const warn = textNode("div", "kit__block kit__block--warn");
  warn.append(textNode("p", "kit__title", k.labels.dont));
  const ul2 = document.createElement("ul");
  for (const d of k.dont) ul2.append(item(d));
  warn.append(ul2);
  kit.append(warn);

  return kit;
}

const SUGGESTIONS = [
  "Diabetes ka waiting period kitna hai?",
  "Room rent kitna milega?",
  "Is robotic surgery covered?",
  "Cataract limit?",
  "Premium kitna hoga?",
];

function askView(p) {
  const sec = textNode("section", "ask");
  sec.append(
    textNode(
      "p",
      null,
      `Questions answer from ${fullName(p)} only. No other product is consulted.`
    )
  );

  const thread = textNode("ul", "thread");
  thread.id = "thread";
  thread.setAttribute("aria-live", "polite");
  for (const t of state.thread) {
    thread.append(agentTurn(t.q));
    thread.append(copilotTurn(p, t.a, t.ms));
  }
  sec.append(thread);

  const chips = textNode("div", "suggest");
  for (const s of SUGGESTIONS) {
    const chip = textNode("button", "chip", s);
    chip.type = "button";
    chip.addEventListener("click", () => ask(p, s));
    chips.append(chip);
  }
  sec.append(chips);

  const row = textNode("div", "ask__row");
  const input = document.createElement("input");
  input.type = "text";
  input.id = "ask-input";
  input.autocomplete = "off";
  input.placeholder = "Ask in English, Hindi or Hinglish";
  input.setAttribute("aria-label", "Ask about this product");

  const btn = textNode("button", "btn", "Ask");
  btn.type = "button";

  const send = () => {
    const q = input.value.trim();
    if (q) ask(p, q);
  };
  btn.addEventListener("click", send);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") send();
  });

  row.append(input, btn);
  sec.append(row);
  return sec;
}

/* ── RAG backend ─────────────────────────────────────────
   Feature 4's two tiers are enforced by WHERE an answer comes from:

   FAST  — a structured fact already verified against a page. Local and
           instant, no model involved, so it cannot hallucinate.
   HARD  — POST /api/ask: bge-m3 retrieval over Chroma, the backend
           quotes the clauses. Anything the fast path does not cover
           goes here, including questions nobody anticipated.

   The backend checks every number in a draft answer against the clause
   it cites and returns status "blocked" when a figure is unsupported.
   That check is why this is safe to put in front of an agent. */

const policyIdOf = (p) => p.policy_id || p.id.replace(/-/g, "_");

async function askBackend(p, question, onToken, onFinal) {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, policy_id: policyIdOf(p) }),
  });
  if (!res.ok || !res.body) throw new Error(`/api/ask returned ${res.status}`);

  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      let ev;
      try { ev = JSON.parse(line.slice(6)); } catch { continue; }
      if (ev.type === "token") onToken(ev.text);
      else if (ev.type === "final") onFinal(ev);
    }
  }
}

function ask(p, question) {
  const t0 = performance.now();
  const intent = classify(question);

  // out of scope never reaches retrieval or the model
  if (intent && intent.kind === "out") {
    state.thread.push({ q: question, a: { kind: "refusal", reason: "out-of-scope" },
                        ms: Math.max(1, Math.round(performance.now() - t0)) });
    render();
    focusAsk();
    return;
  }

  // fast path: a verified fact, answered locally in a millisecond
  if (intent && intent.kind === "fast") {
    const a = fastAnswer(p, intent.id);
    if (a.kind === "fast") {
      state.thread.push({ q: question, a, ms: Math.max(1, Math.round(performance.now() - t0)) });
      render();
      focusAsk();
      return;
    }
  }

  // everything else goes to retrieval over the wording
  const turn = { q: question, a: { kind: "pending", text: "" }, ms: 0 };
  state.thread.push(turn);
  render();
  focusAsk();

  askBackend(
    p, question,
    (tok) => {
      turn.a.text += tok;
      const live = document.getElementById("live-answer");
      if (live) live.textContent = turn.a.text;
    },
    (ev) => {
      turn.a = { kind: "rag", ev };
      turn.ms = ev.ms != null ? ev.ms : Math.round(performance.now() - t0);
      render();
      focusAsk();
    }
  ).catch((err) => {
    turn.a = { kind: "refusal", reason: "backend", detail: String(err.message) };
    turn.ms = Math.round(performance.now() - t0);
    render();
  });
}

function focusAsk() {
  const input = document.getElementById("ask-input");
  if (input) input.focus();
  const thread = document.getElementById("thread");
  if (thread && thread.lastElementChild) {
    thread.lastElementChild.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function askLocalOnly(p, question) {
  const t0 = performance.now();
  const a = answer(p, question);
  const ms = Math.max(1, Math.round(performance.now() - t0));
  state.thread.push({ q: question, a, ms });
  render();
  const input = document.getElementById("ask-input");
  if (input) input.focus();
  const thread = document.getElementById("thread");
  if (thread?.lastElementChild) {
    thread.lastElementChild.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

/* ── render: whole screen ────────────────────────────────── */

function render() {
  el.pinnedSlot.replaceChildren();

  if (state.selected) {
    const p = state.byId.get(state.selected);
    el.pinnedSlot.append(pinnedView(p), askView(p));
    const kit = textNode("section", "ask");
    kit.append(textNode("h2", null, "Close the sale"));
    kit.append(closeKitView(p));
    el.pinnedSlot.append(kit);
    el.resultsSection.hidden = true;
    return;
  }

  el.resultsSection.hidden = false;

  /* Feature 2, two ways in. A sentence carrying an age, a condition, a
     room rent or a budget is a NEED and gets ranked recommendations.
     Anything else is a NAME and gets the disambiguation list. */
  const need = parseNeed(state.query);
  if (need.isNeedQuery) {
    el.count.replaceChildren();
    el.results.replaceChildren();
    el.results.append(recommendationView(need));
    document.getElementById("results-head").textContent = "Best fit";
    return;
  }
  document.getElementById("results-head").textContent = "Matches";

  const ranked = rank();
  const shown = ranked.slice(0, MAX_SHOWN);
  const hidden = ranked.length - shown.length;

  el.count.replaceChildren();
  el.results.replaceChildren();

  if (!ranked.length) {
    const empty = textNode("div", "empty");
    empty.append(textNode("p", null, "Nothing matches that."));
    const hint = textNode("p");
    hint.append(document.createTextNode("Try an insurer name, or clear "));
    hint.append(textNode("b", null, "my insurers"));
    hint.append(document.createTextNode(" above."));
    empty.append(hint);
    el.results.append(empty);
    return;
  }

  const c = textNode("p", "count");
  c.append(textNode("strong", null, String(ranked.length)));
  c.append(
    document.createTextNode(
      ranked.length === 1 ? " product matches." : " products match."
    )
  );
  if (hidden > 0) {
    c.append(
      document.createTextNode(
        ` Closest ${shown.length} shown — narrow the search to see the other ${hidden}.`
      )
    );
  }
  c.append(document.createTextNode(" Pick one to continue."));
  el.count.replaceWith(c);
  el.count = c;

  for (const p of shown) el.results.append(card(p));

  // animate the first paint only, never a keystroke re-filter
  el.results.classList.toggle("results--enter", !state.hasPainted);
  state.hasPainted = true;
}

/* ── events ──────────────────────────────────────────────── */

function select(id) {
  // a thread is scoped to one product; never carry it across a switch
  if (id !== state.selected) state.thread = [];
  state.selected = id;
  if (!id) {
    render();
    el.q.focus();
    return;
  }
  render();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* Feature 2 — the agent's own insurers persist between visits.
   Browser storage can throw or come back empty (private window, blocked
   site data), so every access is guarded and the UI works without it. */
const PROFILE_KEY = "claviq.myInsurers";

function loadProfile() {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (!raw) return;
    const list = JSON.parse(raw);
    if (Array.isArray(list)) state.myInsurers = new Set(list);
  } catch {
    /* no profile; the chips simply start unticked */
  }
}

function saveProfile() {
  try {
    localStorage.setItem(PROFILE_KEY, JSON.stringify([...state.myInsurers]));
  } catch {
    /* not fatal — the filter still works for this session */
  }
}

/* Feature 5 — catalogue freshness. There is no insurer feed; a human
   re-verifies and bumps updated_on. This surfaces when that is overdue. */
function catalogueAge(cat) {
  if (!cat?.updated_on) return null;
  const then = new Date(`${cat.updated_on}T00:00:00`);
  if (Number.isNaN(then.getTime())) return null;
  const days = Math.floor((Date.now() - then.getTime()) / 86400000);
  return { days, stale: days > (cat.review_every_days ?? 90), on: cat.updated_on };
}

function renderCatalogueBanner(cat) {
  const age = catalogueAge(cat);
  const slot = document.getElementById("catalogue-note");
  if (!slot || !age) return;
  slot.replaceChildren();
  const p = textNode("p", "fixture-note" + (age.stale ? "" : " fixture-note--ok"));
  p.append(
    textNode("b", null, age.stale ? "Catalogue overdue." : "Catalogue checked.")
  );
  p.append(
    document.createTextNode(
      age.stale
        ? ` Last verified ${fmtDate(age.on)}, ${age.days} days ago. Withdrawn or repriced products may be missing — re-verify before quoting.`
        : ` Last verified ${fmtDate(age.on)}, ${age.days} days ago.`
    )
  );
  slot.append(p);
}

function buildFilters() {
  el.filters.replaceChildren();

  const note = textNode("span", "search__hint", "My insurers:");
  note.style.alignSelf = "center";
  note.style.margin = "0 4px 0 0";
  el.filters.append(note);

  for (const ins of state.insurers) {
    const chip = textNode("button", "chip", ins);
    chip.type = "button";
    chip.setAttribute("aria-pressed", String(state.myInsurers.has(ins)));
    chip.addEventListener("click", () => {
      if (state.myInsurers.has(ins)) state.myInsurers.delete(ins);
      else state.myInsurers.add(ins);
      chip.setAttribute("aria-pressed", String(state.myInsurers.has(ins)));
      saveProfile();
      render();
    });
    el.filters.append(chip);
  }
}

el.q.addEventListener("input", () => {
  state.query = el.q.value;
  render();
});

/* ── agent PDF upload → hybrid RAG ───────────────────────── */

function setUploadStatus(text, kind) {
  const s = document.getElementById("upload-status");
  if (!s) return;
  s.className = "upload-status" + (kind ? ` upload-status--${kind}` : "");
  s.replaceChildren();
  if (!text) return;
  if (kind === "ok") {
    const b = textNode("b", null, "Ready. ");
    s.append(b);
    s.append(document.createTextNode(text));
  } else {
    s.textContent = text;
  }
}

async function uploadPdf(file) {
  if (!file || state.uploading) return;
  if (!/\.pdf$/i.test(file.name)) {
    setUploadStatus("Upload a PDF policy wording.", "err");
    return;
  }
  state.uploading = true;
  const zone = document.getElementById("upload-zone");
  const drop = zone?.closest(".drop");
  drop?.classList.remove("drop--done");
  drop?.setAttribute("aria-busy", "true");
  const t0 = Date.now();
  const tick = setInterval(() => {
    const s = Math.round((Date.now() - t0) / 1000);
    setUploadStatus(`Reading ${file.name}… ${s}s`, "busy");
  }, 500);
  setUploadStatus(`Reading ${file.name}… 0s`, "busy");

  const fd = new FormData();
  fd.append("file", file, file.name);
  const insurer = (document.getElementById("upload-insurer")?.value || "").trim();
  const product = (document.getElementById("upload-product")?.value || "").trim();
  if (insurer) fd.append("insurer", insurer);
  if (product) fd.append("product", product);

  try {
    const res = await fetch("/api/upload", { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail;
      throw new Error(
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
            : data.message || res.statusText
      );
    }
    const p = data.product;
    if (!p?.id) throw new Error("Upload succeeded but no product card came back.");
    rememberProduct(p);
    buildFilters();
    setUploadStatus(
      `${p.name || file.name} · ${data.n_pages} pages · ${data.n_chunks} clauses in ${(data.ms / 1000).toFixed(1)}s`,
      "ok"
    );
    drop?.classList.add("drop--done");
    const title = zone?.querySelector(".drop__text b");
    if (title) title.textContent = "Policy added";
    select(p.id);
  } catch (err) {
    setUploadStatus(`Couldn't read it — ${err.message || err}`, "err");
  } finally {
    clearInterval(tick);
    state.uploading = false;
    drop?.removeAttribute("aria-busy");
    const input = document.getElementById("pdf-file");
    if (input) input.value = "";
  }
}

(function wireUpload() {
  const input = document.getElementById("pdf-file");
  const zone = document.getElementById("upload-zone");
  if (!input || !zone) return;
  input.addEventListener("change", () => {
    if (input.files?.[0]) uploadPdf(input.files[0]);
  });
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("upload-zone--drag");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("upload-zone--drag"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("upload-zone--drag");
    const f = e.dataTransfer?.files?.[0];
    if (f) uploadPdf(f);
  });
})();

/* ── boot ────────────────────────────────────────────────── */

const getJSON = (url) =>
  fetch(url).then((r) => {
    if (!r.ok) throw new Error(`${url}: ${r.status} ${r.statusText}`);
    return r.json();
  });

Promise.all([
  getJSON(CATALOGUE_URL),
  getJSON("/api/uploads").catch(() => []),
])
  .then(([json, uploads]) => {
    state.documents = json.documents;
    state.products = [...(uploads || []), ...json.products];
    state.byId = new Map(state.products.map((p) => [p.id, p]));
    state.insurers = [...new Set(state.products.map((p) => p.insurer))].sort();
    loadProfile();
    renderCatalogueBanner(json.catalogue);
    buildFilters();
    render();
  })
  .catch((err) => {
    const empty = textNode("div", "empty");
    empty.append(textNode("p", null, "Could not load the product list."));
    empty.append(textNode("p", null, String(err.message)));
    empty.append(
      textNode("p", null, "Serve this folder over http, not file://.")
    );
    el.results.replaceChildren(empty);
  });

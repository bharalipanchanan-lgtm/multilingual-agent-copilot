/* QuickPolicy first-run guide.
   Motion (the vanilla build of Framer Motion) drives every transition.
   Opens once per browser; replay with ?guide or any [data-guide-open]. */

(() => {
  const KEY = "qp_guide_seen_v1";
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const M = !reduce && window.Motion ? window.Motion : null;

  const SPRING = { type: "spring", stiffness: 260, damping: 26, mass: 0.9 };
  const SOFT = { type: "spring", stiffness: 140, damping: 20 };
  const SNAP = { type: "spring", stiffness: 520, damping: 32 };
  const EASE_OUT = [0.16, 1, 0.3, 1];

  /* Without Motion (blocked CDN or reduced motion) every animation jumps to its last frame. */
  const lastFrame = (v) => (Array.isArray(v) ? v[v.length - 1] : v);
  function jump(el, kf) {
    const t = {};
    for (const [k, v] of Object.entries(kf)) {
      const end = lastFrame(v);
      if (["x", "y", "scale", "rotate", "scaleX", "scaleY"].includes(k)) t[k] = end;
      else el.style[k] = typeof end === "number" && k !== "opacity" ? `${end}px` : end;
    }
    if (Object.keys(t).length) {
      el.style.transform =
        `translate(${t.x ?? 0}px, ${t.y ?? 0}px) rotate(${t.rotate ?? 0}deg) ` +
        `scale(${t.scaleX ?? t.scale ?? 1}, ${t.scaleY ?? t.scale ?? 1})`;
    }
  }
  function animate(target, kf, opts = {}) {
    if (!target || (target.length === 0 && !(target instanceof Element))) return done();
    if (M) return M.animate(target, kf, opts);
    const els = target instanceof Element ? [target] : [...target];
    els.forEach((el) => jump(el, kf));
    return done();
  }
  function done() {
    const p = Promise.resolve();
    return { stop() {}, then: (a, b) => p.then(a, b), finished: p };
  }
  const stagger = (s, o) => (M ? M.stagger(s, o) : 0);
  const wait = (ms) => new Promise((r) => setTimeout(r, M ? ms : 0));

  const fmtDate = (d) =>
    d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  const coverStart = (() => {
    const d = new Date();
    d.setMonth(d.getMonth() + 36);
    return fmtDate(d);
  })();

  const ARROW = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>`;
  const TICK = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>`;
  const SEARCH = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>`;
  const LOGO = `<span class="brand__avatar" data-qpa="mark" data-qpa-track data-qpa-hop></span>`;
  const BOT = `<span class="qpg-bot" data-qpa="hero" data-qpa-track data-qpa-hop></span>`;
  const mountAvatars = (el) => window.QPAvatar && QPAvatar.mountAll(el);
  const dropAvatars = (el) => window.QPAvatar && QPAvatar.destroyAll(el);

  /* ── slides ─────────────────────────────────────────────── */

  const SLIDES = [
    {
      kicker: "Welcome to QuickPolicy",
      title: "Scans the policies.<br><em>Explains them instantly.</em>",
      body: "Your policy expert at the desk. QuickPolicy reads the insurer wording so you can answer the customer mid-call — in English, Hindi or Hinglish.",
      points: ["Answers only from the selected wording", "Clause and page on every figure", "If it is not written, QuickPolicy says so"],
      scene: sceneWelcome,
    },
    {
      kicker: "Step 1 · Find",
      title: "Pick the <em>exact</em> product.",
      body: "Names repeat across tiers and years. Search by name, or describe the customer — age, condition, room rent — and get the best one or two.",
      points: ["Variants side by side, never auto-picked", "Your insurers float to the top"],
      scene: scenePick,
    },
    {
      kicker: "Step 2 · Check",
      title: "Ask. Get the <em>clause.</em>",
      body: "A plain answer the customer understands, then the clause and page underneath — plus the date cover actually starts.",
      points: ["English, Hindi or Hinglish", "Fast facts in milliseconds"],
      scene: sceneAsk,
    },
    {
      kicker: "Step 3 · Close",
      title: "Close on the <em>spot.</em>",
      body: "Copy a ready message with the cover date and send it before the customer walks. Withdrawn product? You get the live replacement.",
      points: ["Close-the-sale kit in one tap", "Withdrawn plans never sold by mistake"],
      scene: sceneClose,
    },
  ];

  /* ── scenes: each returns its own markup and a play() that runs the story ── */

  function sceneWelcome() {
    const html = `
      <div class="qpg__layer qpg-halo" data-depth="8"></div>
      <div class="qpg__layer qpg-hero" data-depth="22">${BOT}</div>
      <span class="qpg__layer qpg-chip" data-depth="30" data-pop style="left:8%;top:8%"><b></b>Clause 4.1</span>
      <span class="qpg__layer qpg-chip" data-depth="38" data-pop style="right:8%;top:22%">Page 15</span>
      <span class="qpg__layer qpg-chip qpg-chip--far" data-depth="26" data-pop style="left:7%;bottom:12%">Hinglish</span>
      <span class="qpg__layer qpg-chip qpg-chip--far" data-depth="18" data-pop style="right:30%;top:44%"><b></b>Under 3 seconds</span>`;
    return {
      html,
      async play(root, loop, alive) {
        const pops = root.querySelectorAll("[data-pop]");
        animate(pops, { opacity: [0, 1], scale: [0.6, 1], y: [24, 0] }, { ...SPRING, delay: stagger(0.08, { startDelay: 0.15 }) });
        const bot = root.querySelector(".qpg-bot");
        await animate(bot, { opacity: [0, 1], y: [60, 0], scale: [0.8, 1] }, { ...SOFT, delay: 0.1 });
        if (!alive()) return;

        window.QPAvatar?.get(bot)?.happy();
        loop(animate(root.querySelector(".qpg-halo"), { scale: [1, 1.08, 1], opacity: [0.9, 0.55, 0.9] }, { duration: 3.4, repeat: Infinity, ease: "easeInOut" }));
        root.querySelectorAll(".qpg-chip").forEach((c, i) =>
          loop(animate(c, { y: [0, i % 2 ? 8 : -8, 0] }, { duration: 2.6 + i * 0.4, repeat: Infinity, ease: "easeInOut", delay: 0.8 + i * 0.2 }))
        );
      },
    };
  }

  function scenePick() {
    const rows = [
      ["Optima Secure", "HDFC ERGO · Base"],
      ["Optima Secure", "HDFC ERGO · Super Secure"],
      ["Optima Secure", "HDFC ERGO · Suraksha"],
    ];
    const html = `
      <div class="qpg__layer qpg-pick" data-depth="12">
        <div class="qpg-card qpg-search" data-in>${SEARCH}<span class="qpg-typed"></span><span class="qpg-caret"></span></div>
        ${rows
          .map(
            ([n, m]) => `
          <div class="qpg-card qpg-row" data-row>
            <div><div class="qpg-row__name">${n}</div><div class="qpg-row__meta">${m}</div></div>
            <span class="qpg-row__tick">${TICK}</span>
          </div>`
          )
          .join("")}
      </div>
      <span class="qpg-sample">Live catalogue · 3 variants, one name</span>`;
    return {
      html,
      async play(root, loop, alive) {
        await animate(root.querySelector("[data-in]"), { opacity: [0, 1], y: [30, 0], scale: [0.94, 1] }, SPRING);
        loop(animate(root.querySelector(".qpg-caret"), { opacity: [1, 0, 1] }, { duration: 0.9, repeat: Infinity, ease: "linear" }));
        await type(root.querySelector(".qpg-typed"), "optima secure", alive, 55);
        if (!alive()) return;
        const list = root.querySelectorAll("[data-row]");
        await animate(list, { opacity: [0, 1], y: [26, 0], scale: [0.96, 1] }, { ...SPRING, delay: stagger(0.09) });
        await wait(500);
        if (!alive()) return;
        const pick = list[0];
        await animate(pick, { scale: [1, 0.97] }, { duration: 0.12 });
        pick.classList.add("is-picked");
        animate(pick, { scale: [0.97, 1.03, 1] }, SNAP);
        animate(pick.querySelector(".qpg-row__tick"), { scale: [0.4, 1.25, 1], rotate: [-30, 0] }, SNAP);
        animate([list[1], list[2]], { opacity: 0.45, scale: 0.98 }, { duration: 0.4, ease: EASE_OUT });
      },
    };
  }

  function sceneAsk() {
    const html = `
      <div class="qpg__layer qpg-chat" data-depth="12">
        <div class="qpg-bubble qpg-bubble--me" data-me><span class="qpg-typed"></span></div>
        <div class="qpg-bubble qpg-bubble--ai qpg-wait" data-wait><span class="avatar-mini" data-qpa="mark"></span><span class="qpg-typing"><i></i><i></i><i></i></span></div>
        <div class="qpg-bubble qpg-bubble--ai" data-ans hidden><strong>HDFC ERGO Optima Secure:</strong> a declared pre-existing disease is covered after 36 months.</div>
        <div class="qpg-card qpg-clause" data-clause hidden>
          <div class="qpg-clause__ref"><span>Page 15</span><span>Sec C.1.a</span></div>
          <q>…shall be excluded until the expiry of 36 months of continuous coverage…</q>
        </div>
        <div class="qpg-date" data-date hidden>Cover starts <b>${coverStart}</b></div>
      </div>
      <span class="qpg-sample">Quoted from the HDFC ERGO wording</span>`;
    return {
      html,
      async play(root, loop, alive) {
        const me = root.querySelector("[data-me]");
        await animate(me, { opacity: [0, 1], x: [40, 0], scale: [0.9, 1] }, SPRING);
        await type(me.querySelector(".qpg-typed"), "Diabetes ke liye waiting period kitna hai?", alive, 34);
        if (!alive()) return;
        const w = root.querySelector("[data-wait]");
        await animate(w, { opacity: [0, 1], y: [16, 0], scale: [0.9, 1] }, SPRING);
        window.QPAvatar?.get(w.querySelector("[data-qpa]"))?.scan();
        const dots = w.querySelectorAll("i");
        const bounce = animate(dots, { y: [0, -6, 0], opacity: [0.35, 1, 0.35] }, { duration: 0.7, repeat: Infinity, delay: stagger(0.12) });
        loop(bounce);
        await wait(2600);
        if (!alive()) return;
        bounce.stop();
        await animate(w, { opacity: 0, scale: 0.9 }, { duration: 0.16 });
        w.hidden = true;
        for (const sel of ["[data-ans]", "[data-clause]", "[data-date]"]) {
          const el = root.querySelector(sel);
          el.hidden = false;
          animate(el, { opacity: [0, 1], y: [22, 0], scale: [0.96, 1] }, SPRING);
          await wait(320);
          if (!alive()) return;
        }
        loop(animate(root.querySelector("[data-date] b"), { opacity: [1, 0.55, 1] }, { duration: 2, repeat: Infinity }));
      },
    };
  }

  function sceneClose() {
    const html = `
      <div class="qpg__layer qpg-close" data-depth="12">
        <div class="qpg-swap" data-in>
          <div class="qpg-card qpg-row qpg-row--old" data-old>
            <div><div class="qpg-row__name">National Mediclaim Policy</div><div class="qpg-row__meta">National Insurance · 2014 Edition</div></div>
            <span class="qpg-badge qpg-badge--warn">Withdrawn</span>
          </div>
          <div class="qpg-card qpg-row is-picked" data-new style="opacity:0">
            <div><div class="qpg-row__name">MediCare Premier</div><div class="qpg-row__meta">TATA AIG · live replacement</div></div>
            <span class="qpg-badge qpg-badge--ok">Active</span>
          </div>
        </div>
        <div class="qpg-card qpg-kit" data-in>
          <div class="qpg-kit__head">Close-the-sale kit <span class="qpg-badge qpg-badge--ok">Ready</span></div>
          <div class="qpg-kit__msg">
            <p data-line>Namaste! Here is your HDFC ERGO Optima Secure summary.</p>
            <p data-line>New illnesses are covered from day one.</p>
            <p data-line>Declared conditions are covered from <b>${coverStart}</b>.</p>
          </div>
          <span class="qpg-copy" data-copy>${TICK}<span>Copy message</span></span>
        </div>
      </div>
      <span class="qpg-sample">Withdrawn → replacement from the live catalogue</span>`;
    return {
      html,
      async play(root, loop, alive) {
        await animate(root.querySelectorAll("[data-in]"), { opacity: [0, 1], y: [30, 0], scale: [0.95, 1] }, { ...SPRING, delay: stagger(0.12) });
        if (!alive()) return;
        await animate(root.querySelectorAll("[data-line]"), { opacity: [0, 1], x: [-14, 0] }, { duration: 0.45, ease: EASE_OUT, delay: stagger(0.18) });
        await wait(500);
        if (!alive()) return;
        const oldRow = root.querySelector("[data-old]");
        const newRow = root.querySelector("[data-new]");
        animate(oldRow, { x: [0, -60], opacity: [1, 0], rotate: [0, -3] }, { duration: 0.45, ease: EASE_OUT });
        await animate(newRow, { opacity: [0, 1], x: [60, 0], scale: [0.94, 1] }, SPRING);
        if (!alive()) return;
        await wait(450);
        const copy = root.querySelector("[data-copy]");
        await animate(copy, { scale: [1, 0.92] }, { duration: 0.1 });
        copy.querySelector("span").textContent = "Copied";
        await animate(copy, { scale: [0.92, 1.08, 1] }, SNAP);
        if (!alive()) return;
        loop(animate(copy, { y: [0, -3, 0] }, { duration: 2.2, repeat: Infinity, ease: "easeInOut" }));
      },
    };
  }

  async function type(el, text, alive, speed) {
    if (!M) { el.textContent = text; return; }
    for (const ch of text) {
      if (!alive()) return;
      el.textContent += ch;
      await wait(ch === " " ? speed * 1.6 : speed);
    }
  }

  /* ── shell ──────────────────────────────────────────────── */

  let root, panel, copyEl, stageEl, progressEl, dotsEl, backBtn, nextBtn;
  let index = 0;
  let token = 0;
  let loops = [];
  let lastFocus = null;
  let busy = false;

  function build() {
    root = document.createElement("div");
    root.className = "qpg";
    root.innerHTML = `
      <div class="qpg__panel" role="dialog" aria-modal="true" aria-labelledby="qpg-title">
        <div class="qpg__progress"><i></i></div>
        <button type="button" class="qpg__skip" data-skip>Skip guide</button>
        <div class="qpg__copy">
          <div class="qpg__brand">${LOGO}
            <span class="brand__text"><span class="brand__word">Quick<span>Policy</span></span><small>by Claviq</small></span>
          </div>
          <div class="qpg__slide" aria-live="polite"></div>
          <div class="qpg__foot">
            <div class="qpg__dots" role="tablist" aria-label="Guide steps">
              ${SLIDES.map((_, i) => `<button type="button" class="qpg__dot" data-dot="${i}" aria-label="Step ${i + 1}"></button>`).join("")}
            </div>
            <div class="qpg__nav">
              <button type="button" class="qpg__btn qpg__btn--ghost" data-back>Back</button>
              <button type="button" class="qpg__btn qpg__btn--primary" data-next></button>
            </div>
          </div>
        </div>
        <div class="qpg__stage"><div class="qpg__scene"></div></div>
      </div>`;
    document.body.append(root);
    mountAvatars(root.querySelector(".qpg__brand"));
    panel = root.querySelector(".qpg__panel");
    copyEl = root.querySelector(".qpg__slide");
    stageEl = root.querySelector(".qpg__scene");
    progressEl = root.querySelector(".qpg__progress i");
    dotsEl = [...root.querySelectorAll("[data-dot]")];
    backBtn = root.querySelector("[data-back]");
    nextBtn = root.querySelector("[data-next]");

    root.querySelector("[data-skip]").addEventListener("click", close);
    backBtn.addEventListener("click", () => go(index - 1));
    nextBtn.addEventListener("click", () => (index === SLIDES.length - 1 ? close() : go(index + 1)));
    dotsEl.forEach((d) => d.addEventListener("click", () => go(Number(d.dataset.dot))));
    root.addEventListener("click", (e) => { if (e.target === root) close(); });
    root.addEventListener("keydown", onKey);
    for (const b of root.querySelectorAll("button")) {
      b.addEventListener("pointerdown", () => animate(b, { scale: 0.95 }, SNAP));
      b.addEventListener("pointerup", () => animate(b, { scale: 1 }, SNAP));
      b.addEventListener("pointerleave", () => animate(b, { scale: 1 }, SNAP));
    }
    bindParallax(root.querySelector(".qpg__stage"));
  }

  function bindParallax(stage) {
    if (!M) return;
    stage.addEventListener("pointermove", (e) => {
      const r = stage.getBoundingClientRect();
      const dx = (e.clientX - r.left) / r.width - 0.5;
      const dy = (e.clientY - r.top) / r.height - 0.5;
      stage.querySelectorAll("[data-depth]").forEach((l) => {
        const d = Number(l.dataset.depth);
        animate(l, { x: -dx * d, y: -dy * d }, { type: "spring", stiffness: 120, damping: 18 });
      });
    });
    stage.addEventListener("pointerleave", () =>
      animate(stage.querySelectorAll("[data-depth]"), { x: 0, y: 0 }, SOFT)
    );
  }

  function onKey(e) {
    if (e.key === "Escape") close();
    else if (e.key === "ArrowRight") go(index + 1);
    else if (e.key === "ArrowLeft") go(index - 1);
    else if (e.key === "Tab") {
      const f = [...panel.querySelectorAll("button:not([hidden])")];
      const i = f.indexOf(document.activeElement);
      if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && i === f.length - 1) { e.preventDefault(); f[0].focus(); }
    }
  }

  function renderCopy(s) {
    copyEl.innerHTML = `
      <p class="qpg__kicker" data-in>${s.kicker}</p>
      <h2 class="qpg__title" id="qpg-title" data-in>${s.title}</h2>
      <p class="qpg__body" data-in>${s.body}</p>
      <ul class="qpg__points">${s.points.map((p) => `<li data-in>${p}</li>`).join("")}</ul>`;
  }

  function syncChrome() {
    const last = index === SLIDES.length - 1;
    backBtn.hidden = index === 0;
    nextBtn.className = "qpg__btn " + (last ? "qpg__btn--go" : "qpg__btn--primary");
    nextBtn.innerHTML = last ? "Start selling" : index === 0 ? `Show me how ${ARROW}` : `Next ${ARROW}`;
    dotsEl.forEach((d, i) => {
      d.toggleAttribute("aria-current", i === index);
      if (i === index) d.setAttribute("aria-current", "step");
      animate(d, { width: i === index ? "28px" : "9px" }, SPRING);
    });
    animate(progressEl, { width: `${((index + 1) / SLIDES.length) * 100}%` }, { duration: 0.6, ease: EASE_OUT });
  }

  async function go(next, first = false) {
    if (busy || next < 0 || next >= SLIDES.length || (next === index && !first)) return;
    busy = true;
    const dir = next > index ? 1 : -1;
    token += 1;
    const mine = token;
    loops.forEach((l) => l.stop && l.stop());
    loops = [];

    if (!first) {
      await Promise.all([
        animate(copyEl.querySelectorAll("[data-in]"), { opacity: 0, x: -28 * dir }, { duration: 0.2, ease: "easeIn", delay: stagger(0.025) }),
        animate(stageEl, { opacity: 0, x: -60 * dir, scale: 0.96 }, { duration: 0.24, ease: "easeIn" }),
      ]);
    }

    index = next;
    const s = SLIDES[index];
    const scene = s.scene();
    renderCopy(s);
    dropAvatars(stageEl);
    stageEl.innerHTML = scene.html;
    mountAvatars(stageEl);
    stageEl.querySelectorAll("[data-in],[data-row],[data-me],[data-wait],[data-pop],[data-line],.qpg-bot").forEach((el) => (el.style.opacity = M ? "0" : ""));
    syncChrome();

    animate(copyEl.querySelectorAll("[data-in]"), { opacity: [0, 1], x: [36 * dir, 0] }, { ...SPRING, delay: stagger(0.06) });
    animate(copyEl.querySelector(".qpg__title"), { filter: ["blur(6px)", "blur(0px)"] }, { duration: 0.5, ease: EASE_OUT });
    await animate(stageEl, { opacity: [0, 1], x: [70 * dir, 0], scale: [0.96, 1] }, SPRING);
    busy = false;
    scene.play(stageEl, (l) => loops.push(l), () => token === mine);
  }

  async function open() {
    if (root) return;
    lastFocus = document.activeElement;
    build();
    document.documentElement.style.overflow = "hidden";
    index = 0;
    animate(root, { opacity: [0, 1] }, { duration: 0.35, ease: "easeOut" });
    animate(panel, { opacity: [0, 1], y: [40, 0], scale: [0.92, 1] }, { ...SOFT, delay: 0.05 });
    await go(0, true);
    nextBtn.focus({ preventScroll: true });
  }

  async function close() {
    if (!root || root.dataset.closing) return;
    root.dataset.closing = "1";
    token += 1;
    loops.forEach((l) => l.stop && l.stop());
    try { localStorage.setItem(KEY, String(Date.now())); } catch {}
    await Promise.all([
      animate(panel, { opacity: 0, y: 30, scale: 0.94 }, { duration: 0.32, ease: [0.4, 0, 1, 1] }),
      animate(root, { opacity: 0 }, { duration: 0.38, delay: 0.06 }),
    ]);
    dropAvatars(root);
    root.remove();
    root = null;
    document.documentElement.style.overflow = "";
    revealPage();
    if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true });
  }

  function revealPage() {
    const parts = document.querySelectorAll(".hero__inner > *, #main > *");
    animate(parts, { opacity: [0, 1], y: [18, 0] }, { ...SPRING, delay: stagger(0.05) });
  }

  function shouldOpen() {
    if (new URLSearchParams(location.search).has("guide")) return true;
    try { return !localStorage.getItem(KEY); } catch { return false; }
  }

  window.QPGuide = { open, close };
  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-guide-open]");
    if (!t) return;
    e.preventDefault();
    open();
  });

  const start = () => shouldOpen() && open();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();

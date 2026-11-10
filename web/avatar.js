/* QuickPolicy avatar — the brand mascot and logo mark.
   Motion (vanilla Framer Motion) springs every channel; render() composes them.
   Mount on any element with [data-qpa]. Options via data attributes:
     data-qpa="hero"   float + periodic scan morph (body → policy page → body)
     data-qpa="mark"   logo: breathe, blink, glance
     data-qpa-track    eyes follow the pointer
     data-qpa-hop      hop on hover / click
   API: QPAvatar.get(el) → { hop, scan, talk(on), happy } */

(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const M = reduce ? null : window.Motion || null;

  const NAVY = [6, 77, 152];
  const WHITE = [255, 255, 255];
  const BODY = { x: 25, y: 15, w: 150, h: 190, rx: 74 };
  const DOC = { x: 36, y: 12, w: 128, h: 194, rx: 12 };
  const EYES = [77, 123];
  const EYE_Y = 70;

  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const mix = (c1, c2, t) => `rgb(${c1.map((c, i) => Math.round(lerp(c, c2[i], t))).join(",")})`;
  const last = (v) => (Array.isArray(v) ? v[v.length - 1] : v);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const MARKUP = `
  <svg class="qpa" viewBox="-6 -6 212 232" aria-hidden="true" focusable="false">
    <ellipse class="qpa__shadow" cx="100" cy="216" rx="58" ry="6" fill="rgba(6,50,100,.16)"/>
    <g class="qpa__rig">
      <rect class="qpa__body" x="25" y="15" width="150" height="190" rx="74" fill="#064d98" stroke="#064d98" stroke-width="0"/>
      <g class="qpa__lines" fill="none" stroke="#2acb55" stroke-width="8" stroke-linecap="round">
        <path pathLength="1" d="M60 134h80"/>
        <path pathLength="1" d="M54 152h92"/>
        <path pathLength="1" d="M64 170h72"/>
        <path pathLength="1" d="M58 188h84"/>
      </g>
      <g class="qpa__face">
        <ellipse cx="100" cy="76" rx="57" ry="41" fill="#fbf1d8"/>
        <ellipse class="qpa__cheek" cx="63" cy="89" rx="9.5" ry="5.8" fill="#f6b3c2"/>
        <ellipse class="qpa__cheek" cx="137" cy="89" rx="9.5" ry="5.8" fill="#f6b3c2"/>
        <g class="qpa__eye"><circle cx="77" cy="70" r="7.6" fill="#161616"/><circle cx="79.6" cy="67.4" r="2.5" fill="#fff"/></g>
        <g class="qpa__eye"><circle cx="123" cy="70" r="7.6" fill="#161616"/><circle cx="125.6" cy="67.4" r="2.5" fill="#fff"/></g>
        <path class="qpa__smile" d="M86 93q14 10 28 0" fill="none" stroke="#161616" stroke-width="3.6" stroke-linecap="round"/>
        <ellipse class="qpa__talk" cx="100" cy="96" rx="8" ry="0" fill="#161616"/>
      </g>
      <g class="qpa__shield">
        <path d="M83 136h34v19l-17 17-17-17z" fill="#2acb55"/>
        <path d="m91.5 153 6.5 6.5 12-13" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
      </g>
    </g>
    <g class="qpa__lens" opacity="0">
      <path d="M15 15l19 19" stroke="#2acb55" stroke-width="9" stroke-linecap="round"/>
      <circle r="22" fill="rgba(255,255,255,.88)" stroke="#2acb55" stroke-width="6.5"/>
      <circle r="15" fill="none" stroke="#064d98" stroke-width="1.6" opacity=".5"/>
      <path class="qpa__lens-tick" pathLength="1" d="m-9 0 6.5 6.5 12-13" fill="none" stroke="#2acb55" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>
    </g>
  </svg>`;

  const registry = new WeakMap();

  function create(host) {
    host.innerHTML = MARKUP;
    const svg = host.querySelector("svg");
    const q = (s) => svg.querySelector(s);
    const qa = (s) => [...svg.querySelectorAll(s)];
    const el = {
      rig: q(".qpa__rig"),
      body: q(".qpa__body"),
      face: q(".qpa__face"),
      eyes: qa(".qpa__eye"),
      cheeks: qa(".qpa__cheek"),
      smile: q(".qpa__smile"),
      talk: q(".qpa__talk"),
      shield: q(".qpa__shield"),
      lines: qa(".qpa__lines path"),
      lens: q(".qpa__lens"),
      tick: q(".qpa__lens-tick"),
      shadow: q(".qpa__shadow"),
    };

    /* every animatable channel lives here; tweens write, render() reads */
    const st = {
      sx: 1, sy: 1, jump: 0, float: 0, breathe: 1, tilt: 0,
      morph: 0, lines: 0, shield: 1, blink: 1, lookX: 0, lookY: 0,
      talk: 0, blush: 0, lens: 0, lx: 152, ly: 34, tick: 0,
    };
    let raf = 0;
    const set = (patch) => {
      Object.assign(st, patch);
      if (!raf) raf = requestAnimationFrame(render);
    };

    function render() {
      raf = 0;
      const m = st.morph;
      const mc = clamp(m);
      const ty = st.jump + st.float;
      const bx = st.sx * (1 - (st.breathe - 1) * 0.6);
      const by = st.sy * st.breathe;
      el.rig.setAttribute(
        "transform",
        `translate(0 ${ty}) translate(100 205) rotate(${st.tilt}) scale(${bx} ${by}) translate(-100 -205)`
      );

      el.body.setAttribute("x", lerp(BODY.x, DOC.x, m));
      el.body.setAttribute("y", lerp(BODY.y, DOC.y, m));
      el.body.setAttribute("width", Math.max(1, lerp(BODY.w, DOC.w, m)));
      el.body.setAttribute("height", Math.max(1, lerp(BODY.h, DOC.h, m)));
      el.body.setAttribute("rx", Math.max(0, lerp(BODY.rx, DOC.rx, m)));
      el.body.setAttribute("fill", mix(NAVY, WHITE, mc));
      el.body.setAttribute("stroke-width", 6 * mc);

      el.face.setAttribute("transform", `translate(100 ${76 - 4 * mc}) scale(${1 - 0.1 * mc}) translate(-100 -76)`);

      el.eyes.forEach((g, i) => {
        const cx = EYES[i];
        g.setAttribute(
          "transform",
          `translate(${cx + st.lookX} ${EYE_Y + st.lookY}) scale(1 ${Math.max(0.06, st.blink)}) translate(${-cx} ${-EYE_Y})`
        );
      });
      el.cheeks.forEach((c) => c.setAttribute("opacity", 0.75 + st.blush * 0.25));
      el.cheeks.forEach((c) => c.setAttribute("ry", 5.8 + st.blush * 1.6));
      el.smile.setAttribute("opacity", 1 - clamp(st.talk * 1.4));
      el.talk.setAttribute("ry", 7.5 * clamp(st.talk));

      const s = Math.max(0, st.shield);
      el.shield.setAttribute("transform", `translate(100 154) scale(${s}) translate(-100 -154)`);
      el.shield.setAttribute("opacity", clamp(s * 1.5));

      el.lines.forEach((p, i) => {
        const t = clamp(st.lines * 1.7 - i * 0.22);
        p.setAttribute("stroke-dasharray", "1 1");
        p.setAttribute("stroke-dashoffset", 1 - t);
        p.setAttribute("opacity", t > 0 ? 1 : 0);
      });

      const ls = Math.max(0, st.lens);
      el.lens.setAttribute("opacity", clamp(ls * 1.4));
      el.lens.setAttribute("transform", `translate(${st.lx} ${st.ly}) scale(${ls})`);
      el.tick.setAttribute("stroke-dasharray", "1 1");
      el.tick.setAttribute("stroke-dashoffset", 1 - clamp(st.tick));

      const lift = clamp(-ty / 26);
      el.shadow.setAttribute("rx", 58 * (1 - lift * 0.35) * (st.sx * 0.5 + 0.5));
      el.shadow.setAttribute("opacity", 1 - lift * 0.5);
    }

    const chans = {};
    function to(key, value, opt = {}) {
      if (chans[key]) chans[key].stop();
      if (!M) {
        set({ [key]: last(value) });
        return Promise.resolve();
      }
      const c = M.animate(st[key], value, { ...opt, onUpdate: (v) => set({ [key]: v }) });
      chans[key] = c;
      return c.then ? c.then(() => {}, () => {}) : Promise.resolve();
    }

    const SPRING = { type: "spring", stiffness: 300, damping: 20 };
    const BOUNCY = { type: "spring", stiffness: 210, damping: 11 };

    function blink(double = false) {
      return to("blink", double ? [1, 0.06, 1, 0.06, 1] : [1, 0.06, 1], {
        duration: double ? 0.42 : 0.2,
        ease: "easeInOut",
      });
    }

    function hop() {
      const t = { duration: 0.78, times: [0, 0.16, 0.42, 0.68, 0.84, 1], ease: "easeOut" };
      to("sy", [1, 0.84, 1.14, 0.9, 1.03, 1], t);
      to("sx", [1, 1.14, 0.9, 1.1, 0.98, 1], t);
      to("jump", [0, 3, -26, 0, 0, 0], t);
      to("blush", [0, 1, 1, 0.4], { duration: 1.2 });
      return sleep(780);
    }

    function happy() {
      blink(true);
      to("tilt", [0, -7, 6, -3, 0], { duration: 0.9, ease: "easeInOut" });
      to("blush", [0, 1, 0], { duration: 1.4 });
      return hop();
    }

    let talking = null;
    function talk(on) {
      if (talking) { talking.stop(); talking = null; }
      if (!on || !M) return to("talk", 0, { duration: 0.15 });
      talking = M.animate(0, [0, 1, 0.25, 0.85, 0.1, 0.7, 0], {
        duration: 1.1,
        repeat: Infinity,
        ease: "easeInOut",
        onUpdate: (v) => set({ talk: v }),
      });
    }

    let scanning = false;
    async function scan() {
      if (scanning || !M || dead) return false;
      scanning = true;
      await to("sy", [1, 0.88, 1], { duration: 0.28, ease: "easeInOut" });
      to("sx", [1, 1.08, 1], { duration: 0.28 });
      to("shield", 0, { duration: 0.2, ease: "easeIn" });
      to("morph", 1, { type: "spring", stiffness: 170, damping: 13 });
      await sleep(240);
      to("lines", 1, { duration: 0.7, ease: [0.16, 1, 0.3, 1] });
      set({ lx: 156, ly: 30, tick: 0 });
      await to("lens", 1, BOUNCY);
      const path = { duration: 1.5, ease: "easeInOut", times: [0, 0.3, 0.55, 0.8, 1] };
      to("lx", [156, 72, 132, 80, 156], path);
      await to("ly", [30, 136, 158, 182, 30], path);
      await to("tick", 1, { duration: 0.35, ease: "easeOut" });
      blink(true);
      await sleep(520);
      to("lens", 0, { duration: 0.22, ease: "easeIn" });
      to("lines", 0, { duration: 0.25, ease: "easeIn" });
      await sleep(140);
      to("morph", 0, { type: "spring", stiffness: 190, damping: 10 });
      await sleep(180);
      to("shield", [0, 1.3, 1], { duration: 0.5, ease: [0.34, 1.56, 0.64, 1] });
      await happy();
      scanning = false;
      return true;
    }

    /* idle life: breathe, blink, glance — never in lockstep */
    let dead = false;
    let timers = [];
    const later = (fn, ms) => {
      if (!dead) timers.push(setTimeout(() => (host.isConnected ? fn() : destroy()), ms));
    };
    function idle(mode) {
      if (!M) return;
      to("breathe", [1, 1.028, 1], { duration: 3.4, repeat: Infinity, ease: "easeInOut" });
      if (mode === "hero") to("float", [0, -8, 0], { duration: 3.4, repeat: Infinity, ease: "easeInOut" });
      const loopBlink = () => {
        blink(Math.random() < 0.25);
        later(loopBlink, 2200 + Math.random() * 2800);
      };
      later(loopBlink, 900 + Math.random() * 1500);
      if (!host.hasAttribute("data-qpa-track")) {
        const glance = () => {
          if (!scanning) {
            to("lookX", (Math.random() - 0.5) * 7, SPRING);
            to("lookY", (Math.random() - 0.5) * 4, SPRING);
          }
          later(glance, 1800 + Math.random() * 2400);
        };
        later(glance, 1400);
      }
      if (mode === "hero") {
        const loopScan = async () => {
          await scan();
          later(loopScan, 4200);
        };
        later(loopScan, 1600);
      }
    }

    let onMove = null;
    function track() {
      if (!M) return;
      let pending = false;
      window.addEventListener("pointermove", (onMove = (e) => {
        if (pending) return;
        pending = true;
        requestAnimationFrame(() => {
          pending = false;
          const r = svg.getBoundingClientRect();
          if (!r.width) return;
          const dx = e.clientX - (r.left + r.width / 2);
          const dy = e.clientY - (r.top + r.height * 0.32);
          const d = Math.hypot(dx, dy) || 1;
          const reach = Math.min(1, d / 260);
          to("lookX", (dx / d) * 4.2 * reach, SPRING);
          to("lookY", (dy / d) * 3 * reach, SPRING);
        });
      }), { passive: true });
    }

    function destroy() {
      dead = true;
      if (onMove) window.removeEventListener("pointermove", onMove);
      registry.delete(host);
      timers.forEach(clearTimeout);
      Object.values(chans).forEach((c) => c.stop && c.stop());
      if (talking) talking.stop();
    }

    render();
    const mode = host.getAttribute("data-qpa") || "mark";
    idle(mode);
    if (host.hasAttribute("data-qpa-track")) track();
    if (host.hasAttribute("data-qpa-hop")) {
      const target = host.closest("a, button") || host;
      target.addEventListener("pointerenter", () => hop());
      target.addEventListener("click", () => hop());
    }

    const api = { hop, scan, talk, happy, blink, destroy };
    registry.set(host, api);
    return api;
  }

  function mountAll(root = document) {
    root.querySelectorAll("[data-qpa]").forEach((h) => {
      if (!registry.has(h)) create(h);
    });
  }

  function destroyAll(root) {
    root.querySelectorAll("[data-qpa]").forEach((h) => registry.get(h)?.destroy());
  }

  window.QPAvatar = { mount: create, mountAll, destroyAll, get: (h) => registry.get(h) };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => mountAll());
  else mountAll();
})();

# DESIGN.md — Claviq Agent Copilot (Quickinsure skin)

Tokens below were read from the computed styles of https://quickinsure.co.in on 2026-11-10.
They are measured, not invented. Re-run the extraction if the site is restyled.

## 1. Reference

Quickinsure.co.in — Next.js marketing + quote funnel. Flat, bright, high-trust Indian
insurtech look. Navy headings, a loud green for emphasis, generous white, soft 15px
cards, flat illustrations. No gradients, no glass, no dark mode.

## 2. Tone

Plain and fast. The agent is mid-call with a customer. Nothing decorative may slow a
read. Confidence comes from citations and dates, not from visual weight.

## 3. Audience

Insurance agents on a laptop, often in a noisy office, typing English / Hindi / Hinglish.
Not consumers, not the CEO — though the CEO watches the demo.

## 4. Tokens

```css
:root {
  /* brand */
  --qi-navy:        #064D98;  /* rgb(6,77,152)   headings, primary bg, logo blue */
  --qi-navy-2:      #1F4E93;  /* rgb(31,78,147)  secondary/interactive navy */
  --qi-slate:       #2A3F55;  /* rgb(42,63,85)   dark section bg, footer */
  --qi-green:       #2ACB55;  /* rgb(42,203,85)  emphasis only — FAST/EASY/TRANSPARENT */
  --qi-link:        #007BFF;  /* rgb(0,123,255)  link blue (Bootstrap default, inherited) */

  /* neutrals */
  --qi-ink:         #333333;  /* body text */
  --qi-ink-strong:  #101010;
  --qi-muted:       #707070;
  --qi-line:        #BFB9B9;
  --qi-surface:     #FFFFFF;
  --qi-surface-2:   #F6F6F6;  /* section band */

  /* type */
  --qi-font: Assistant, system-ui, sans-serif;  /* Google Fonts: Assistant */
  --qi-fs-body: 16px;
  --qi-lh: 1.2;          /* site runs tight 1.2 on headings */
  --qi-lh-body: 1.55;    /* our override — 1.2 is unreadable for clause text */

  /* shape */
  --qi-r-card: 15px;
  --qi-r-input: 4px;
  --qi-r-pill: 28px;
}
```

### Type scale (measured)

| Role | Size | Weight | Color |
|---|---|---|---|
| H1 | 34px | 700 | `--qi-navy` |
| H2 section | 34px | 600 | `--qi-navy` |
| H2 emphasis | 60px | 700 | `--qi-green` |
| H3 | 22–28px | 500 | `--qi-navy` / `--qi-ink` |
| Body | 16px | 400 | `--qi-ink` |

Assistant is the whole system — display and UI both. It is a Hebrew/Latin family and has
**no Devanagari**. For Hindi answers pair with **Noto Sans Devanagari** at the same weights;
set it first in the stack for `[lang="hi"]` only, so English never shifts.

## 5. Required

- Citation card is the hero element, not an afterthought: quoted clause, page, section no.
- Product disambiguation must be visible before any answer renders. Never auto-pick.
- Every number in an answer carries its page ref inline.
- Waiting-period answers show an absolute date, not only a duration.
- Withdrawn products render with a persistent strikethrough + replacement link, never silent.
- Buttons size to their label. Never full-width.
- Motion: springs for movement, long ease-out for reveals, one shared timing set,
  `prefers-reduced-motion` respected.
- Feedback inside 400ms; streamed tokens count as feedback.

## 6. Banned

- Slate/zinc backgrounds, gradient blobs, gradient text, purple accents.
- Icon badges in rounded squares, three-card feature grids.
- Fake charts, fake logos, invented proof numbers.
- Stock photos of people, emoji.
- Buzzwords ("seamless", "revolutionise", "AI-powered").
- Inter as the display face — Assistant is the brand face.
- `--qi-green` as a surface or a body color. It is emphasis only; at 16px on white it is
  below WCAG AA (~1.9:1). Use `--qi-navy` for anything that must be read.

## 7. Self-review before showing

1. Could this screen be any other product's? If yes, it is not Quickinsure.
2. Is any clause text under 1.4 line-height?
3. Does every number trace to a page?
4. Does green appear anywhere a user must read?
5. Does it survive 320px and a 10-inch laptop?

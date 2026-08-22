"""Shared visual language for the HTML reports.

One stylesheet, inlined into every page so a document is a single file that can
be emailed, opened offline, or printed to PDF without anything else alongside it.

Colour carries information here rather than decoration: each action category
(audio, caller input, logic, routing, data, end-of-call) has its own hue, so a
reader can see the shape of a flow before reading a word of it.
"""

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=Archivo:wght@600;700&'
    'family=IBM+Plex+Mono:wght@400;500;600&'
    'family=IBM+Plex+Sans:wght@400;500;600&display=swap">'
)

CSS = """
:root {
  --ground:      #f4f6f7;
  --surface:     #ffffff;
  --surface-2:   #eef1f3;
  --ink:         #121a20;
  --ink-2:       #3d4c58;
  --muted:       #61717e;
  --hairline:    #dde3e7;
  --hairline-2:  #c9d3d9;
  --accent:      #0b6e62;
  --accent-ink:  #ffffff;
  --accent-wash: #e3f0ed;

  --cat-audio:   #2f6fb0;
  --cat-input:   #a86a12;
  --cat-logic:   #6b5bb5;
  --cat-routing: #0b6e62;
  --cat-data:    #4a6070;
  --cat-bot:     #157a8c;
  --cat-terminal:#a44a4a;
  --cat-other:   #61717e;

  --shadow: 0 1px 2px rgba(18, 26, 32, .06), 0 8px 24px -16px rgba(18, 26, 32, .28);

  --step-1: .35rem;
  --step-2: .7rem;
  --step-3: 1.1rem;
  --step-4: 1.8rem;
  --step-5: 3rem;
  --radius: 10px;
  --measure: 68ch;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground:      #0d1317;
    --surface:     #141d23;
    --surface-2:   #1b262d;
    --ink:         #e7edf1;
    --ink-2:       #bdcbd5;
    --muted:       #90a1ad;
    --hairline:    #253139;
    --hairline-2:  #33434e;
    --accent:      #45c3ac;
    --accent-ink:  #06231f;
    --accent-wash: #14332f;

    --cat-audio:   #7cb2e8;
    --cat-input:   #e0aa5c;
    --cat-logic:   #a496e8;
    --cat-routing: #45c3ac;
    --cat-data:    #9ab0c0;
    --cat-bot:     #5cc2d6;
    --cat-terminal:#e08a8a;
    --cat-other:   #90a1ad;

    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 10px 28px -18px rgba(0,0,0,.9);
  }
}

:root[data-theme="dark"] {
  --ground:      #0d1317;
  --surface:     #141d23;
  --surface-2:   #1b262d;
  --ink:         #e7edf1;
  --ink-2:       #bdcbd5;
  --muted:       #90a1ad;
  --hairline:    #253139;
  --hairline-2:  #33434e;
  --accent:      #45c3ac;
  --accent-ink:  #06231f;
  --accent-wash: #14332f;

  --cat-audio:   #7cb2e8;
  --cat-input:   #e0aa5c;
  --cat-logic:   #a496e8;
  --cat-routing: #45c3ac;
  --cat-data:    #9ab0c0;
  --cat-bot:     #5cc2d6;
  --cat-terminal:#e08a8a;
  --cat-other:   #90a1ad;

  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 10px 28px -18px rgba(0,0,0,.9);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font-family: "IBM Plex Sans", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 16px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}

h1, h2, h3, h4 {
  font-family: Archivo, "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
  font-weight: 700;
  text-wrap: balance;
  margin: 0;
  line-height: 1.2;
}
h1 { font-size: clamp(1.9rem, 1.2rem + 2.4vw, 2.9rem); letter-spacing: -.022em; }
h2 { font-size: 1.45rem; letter-spacing: -.014em; }
h3 { font-size: 1.08rem; letter-spacing: -.008em; }
h4 { font-size: .98rem; letter-spacing: -.004em; font-weight: 600; }
p  { margin: 0; }

a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }
a:focus-visible, summary:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: 3px;
}

.eyebrow {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: .715rem;
  font-weight: 500;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: var(--muted);
}

/* ---------------------------------------------------------------- shell */

.page {
  max-width: 1220px;
  margin: 0 auto;
  padding: 0 var(--step-4) var(--step-5);
}

.masthead {
  border-bottom: 1px solid var(--hairline);
  padding: var(--step-5) 0 var(--step-4);
  margin-bottom: var(--step-4);
  display: flex;
  flex-direction: column;
  gap: var(--step-2);
}
.masthead__kicker {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--step-2);
}
.masthead__rule {
  width: 2.6rem;
  height: 3px;
  background: var(--accent);
  border-radius: 2px;
}
.masthead__sub {
  color: var(--ink-2);
  max-width: var(--measure);
  font-size: 1.05rem;
}
.masthead__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--step-1) var(--step-3);
  color: var(--muted);
  font-size: .84rem;
  padding-top: var(--step-1);
}

.layout {
  display: grid;
  grid-template-columns: 218px minmax(0, 1fr);
  gap: var(--step-5);
  align-items: start;
}
@media (max-width: 940px) {
  .layout { grid-template-columns: minmax(0, 1fr); gap: var(--step-4); }
  .rail { position: static; }
}

.rail {
  position: sticky;
  top: var(--step-3);
  display: flex;
  flex-direction: column;
  gap: var(--step-2);
}
.rail__title { margin-bottom: var(--step-1); }
.rail ol { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.rail a {
  display: block;
  padding: .3rem 0 .3rem var(--step-2);
  border-left: 2px solid var(--hairline);
  color: var(--ink-2);
  text-decoration: none;
  font-size: .88rem;
}
.rail a:hover { border-left-color: var(--accent); color: var(--ink); }

.stack { display: flex; flex-direction: column; gap: var(--step-5); min-width: 0; }

.panel { display: flex; flex-direction: column; gap: var(--step-3); scroll-margin-top: var(--step-3); }
.panel__intro { color: var(--muted); max-width: var(--measure); font-size: .94rem; }

/* ----------------------------------------------------------- fact cards */

.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--step-2);
}
.fact {
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--radius);
  padding: var(--step-3);
  display: flex;
  flex-direction: column;
  gap: .2rem;
  box-shadow: var(--shadow);
}
.fact__value {
  font-family: Archivo, sans-serif;
  font-weight: 700;
  font-size: 1.5rem;
  line-height: 1.15;
  letter-spacing: -.02em;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.fact__value--sm { font-size: 1.05rem; line-height: 1.35; }

/* --------------------------------------------------------------- tables */

.scroller { overflow-x: auto; }

table {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--radius);
  overflow: hidden;
  font-size: .92rem;
}
th, td {
  text-align: left;
  padding: .62rem .85rem;
  border-bottom: 1px solid var(--hairline);
  vertical-align: top;
}
thead th {
  background: var(--surface-2);
  font-size: .72rem;
  font-weight: 600;
  letter-spacing: .09em;
  text-transform: uppercase;
  color: var(--muted);
  white-space: nowrap;
}
tbody tr:last-child td { border-bottom: 0; }
td.num { font-variant-numeric: tabular-nums; }
code, .mono {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: .86em;
}
td code { color: var(--ink-2); overflow-wrap: anywhere; }

/* ---------------------------------------------------------------- chips */

.chipset { display: flex; flex-direction: column; gap: var(--step-2); }
.chipset__row { display: flex; flex-wrap: wrap; gap: .4rem; align-items: baseline; }
.chipset__label {
  flex: 0 0 9.5rem;
  color: var(--muted);
  font-size: .8rem;
  font-weight: 600;
  padding-top: .15rem;
}
.chip {
  background: var(--surface);
  border: 1px solid var(--hairline-2);
  border-radius: 999px;
  padding: .18rem .62rem;
  font-size: .82rem;
  color: var(--ink-2);
}
.chip--accent { background: var(--accent-wash); border-color: transparent; color: var(--accent); font-weight: 500; }

/* ------------------------------------------------------------- keypad */

.dtmf {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-weight: 600;
  font-size: .82rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.85rem;
  height: 1.85rem;
  padding: 0 .35rem;
  border-radius: 7px;
  background: var(--surface-2);
  border: 1px solid var(--hairline-2);
  color: var(--ink);
}
.dtmf--wide { min-width: auto; font-size: .72rem; padding: 0 .5rem; }

/* --------------------------------------------------------- journey track */

.track { list-style: none; margin: 0; padding: 0 0 0 0; display: flex; flex-direction: column; }
.stage {
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow: hidden;
}
.stage + .stage { margin-top: var(--step-3); }
.stage__head {
  display: flex;
  flex-wrap: wrap;
  gap: var(--step-1) var(--step-2);
  align-items: baseline;
  padding: var(--step-3);
  border-bottom: 1px solid var(--hairline);
  background: var(--surface-2);
}
.stage__head h3 { margin-right: auto; }
.stage__body { padding: var(--step-3); display: flex; flex-direction: column; gap: var(--step-2); }

.step {
  position: relative;
  padding: 0 0 var(--step-3) var(--step-4);
  border-left: 2px solid var(--hairline-2);
}
.step:last-child { padding-bottom: 0; border-left-color: transparent; }
.step:last-child::after {
  content: "";
  position: absolute;
  left: -2px; top: 0; height: .95rem;
  border-left: 2px solid var(--hairline-2);
}
.step__dot {
  position: absolute;
  left: -.56rem;
  top: .28rem;
  width: 1.05rem;
  height: 1.05rem;
  border-radius: 50%;
  background: var(--surface);
  border: 2px solid var(--cat, var(--cat-other));
}
.step__dtmf { position: absolute; left: -1rem; top: 0; }
.step--dtmf { padding-left: 2.6rem; }
.step__head { display: flex; flex-wrap: wrap; gap: .35rem var(--step-2); align-items: baseline; }
.step__no {
  font-family: "IBM Plex Mono", monospace;
  font-size: .74rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.step__what { color: var(--ink-2); max-width: var(--measure); margin-top: .12rem; }

.tag {
  font-size: .68rem;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: var(--cat, var(--cat-other));
  border: 1px solid currentColor;
  border-radius: 4px;
  padding: .05rem .34rem;
  white-space: nowrap;
}

.branch { margin-top: var(--step-2); }
.branch__label {
  display: inline-flex;
  align-items: center;
  gap: .4rem;
  font-size: .74rem;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: .45rem;
}
.branch__label::before {
  content: "";
  width: .9rem; height: 1px;
  background: var(--hairline-2);
}

.say {
  margin: .5rem 0 0;
  padding: .5rem .8rem;
  border-left: 3px solid var(--cat-audio);
  background: var(--surface-2);
  border-radius: 0 6px 6px 0;
  color: var(--ink);
  font-size: .93rem;
  max-width: var(--measure);
}
.say--muted { border-left-color: var(--hairline-2); color: var(--muted); font-size: .88rem; }
.say__src {
  display: block;
  font-family: "IBM Plex Mono", monospace;
  font-size: .68rem;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: .12rem;
}

.jump {
  display: inline-block;
  margin-top: .4rem;
  font-size: .82rem;
  color: var(--muted);
}
.jump code { color: var(--ink-2); }

/* -------------------------------------------------------------- script */

.script { display: flex; flex-direction: column; gap: var(--step-2); }
.script__line {
  display: grid;
  grid-template-columns: 2.1rem minmax(0, 1fr);
  gap: var(--step-2);
  align-items: start;
  padding-bottom: var(--step-2);
  border-bottom: 1px solid var(--hairline);
}
.script__line:last-child { border-bottom: 0; padding-bottom: 0; }
.script__no {
  font-family: "IBM Plex Mono", monospace;
  font-size: .74rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  padding-top: .28rem;
}
.script__text { font-size: 1.02rem; max-width: var(--measure); }

/* ------------------------------------------------------------- callouts */

.note {
  border: 1px solid var(--hairline);
  border-left: 3px solid var(--cat-input);
  background: var(--surface);
  border-radius: 0 var(--radius) var(--radius) 0;
  padding: var(--step-2) var(--step-3);
  color: var(--ink-2);
  font-size: .92rem;
  max-width: var(--measure);
}
.note--ok { border-left-color: var(--accent); }
.note--flag { border-left-color: var(--cat-terminal); }
.note strong { color: var(--ink); }

.checklist { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--step-2); }
.checklist > li {
  display: grid;
  grid-template-columns: 1.15rem minmax(0, 1fr);
  gap: var(--step-2);
  color: var(--ink-2);
  max-width: var(--measure);
}
.checklist > li::before {
  content: "";
  width: .95rem; height: .95rem;
  margin-top: .32rem;
  border: 1.5px solid var(--hairline-2);
  border-radius: 3px;
}

/* Where calls end up: a category tag followed by a sentence, on one line.
   Deliberately not `.checklist` -- that is a two-column grid and a second
   child would be pushed into the narrow marker column. */
.outcomes { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--step-2); }
.outcomes li {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: .45rem;
  color: var(--ink-2);
  max-width: var(--measure);
}
.outcomes li > span:last-child { flex: 1 1 14rem; min-width: 0; }

/* ------------------------------------------------------------- diagrams */

.diagram {
  overflow-x: auto;
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--radius);
  padding: var(--step-3);
}
.diagram + .diagram { margin-top: var(--step-2); }
.diagram__caption {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: .7rem;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: var(--step-2);
}
svg.flowsvg { display: block; max-width: 100%; height: auto; }
.legend { display: flex; flex-wrap: wrap; gap: .35rem .9rem; font-size: .78rem; color: var(--muted); }
.legend span { display: inline-flex; align-items: center; gap: .35rem; }
.legend i {
  width: .7rem; height: .7rem; border-radius: 3px;
  background: var(--cat, var(--cat-other));
  display: inline-block;
}

/* --------------------------------------------------------------- detail */

details {
  border: 1px solid var(--hairline);
  border-radius: var(--radius);
  background: var(--surface);
  overflow: hidden;
}
summary {
  cursor: pointer;
  padding: .55rem .85rem;
  font-size: .85rem;
  font-weight: 500;
  color: var(--ink-2);
  background: var(--surface-2);
  list-style: none;
}
summary::-webkit-details-marker { display: none; }
summary::before { content: "▸ "; color: var(--muted); }
details[open] summary::before { content: "▾ "; }
details > .scroller, details > pre { border-top: 1px solid var(--hairline); }
details table { border: 0; border-radius: 0; }

pre {
  margin: 0;
  padding: var(--step-3);
  overflow-x: auto;
  font-family: "IBM Plex Mono", monospace;
  font-size: .78rem;
  line-height: 1.5;
  color: var(--ink-2);
  background: var(--surface);
}

.footer {
  margin-top: var(--step-5);
  padding-top: var(--step-3);
  border-top: 1px solid var(--hairline);
  color: var(--muted);
  font-size: .82rem;
  display: flex;
  flex-wrap: wrap;
  gap: var(--step-1) var(--step-3);
}

/* ---------------------------------------------------------------- index */

.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--step-3); }
.card {
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--radius);
  padding: var(--step-3);
  display: flex;
  flex-direction: column;
  gap: var(--step-1);
  box-shadow: var(--shadow);
}
.card h3 a { color: inherit; text-decoration: none; }
.card h3 a:hover { color: var(--accent); }
.card__links { display: flex; gap: var(--step-2); font-size: .85rem; margin-top: auto; padding-top: var(--step-2); }

@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}

@media print {
  :root { --shadow: none; }
  body { background: #fff; font-size: 10.5pt; }
  .rail, .footer__hint { display: none; }
  .layout { grid-template-columns: 1fr; }
  .page { padding: 0; max-width: none; }
  a { text-decoration: none; color: inherit; }

  /* Only ever protect boxes that comfortably fit a page. A stage card can be
     several pages tall, and `break-inside: avoid` on one of those leaves a
     mostly-blank page and then overflows anyway -- which is exactly the
     failure this replaces. Stages are allowed to split; the pieces inside
     them are not. */
  .fact, .note, .script__line, .chipset__row, tr { break-inside: avoid; }
  .step > .step__body > .step__head,
  .step > .step__body > .step__what { break-inside: avoid; }
  .diagram { break-inside: avoid-page; }
  .stage, .step, details, table { break-inside: auto; }

  /* Never strand a heading at the foot of a page. */
  h1, h2, h3, h4, .stage__head, .branch__label { break-after: avoid; }
  h2, h3 { break-inside: avoid; }
  p, li, blockquote { orphans: 3; widows: 3; }

  .panel { break-before: auto; }
  details { border-color: #ccc; }
  details[open] > summary { display: none; }   /* the label is noise on paper */
}
"""

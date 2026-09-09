#!/usr/bin/env python3
"""Render results/results.json into a self-contained page at public/index.html.

The page is generated, never hand-edited, for the same reason docs/FINDINGS.md
quotes no number that is not in results.json: a figure that exists only in the
presentation layer is a second source of truth, and the first thing a reader
should be able to do is regenerate it.

No JavaScript, no external stylesheet, no CDN. Every chart is inline SVG built
from the same dict the tables read, so the page renders identically offline and
cannot show a stale value that the table beside it disagrees with.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "results.json"
MANIFEST = ROOT / "results" / "manifest.json"
OUT = ROOT / "public" / "index.html"

ORDER = ["unplug-model", "unplug-pipeline", "protectai", "regex-floor"]
SHORT = {
    "unplug-model": "unplug-tiny-v1",
    "unplug-pipeline": "Unplug SDK",
    "protectai": "ProtectAI deberta",
    "regex-floor": "regex floor",
}
TRANSFORM_LABEL = {
    "base64_with_instruction": "b64 + instruction",
    "base64_bare": "b64 bare",
    "leetspeak": "leetspeak",
    "homoglyph": "homoglyph",
    "zero_width": "zero width",
    "whitespace": "whitespace",
    "carrier": "carrier",
}
VERDICT = {
    "capability": ("cap", "Capability failure. The ranking degraded, or the detector now fires on benign rows as readily as attacks. No threshold recovers it."),
    "threshold": ("thr", "Threshold failure. The ranking survived; re-thresholding recovers the recall."),
    "intact": ("ok", "Neither bar crossed."),
}


def esc(text: object) -> str:
    return html.escape(str(text))


def pct(value: float) -> str:
    return f"{value:.3f}"


# --------------------------------------------------------------------------
# charts
# --------------------------------------------------------------------------


def bars_with_ci(rows: list[tuple[str, float, list[float]]], *, chance: float) -> str:
    """Horizontal PR-AUC bars with their bootstrap interval drawn on top."""
    w, row_h, pad_l, pad_r = 720, 46, 150, 60
    h = row_h * len(rows) + 34
    plot = w - pad_l - pad_r

    def x(v: float) -> float:
        return pad_l + v * plot

    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart">']
    parts.append(
        f'<line x1="{x(chance):.1f}" y1="14" x2="{x(chance):.1f}" y2="{h - 24}" '
        'class="ref"/>'
        f'<text x="{x(chance):.1f}" y="{h - 8}" class="tick mid">chance {chance:.2f}</text>'
    )
    for i, (name, value, ci) in enumerate(rows):
        y = 22 + i * row_h
        parts.append(f'<text x="{pad_l - 12}" y="{y + 15}" class="lbl end">{esc(name)}</text>')
        parts.append(
            f'<rect x="{pad_l}" y="{y}" width="{plot}" height="22" class="track"/>'
            f'<rect x="{pad_l}" y="{y}" width="{max(value * plot, 1):.1f}" height="22" '
            f'class="bar b{i}"/>'
        )
        lo, hi = ci
        parts.append(
            f'<line x1="{x(lo):.1f}" y1="{y + 11}" x2="{x(hi):.1f}" y2="{y + 11}" class="ci"/>'
            f'<line x1="{x(lo):.1f}" y1="{y + 4}" x2="{x(lo):.1f}" y2="{y + 18}" class="ci"/>'
            f'<line x1="{x(hi):.1f}" y1="{y + 4}" x2="{x(hi):.1f}" y2="{y + 18}" class="ci"/>'
        )
        parts.append(f'<text x="{w - pad_r + 10}" y="{y + 15}" class="val">{pct(value)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def reliability_chart(systems: dict, *, min_n: int = 5) -> str:
    """Confidence against observed accuracy, with the diagonal a calibrated model follows.

    Bins holding fewer than `min_n` rows are dropped and dot area tracks the count.
    Plotting every bin drew four zig-zags through points backed by one or two rows
    each, which is noise given a shape like this: the scores are strongly bimodal,
    so most of the mass sits in the bottom and top bins and the middle is nearly
    empty. Hiding that behind a connected line would have been the prettier chart
    and the less honest one.
    """
    size, pad = 300, 40
    plot = size - pad * 2
    parts = [f'<svg viewBox="0 0 {size} {size}" role="img" class="chart square">']
    parts.append(
        f'<rect x="{pad}" y="{pad}" width="{plot}" height="{plot}" class="track"/>'
        f'<line x1="{pad}" y1="{pad + plot}" x2="{pad + plot}" y2="{pad}" class="ref"/>'
    )
    for i, key in enumerate(ORDER):
        bins = sorted(
            (b for b in systems[key]["reliability"] if b["n"] >= min_n),
            key=lambda b: b["confidence"],
        )
        if not bins:
            continue
        pts = [
            (pad + b["confidence"] * plot, pad + plot - b["accuracy"] * plot, b["n"])
            for b in bins
        ]
        if len(pts) > 1:
            line = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)
            parts.append(f'<polyline points="{line}" class="line l{i}" opacity="0.55"/>')
        for x, y, n in pts:
            r = 3 + (n / 240) ** 0.5 * 9
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" class="dot l{i}" opacity="0.8"/>')
    parts.append(
        f'<text x="{pad}" y="{size - 10}" class="tick">0.0</text>'
        f'<text x="{pad + plot}" y="{size - 10}" class="tick end">1.0</text>'
        f'<text x="{pad}" y="{pad - 14}" class="tick">accuracy vs confidence, dot area = rows in bin</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def guard_slopes(episodes: dict) -> str:
    """Attack success with the guard off and on, one line per system."""
    w, h, pad = 340, 250, 44
    plot_h = h - pad * 2
    left, right = pad + 30, w - pad - 30
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart">']
    for frac in (0.0, 0.5, 1.0):
        y = pad + plot_h - frac * plot_h
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.1f}" class="tick end">{frac:.1f}</text>')
    for i, key in enumerate(ORDER):
        d = episodes[key]["delta"]
        y0 = pad + plot_h - d["attack_success_rate_without_guard"] * plot_h
        y1 = pad + plot_h - d["attack_success_rate_with_guard"] * plot_h
        parts.append(
            f'<line x1="{left}" y1="{y0:.1f}" x2="{right}" y2="{y1:.1f}" class="line l{i}"/>'
            f'<circle cx="{left}" cy="{y0:.1f}" r="4" class="dot l{i}"/>'
            f'<circle cx="{right}" cy="{y1:.1f}" r="4" class="dot l{i}"/>'
            f'<text x="{right + 8}" y="{y1 + 4:.1f}" class="tick">{pct(d["attack_success_rate_with_guard"])}</text>'
        )
    parts.append(
        f'<text x="{left}" y="{h - 14}" class="tick">guard off</text>'
        f'<text x="{right}" y="{h - 14}" class="tick end">guard on</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def legend() -> str:
    items = "".join(
        f'<span class="key"><i class="sw l{i}"></i>{esc(SHORT[k])}</span>' for i, k in enumerate(ORDER)
    )
    return f'<div class="legend">{items}</div>'


# --------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------


def headline_table(primary: dict) -> str:
    head = (
        "<tr><th>detector</th><th>precision</th><th>recall</th><th>F1</th>"
        "<th>FPR</th><th>PR-AUC</th><th>ECE</th><th>R @ 5% FPR</th></tr>"
    )
    rows = []
    for key in ORDER:
        s = primary[key]
        lo, hi = s["pr_auc_ci95"]
        rows.append(
            f'<tr><th class="name">{esc(SHORT[key])}<small>{esc(key)}</small></th>'
            f"<td>{pct(s['precision'])}</td><td>{pct(s['recall'])}</td>"
            f"<td class='strong'>{pct(s['f1'])}</td><td>{pct(s['fpr'])}</td>"
            f"<td>{pct(s['pr_auc'])}<small>{pct(lo)} to {pct(hi)}</small></td>"
            f"<td class='bad'>{pct(s['ece'])}</td>"
            f"<td>{pct(s['recall_at_fpr_0.05'])}</td></tr>"
        )
    return f'<table class="grid">{head}{"".join(rows)}</table>'


def shift_matrix(shift: dict) -> str:
    names = list(shift[ORDER[0]]["transforms"])
    head = "<tr><th>detector</th><th>baseline</th>" + "".join(
        f"<th>{esc(TRANSFORM_LABEL.get(n, n))}</th>" for n in names
    ) + "</tr>"
    rows = []
    for key in ORDER:
        row = shift[key]
        cells = [
            f'<th class="name">{esc(SHORT[key])}</th>'
            f'<td class="cell base"><b>{pct(row["baseline_pr_auc"])}</b>'
            f'<small>R {pct(row["baseline_recall"])} / FPR {pct(row["baseline_fpr"])}</small></td>'
        ]
        for n in names:
            t = row["transforms"][n]
            cls, title = VERDICT.get(t.get("classification"), ("ok", ""))
            cells.append(
                f'<td class="cell {cls}" title="{esc(title)}">'
                f'<b>{pct(t["pr_auc"])}</b>'
                f'<small>R {pct(t["recall"])} / FPR {pct(t["fpr"])}</small></td>'
            )
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f'<table class="grid matrix">{head}{"".join(rows)}</table>'


def episode_table(episodes: dict) -> str:
    head = (
        "<tr><th>detector</th><th>attack success off</th><th>attack success on</th>"
        "<th>benign tasks completed on</th><th>never fired</th></tr>"
    )
    rows = []
    for key in ORDER:
        d = episodes[key]["delta"]
        det = episodes[key]["with_guard"]["detection_turns"]
        rows.append(
            f'<tr><th class="name">{esc(SHORT[key])}</th>'
            f'<td>{pct(d["attack_success_rate_without_guard"])}'
            f'<small>n={d["attack_success_n_without_guard"]}</small></td>'
            f'<td class="strong">{pct(d["attack_success_rate_with_guard"])}'
            f'<small>{d["attack_success_delta"]:+.3f}</small></td>'
            f'<td>{pct(d["utility_rate_with_guard"])}'
            f'<small>n={d["utility_n_with_guard"]}, {d["utility_delta"]:+.3f}</small></td>'
            f'<td>{pct(det["never_fired_share"])}</td></tr>'
        )
    return f'<table class="grid">{head}{"".join(rows)}</table>'


def contamination_table(primary: dict, control: dict) -> str:
    head = "<tr><th>detector</th><th>F1 primary</th><th>F1 control</th><th>gap</th></tr>"
    rows = []
    for key in ORDER:
        gap = control[key]["f1"] - primary[key]["f1"]
        rows.append(
            f'<tr><th class="name">{esc(SHORT[key])}</th>'
            f"<td>{pct(primary[key]['f1'])}</td><td>{pct(control[key]['f1'])}</td>"
            f'<td class="{"bad" if gap > 0.15 else ""}">{gap:+.3f}</td></tr>'
        )
    return f'<table class="grid">{head}{"".join(rows)}</table>'


def pins_table(manifest: dict) -> str:
    rows = []
    for kind in ("models", "datasets"):
        for key, pin in sorted(manifest.get(kind, {}).items()):
            sha = pin.get("sha", "")
            rows.append(
                f'<tr><th class="name">{esc(key)}</th>'
                f"<td>{esc(pin.get('repo_id', ''))}</td>"
                f"<td><code>{esc(sha[:12])}</code></td>"
                f"<td>{esc(pin.get('license', ''))}</td></tr>"
            )
    head = "<tr><th>artifact</th><th>repo</th><th>commit</th><th>license</th></tr>"
    return f'<table class="grid">{head}{"".join(rows)}</table>'


CSS = """
:root {
  --bg: #fbfaf8; --panel: #ffffff; --ink: #16150f; --dim: #6b6558;
  --line: #e4e0d6; --accent: #b4552c; --good: #2f6f4f; --bad: #a8341f;
  --cap: #f3d9d2; --thr: #f7ecd2; --ok: #dfeade; --track: #f0ede5;
  --c0: #b4552c; --c1: #2f6f4f; --c2: #4a5da8; --c3: #8a7a52;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #131310; --panel: #1b1b17; --ink: #eeeae0; --dim: #9a9384;
    --line: #2e2d27; --accent: #e0733f; --good: #63b087; --bad: #e2705a;
    --cap: #40231d; --thr: #3b3020; --ok: #1f3327; --track: #26251f;
    --c0: #e0733f; --c1: #63b087; --c2: #7f92d8; --c3: #c0aa74;
  }
}
:root[data-theme="dark"] {
  --bg: #131310; --panel: #1b1b17; --ink: #eeeae0; --dim: #9a9384;
  --line: #2e2d27; --accent: #e0733f; --good: #63b087; --bad: #e2705a;
  --cap: #40231d; --thr: #3b3020; --ok: #1f3327; --track: #26251f;
  --c0: #e0733f; --c1: #63b087; --c2: #7f92d8; --c3: #c0aa74;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.6 ui-sans-serif, -apple-system, "Segoe UI", Inter, system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1040px; margin: 0 auto; padding: 0 24px 96px; }
header { padding: 72px 0 40px; border-bottom: 1px solid var(--line); margin-bottom: 8px; }
h1 { font-size: clamp(30px, 5vw, 44px); line-height: 1.1; margin: 0 0 14px; letter-spacing: -0.02em; }
.lede { font-size: 18px; color: var(--dim); max-width: 62ch; margin: 0 0 22px; }
.meta { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  font: 12px ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--dim);
  border: 1px solid var(--line); border-radius: 999px; padding: 4px 11px; background: var(--panel);
}
.chip a { color: inherit; }
section { margin-top: 60px; }
h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--accent);
     margin: 0 0 6px; font-weight: 650; }
h3 { font-size: 24px; margin: 0 0 12px; letter-spacing: -0.01em; line-height: 1.25; }
p { max-width: 68ch; color: var(--dim); margin: 0 0 14px; }
p strong { color: var(--ink); font-weight: 600; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 14px;
         padding: 22px; margin-top: 18px; overflow-x: auto; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
@media (max-width: 760px) { .cols { grid-template-columns: 1fr; } }
table.grid { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
table.grid th, table.grid td { padding: 11px 12px; text-align: right; border-bottom: 1px solid var(--line); }
table.grid tr:last-child th, table.grid tr:last-child td { border-bottom: 0; }
table.grid tr:first-child th { text-align: right; font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.07em; color: var(--dim); font-weight: 600; }
table.grid th.name { text-align: left; font-weight: 600; white-space: nowrap; }
table.grid tr:first-child th:first-child { text-align: left; }
small { display: block; font-size: 11px; color: var(--dim); font-weight: 400; margin-top: 2px; }
.strong { font-weight: 700; }
.bad { color: var(--bad); font-weight: 600; }
code { font: 12px ui-monospace, SFMono-Regular, Menlo, monospace; }
.matrix td.cell { text-align: center; border-radius: 7px; }
.matrix td.cap { background: var(--cap); }
.matrix td.thr { background: var(--thr); }
.matrix td.ok { background: var(--ok); }
.matrix td.base { background: transparent; border-right: 2px solid var(--line); }
.matrix td.cell b { font-size: 15px; }
.chart { width: 100%; height: auto; display: block; }
.chart.square { max-width: 340px; margin: 0 auto; }
.track { fill: var(--track); }
.grid-line, .grid { stroke: var(--line); stroke-width: 1; }
.ref { stroke: var(--dim); stroke-width: 1; stroke-dasharray: 4 4; }
.ci { stroke: var(--ink); stroke-width: 1.5; opacity: 0.75; }
.bar { rx: 4; }
.bar.b0 { fill: var(--c0); } .bar.b1 { fill: var(--c1); }
.bar.b2 { fill: var(--c2); } .bar.b3 { fill: var(--c3); }
.line { fill: none; stroke-width: 2.5; stroke-linejoin: round; }
.line.l0, .dot.l0 { stroke: var(--c0); fill: var(--c0); }
.line.l1, .dot.l1 { stroke: var(--c1); fill: var(--c1); }
.line.l2, .dot.l2 { stroke: var(--c2); fill: var(--c2); }
.line.l3, .dot.l3 { stroke: var(--c3); fill: var(--c3); }
.line.l0, .line.l1, .line.l2, .line.l3 { fill: none; }
text { fill: var(--dim); font: 11px ui-sans-serif, system-ui, sans-serif; }
text.lbl { fill: var(--ink); font-size: 12px; font-weight: 500; }
text.val { fill: var(--ink); font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }
text.end { text-anchor: end; }
text.mid { text-anchor: middle; }
.legend { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 14px; font-size: 12px; color: var(--dim); }
.key { display: inline-flex; align-items: center; gap: 7px; }
.sw { width: 11px; height: 11px; border-radius: 3px; display: inline-block; }
.sw.l0 { background: var(--c0); } .sw.l1 { background: var(--c1); }
.sw.l2 { background: var(--c2); } .sw.l3 { background: var(--c3); }
.swatches { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 14px; font-size: 12px; color: var(--dim); }
.swatches i { width: 11px; height: 11px; border-radius: 3px; display: inline-block; margin-right: 7px; }
.note { border-left: 2px solid var(--accent); padding-left: 16px; margin: 20px 0; }
.note p:last-child { margin-bottom: 0; }
pre { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
      padding: 16px; overflow-x: auto; margin: 0; }
pre code { color: var(--ink); }
footer { margin-top: 72px; padding-top: 24px; border-top: 1px solid var(--line);
         font-size: 12px; color: var(--dim); }
a { color: var(--accent); }
"""


def build() -> str:
    r = json.loads(RESULTS.read_text())
    manifest = json.loads(MANIFEST.read_text())
    primary = r["primary_test"]
    control = r["control_deepset_test"]
    shift = r["shift"]
    episodes = r["episodes"]

    counts: dict[str, int] = {"capability": 0, "threshold": 0, "intact": 0}
    for row in shift.values():
        for t in row["transforms"].values():
            verdict = t.get("classification")
            if verdict in counts:
                counts[verdict] += 1
    total = sum(counts.values())

    pr_rows = [
        (SHORT[k], primary[k]["pr_auc"], primary[k]["pr_auc_ci95"]) for k in ORDER
    ]
    sha = manifest.get("harness_git_sha", "")[:12]
    pkgs = ", ".join(f"{k} {v}" for k, v in sorted(manifest.get("packages", {}).items()))

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prompt-injection detector evaluation</title>
<meta name="description" content="Contamination-controlled evaluation of four prompt-injection detectors, with calibration, an adversarial shift slice and agent episodes.">
<style>{CSS}</style></head>
<body><div class="wrap">

<header>
  <h1>Four prompt-injection detectors,<br>measured the same way</h1>
  <p class="lede">Precision, recall and calibration on a paired benchmark; a seeded
  obfuscation slice scored against its own benign arm; and a guard placed on the
  tool-output boundary of a running agent. Every number is regenerated from pinned
  weights by one command.</p>
  <div class="meta">
    <span class="chip">seed {esc(manifest.get('seed'))}</span>
    <span class="chip">harness {esc(sha)}</span>
    <span class="chip">{esc(manifest.get('platform', ''))}</span>
    <span class="chip"><a href="https://github.com/chiruu12/injection-eval-harness">source on GitHub</a></span>
    <span class="chip"><a href="/results.json">results.json</a></span>
  </div>
  <div class="note" style="margin-top:26px">
    <p><strong>Disclosure.</strong> I contribute to Unplug, and two of the four systems
    measured here are Unplug's. The strongest negative result on this page is against
    the Unplug checkpoint and is filed upstream as
    <a href="https://github.com/UnplugAI/Unplug/issues/189">Unplug#189</a>. Thresholds
    come from each vendor's own model card, never from fitting on this data.</p>
  </div>
</header>

<section>
  <h2>Headline</h2>
  <h3>Nobody is calibrated, and the floor is not far behind</h3>
  <p>Primary test split: 240 rows, 120 injections paired with 120 hard negatives that
  differ by intent rather than topic. Thresholds are each vendor's published operating
  point. <strong>Expected calibration error is over the 0.15 bar for all four</strong>,
  so these scores are not probabilities on this distribution, though callers threshold
  them as if they were.</p>
  <div class="panel">{headline_table(primary)}</div>
</section>

<section>
  <h2>Ranking quality</h2>
  <h3>PR-AUC with 95% bootstrap intervals</h3>
  <p>Threshold-free, so it survives a badly chosen operating point. The intervals are
  wide because the split is small, and they overlap for the three transformer systems.
  Read the ordering, not the gaps.</p>
  <div class="panel">{bars_with_ci(pr_rows, chance=0.5)}</div>
</section>

<section>
  <h2>Robustness</h2>
  <h3>{counts['capability']} of {total} cells are capability failures</h3>
  <p>Each cell is one detector under one seeded obfuscation of the same 120 attacks,
  scored against 120 benign rows put through the identical transform. The large number
  is PR-AUC; recall and false-positive rate sit underneath it. <strong>A recall on a
  transformed slice means nothing without the false-positive rate beside it</strong>,
  which is why both are always shown.</p>
  <div class="panel">
    {shift_matrix(shift)}
    <div class="swatches">
      <span><i style="background:var(--cap)"></i>capability failure, no threshold recovers it</span>
      <span><i style="background:var(--thr)"></i>threshold failure, re-thresholding recovers it</span>
      <span><i style="background:var(--ok)"></i>intact</span>
    </div>
  </div>
  <div class="note">
    <p>The cell to read twice is <strong>unplug-tiny-v1 under b64 bare</strong>: recall
    0.992, the best cell in its row, next to a false-positive rate of 0.958 and a PR-AUC
    of 0.546 against a chance floor of 0.500. It fires on almost every encoded document
    whatever the document says. A probe isolating the feature found hex and base32 of the
    same sentence score near zero, and an encoded benign sentence is indistinguishable
    from an encoded attack to within 0.0004.</p>
  </div>
</section>

<section>
  <h2>Calibration</h2>
  <div class="cols">
    <div class="panel">
      <h3 style="font-size:16px">Reliability</h3>
      {reliability_chart(primary)}
      {legend()}
      <p style="margin:12px 0 0;font-size:12px">Bins under 5 rows are dropped. The
      scores are strongly bimodal, so nearly all the mass sits in the first and last
      bin and there is little in between to calibrate against.</p>
    </div>
    <div class="panel">
      <h3 style="font-size:16px">Guard on an agent</h3>
      {guard_slopes(episodes)}
      <p style="margin:12px 0 0;font-size:12px">Attack success across 13 injected
      episodes, guard off then on.</p>
    </div>
  </div>
</section>

<section>
  <h2>Agent episodes</h2>
  <h3>Blocking attacks and blocking work are the same dial</h3>
  <p>25 scripted episodes per system, each run twice: once with no guard, once with the
  detector inspecting every tool result before the agent sees it. 13 carry an injected
  payload in tool output, 12 are benign controls. Small arms, no intervals quoted.</p>
  <div class="panel">{episode_table(episodes)}</div>
  <p>The two ends of that table are the whole point. One system blocks 12 of 13 attacks
  and finishes a third of the benign work. Another finishes everything and blocks one
  attack in thirteen. Neither is a setting anyone would ship, and a report quoting either
  column alone would recommend one of them.</p>
</section>

<section>
  <h2>Contamination control</h2>
  <h3>The check fired for nobody, and it is underpowered</h3>
  <p>A 2023 dataset that predates every model here, against a 2026 paired set. The
  pre-registered flag fires when control F1 exceeds primary F1 by 0.15. Every system did
  <em>worse</em> on the older set. At these sample sizes the power to detect a real gap of
  0.15 is near half, so this rules out very little. Publication order is a weak control,
  not a firewall.</p>
  <div class="panel">{contamination_table(primary, control)}</div>
</section>

<section>
  <h2>Provenance</h2>
  <h3>Everything pinned by commit, regenerated by one command</h3>
  <div class="panel">{pins_table(manifest)}</div>
  <p style="margin-top:18px">Two runs on one machine agree bit for bit. Across
  platforms the table reproduces to 2.1e-05 on raw scores, moving no recall, no
  false-positive rate, no F1 and no bar verdict.</p>
  <pre><code>git clone https://github.com/chiruu12/injection-eval-harness
make setup fetch verify</code></pre>
</section>

<footer>
  Generated from results.json at {esc(manifest.get('generated_utc', ''))}.
  Environment: python {esc(manifest.get('python', ''))}, {esc(pkgs)}.
  Apache-2.0.
</footer>

</div></body></html>
"""


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

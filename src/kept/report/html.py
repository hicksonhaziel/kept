"""Render a ledger as a self-contained HTML evidence map. Pure: data in, text out.

One file, no network. No CDN font, no external stylesheet, no script tag pointing
anywhere: kept claims to work offline, and a report that phones out for a typeface
would quietly break that claim the first time someone opens it on a plane.
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from kept.ids import display_hash
from kept.ledger import Ledger
from kept.report.brief import line_ranges
from kept.verdict import Missed, Ruling, Verdict

#: Verdict → (label, one-line meaning). The meaning is shown on hover and to
#: screen readers, so the colour is never the only carrier of information.
_MEANING: dict[Verdict, str] = {
    Verdict.KEPT: "This promise's own tests caught every breakage kept could prove detectable.",
    Verdict.WEAK: "The tests passed while the code was broken. They would have passed anyway.",
    Verdict.UNPROVEN: "Nothing was actually checked.",
    Verdict.BROKEN: "A bound test fails, so no mutation evidence applies yet.",
    Verdict.STALE: "The evidence describes different criterion text or different code.",
}


@dataclass(frozen=True, slots=True)
class MutationDiff:
    """The exact line a mutant changed, before and after.

    Recomputed from the source at the hash the ledger recorded. When the file has
    moved since, `stale` is set and no diff is shown rather than a plausible guess.
    """

    path: str
    line: int
    operator: str
    description: str
    before: str = ""
    after: str = ""
    stale: bool = False

    @property
    def key(self) -> tuple[str, int, str, str]:
        return (self.path, self.line, self.operator, self.description)


def render(
    ledger: Ledger,
    *,
    texts: Mapping[str, str] | None = None,
    diffs: Mapping[tuple[str, int, str, str], MutationDiff] | None = None,
) -> str:
    """Render the whole ledger as one HTML document.

    Args:
        texts: Criterion wording by identifier, so a promise reads as a promise
            rather than as an identifier. Absent wording is simply omitted.
        diffs: The line each missed mutant changed, keyed by (path, line,
            operator, description).
    """
    words = texts or {}
    changes = diffs or {}
    counts = ledger.counts
    present = [verdict for verdict in Verdict if counts[str(verdict)]]

    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta name="color-scheme" content="dark light">',
        f"<title>kept — evidence for {html.escape(_short(ledger.commit))}</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
        _masthead(ledger, present),
        _controls(present),
        "<main id='promises'>",
        *(
            _promise(ruling, position, words.get(ruling.criterion), changes)
            for position, ruling in enumerate(ledger.rulings)
        ),
        "<p class='empty' hidden>Nothing matches that filter.</p>",
        "</main>",
        _unpinned(ledger),
        _excluded(ledger),
        _footer(ledger),
        f"<script>{_JS}</script>",
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(part for part in parts if part)


def _masthead(ledger: Ledger, present: Sequence[Verdict]) -> str:
    total = max(ledger.promises, 1)
    counts = ledger.counts

    segments = "".join(
        f'<span class="seg v-{verdict}" style="--w:{counts[str(verdict)] / total:.4f}"'
        f' title="{counts[str(verdict)]} {verdict}"></span>'
        for verdict in present
    )
    chips = "".join(
        f'<span class="chip v-{verdict}"><b>{counts[str(verdict)]}</b> {verdict}</span>'
        for verdict in present
    )
    commit = (
        f'<code class="commit" title="the commit this evidence describes">'
        f"{html.escape(_short(ledger.commit))}</code>"
        if ledger.commit
        else '<span class="commit">no commit recorded</span>'
    )

    return f"""<header class="masthead">
  <div class="masthead-top">
    <div class="brand"><span class="mark" aria-hidden="true"></span>kept</div>
    <button class="ghost" id="theme" type="button" aria-label="Switch between dark and light">
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path
        d="M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6l1.4 1.4m10 10 1.4 1.4m0-12.8-1.4 1.4m-10 10-1.4 1.4"
        stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/><circle
        cx="12" cy="12" r="3.6" stroke="currentColor" stroke-width="1.6" fill="none"/></svg>
    </button>
  </div>
  <h1>Evidence</h1>
  <p class="headline">{html.escape(ledger.headline())}</p>
  <div class="meter" role="img" aria-label="{html.escape(ledger.headline())}">{segments}</div>
  <div class="chips">{chips}</div>
  <p class="meta">
    {commit} · kept {html.escape(ledger.kept_version)} ·
    threshold {ledger.settings.threshold} · cap {ledger.settings.cap} mutants per promise
  </p>
  <p class="disclaimer">
    <strong>Evidence, not proof.</strong> A killed mutant is not a guarantee of
    correctness, and a verdict is bounded by the lines these tests executed and the
    mutations kept was able to generate. No model produced any part of this page.
  </p>
</header>"""


def _controls(present: Sequence[Verdict]) -> str:
    buttons = "".join(
        f'<button class="filter v-{verdict}" data-verdict="{verdict}" type="button">'
        f"{verdict}</button>"
        for verdict in present
    )
    return f"""<nav class="controls" aria-label="Filter promises">
  <div class="filters">
    <button class="filter is-on" data-verdict="all" type="button">all</button>{buttons}
  </div>
  <div class="tools">
    <label class="search">
      <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><circle cx="11" cy="11"
        r="6.5" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="m16 16 4.5 4.5"
        stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
      <input id="search" type="search" placeholder="Filter by promise, file or test  (/)"
        autocomplete="off" spellcheck="false">
    </label>
    <button class="ghost" id="expand" type="button">Expand all</button>
  </div>
</nav>"""


def _promise(
    ruling: Ruling,
    position: int,
    text: str | None,
    diffs: Mapping[tuple[str, int, str, str], MutationDiff],
) -> str:
    evidence = ruling.evidence
    verdict = str(ruling.verdict)
    score = evidence.score
    caught = (
        f"{evidence.discriminating - len(evidence.missed)}/{evidence.discriminating}"
        if score is not None
        else "—"
    )
    haystack = " ".join(
        [
            ruling.criterion,
            text or "",
            *(nodeid for nodeid, _ in evidence.oracles),
            *(path for path, _ in evidence.covered),
        ]
    ).lower()

    return f"""<article class="promise" data-verdict="{verdict}"
  data-find="{html.escape(haystack, quote=True)}" style="--i:{position}">
  <details>
    <summary>
      <span class="row">
        <span class="id">{html.escape(ruling.criterion)}</span>
        <span class="pill v-{verdict}" title="{html.escape(_MEANING[ruling.verdict])}">
          {verdict}</span>
        <span class="score" title="detectable breakages caught by this promise's own tests">
          {caught}</span>
        <svg class="caret" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path
          d="m9 6 6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round"
          fill="none"/></svg>
      </span>
      {f'<span class="text">{html.escape(text)}</span>' if text else ""}
    </summary>
    <div class="wrap"><div class="body">
      {_reason(ruling)}
      {_bars(ruling)}
      {_oracles(ruling)}
      {_covered(ruling)}
      {_misses(ruling, diffs)}
    </div></div>
  </details>
</article>"""


def _reason(ruling: Ruling) -> str:
    if not ruling.reason:
        return ""
    return f'<p class="reason">{html.escape(str(ruling.reason))}</p>'


def _bars(ruling: Ruling) -> str:
    evidence = ruling.evidence
    if not evidence.probed:
        return ""
    killed = evidence.discriminating - len(evidence.missed)
    total = max(evidence.discriminating, 1)
    return f"""<div class="bars">
  <div class="bar" style="--w:{killed / total:.4f}"><span></span></div>
  <dl class="numbers">
    <div><dt>probed</dt><dd>{evidence.probed}</dd></div>
    <div><dt>noticed</dt><dd>{killed}</dd></div>
    <div><dt>missed</dt><dd class="{"bad" if evidence.missed else ""}">{
        len(evidence.missed)
    }</dd></div>
    <div><dt>unpinned</dt><dd>{evidence.unpinned}</dd></div>
  </dl>
</div>"""


def _oracles(ruling: Ruling) -> str:
    if not ruling.evidence.oracles:
        return '<section class="block"><h3>Oracles</h3><p class="none">Nothing claims to verify this promise.</p></section>'
    items = "".join(
        f'<li><span class="status s-{html.escape(status)}">{html.escape(status)}</span>'
        f"<code>{html.escape(nodeid)}</code></li>"
        for nodeid, status in ruling.evidence.oracles
    )
    return f'<section class="block"><h3>Oracles <span class="count">{len(ruling.evidence.oracles)}</span></h3><ul class="oracles">{items}</ul></section>'


def _covered(ruling: Ruling) -> str:
    if not ruling.evidence.covered:
        return ""
    items = "".join(
        f"<li><code>{html.escape(path)}</code><span class='lines'>{html.escape(line_ranges(lines))}</span></li>"
        for path, lines in ruling.evidence.covered
    )
    return f'<section class="block"><h3>Lines under audit</h3><ul class="covered">{items}</ul></section>'


def _misses(
    ruling: Ruling,
    diffs: Mapping[tuple[str, int, str, str], MutationDiff],
) -> str:
    missed = ruling.evidence.missed
    if not missed:
        return ""
    cards = "".join(_miss(entry, diffs) for entry in missed)
    return f"""<section class="block">
  <h3>Breakages this promise did not notice <span class="count">{len(missed)}</span></h3>
  <p class="note">Each change below was applied on its own, and these tests still
  passed. Another promise's tests did notice it, which is how kept knows the change
  is detectable rather than equivalent to the original.</p>
  {cards}
</section>"""


def _miss(
    missed: Missed,
    diffs: Mapping[tuple[str, int, str, str], MutationDiff],
) -> str:
    key = (missed.path, missed.line, missed.operator, missed.description)
    diff = diffs.get(key)
    caught = "".join(
        f'<span class="caught">{html.escape(criterion)}</span>' for criterion in missed.caught_by
    )

    if diff is None or diff.stale:
        body = (
            '<p class="none">The source has changed since this evidence was recorded, '
            "so the exact line is not shown.</p>"
            if diff is not None and diff.stale
            else ""
        )
    else:
        body = f"""<pre class="diff" tabindex="0"><code><span class="line del"><span
class="gutter">{missed.line}</span><span class="sign">-</span>{html.escape(diff.before)}</span><span
class="line ins"><span class="gutter">{missed.line}</span><span class="sign">+</span>{
            html.escape(diff.after)
        }</span></code></pre>"""

    return f"""<div class="miss">
  <div class="miss-head">
    <code class="loc">{html.escape(missed.path)}:{missed.line}</code>
    <span class="op">{html.escape(missed.operator)}</span>
    <span class="desc">{html.escape(missed.description)}</span>
  </div>
  {body}
  <div class="miss-foot"><span class="label">noticed by</span>{caught}</div>
</div>"""


def _unpinned(ledger: Ledger) -> str:
    if not ledger.unpinned:
        return ""
    rows = "".join(
        f"<tr><td><code>{html.escape(entry.path)}:{entry.line}</code></td>"
        f"<td>{html.escape(entry.description)}</td>"
        f"<td>{len(entry.covered_by)}</td></tr>"
        for entry in ledger.unpinned
    )
    return f"""<section class="panel">
  <h2>Unpinned lines <span class="count">{len(ledger.unpinned)}</span></h2>
  <p class="note">Breakages <strong>no</strong> bound test noticed. Charged to the
  suite rather than to any one promise: if nothing detects them, blaming a single
  promise would be misattribution.</p>
  <table><thead><tr><th>Location</th><th>Breakage</th><th>Promises covering it</th></tr></thead>
  <tbody>{rows}</tbody></table>
</section>"""


def _excluded(ledger: Ledger) -> str:
    if not ledger.excluded:
        return ""
    rows = "".join(
        f"<tr><td><code>{html.escape(criterion)}</code></td><td>{html.escape(reason)}</td></tr>"
        for criterion, reason in ledger.excluded
    )
    return f"""<section class="panel">
  <h2>Excluded <span class="count">{len(ledger.excluded)}</span></h2>
  <p class="note">Promises deliberately kept out of the verdicts, with the stated
  reason, so the exclusion is a choice a reviewer can challenge.</p>
  <table><thead><tr><th>Promise</th><th>Reason</th></tr></thead><tbody>{rows}</tbody></table>
</section>"""


def _footer(ledger: Ledger) -> str:
    sources = "".join(
        f"<li><code>{html.escape(path)}</code><span class='hash'>{display_hash(digest)}</span></li>"
        for path, digest in ledger.sources
    )
    listing = f'<ul class="sources">{sources}</ul>' if sources else ""
    return f"""<footer class="footer">
  <h2>Sources judged</h2>
  <p class="note">The files these verdicts were measured against, by content hash.
  Evidence recorded for a different hash no longer applies.</p>
  {listing}
  <p class="fine">Generated by <code>kept report</code> from
  <code>.kept/ledger.json</code>. Deterministic: the same ledger renders the same
  page. Offline: this file references nothing outside itself.</p>
</footer>"""


def _short(commit: str | None) -> str:
    return (commit or "no commit")[:12]


_CSS = """
:root{
  --bg:#0b0d10; --bg-soft:#11151a; --card:#141a21; --card-2:#171e26;
  --line:#222c37; --line-soft:#1b232c;
  --ink:#e8edf3; --ink-dim:#9fb0c0; --ink-faint:#6d7f90;
  --kept:#34d399; --weak:#fbbf24; --unproven:#7d8fa1; --broken:#f87171; --stale:#a78bfa;
  --del:#f87171; --del-bg:rgba(248,113,113,.10); --ins:#34d399; --ins-bg:rgba(52,211,153,.10);
  --accent:#818cf8;
  --r:14px; --r-sm:9px;
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:32px; --s7:48px; --s8:72px;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,"Helvetica Neue",Arial,sans-serif;
  --ease:cubic-bezier(.2,.7,.2,1);
}
html[data-theme=light]{
  --bg:#f7f8fa; --bg-soft:#fff; --card:#fff; --card-2:#f4f6f9;
  --line:#e2e7ee; --line-soft:#eceff4;
  --ink:#0f1720; --ink-dim:#53647a; --ink-faint:#7d8ea3;
  --kept:#059669; --weak:#b45309; --unproven:#64748b; --broken:#dc2626; --stale:#7c3aed;
  --del:#dc2626; --del-bg:rgba(220,38,38,.07); --ins:#059669; --ins-bg:rgba(5,150,105,.08);
  --accent:#4f46e5;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--bg); color:var(--ink); font-family:var(--sans);
  font-size:15px; line-height:1.6; letter-spacing:-.006em;
  -webkit-font-smoothing:antialiased;
  padding:0 var(--s5) var(--s8);
}
body::before{
  content:""; position:fixed; inset:0 0 auto 0; height:340px; pointer-events:none; z-index:0;
  background:radial-gradient(1100px 300px at 22% -10%,rgba(129,140,248,.13),transparent 70%);
}
.masthead,.controls,main,.panel,.footer{max-width:1120px; margin:0 auto; position:relative; z-index:1}

.masthead{padding:var(--s7) 0 var(--s5)}
.masthead-top{display:flex; align-items:center; justify-content:space-between; margin-bottom:var(--s6)}
.brand{display:flex; align-items:center; gap:var(--s2); font-weight:640; letter-spacing:-.02em}
.mark{
  width:11px; height:11px; border-radius:3px; background:var(--kept);
  box-shadow:0 0 0 3px color-mix(in srgb,var(--kept) 18%,transparent);
  animation:pulse 3.4s var(--ease) infinite;
}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(.82)}}
h1{
  margin:0; font-size:clamp(34px,5.4vw,56px); line-height:1.02; font-weight:660;
  letter-spacing:-.035em;
}
.headline{
  margin:var(--s3) 0 var(--s4); font-size:19px; color:var(--ink-dim);
  font-variant-numeric:tabular-nums;
}
.meter{display:flex; gap:3px; height:9px; margin-bottom:var(--s4)}
.seg{
  width:0; border-radius:99px; transform-origin:left;
  transition:width 1.05s var(--ease) .18s;
}
body.ready .seg{width:calc(var(--w) * 100%)}
.seg.v-kept{background:var(--kept)} .seg.v-weak{background:var(--weak)}
.seg.v-unproven{background:var(--unproven)} .seg.v-broken{background:var(--broken)}
.seg.v-stale{background:var(--stale)}
.chips{display:flex; flex-wrap:wrap; gap:var(--s2); margin-bottom:var(--s4)}
.chip{
  display:inline-flex; align-items:baseline; gap:6px; padding:5px 11px;
  border:1px solid var(--line); border-radius:99px; background:var(--card);
  font-size:12.5px; color:var(--ink-dim); text-transform:lowercase;
}
.chip b{font-size:14px; color:var(--ink); font-variant-numeric:tabular-nums}
.chip.v-kept b{color:var(--kept)} .chip.v-weak b{color:var(--weak)}
.chip.v-unproven b{color:var(--unproven)} .chip.v-broken b{color:var(--broken)}
.chip.v-stale b{color:var(--stale)}
.meta{margin:0 0 var(--s4); color:var(--ink-faint); font-size:13px}
.commit{
  font-family:var(--mono); font-size:12px; padding:2px 7px; border-radius:6px;
  background:var(--card); border:1px solid var(--line); color:var(--ink-dim);
}
.disclaimer{
  margin:0; padding:var(--s3) var(--s4); max-width:74ch;
  border-left:2px solid var(--accent); border-radius:0 var(--r-sm) var(--r-sm) 0;
  background:linear-gradient(90deg,color-mix(in srgb,var(--accent) 9%,transparent),transparent 82%);
  color:var(--ink-dim); font-size:13.5px;
}
.disclaimer strong{color:var(--ink)}

.controls{
  position:sticky; top:0; z-index:5; display:flex; flex-wrap:wrap; gap:var(--s3);
  align-items:center; justify-content:space-between;
  padding:var(--s3) 0; margin-bottom:var(--s4);
  background:color-mix(in srgb,var(--bg) 86%,transparent); backdrop-filter:blur(10px);
  border-bottom:1px solid var(--line-soft);
}
.filters,.tools{display:flex; gap:var(--s2); align-items:center; flex-wrap:wrap}
.filter,.ghost{
  font:inherit; font-size:12.5px; color:var(--ink-dim); cursor:pointer;
  padding:6px 12px; border-radius:99px; border:1px solid var(--line);
  background:var(--card); text-transform:lowercase;
  transition:color .18s var(--ease),border-color .18s var(--ease),
             background .18s var(--ease),transform .18s var(--ease);
}
.filter:hover,.ghost:hover{color:var(--ink); border-color:var(--ink-faint); transform:translateY(-1px)}
.filter.is-on{color:var(--bg); background:var(--ink); border-color:var(--ink); font-weight:600}
.filter.v-kept.is-on{background:var(--kept); border-color:var(--kept)}
.filter.v-weak.is-on{background:var(--weak); border-color:var(--weak)}
.filter.v-unproven.is-on{background:var(--unproven); border-color:var(--unproven)}
.filter.v-broken.is-on{background:var(--broken); border-color:var(--broken)}
.filter.v-stale.is-on{background:var(--stale); border-color:var(--stale)}
.ghost{display:inline-flex; align-items:center; gap:6px; text-transform:none}
.search{
  display:flex; align-items:center; gap:var(--s2); padding:0 var(--s3);
  border:1px solid var(--line); border-radius:99px; background:var(--card);
  color:var(--ink-faint); transition:border-color .18s var(--ease)
}
.search:focus-within{border-color:var(--accent)}
.search input{
  font:inherit; font-size:13px; color:var(--ink); background:none; border:0; outline:0;
  padding:7px 0; width:min(38vw,290px);
}

.promise{
  border:1px solid var(--line); border-radius:var(--r); background:var(--card);
  margin-bottom:var(--s3); overflow:clip;
  opacity:0; transform:translateY(9px);
  animation:rise .55s var(--ease) forwards;
  animation-delay:calc(var(--i) * 22ms + 120ms);
  transition:border-color .2s var(--ease),box-shadow .2s var(--ease);
}
.promise:hover{border-color:color-mix(in srgb,var(--ink-faint) 55%,var(--line))}
.promise:has(details[open]){box-shadow:0 14px 34px -22px rgba(0,0,0,.6)}
@keyframes rise{to{opacity:1; transform:none}}
summary{
  display:block; padding:var(--s4); cursor:pointer; list-style:none;
  transition:background .18s var(--ease);
}
summary::-webkit-details-marker{display:none}
summary:hover{background:var(--card-2)}
summary:focus-visible{outline:2px solid var(--accent); outline-offset:-2px}
.row{display:flex; align-items:center; gap:var(--s3)}
.id{
  font-family:var(--mono); font-size:13px; font-weight:600; letter-spacing:-.02em;
  min-width:80px;
}
.pill{
  font-size:11px; font-weight:650; letter-spacing:.04em; text-transform:uppercase;
  padding:3px 9px; border-radius:99px; white-space:nowrap;
}
.pill.v-kept{color:var(--kept); background:color-mix(in srgb,var(--kept) 15%,transparent)}
.pill.v-weak{color:var(--weak); background:color-mix(in srgb,var(--weak) 16%,transparent)}
.pill.v-unproven{color:var(--unproven); background:color-mix(in srgb,var(--unproven) 18%,transparent)}
.pill.v-broken{color:var(--broken); background:color-mix(in srgb,var(--broken) 15%,transparent)}
.pill.v-stale{color:var(--stale); background:color-mix(in srgb,var(--stale) 15%,transparent)}
.score{
  margin-left:auto; font-family:var(--mono); font-size:12.5px; color:var(--ink-dim);
  font-variant-numeric:tabular-nums;
}
.caret{color:var(--ink-faint); transition:transform .26s var(--ease); flex:none}
details[open] .caret{transform:rotate(90deg)}
.text{
  display:block; margin:var(--s2) 0 0; padding-left:calc(80px + var(--s3));
  color:var(--ink-dim); font-size:14px; max-width:88ch;
}
.wrap{display:grid; grid-template-rows:0fr; transition:grid-template-rows .32s var(--ease)}
details[open] .wrap{grid-template-rows:1fr}
.body{
  overflow:hidden; padding:0 var(--s4) var(--s4);
  display:flex; flex-direction:column; gap:var(--s4);
}
.reason{
  margin:0; padding:var(--s3); border-radius:var(--r-sm); background:var(--card-2);
  color:var(--ink-dim); font-size:13.5px; border:1px solid var(--line-soft);
}
.bars{display:flex; flex-direction:column; gap:var(--s2)}
.bar{height:5px; border-radius:99px; background:var(--line); overflow:hidden}
.bar span{
  display:block; height:100%; width:0; border-radius:99px; background:var(--kept);
  transition:width .9s var(--ease) .1s;
}
details[open] .bar span{width:calc(var(--w) * 100%)}
.numbers{display:flex; flex-wrap:wrap; gap:var(--s5); margin:0}
.numbers div{display:flex; flex-direction:column; gap:1px}
.numbers dt{font-size:11px; text-transform:uppercase; letter-spacing:.07em; color:var(--ink-faint)}
.numbers dd{margin:0; font-family:var(--mono); font-size:15px; font-variant-numeric:tabular-nums}
.numbers dd.bad{color:var(--weak)}
.block h3{
  margin:0 0 var(--s3); font-size:12px; font-weight:640; text-transform:uppercase;
  letter-spacing:.08em; color:var(--ink-faint);
  display:flex; align-items:center; gap:var(--s2);
}
.count{
  font-family:var(--mono); font-size:11px; padding:1px 6px; border-radius:99px;
  background:var(--card-2); border:1px solid var(--line); color:var(--ink-dim);
  letter-spacing:0;
}
.note{margin:0 0 var(--s3); color:var(--ink-faint); font-size:13px; max-width:78ch}
.none{margin:0; color:var(--ink-faint); font-size:13px; font-style:italic}
.oracles,.covered,.sources{list-style:none; margin:0; padding:0; display:flex;
  flex-direction:column; gap:var(--s1)}
.oracles li,.covered li,.sources li{
  display:flex; align-items:center; gap:var(--s3); padding:7px var(--s3);
  border-radius:var(--r-sm); background:var(--card-2); font-size:13px;
}
.oracles code,.covered code,.sources code{font-family:var(--mono); font-size:12.5px; color:var(--ink)}
.status{
  font-size:10.5px; font-weight:650; text-transform:uppercase; letter-spacing:.05em;
  padding:2px 7px; border-radius:5px; flex:none; min-width:62px; text-align:center;
}
.s-passed{color:var(--kept); background:color-mix(in srgb,var(--kept) 14%,transparent)}
.s-failed,.s-error{color:var(--broken); background:color-mix(in srgb,var(--broken) 14%,transparent)}
.s-skipped,.s-notrun,.s-missing{color:var(--unproven); background:color-mix(in srgb,var(--unproven) 16%,transparent)}
.lines,.hash{margin-left:auto; font-family:var(--mono); font-size:12px; color:var(--ink-faint)}

.miss{
  border:1px solid var(--line); border-radius:var(--r-sm); background:var(--bg-soft);
  padding:var(--s3); margin-bottom:var(--s2);
}
.miss-head{display:flex; align-items:center; gap:var(--s2); flex-wrap:wrap; margin-bottom:var(--s2)}
.loc{font-family:var(--mono); font-size:12.5px; color:var(--ink)}
.op{
  font-size:10.5px; text-transform:uppercase; letter-spacing:.06em; padding:2px 7px;
  border-radius:5px; background:var(--card-2); color:var(--ink-faint); border:1px solid var(--line);
}
.desc{font-family:var(--mono); font-size:12.5px; color:var(--weak)}
.diff{
  margin:0; border-radius:var(--r-sm); overflow-x:auto; border:1px solid var(--line);
  background:var(--bg); font-family:var(--mono); font-size:12.5px; line-height:1.75;
}
.diff:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
.diff code{display:block}
.line{display:flex; white-space:pre; min-width:100%}
.line.del{background:var(--del-bg); color:var(--del)}
.line.ins{background:var(--ins-bg); color:var(--ins)}
.gutter{
  flex:none; width:52px; padding-right:var(--s3); text-align:right; color:var(--ink-faint);
  background:color-mix(in srgb,var(--card) 60%,transparent); user-select:none;
}
.sign{flex:none; width:22px; text-align:center; opacity:.85; user-select:none}
.miss-foot{display:flex; align-items:center; gap:var(--s2); margin-top:var(--s2); flex-wrap:wrap}
.label{font-size:11px; text-transform:uppercase; letter-spacing:.07em; color:var(--ink-faint)}
.caught{
  font-family:var(--mono); font-size:11.5px; padding:2px 8px; border-radius:99px;
  background:color-mix(in srgb,var(--kept) 12%,transparent); color:var(--kept);
}

.panel,.footer{margin-top:var(--s7); padding-top:var(--s5); border-top:1px solid var(--line-soft)}
.panel h2,.footer h2{margin:0 0 var(--s2); font-size:17px; font-weight:640; letter-spacing:-.02em;
  display:flex; align-items:center; gap:var(--s2)}
table{width:100%; border-collapse:collapse; font-size:13px}
th{
  text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.07em;
  color:var(--ink-faint); font-weight:600; padding:var(--s2) var(--s3);
  border-bottom:1px solid var(--line);
}
td{padding:9px var(--s3); border-bottom:1px solid var(--line-soft); color:var(--ink-dim)}
tbody tr{transition:background .15s var(--ease)}
tbody tr:hover{background:var(--card)}
td code{font-family:var(--mono); font-size:12.5px; color:var(--ink)}
.fine{margin:var(--s4) 0 0; color:var(--ink-faint); font-size:12.5px; max-width:78ch}
.fine code{font-family:var(--mono); font-size:12px}
.empty{text-align:center; color:var(--ink-faint); padding:var(--s7) 0; font-size:14px}

@media (max-width:720px){
  body{padding:0 var(--s4) var(--s7)}
  .text{padding-left:0}
  .score{margin-left:0}
  .search input{width:100%}
}
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation:none!important; transition:none!important}
  .promise{opacity:1; transform:none}
  body.ready .seg{width:calc(var(--w) * 100%)}
  details[open] .wrap{grid-template-rows:1fr}
}
@media print{
  body{background:#fff; color:#000; padding:0}
  .controls,.ghost{display:none}
  .promise{break-inside:avoid; border-color:#ccc}
  .wrap{grid-template-rows:1fr!important}
}
"""

_JS = """
(() => {
  const root = document.documentElement;
  const stored = localStorage.getItem('kept-theme');
  if (stored) root.dataset.theme = stored;
  else if (window.matchMedia('(prefers-color-scheme: light)').matches) root.dataset.theme = 'light';

  requestAnimationFrame(() => document.body.classList.add('ready'));

  document.getElementById('theme').addEventListener('click', () => {
    const next = root.dataset.theme === 'light' ? 'dark' : 'light';
    root.dataset.theme = next;
    localStorage.setItem('kept-theme', next);
  });

  const promises = [...document.querySelectorAll('.promise')];
  const filters = [...document.querySelectorAll('.filter')];
  const search = document.getElementById('search');
  const empty = document.querySelector('.empty');
  let verdict = 'all';

  const apply = () => {
    const needle = search.value.trim().toLowerCase();
    let shown = 0;
    for (const promise of promises) {
      const byVerdict = verdict === 'all' || promise.dataset.verdict === verdict;
      const byText = !needle || promise.dataset.find.includes(needle);
      const visible = byVerdict && byText;
      promise.hidden = !visible;
      if (visible) shown++;
    }
    empty.hidden = shown > 0;
  };

  for (const button of filters) {
    button.addEventListener('click', () => {
      verdict = button.dataset.verdict;
      filters.forEach(other => other.classList.toggle('is-on', other === button));
      apply();
    });
  }
  search.addEventListener('input', apply);

  const expand = document.getElementById('expand');
  expand.addEventListener('click', () => {
    const opening = expand.textContent.trim() === 'Expand all';
    for (const details of document.querySelectorAll('.promise details')) {
      if (!details.closest('.promise').hidden) details.open = opening;
    }
    expand.textContent = opening ? 'Collapse all' : 'Expand all';
  });

  document.addEventListener('keydown', event => {
    if (event.key === '/' && document.activeElement !== search) {
      event.preventDefault();
      search.focus();
    } else if (event.key === 'Escape' && document.activeElement === search) {
      search.value = '';
      apply();
      search.blur();
    }
  });
})();
"""

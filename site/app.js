/* Sovereignty Drift — dashboard.
   Reads data/index.json, which the Actions collector commits. No live fetching:
   everything shown here was gathered server-side, so nothing depends on a
   third party allowing browser requests. */

const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const COMPONENTS = [
  ["footprint", "Hiring footprint", "Share of placeable roles naming no EEA site."],
  ["access", "Access signals", "Weighted job-description signals: rotations, travel, production access."],
  ["transparency", "Document coverage", "Whether a privacy policy, DPA and sub-processor list exist and can be read as text."],
  ["record", "Archive record", "How much revision history the Wayback Machine holds for those pages."],
];

const KIND_LABEL = {
  privacy: "Privacy policy",
  dpa: "Data processing agreement",
  subprocessors: "Sub-processor list",
  terms: "Terms",
  other: "Other legal page",
};

let DATA = null;
let openId = null;

init();

async function init() {
  try {
    const res = await fetch("data/index.json", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    DATA = await res.json();
  } catch (e) {
    $("#main").innerHTML =
      `<p class="error">Could not load <code>data/index.json</code> (${esc(e.message)}).
       Run the collector, or trigger the workflow from the Actions tab.</p>`;
    return;
  }
  renderRunbar();
  render();
}

function renderRunbar() {
  const when = new Date(DATA.generated_at);
  const flags = DATA.vendors.reduce((n, v) => n + v.crosschecks.length, 0);
  const high = DATA.vendors.reduce(
    (n, v) => n + v.crosschecks.filter(f => f.severity === "high").length, 0);
  const docs = DATA.vendors.reduce((n, v) => n + v.docs.filter(d => d.path).length, 0);
  $("#runbar").innerHTML = `
    <span>collected <b>${when.toISOString().slice(0, 16).replace("T", " ")}Z</b></span>
    <span><b>${DATA.vendors.length}</b> vendors</span>
    <span><b>${docs}</b> documents tracked</span>
    <span><b>${flags}</b> open questions · <b>${high}</b> high</span>`;
}

function render() {
  const rows = [...DATA.vendors].sort((a, b) => b.score.total - a.score.total);
  $("#main").innerHTML = `
    <section>
      <div class="sec-hd">
        <h2>Where claims and evidence disagree</h2>
        <span class="eyebrow">sorted by public-evidence index</span>
      </div>
      <p class="note">
        The index is not a rating of a vendor. It counts how much exposure is visible in public
        sources and how much of it cannot be verified — a vendor scoring high may simply publish
        less. Open a row for the reconciliations.
      </p>
      <div class="matrix">
        <div class="mhdr">
          <span>Vendor</span><span>Index composition</span><span>Open questions</span><span>Index</span>
        </div>
        ${rows.map(matrixRow).join("")}
      </div>
    </section>

    <section>
      <div class="sec-hd"><h2>How the index is built</h2></div>
      <div class="method">
        ${COMPONENTS.map(([k, label, why]) => `
          <div class="card">
            <h4><span class="key seg ${k}" style="display:inline-block"></span>${esc(label)} — up to 25</h4>
            <p>${esc(why)}</p>
          </div>`).join("")}
      </div>
    </section>`;

  document.querySelectorAll(".mrow").forEach(b =>
    b.addEventListener("click", () => toggle(b.dataset.id)));
  if (openId) mountDetail(openId);
}

function matrixRow(v) {
  const s = v.score;
  const counts = { high: 0, medium: 0, low: 0 };
  v.crosschecks.forEach(f => counts[f.severity]++);
  const chips = ["high", "medium", "low"]
    .filter(k => counts[k])
    .map(k => `<span class="chip ${k}">${counts[k]} ${k}</span>`).join("");

  return `
    <button class="mrow" data-id="${esc(v.id)}" aria-expanded="false">
      <span class="mhead">
        <span class="mname"><span class="caret">▶</span>${esc(v.name)}</span>
        <span class="mmeta">${esc(v.category)} · ${esc(v.hq)}</span>
      </span>
      <span class="stackwrap">
        <span class="stack">
          ${COMPONENTS.map(([k]) =>
            `<span class="seg ${k}" style="width:${s[k]}%" title="${k}: ${s[k]}"></span>`).join("")}
        </span>
        <span class="stack-scale"><span>0</span><span>100</span></span>
      </span>
      <span class="chips">${chips || '<span class="chip none">none open</span>'}</span>
      <span class="idx">${s.total}</span>
    </button>
    <div class="detail" id="d-${esc(v.id)}" hidden></div>`;
}

function toggle(id) {
  const btn = document.querySelector(`.mrow[data-id="${id}"]`);
  const panel = $("#d-" + id);
  const isOpen = openId === id;
  document.querySelectorAll(".detail").forEach(d => { d.hidden = true; d.innerHTML = ""; });
  document.querySelectorAll(".mrow").forEach(b => b.setAttribute("aria-expanded", "false"));
  if (isOpen) { openId = null; return; }
  openId = id;
  btn.setAttribute("aria-expanded", "true");
  panel.hidden = false;
  panel.innerHTML = detailHTML(DATA.vendors.find(v => v.id === id));
}

function mountDetail(id) {
  const panel = $("#d-" + id);
  if (!panel) return;
  panel.hidden = false;
  panel.innerHTML = detailHTML(DATA.vendors.find(v => v.id === id));
  document.querySelector(`.mrow[data-id="${id}"]`).setAttribute("aria-expanded", "true");
}

function detailHTML(v) {
  return `
    <h3>Reconciliations</h3>
    ${v.crosschecks.length
      ? v.crosschecks.map(reconCard).join("")
      : `<p class="note">Nothing to reconcile from the sources collected. That is a clean pass on
         these checks, not a clean bill of health — re-run and compare.</p>`}

    <h3>Documents tracked</h3>
    ${docsTable(v)}

    <h3>Open roles by country</h3>
    ${geoHTML(v.jobs)}`;
}

function reconCard(f) {
  const left = f.claim
    ? `<div class="side">
         <span class="eyebrow">What the ${esc(KIND_LABEL[f.claim.kind] || f.claim.kind)} says</span>
         <div class="quote claim">${esc(f.claim.text)}</div>
         ${f.claim.url ? `<div style="margin-top:8px"><a href="${esc(f.claim.url)}" target="_blank" rel="noopener">Source document</a></div>` : ""}
       </div>`
    : `<div class="side">
         <span class="eyebrow">What is missing</span>
         <div class="quote">${esc(f.detail)}</div>
       </div>`;

  const ev = (f.evidence || []).map(e => {
    if (e.kind === "job") {
      return `<div class="evline">
        <span class="who">${e.url ? `<a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.title)}</a>` : esc(e.title)}${e.location ? " · " + esc(e.location) : ""}</span>
        <span class="ex">…${highlight(e.excerpt, e.matched)}…</span>
      </div>`;
    }
    if (e.kind === "doc") {
      return `<div class="evline"><span class="ex">${e.url ? `<a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.excerpt)}</a>` : esc(e.excerpt)}</span></div>`;
    }
    return `<div class="evline"><span class="ex">${esc(e.excerpt)}</span></div>`;
  }).join("");

  const right = `<div class="side">
      <span class="eyebrow">What the public evidence shows</span>
      ${ev || `<div class="ex" style="font-size:12.5px;color:var(--muted)">No individual postings attached — see the summary above.</div>`}
    </div>`;

  return `
    <div class="recon">
      <div class="recon-top">
        <span class="recon-title">${esc(f.headline)}</span>
        <span class="sev ${esc(f.severity)}">${esc(f.severity)}</span>
      </div>
      ${f.claim ? `<div class="recon-detail">${esc(f.detail)}</div>` : ""}
      <div class="pair">${left}${right}</div>
      <p class="ask"><span class="eyebrow">Ask</span><span>${esc(f.question)}</span></p>
    </div>`;
}

function highlight(text, matched) {
  const safe = esc(text);
  if (!matched) return safe;
  const rx = new RegExp(esc(matched).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");
  return safe.replace(rx, m => `<mark>${m}</mark>`);
}

function docsTable(v) {
  if (!v.docs.length) return `<p class="note">No legal documents were reachable.</p>`;
  return `<table class="docs">
    <thead><tr><th>Document</th><th>Status</th><th>Archive</th><th style="text-align:right">Lines</th></tr></thead>
    <tbody>${v.docs.map(d => {
      const a = d.archive || {};
      const archive = !a.ok ? `<span class="tag">${esc(a.reason || "not checked")}</span>`
        : a.captures ? `${a.revisions} revisions · last ${esc(a.last)}`
        : `<span class="tag warn">never captured</span>`;
      const status = d.path
        ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">live page</a>`
        : `<span class="tag warn">no diffable text</span>`;
      return `<tr>
        <td>${esc(KIND_LABEL[d.kind] || d.kind)}</td>
        <td>${status}</td>
        <td>${archive}</td>
        <td class="num">${d.lines || "—"}</td>
      </tr>`;
    }).join("")}</tbody></table>`;
}

function geoHTML(jobs) {
  if (!jobs || !jobs.ok) {
    return `<p class="note">The job board did not answer (${esc(jobs && jobs.reason || "unknown")}).</p>`;
  }
  const entries = Object.entries(jobs.countries).slice(0, 8);
  if (!entries.length) {
    return `<p class="note">${jobs.unplaceable} of ${jobs.total} postings name a work mode instead of
      a place, so the board cannot be mapped. A vendor whose own candidates cannot tell which country
      a role sits in is a finding in itself.</p>`;
  }
  const max = entries[0][1];
  const EEA = new Set(["Austria","Belgium","Bulgaria","Croatia","Cyprus","Czechia","Denmark","Estonia",
    "Finland","France","Germany","Greece","Hungary","Iceland","Ireland","Italy","Latvia","Liechtenstein",
    "Lithuania","Luxembourg","Malta","Netherlands","Norway","Poland","Portugal","Romania","Slovakia",
    "Slovenia","Spain","Sweden"]);
  return entries.map(([c, n]) => `
      <div class="geo">
        <span class="who" title="${esc(c)}">${esc(c)}</span>
        <span><span class="bar ${EEA.has(c) ? "eea" : ""}" style="width:${Math.max(3, (n / max) * 100)}%"></span></span>
        <span class="n">${n}</span>
      </div>`).join("") +
    `<p class="note" style="margin-top:12px">
      ${jobs.non_eea} of ${jobs.placeable} placeable roles name no EEA site
      ${jobs.unplaceable ? `· ${jobs.unplaceable} postings give no location at all` : ""}.
      Green is EEA. A posting naming several cities counts in each.
    </p>`;
}

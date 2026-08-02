/* Data Drift Detection — dashboard.
   Reads data/index.json (real, collector-generated) and, if present,
   data/demo-vendor.json (one fictional, clearly-badged vendor used to show the
   drift feature before two real collection runs have accumulated history).
   No live fetching otherwise: everything shown here was gathered server-side. */

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

const EEA = new Set(["Austria","Belgium","Bulgaria","Croatia","Cyprus","Czechia","Denmark","Estonia",
  "Finland","France","Germany","Greece","Hungary","Iceland","Ireland","Italy","Latvia","Liechtenstein",
  "Lithuania","Luxembourg","Malta","Netherlands","Norway","Poland","Portugal","Romania","Slovakia",
  "Slovenia","Spain","Sweden"]);

const DEFAULT_ALLOWED = ["United States", "Canada"];

let DATA = null;        // raw index.json
let VENDORS = [];        // real vendors + demo vendor if loaded/shown
let DEMO_VENDOR = null;
let openId = null;
let allowed = new Set(DEFAULT_ALLOWED);
let sortMode = "index";   // "index" | "exposure"
let showDemo = true;

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
  try {
    const res = await fetch("data/demo-vendor.json", { cache: "no-store" });
    if (res.ok) DEMO_VENDOR = await res.json();
  } catch { /* optional */ }

  render();
}

function allCountries() {
  const tally = new Map();
  for (const v of DATA.vendors) {
    if (!v.jobs?.ok) continue;
    for (const [c, n] of Object.entries(v.jobs.countries || {})) {
      tally.set(c, (tally.get(c) || 0) + n);
    }
  }
  for (const c of DEFAULT_ALLOWED) if (!tally.has(c)) tally.set(c, 0);
  return [...tally.entries()].sort((a, b) => b[1] - a[1]).map(([c]) => c);
}

function hqCountries(v) {
  return (v.hq || "").split("/").map(s => s.trim()).filter(Boolean);
}

function exposure(v) {
  const jobs = v.jobs;
  if (!jobs?.ok || !jobs.placeable) {
    return { outside: 0, pct: null, hqOutside: [] };
  }
  let outside = 0;
  for (const [c, n] of Object.entries(jobs.countries || {})) {
    if (!allowed.has(c)) outside += n;
  }
  return {
    outside,
    // A posting naming several countries counts in each, so the raw sum can
    // exceed placeable -- cap the displayed share at 100%.
    pct: Math.min(100, Math.round((outside / jobs.placeable) * 100)),
    hqOutside: hqCountries(v).filter(c => !allowed.has(c)),
  };
}

function renderRunbar(vendors) {
  const when = new Date(DATA.generated_at);
  const flags = vendors.reduce((n, v) => n + v.crosschecks.length, 0);
  const high = vendors.reduce(
    (n, v) => n + v.crosschecks.filter(f => f.severity === "high").length, 0);
  const docs = vendors.reduce((n, v) => n + v.docs.filter(d => d.path).length, 0);
  const driftCount = vendors.reduce((n, v) => n + (v.drift || []).length, 0);
  $("#runbar").innerHTML = `
    <span>collected <b>${when.toISOString().slice(0, 16).replace("T", " ")}Z</b></span>
    <span><b>${vendors.length}</b> vendors</span>
    <span><b>${docs}</b> documents tracked</span>
    <span><b>${flags}</b> open questions · <b>${high}</b> high</span>
    <span><b>${driftCount}</b> wording change${driftCount === 1 ? "" : "s"} detected</span>`;
}

function render() {
  VENDORS = [...DATA.vendors];
  if (showDemo && DEMO_VENDOR) VENDORS.push(DEMO_VENDOR);
  renderRunbar(VENDORS);

  const rows = [...VENDORS].sort((a, b) => {
    if (sortMode === "exposure") {
      const pa = exposure(a).pct ?? -1, pb = exposure(b).pct ?? -1;
      if (pb !== pa) return pb - pa;
    }
    return b.score.total - a.score.total;
  });

  $("#main").innerHTML = `
    <section>
      <div class="sec-hd">
        <h2>Top vendors</h2>
        <span class="eyebrow">${sortMode === "exposure"
          ? "sorted by exposure outside allowed countries"
          : "sorted by public-evidence index"}</span>
      </div>
      <p class="note">
        The index is not a rating of a vendor. It counts how much exposure is visible in public
        sources and how much of it cannot be verified — a vendor scoring high may simply publish
        less. Open a row for the reconciliations and the recent drift.
      </p>

      <div class="ctrlbar">
        <div class="ctrl-group">
          <span class="eyebrow">Allowed countries</span>
          <div class="cchips">
            ${allCountries().map(c => `
              <button type="button" class="cchip ${allowed.has(c) ? "on" : ""}" data-country="${esc(c)}">
                ${esc(c)}
              </button>`).join("")}
          </div>
        </div>
        <div class="ctrl-group ctrl-right">
          <label class="sortlabel">
            <span class="eyebrow">Sort by</span>
            <select id="sortSel">
              <option value="index" ${sortMode === "index" ? "selected" : ""}>Public-evidence index</option>
              <option value="exposure" ${sortMode === "exposure" ? "selected" : ""}>Exposure outside allowed countries</option>
            </select>
          </label>
          ${DEMO_VENDOR ? `
          <label class="demolabel">
            <input type="checkbox" id="demoToggle" ${showDemo ? "checked" : ""}>
            Show demo vendor
          </label>` : ""}
        </div>
      </div>

      <div class="matrix">
        <div class="mhdr">
          <span>Vendor</span><span>Index composition</span><span>Outside allowed</span><span>Index</span>
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
  document.querySelectorAll(".cchip").forEach(b =>
    b.addEventListener("click", () => {
      const c = b.dataset.country;
      allowed.has(c) ? allowed.delete(c) : allowed.add(c);
      render();
    }));
  const sortSel = $("#sortSel");
  if (sortSel) sortSel.addEventListener("change", e => { sortMode = e.target.value; render(); });
  const demoToggle = $("#demoToggle");
  if (demoToggle) demoToggle.addEventListener("change", e => { showDemo = e.target.checked; render(); });

  if (openId) mountDetail(openId);
}

function matrixRow(v) {
  const s = v.score;
  const counts = { high: 0, medium: 0, low: 0 };
  v.crosschecks.forEach(f => counts[f.severity]++);
  const chips = ["high", "medium", "low"]
    .filter(k => counts[k])
    .map(k => `<span class="chip ${k}">${counts[k]} ${k}</span>`).join("");

  const ex = exposure(v);
  const exBadge = ex.pct === null
    ? `<span class="chip none">no data</span>`
    : `<span class="xchip ${ex.pct === 0 ? "low" : ex.pct <= 40 ? "medium" : "high"}">${ex.pct}%</span>`;

  const driftBadge = (v.drift || []).length
    ? `<span class="dchip">${v.drift.length} drift</span>` : "";

  return `
    <button class="mrow" data-id="${esc(v.id)}" aria-expanded="false">
      <span class="mhead">
        <span class="mname">
          <span class="caret">▶</span>${esc(v.name)}
          ${v.demo ? `<span class="demoribbon">DEMO</span>` : ""}
        </span>
        <span class="mmeta">${esc(v.category)} · ${esc(v.hq)} ${chips ? "· " + chips : ""} ${driftBadge}</span>
      </span>
      <span class="stackwrap">
        <span class="stack">
          ${COMPONENTS.map(([k]) =>
            `<span class="seg ${k}" style="width:${s[k]}%" title="${k}: ${s[k]}"></span>`).join("")}
        </span>
        <span class="stack-scale"><span>0</span><span>100</span></span>
      </span>
      <span class="expwrap">${exBadge}</span>
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
  panel.innerHTML = detailHTML(VENDORS.find(v => v.id === id));
}

function mountDetail(id) {
  const panel = $("#d-" + id);
  if (!panel) return;
  panel.hidden = false;
  panel.innerHTML = detailHTML(VENDORS.find(v => v.id === id));
  const row = document.querySelector(`.mrow[data-id="${id}"]`);
  if (row) row.setAttribute("aria-expanded", "true");
}

function detailHTML(v) {
  return `
    ${v.demo ? `
    <div class="demonote">
      <b>This is a fictional example vendor.</b> It is not one of your tracked vendors — it exists
      to show what a caught wording change looks like before two real collection runs have gone by.
    </div>` : ""}

    <h3>Recent drift</h3>
    ${driftHTML(v)}

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

function driftHTML(v) {
  const events = v.drift || [];
  if (!events.length) {
    return `<p class="note">No wording changes detected in ${esc(KIND_LABEL.privacy)} or
      ${esc(KIND_LABEL.dpa).toLowerCase()} since tracking began. Re-run the collector on a later
      date to compare against today's snapshot.</p>`;
  }
  return events.map(ev => `
    <div class="drift">
      <div class="drift-top">
        <span class="drift-doc">${esc(ev.document_label)}</span>
        <span class="drift-date mono">${esc(ev.date)}</span>
        ${ev.url ? `<a href="${esc(ev.url)}" target="_blank" rel="noopener">source</a>` : ""}
      </div>
      ${ev.hunks.map(h => `
        <div class="drift-pair">
          ${h.before ? `<div class="drift-before"><span class="eyebrow">Before</span>${esc(h.before)}</div>` : ""}
          ${h.after ? `<div class="drift-after"><span class="eyebrow">After</span>${esc(h.after)}</div>` : ""}
        </div>`).join("")}
    </div>`).join("");
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
  const outside = entries.reduce((n, [c, k]) => n + (allowed.has(c) ? 0 : k), 0);
  return entries.map(([c, n]) => `
      <div class="geo">
        <span class="who" title="${esc(c)}">${esc(c)}${allowed.has(c) ? "" : " ⚑"}</span>
        <span><span class="bar ${allowed.has(c) ? "allowed" : "outside"}" style="width:${Math.max(3, (n / max) * 100)}%"></span></span>
        <span class="n">${n}</span>
      </div>`).join("") +
    `<p class="note" style="margin-top:12px">
      ${outside} of ${jobs.placeable} placeable roles (${Math.min(100, Math.round(100 * outside / jobs.placeable))}%)
      are outside your allowed countries (${[...allowed].join(", ") || "none selected"}).
      ⚑ marks a country outside the allow-list. Of these, ${jobs.non_eea} name no EEA site.
      A posting naming several cities counts in each.
    </p>`;
}

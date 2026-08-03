/* Data Drift Detection — dashboard.
   Reads data/index.json (real, collector-generated) and, if present,
   data/demo-vendor.json (one fictional, clearly-badged vendor used to show the
   drift feature before two real collection runs have accumulated history).
   No live fetching otherwise: everything shown here was gathered server-side.

   Per-vendor authorization (which countries you approved, and since when) is
   the one thing this static site cannot collect itself, so it lives in the
   browser's localStorage rather than in a committed file. */

const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const KIND_LABEL = {
  privacy: "Privacy policy",
  dpa: "Data processing agreement",
  subprocessors: "Sub-processor list",
  terms: "Terms",
  other: "Other legal page",
};

const RISK_FACTORS = [
  ["auth", "Exposure outside authorized countries", 40,
    "Share of this vendor's workforce (our best public proxy for who can reach your data) sitting outside the countries you authorized for it."],
  ["data", "Data sensitivity", 30,
    "The most sensitive data type this vendor's own privacy policy or DPA admits to processing, from business contact info up to biometric or special-category data."],
  ["osint", "OSINT flags", 20,
    "Open reconciliations where the vendor's claims and its public hiring evidence disagree."],
  ["since", "Changed since you authorized", 10,
    "Whether any tracked wording in the privacy policy or DPA has changed since the date you recorded as your authorization."],
];

const DEFAULT_ALLOWED = ["United States", "Canada"];
const AUTH_KEY = "ddd:auth:v1";
const DISMISS_KEY = "ddd:dismissed:v1";

let DATA = null;         // raw index.json
let VENDORS = [];         // real vendors + demo vendor if loaded/shown
let DEMO_VENDOR = null;
let openId = null;
let allowed = new Set(DEFAULT_ALLOWED);   // global default allow-list
let sortMode = "risk";     // "risk" | "exposure" | "index"
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

// ---------------------------------------------------------------------------
// per-vendor authorization (localStorage — see file header)
// ---------------------------------------------------------------------------

function loadAuthStore() {
  try { return JSON.parse(localStorage.getItem(AUTH_KEY)) || {}; }
  catch { return {}; }
}
function saveAuthStore(store) {
  try { localStorage.setItem(AUTH_KEY, JSON.stringify(store)); } catch { /* storage disabled */ }
}
function vendorAuth(v) {
  return loadAuthStore()[v.id] || {};
}
function vendorAllowed(v) {
  const custom = vendorAuth(v).countries;
  return new Set(custom || allowed);
}
function vendorIsCustom(v) {
  return Array.isArray(vendorAuth(v).countries);
}
function vendorSince(v) {
  return vendorAuth(v).since || v.authorized_since_default || null;
}
function setVendorCountries(vendorId, countries) {
  const store = loadAuthStore();
  store[vendorId] = { ...store[vendorId], countries };
  saveAuthStore(store);
}
function setVendorSince(vendorId, since) {
  const store = loadAuthStore();
  store[vendorId] = { ...store[vendorId], since: since || undefined };
  saveAuthStore(store);
}
function clearVendorCountries(vendorId) {
  const store = loadAuthStore();
  if (store[vendorId]) delete store[vendorId].countries;
  saveAuthStore(store);
}

// ---------------------------------------------------------------------------
// dismissed findings (localStorage) — a reviewer's call that a specific data
// tag or OSINT flag doesn't apply, kept and reversible rather than deleted
// ---------------------------------------------------------------------------

function loadDismissed() {
  try { return JSON.parse(localStorage.getItem(DISMISS_KEY)) || {}; }
  catch { return {}; }
}
function saveDismissed(store) {
  try { localStorage.setItem(DISMISS_KEY, JSON.stringify(store)); } catch { /* storage disabled */ }
}
function dismissedSet(vendorId, kind) {
  const store = loadDismissed();
  return new Set((store[vendorId] && store[vendorId][kind]) || []);
}
function toggleDismissed(vendorId, kind, itemKey) {
  const store = loadDismissed();
  const entry = store[vendorId] || (store[vendorId] = {});
  const list = new Set(entry[kind] || []);
  list.has(itemKey) ? list.delete(itemKey) : list.add(itemKey);
  entry[kind] = [...list];
  saveDismissed(store);
}

function liveTags(v) {
  const dismissed = dismissedSet(v.id, "tags");
  const all = v.data_classification?.tags || [];
  return { live: all.filter(t => !dismissed.has(t.key)), dismissed: all.filter(t => dismissed.has(t.key)) };
}
function liveCrosschecks(v) {
  const dismissed = dismissedSet(v.id, "flags");
  const all = v.crosschecks || [];
  return { live: all.filter(f => !dismissed.has(f.rule)), dismissed: all.filter(f => dismissed.has(f.rule)) };
}
function effectiveSensitivity(v) {
  const stated = liveTags(v).live.filter(t => t.confidence !== "conditional");
  const top = stated[0]; // tags arrive pre-sorted by sensitivity rank, descending
  const sensitivity = top ? top.sensitivity : "low";
  return { sensitivity, score: { low: 10, medium: 20, high: 30 }[sensitivity] };
}

// ---------------------------------------------------------------------------
// derived per-vendor numbers
// ---------------------------------------------------------------------------

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
  const va = vendorAllowed(v);
  if (!jobs?.ok || !jobs.placeable) {
    return { outside: 0, pct: null, hqOutside: [] };
  }
  let outside = 0;
  for (const [c, n] of Object.entries(jobs.countries || {})) {
    if (!va.has(c)) outside += n;
  }
  return {
    outside,
    // A posting naming several countries counts in each, so the raw sum can
    // exceed placeable -- cap the displayed share at 100%.
    pct: Math.min(100, Math.round((outside / jobs.placeable) * 100)),
    hqOutside: hqCountries(v).filter(c => !va.has(c)),
  };
}

function severityCounts(list) {
  const counts = { high: 0, medium: 0, low: 0 };
  (list || []).forEach(f => counts[f.severity]++);
  return counts;
}

function topTag(v) {
  const tags = liveTags(v).live;
  return tags.length ? tags[0] : null;
}

function driftSinceAuth(v) {
  const since = vendorSince(v);
  const events = v.drift || [];
  if (!since) return { since: null, changed: null, events };
  const after = events.filter(e => e.date >= since);
  return { since, changed: after.length > 0, events, after };
}

function riskScore(v) {
  const ex = exposure(v);
  const authPts = ex.pct == null ? 0 : Math.round(ex.pct * 0.4);
  const dataPts = effectiveSensitivity(v).score;
  const sc = severityCounts(liveCrosschecks(v).live);
  const osintPts = sc.high ? 20 : sc.medium ? 14 : sc.low ? 6 : 0;
  const since = driftSinceAuth(v);
  const sincePts = since.changed === true ? 10 : 0;
  const total = Math.min(100, authPts + dataPts + osintPts + sincePts);
  return { total, authPts, dataPts, osintPts, sincePts, ex, since };
}

function riskTier(total) {
  return total <= 35 ? "low" : total <= 65 ? "medium" : "high";
}

// ---------------------------------------------------------------------------
// top-level render
// ---------------------------------------------------------------------------

function renderRunbar(vendors) {
  const when = new Date(DATA.generated_at);
  const flags = vendors.reduce((n, v) => n + liveCrosschecks(v).live.length, 0);
  const high = vendors.reduce(
    (n, v) => n + liveCrosschecks(v).live.filter(f => f.severity === "high").length, 0);
  const docs = vendors.reduce((n, v) => n + v.docs.filter(d => d.path).length, 0);
  const driftCount = vendors.reduce((n, v) => n + (v.drift || []).length, 0);
  $("#runbar").innerHTML = `
    <span>collected <b>${when.toISOString().slice(0, 16).replace("T", " ")}Z</b></span>
    <span><b>${vendors.length}</b> vendors</span>
    <span><b>${docs}</b> documents tracked</span>
    <span><b>${flags}</b> OSINT flags · <b>${high}</b> high</span>
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
    } else if (sortMode === "index") {
      if (b.score.total !== a.score.total) return b.score.total - a.score.total;
    } else {
      const ra = riskScore(a).total, rb = riskScore(b).total;
      if (rb !== ra) return rb - ra;
    }
    return b.score.total - a.score.total;
  });

  $("#main").innerHTML = `
    <section>
      <div class="sec-hd">
        <h2>Top vendors</h2>
        <span class="eyebrow">${
          sortMode === "exposure" ? "sorted by exposure outside authorized countries"
          : sortMode === "index" ? "sorted by public-evidence index (legacy)"
          : "sorted by risk score"}</span>
      </div>
      <p class="note">
        Four questions per vendor: where you authorized processing, what kind of data it handles,
        whether the public evidence disagrees with its own claims, and whether anything has changed
        since you authorized it. The risk score is those four, added up and shown below — open a row
        to see the breakdown.
      </p>

      <div class="ctrlbar">
        <div class="ctrl-group">
          <span class="eyebrow">Default authorized countries</span>
          <div class="cchips">
            ${allCountries().map(c => `
              <button type="button" class="cchip ${allowed.has(c) ? "on" : ""}" data-country="${esc(c)}">
                ${esc(c)}
              </button>`).join("")}
          </div>
          <span class="hint">Applies to any vendor without its own override (set per-vendor below).</span>
        </div>
        <div class="ctrl-group ctrl-right">
          <label class="sortlabel">
            <span class="eyebrow">Sort by</span>
            <select id="sortSel">
              <option value="risk" ${sortMode === "risk" ? "selected" : ""}>Risk score</option>
              <option value="exposure" ${sortMode === "exposure" ? "selected" : ""}>Exposure outside authorized countries</option>
              <option value="index" ${sortMode === "index" ? "selected" : ""}>Public-evidence index (legacy)</option>
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
          <span>Vendor</span><span>Signals</span><span>Risk score</span>
        </div>
        ${rows.map(matrixRow).join("")}
      </div>
    </section>

    <section>
      <div class="sec-hd"><h2>How the risk score is built</h2></div>
      <div class="method">
        ${RISK_FACTORS.map(([k, label, pts, why]) => `
          <div class="card">
            <h4><span class="key riskkey ${k}" style="display:inline-block"></span>${esc(label)} — up to ${pts}</h4>
            <p>${esc(why)}</p>
          </div>`).join("")}
      </div>
    </section>`;

  document.querySelectorAll(".mrow").forEach(b =>
    b.addEventListener("click", () => toggle(b.dataset.id)));
  document.querySelectorAll(".ctrlbar > .ctrl-group:first-child .cchip").forEach(b =>
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

// ---------------------------------------------------------------------------
// vendor row (collapsed)
// ---------------------------------------------------------------------------

function matrixRow(v) {
  const risk = riskScore(v);
  const va = vendorAllowed(v);
  const authList = [...va];
  const authLabel = authList.length <= 2 ? (authList.join(", ") || "none")
    : `${authList.slice(0, 2).join(", ")} +${authList.length - 2}`;

  const tag = topTag(v);
  const dataLabel = tag ? (tag.label + (tag.confidence === "conditional" ? " (possible)" : "")) : "Not classified";
  const dataSev = tag ? tag.sensitivity : "low";

  const liveFlags = liveCrosschecks(v).live;
  const sc = severityCounts(liveFlags);
  const osintSev = sc.high ? "high" : sc.medium ? "medium" : sc.low ? "low" : "none";
  const osintLabel = liveFlags.length ? `${liveFlags.length} flag${liveFlags.length === 1 ? "" : "s"}` : "clear";

  const since = risk.since;
  const sinceState = since.since === null ? "unset" : since.changed ? "changed" : "clear";
  const sinceLabel = since.since === null ? "not set" : since.changed ? "changed" : "no change";

  return `
    <button class="mrow" data-id="${esc(v.id)}" aria-expanded="false">
      <span class="mhead">
        <span class="mname">
          <span class="caret">▶</span>${esc(v.name)}
          ${v.demo ? `<span class="demoribbon">DEMO</span>` : ""}
        </span>
        <span class="mmeta">${esc(v.category)} · ${esc(v.hq)}</span>
      </span>
      <span class="badges4">
        <span class="b4 auth" title="Authorized countries${vendorIsCustom(v) ? " (custom for this vendor)" : " (default)"}">
          Auth: ${esc(authLabel)}${vendorIsCustom(v) ? " *" : ""}
        </span>
        <span class="b4 data ${dataSev}" title="${esc(tag ? tag.why : "")}">Data: ${esc(dataLabel)}</span>
        <span class="b4 osint ${osintSev}">OSINT: ${esc(osintLabel)}</span>
        <span class="b4 since ${sinceState}">Since auth: ${esc(sinceLabel)}</span>
      </span>
      <span class="risk ${riskTier(risk.total)}">${risk.total}</span>
    </button>
    <div class="detail" id="d-${esc(v.id)}" hidden></div>`;
}

// ---------------------------------------------------------------------------
// vendor detail (expanded)
// ---------------------------------------------------------------------------

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
  mountDetailInto(panel, VENDORS.find(v => v.id === id));
}

function mountDetail(id) {
  const panel = $("#d-" + id);
  if (!panel) return;
  panel.hidden = false;
  mountDetailInto(panel, VENDORS.find(v => v.id === id));
  const row = document.querySelector(`.mrow[data-id="${id}"]`);
  if (row) row.setAttribute("aria-expanded", "true");
}

function mountDetailInto(panel, v) {
  panel.innerHTML = detailHTML(v);
  wireAuthEditor(panel, v);
  wireDismissButtons(panel, v);
}

function wireDismissButtons(panel, v) {
  panel.querySelectorAll(".dismissbtn, .restorebtn").forEach(b =>
    b.addEventListener("click", () => {
      toggleDismissed(v.id, b.dataset.kind, b.dataset.key);
      render();
    }));
}

function detailHTML(v) {
  const risk = riskScore(v);
  return `
    ${v.demo ? `
    <div class="demonote">
      <b>This is a fictional example vendor.</b> It is not one of your tracked vendors — it exists
      to show what a caught wording change looks like before two real collection runs have gone by.
    </div>` : ""}

    <div class="riskbreak">
      <div class="riskbreak-hd"><span class="eyebrow">Risk score breakdown</span><span class="risk ${riskTier(risk.total)}">${risk.total}</span></div>
      <div class="riskrow"><span>1 · Exposure outside authorized countries</span><b>${risk.authPts} / 40</b></div>
      <div class="riskrow"><span>2 · Data sensitivity</span><b>${risk.dataPts} / 30</b></div>
      <div class="riskrow"><span>3 · OSINT flags</span><b>${risk.osintPts} / 20</b></div>
      <div class="riskrow"><span>4 · Changed since authorized</span><b>${risk.sincePts} / 10</b></div>
    </div>

    <h3>1 · Where you authorized processing</h3>
    ${authEditorHTML(v)}

    <h3>2 · What kind of data this vendor processes</h3>
    ${classificationHTML(v)}

    <h3>3 · Is anything fishy in the OSINT</h3>
    ${osintHTML(v)}

    <h3>4 · Has anything changed since you authorized this</h3>
    ${driftHTML(v)}

    <h3>Documents tracked</h3>
    ${docsTable(v)}

    <h3>Open roles by country</h3>
    ${geoHTML(v)}`;
}

function authEditorHTML(v) {
  const va = vendorAllowed(v);
  const since = vendorAuth(v).since || "";
  const defaultSince = v.authorized_since_default || "";
  return `
    <div class="authbox" data-vid="${esc(v.id)}">
      <div class="authrow">
        <span class="eyebrow">Authorized in</span>
        <div class="cchips">
          ${allCountries().map(c => `
            <button type="button" class="cchip vcchip ${va.has(c) ? "on" : ""}" data-country="${esc(c)}">
              ${esc(c)}
            </button>`).join("")}
        </div>
        ${vendorIsCustom(v) ? `<button type="button" class="linkbtn vreset">Reset to default</button>`
          : `<span class="hint">Using your default allow-list — click a country to set a custom list for this vendor.</span>`}
      </div>
      <div class="authrow">
        <label class="eyebrow" for="since-${esc(v.id)}">Authorized since</label>
        <input type="date" id="since-${esc(v.id)}" class="vsince" value="${esc(since || defaultSince)}">
        ${!since && defaultSince ? `<span class="hint">Suggested default — confirm or change it.</span>` : ""}
      </div>
    </div>`;
}

function wireAuthEditor(panel, v) {
  const box = panel.querySelector(".authbox");
  if (!box) return;
  box.querySelectorAll(".vcchip").forEach(b => b.addEventListener("click", () => {
    const current = new Set(vendorAllowed(v));
    const c = b.dataset.country;
    current.has(c) ? current.delete(c) : current.add(c);
    setVendorCountries(v.id, [...current]);
    render();
  }));
  const reset = box.querySelector(".vreset");
  if (reset) reset.addEventListener("click", () => { clearVendorCountries(v.id); render(); });
  const since = box.querySelector(".vsince");
  if (since) since.addEventListener("change", e => { setVendorSince(v.id, e.target.value); render(); });
}

function tagRow(t, dismissed) {
  return `
    <div class="tagrow${dismissed ? " dismissedrow" : ""}">
      <span class="dtag ${t.sensitivity}">${esc(t.label)}${t.confidence === "conditional" ? ` <em>possible</em>` : ""}</span>
      <div class="tagbody">
        <p class="tagwhy">${esc(t.why)}</p>
        <p class="tagex">${esc(KIND_LABEL[t.source] || t.source)}: “${esc(t.excerpt)}”</p>
      </div>
      <button type="button" class="linkbtn ${dismissed ? "restorebtn" : "dismissbtn"}" data-kind="tags" data-key="${esc(t.key)}">
        ${dismissed ? "Restore" : "Dismiss"}
      </button>
    </div>`;
}

function classificationHTML(v) {
  const all = v.data_classification?.tags || [];
  if (!all.length) {
    return `<p class="note">No specific data types were recognised in the text collected. That is a
      reading of the wording, not a guarantee of what is actually processed.</p>`;
  }
  const { live, dismissed } = liveTags(v);
  return `
    <div class="taglist">${live.length ? live.map(t => tagRow(t, false)).join("")
      : `<p class="note">All data-type findings for this vendor have been dismissed.</p>`}</div>
    ${dismissed.length ? `
    <details class="dismissed-group">
      <summary>Dismissed (${dismissed.length})</summary>
      <div class="taglist">${dismissed.map(t => tagRow(t, true)).join("")}</div>
    </details>` : ""}`;
}

function driftHTML(v) {
  const { since, changed, events, after } = driftSinceAuth(v);
  if (!events.length) {
    return `<p class="note">No wording changes detected in ${esc(KIND_LABEL.privacy)} or
      ${esc(KIND_LABEL.dpa).toLowerCase()} since tracking began. Re-run the collector on a later
      date to compare against today's snapshot.</p>`;
  }
  const banner = since === null
    ? `<p class="note sinceflag unset">No authorization date is recorded for this vendor yet — set one
        above to see whether these changes happened before or after you approved it.</p>`
    : changed
    ? `<p class="note sinceflag changed">${after.length} of ${events.length} change${events.length === 1 ? "" : "s"}
        happened on or after ${esc(since)}, the date you authorized this vendor.</p>`
    : `<p class="note sinceflag clear">All ${events.length} tracked change${events.length === 1 ? "" : "s"}
        happened before ${esc(since)}, the date you authorized this vendor.</p>`;
  return banner + events.map(ev => `
    <div class="drift ${since !== null && ev.date >= since ? "postauth" : ""}">
      <div class="drift-top">
        <span class="drift-doc">${esc(ev.document_label)}</span>
        <span class="drift-date mono">${esc(ev.date)}</span>
        ${since !== null && ev.date >= since ? `<span class="dchip">after authorization</span>` : ""}
        ${ev.url ? `<a href="${esc(ev.url)}" target="_blank" rel="noopener">source</a>` : ""}
      </div>
      ${ev.hunks.map(h => `
        <div class="drift-pair">
          ${h.before ? `<div class="drift-before"><span class="eyebrow">Before</span>${esc(h.before)}</div>` : ""}
          ${h.after ? `<div class="drift-after"><span class="eyebrow">After</span>${esc(h.after)}</div>` : ""}
        </div>`).join("")}
    </div>`).join("");
}

function osintHTML(v) {
  if (!v.crosschecks.length) {
    return `<p class="note">Nothing to reconcile from the sources collected. That is a clean pass on
      these checks, not a clean bill of health — re-run and compare.</p>`;
  }
  const { live, dismissed } = liveCrosschecks(v);
  return `
    ${live.length ? live.map(f => reconCard(f, false)).join("")
      : `<p class="note">All OSINT flags for this vendor have been dismissed.</p>`}
    ${dismissed.length ? `
    <details class="dismissed-group">
      <summary>Dismissed (${dismissed.length})</summary>
      ${dismissed.map(f => reconCard(f, true)).join("")}
    </details>` : ""}`;
}

function reconCard(f, dismissed) {
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
    <div class="recon${dismissed ? " dismissedrow" : ""}">
      <div class="recon-top">
        <span class="recon-title">${esc(f.headline)}</span>
        <span class="sev ${esc(f.severity)}">${esc(f.severity)}</span>
        <button type="button" class="linkbtn ${dismissed ? "restorebtn" : "dismissbtn"}" data-kind="flags" data-key="${esc(f.rule)}">
          ${dismissed ? "Restore" : "Dismiss as not relevant"}
        </button>
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

function geoHTML(v) {
  const jobs = v.jobs;
  const va = vendorAllowed(v);
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
  const outside = entries.reduce((n, [c, k]) => n + (va.has(c) ? 0 : k), 0);
  return entries.map(([c, n]) => `
      <div class="geo">
        <span class="who" title="${esc(c)}">${esc(c)}${va.has(c) ? "" : " ⚑"}</span>
        <span><span class="bar ${va.has(c) ? "allowed" : "outside"}" style="width:${Math.max(3, (n / max) * 100)}%"></span></span>
        <span class="n">${n}</span>
      </div>`).join("") +
    `<p class="note" style="margin-top:12px">
      ${outside} of ${jobs.placeable} placeable roles (${Math.min(100, Math.round(100 * outside / jobs.placeable))}%)
      are outside the countries authorized for this vendor (${[...va].join(", ") || "none selected"}).
      ⚑ marks a country outside that list. A posting naming several cities counts in each.
    </p>`;
}

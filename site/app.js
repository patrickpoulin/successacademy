(async function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  let data;
  try {
    data = await (await fetch("data/schools.json", { cache: "no-cache" })).json();
  } catch (e) {
    $("updated").textContent = "Could not load data/schools.json";
    return;
  }

  const SRC = data.sources; // { key: {label, short, url, ok, count, error, fetched_at} }
  const srcKeys = Object.keys(SRC);
  $("updated").textContent = "Data refreshed " + new Date(data.generated_at).toLocaleString() +
    " · " + data.schools.length + " schools";
  $("sources").innerHTML = srcKeys.map((k) => {
    const s = SRC[k];
    const tip = s.ok ? `${s.count} schools from ${s.label}` : `${s.label} failed: ${s.error || "unknown error"}`;
    if (s.partial) return `<a class="src" href="${esc(s.url)}" target="_blank" rel="noopener" title="${esc(s.label)}: still loading the full list">
      <span class="dot" style="background:var(--warn)"></span>${esc(s.short)} <b>${s.count}+</b></a>`;
    return `<a class="src ${s.ok ? "" : "down"}" href="${esc(s.url)}" target="_blank" rel="noopener" title="${esc(tip)}">
      <span class="dot"></span>${esc(s.short)} <b>${s.ok ? s.count : "down"}</b></a>`;
  }).join("");

  // source tag filter: each tag cycles any -> listed -> not listed
  const tagState = Object.fromEntries(srcKeys.map((k) => [k, ""]));
  $("tags").innerHTML = srcKeys.map((k) =>
    `<button type="button" class="tag" data-k="${esc(k)}" aria-pressed="false" title="${esc(SRC[k].label)}">${esc(SRC[k].short)}</button>`).join("");
  $("tags").addEventListener("click", (e) => {
    const b = e.target.closest(".tag"); if (!b) return;
    const k = b.dataset.k, next = { "": "yes", yes: "no", no: "" }[tagState[k]];
    tagState[k] = next;
    b.className = "tag " + next;
    b.setAttribute("aria-pressed", next ? "true" : "false");
    render();
  });
  const how = $("how");
  $("howBtn").addEventListener("click", () => how.showModal());
  how.addEventListener("click", (e) => { if (e.target === how) how.close(); });

  const uniq = (arr) => [...new Set(arr.filter(Boolean))].sort();
  for (const b of uniq(data.schools.map((s) => s.borough))) $("boro").add(new Option(b, b));
  for (const a of uniq(data.schools.map((s) => s.authorizer))) $("auth").add(new Option(a, a));

  const map = L.map("map", { preferCanvas: true }).setView([40.7128, -73.95], 11);
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  // OpenStreetMap's standard tiles: no API key, attribution required
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, className: dark ? "tiles-dark" : "tiles-light",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  const css = getComputedStyle(document.documentElement);
  const color = (s) => css.getPropertyValue(s.issues.length ? "--warn" : "--ok").trim();

  const badges = (s) => `<div class="badges">${srcKeys.map((k) => {
    if (!SRC[k].ok) return `<span class="b" title="${esc(SRC[k].label)} unavailable">${esc(SRC[k].short)} ?</span>`;
    const yes = s.in[k];
    if (!yes && SRC[k].partial) return `<span class="b" title="${esc(SRC[k].label)} still loading">${esc(SRC[k].short)} ?</span>`;
    return `<span class="b ${yes ? "yes" : "no"}" title="${yes ? "Listed" : "Not listed"} in ${esc(SRC[k].label)}">${esc(SRC[k].short)}</span>`;
  }).join("")}</div>`;
  const ids = (s) => [s.dbn && "DBN " + s.dbn, s.beds && "BEDS " + s.beds].filter(Boolean).join(" · ");

  const popup = (s) => `<strong>${esc(s.name)}</strong><br>${esc(s.address || "")}${s.borough ? ", " + esc(s.borough) : ""}
    <br><span class="meta">${esc([s.grades && "Grades " + s.grades, s.authorizer].filter(Boolean).join(" · "))}</span>
    <br><span class="meta">${esc(ids(s))}</span>${badges(s)}
    ${s.issues.map((i) => `<div class="issue">⚠ ${esc(i)}</div>`).join("")}`;

  const markers = new Map();
  for (const s of data.schools) {
    if (s.lat == null || s.lon == null) continue;
    const m = L.circleMarker([s.lat, s.lon], { radius: 6, weight: 1, color: "#0006", fillColor: color(s), fillOpacity: 0.85 })
      .bindPopup(() => popup(s));
    m.on("click", () => select(s.id, false));
    markers.set(s.id, m);
  }
  const layer = L.featureGroup().addTo(map);

  let selected = null;
  function select(id, fly) {
    selected = id;
    for (const li of $("list").children) li.classList.toggle("sel", li.dataset.id === id);
    const li = $("list").querySelector(`[data-id="${CSS.escape(id)}"]`);
    if (li && !fly) li.scrollIntoView({ block: "nearest" });
    const m = markers.get(id);
    if (m && fly) { map.flyTo(m.getLatLng(), Math.max(map.getZoom(), 15), { duration: 0.6 }); m.openPopup(); }
  }

  let shown = [];
  // "0K,01,02,03" -> "K-3"; leaves already-tidy text like "K-5" alone
  const gradeRange = (g) => {
    const parts = String(g || "").split(/\s*,\s*/).filter(Boolean);
    if (parts.length < 2) return g || "";
    const n = (p) => (/^0?K$/i.test(p) ? 0 : /^PK$/i.test(p) ? -1 : parseInt(p, 10));
    const v = parts.map(n).filter((x) => !isNaN(x)).sort((a, b) => a - b);
    if (!v.length) return g;
    const lab = (x) => (x === -1 ? "PK" : x === 0 ? "K" : String(x));
    return lab(v[0]) + "–" + lab(v[v.length - 1]);
  };
  const tidy = (a) => (a && a === a.toUpperCase() ? a.toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase()) : a || "");
  function exportList() {
    const filters = [
      $("q").value.trim() && `search "${$("q").value.trim()}"`,
      $("boro").value, $("auth").value,
      { ok: "sources agree", issue: "sources disagree" }[$("agree").value],
      ...srcKeys.filter((k) => tagState[k]).map((k) => (tagState[k] === "no" ? "not listed by " : "listed by ") + SRC[k].short),
    ].filter(Boolean);
    const byBoro = {};
    for (const s of shown) (byBoro[s.borough || "Borough unknown"] ||= []).push(s);
    const order = ["Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island", "Borough unknown"];
    const listed = (s) => srcKeys.filter((k) => s.in[k]).map((k) => SRC[k].short).join(", ");
    const sections = order.filter((b) => byBoro[b]).map((b) => `
      <h2>${esc(b)} <span>${byBoro[b].length}</span></h2>
      <table><thead><tr><th>School</th><th>Address</th><th>Grades</th><th>IDs</th><th>Listed by</th><th>Notes</th></tr></thead><tbody>
      ${byBoro[b].map((s) => `<tr>
        <td><b>${esc(s.name)}</b>${s.authorizer ? `<br><small>${esc(s.authorizer)}</small>` : ""}</td>
        <td>${esc(tidy(s.address))}</td><td>${esc(gradeRange(s.grades))}</td>
        <td><small>${esc([s.dbn && "DBN " + s.dbn, s.beds && "BEDS " + s.beds].filter(Boolean).join("\n"))}</small></td>
        <td><small>${esc(listed(s))}</small></td>
        <td><small>${s.issues.map(esc).join("<br>")}</small></td></tr>`).join("")}
      </tbody></table>`).join("");
    const title = "NYC Charter Schools";
    const doc = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title} (${shown.length})</title><style>
body{font:12px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;color:#111;margin:24px;max-width:1100px}
h1{font-size:20px;margin:0}h2{font-size:15px;margin:22px 0 6px;border-bottom:2px solid #111;padding-bottom:3px;break-after:avoid}
h2 span{font-weight:400;color:#666}.meta{color:#555;margin:4px 0 0}
table{width:100%;border-collapse:collapse}th,td{text-align:left;vertical-align:top;padding:5px 6px;border-bottom:1px solid #ddd}
th{font-size:11px;text-transform:uppercase;letter-spacing:.03em;color:#555}tr{break-inside:avoid}small{color:#444;white-space:pre-line}
.bar{margin:14px 0}.bar button{font:inherit;padding:6px 14px;border:1px solid #111;background:#fff;border-radius:6px;cursor:pointer}
@media print{body{margin:0}.bar{display:none}thead{display:table-header-group}@page{margin:12mm}}
</style></head><body>
<h1>${title}</h1>
<p class="meta">${shown.length} schools · data refreshed ${esc(new Date(data.generated_at).toLocaleString())} · sources: ${esc(srcKeys.map((k) => SRC[k].label).join("; "))}</p>
${filters.length ? `<p class="meta">Filtered to: ${esc(filters.join(" · "))}</p>` : ""}
<div class="bar"><button onclick="print()">Print</button></div>
${sections}
<p class="meta">Exported from ${esc(location.href)}</p>
</body></html>`;
    const url = URL.createObjectURL(new Blob([doc], { type: "text/html" }));
    const w = window.open(url, "_blank");
    if (!w) { const a = document.createElement("a"); a.href = url; a.download = "nyc-charter-schools.html"; a.click(); }
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  $("exportBtn").addEventListener("click", exportList);

  function render() {
    const q = $("q").value.trim().toLowerCase();
    const boro = $("boro").value, auth = $("auth").value, agree = $("agree").value;
    const rows = data.schools.filter((s) =>
      (!boro || s.borough === boro) && (!auth || s.authorizer === auth) &&
      (!agree || (agree === "issue") === s.issues.length > 0) &&
      srcKeys.every((k) => !tagState[k] || (tagState[k] === "yes") === !!s.in[k]) &&
      (!q || [s.name, s.address, s.dbn, s.beds, s.zip, ...Object.values(s.names || {})].join(" ").toLowerCase().includes(q)));
    shown = rows;
    $("count").textContent = `${rows.length} shown`;
    $("list").innerHTML = rows.map((s) => `<li data-id="${esc(s.id)}" class="${s.id === selected ? "sel" : ""}">
      <div class="name">${esc(s.name)}</div>
      <div class="meta">${esc([s.address, s.borough].filter(Boolean).join(", "))}${markers.has(s.id) ? "" : ' <span class="nomap">(not on map)</span>'}</div>
      <div class="meta">${esc([s.grades && "Grades " + s.grades, s.authorizer, ids(s)].filter(Boolean).join(" · "))}</div>
      ${badges(s)}${s.issues.map((i) => `<div class="issue">⚠ ${esc(i)}</div>`).join("")}</li>`).join("");
    layer.clearLayers();
    for (const s of rows) { const m = markers.get(s.id); if (m) layer.addLayer(m); }
  }
  $("list").addEventListener("click", (e) => { const li = e.target.closest("li"); if (li) select(li.dataset.id, true); });
  for (const id of ["q", "boro", "auth", "agree"]) $(id).addEventListener("input", render);
  render();
  if (layer.getLayers().length) map.fitBounds(layer.getBounds(), { padding: [20, 20] });
})();

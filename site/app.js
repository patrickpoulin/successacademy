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

  function render() {
    const q = $("q").value.trim().toLowerCase();
    const boro = $("boro").value, auth = $("auth").value, agree = $("agree").value;
    const rows = data.schools.filter((s) =>
      (!boro || s.borough === boro) && (!auth || s.authorizer === auth) &&
      (!agree || (agree === "issue") === s.issues.length > 0) &&
      srcKeys.every((k) => !tagState[k] || (tagState[k] === "yes") === !!s.in[k]) &&
      (!q || [s.name, s.address, s.dbn, s.beds, s.zip, ...Object.values(s.names || {})].join(" ").toLowerCase().includes(q)));
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

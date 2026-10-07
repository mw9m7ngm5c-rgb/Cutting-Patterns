// Sawing-pattern screen: pattern list, builder, end-view diagram, single-log and class results.
"use strict";

const root = document.getElementById("pattern-app");
const DS = root.dataset.ds;
const THICK = JSON.parse(root.dataset.thicknesses);
const WIDTHS = JSON.parse(root.dataset.widths);
const $ = id => document.getElementById(id);
const state = { patterns: [], logs: [], current: null, logIndex: 0, timer: null, diagram: null };

const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// fixed format whatever the browser's locale: space for thousands, point for decimals (as on the reports)
const fmt = (v, nd = 2) => {
  if (v == null || isNaN(v)) return "";
  const [i, f] = Math.abs(Number(v)).toFixed(nd).split(".");
  return (v < 0 ? "-" : "") + i.replace(/\B(?=(\d{3})+(?!\d))/g, " ") + (f ? "." + f : "");
};
const pct = v => fmt(100 * v, 1) + " %";
const rand = v => "R " + fmt(v, 2);

async function getJSON(url, opts) {
  const r = await fetch(url, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((body.errors || [body.detail || "Request failed"]).join("; "));
  return body;
}

// ------------------------------------------------------------------ choose line and class

function selection() { return { line: $("line").value, cls: $("cls").value }; }

function fromHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  if (h.get("line")) $("line").value = h.get("line");
  if (h.get("class")) {
    const opt = [...$("cls").options].find(o => o.dataset.no === h.get("class"));
    if (opt) $("cls").value = opt.value;
  }
}

function toHash() {
  const opt = $("cls").selectedOptions[0];
  history.replaceState(null, "", `#line=${$("line").value}&class=${opt ? opt.dataset.no : ""}`);
}

async function loadList(selectId) {
  const { line, cls } = selection();
  if (!line || !cls) { $("list").innerHTML = "<li>Add a production line and a log class first.</li>"; return; }
  toHash();
  const data = await getJSON(`/api/d/${DS}/patterns?line_id=${line}&class_id=${cls}`);
  state.patterns = data.patterns;
  state.logs = data.logs;
  $("log").innerHTML = state.logs.map((g, i) =>
    `<option value="${i}">Log ${g.no}: ${fmt(g.sed_cm, 1)} cm × ${fmt(g.length_m, 1)} m</option>`).join("");
  state.logIndex = Math.min(state.logIndex, Math.max(0, state.logs.length - 1));
  $("log").value = state.logIndex;
  renderList();
  const pick = state.patterns.find(p => p.id === selectId) || state.patterns[0];
  if (pick) choose(pick); else newPattern();
  $("class-result").innerHTML = "";
}

function renderList() {
  $("list").innerHTML = state.patterns.map(p => `
    <li data-id="${p.id}" class="${state.current && state.current.id === p.id ? "active" : ""}">
      <strong>${p.pattern_no}.</strong> <code>${esc(p.primary)}</code> &nbsp; <code>${esc(p.secondary)}</code>
      <small>${p.problems.length ? `<span class="tag bad">cannot saw</span> ${esc(p.problems[0])}` :
        `<span class="tag ok">ready</span>`} ${p.source !== "manual" ? `<span class="tag">${esc(p.source)}</span>` : ""}</small>
    </li>`).join("") || '<li class="help">No patterns yet for this class.</li>';
  $("list").querySelectorAll("li[data-id]").forEach(li =>
    li.onclick = () => choose(state.patterns.find(p => p.id === +li.dataset.id)));
}

function choose(p) {
  state.current = p;
  $("primary").value = p.primary;
  $("secondary").value = p.secondary;
  $("delete").disabled = false;
  $("save").textContent = `Save pattern ${p.pattern_no}`;
  renderList();
  refresh(0);
}

function newPattern() {
  state.current = null;
  $("primary").value = "";
  $("secondary").value = "";
  $("delete").disabled = true;
  $("save").textContent = "Save";
  renderList();
  refresh(0);
}

// ------------------------------------------------------------------ builder (simple patterns only)

function expand(text) {
  const out = [];
  for (const tok of text.trim().split(/\s+/).filter(Boolean)) {
    const m = tok.match(/^(?:(\d+)\*)?(\d+(?:\.\d+)?)$/);
    if (!m) return null;
    for (let i = 0; i < (m[1] ? +m[1] : 1); i++) out.push(+m[2]);
  }
  return out;
}

function collapse(list) {
  const out = [];
  for (let i = 0; i < list.length;) {
    let j = i;
    while (j + 1 < list.length && list[j + 1] === list[i]) j++;
    out.push(j > i ? `${j - i + 1}*${list[i]}` : `${list[i]}`);
    i = j + 1;
  }
  return out.join(" ");
}

function parseSimple() {
  const p = $("primary").value, s = $("secondary").value;
  if (/[,<>xX]/.test(p + s)) return null;          // markers and fixed widths: edit as text
  const parts = p.split("/");
  if (p.trim() && parts.length !== 3) return null;
  const left = expand(parts[0] || ""), right = expand(parts[2] || ""), sec = expand(s);
  const cant = parts.length === 3 && parts[1].trim() ? +parts[1] : null;
  if (!left || !right || !sec || (parts.length === 3 && parts[1].trim() && isNaN(cant))) return null;
  return { left, cant, right, sec };
}

function writeSimple(b) {
  $("primary").value = b.cant == null && !b.left.length && !b.right.length ? "" :
    `${collapse(b.left)}/${b.cant == null ? "" : b.cant}/${collapse(b.right)}`;
  $("secondary").value = collapse(b.sec);
  refresh();
}

function withBuilder(fn) {
  const b = parseSimple();
  if (!b) { $("builder-note").textContent = "This pattern uses markers or fixed widths: edit it as text."; return; }
  $("builder-note").textContent = "";
  fn(b);
  writeSimple(b);
}

function addBoard(zone, t) {
  withBuilder(b => {
    const sym = $("symmetric").checked;
    if (zone === "sec") b.sec.push(t);
    else {
      if (zone === "left" || sym) b.left.unshift(t);   // written outermost first
      if (zone === "right" || sym) b.right.push(t);
    }
  });
}

function setCant(w) { withBuilder(b => { b.cant = w; }); }

function zone() { return document.querySelector('input[name="zone"]:checked').value; }

function buildPalette() {
  $("cants").innerHTML = WIDTHS.map(w => `<span class="chip cant" draggable="true" data-kind="cant" data-v="${w}">${w}</span>`).join("");
  $("thicks").innerHTML = THICK.map(t => `<span class="chip" draggable="true" data-kind="board" data-v="${t}">${t}</span>`).join("");
  document.querySelectorAll(".chip").forEach(ch => {
    ch.onclick = () => ch.dataset.kind === "cant" ? setCant(+ch.dataset.v) : addBoard(zone(), +ch.dataset.v);
    ch.ondragstart = e => e.dataTransfer.setData("text/plain", JSON.stringify({ kind: ch.dataset.kind, v: +ch.dataset.v }));
  });
  $("undo").onclick = () => withBuilder(b => {
    const z = zone(), sym = $("symmetric").checked;
    if (z === "sec") b.sec.pop();
    else { if (z === "left" || sym) b.left.shift(); if (z === "right" || sym) b.right.pop(); }
  });
  $("clear").onclick = () => { $("primary").value = ""; $("secondary").value = ""; refresh(); };
}

// ------------------------------------------------------------------ diagram

function svgPoint(svg, e) {
  const pt = svg.createSVGPoint();
  pt.x = e.clientX; pt.y = e.clientY;
  return pt.matrixTransform(svg.getScreenCTM().inverse());
}

function poly(points) { return points.map(([x, y]) => `${x},${-y}`).join(" "); }

function drawDiagram(d) {
  const box = $("diagram-box");
  if (!d.large_end) { box.innerHTML = '<p class="help">No log to draw.</p>'; return; }
  const all = d.large_end.concat(d.small_end);
  let minX = Math.min(...all.map(p => p[0])), maxX = Math.max(...all.map(p => p[0]));
  let minY = Math.min(...all.map(p => p[1])), maxY = Math.max(...all.map(p => p[1]));
  const pad = 0.08 * Math.max(maxX - minX, maxY - minY) + 10;
  minX -= pad; maxX += pad; minY -= pad; maxY += pad;
  const W = maxX - minX, H = maxY - minY;
  const parts = [];
  parts.push(`<polygon points="${poly(d.large_end)}" fill="var(--wood)" stroke="var(--wood-edge)" stroke-width="${W / 400}"/>`);
  parts.push(`<polygon points="${poly(d.small_end)}" fill="none" stroke="var(--wood-edge)" stroke-width="${W / 400}" stroke-dasharray="${W / 100} ${W / 160}"/>`);
  if (d.core) parts.push(`<polygon points="${poly(d.core)}" fill="none" stroke="#9b2c2c" stroke-width="${W / 500}" stroke-dasharray="${W / 200}"><title>Defect core</title></polygon>`);
  (d.boards || []).forEach(b => {
    const w = b.right - b.left, h = b.top - b.bottom;
    parts.push(`<rect x="${b.left}" y="${-b.top}" width="${w}" height="${h}" fill="var(--board)" stroke="var(--board-edge)"
      stroke-width="${W / 600}" ${b.resawn ? `stroke-dasharray="${W / 150} ${W / 300}"` : ""}>
      <title>${esc(b.kind)} ${b.board_no + 1}: ${esc(b.label)}${b.resawn ? " (resawn)" : ""}, ${fmt(b.front_m, 2)}–${fmt(b.back_m, 2)} m from the small end</title></rect>`);
    const vertical = h > w * 1.15;
    const long = vertical ? h : w, short = vertical ? w : h;
    const fs = Math.max(2.5, Math.min(short * 0.5, long * 0.9 / (b.label.length * 0.6), W / 32));
    const cx = b.left + w / 2, cy = -(b.bottom + h / 2);
    parts.push(`<text x="${cx}" y="${cy}" font-size="${fs}" text-anchor="middle" dominant-baseline="central" fill="#3b2a0c"
      ${vertical ? `transform="rotate(-90 ${cx} ${cy})"` : ""} pointer-events="none">${esc(b.label)}</text>`);
  });
  (d.primary_kerfs || []).forEach(([a, b]) =>
    parts.push(`<rect x="${a}" y="${-maxY}" width="${b - a}" height="${H}" fill="var(--kerf)" opacity=".55"/>`));
  if (d.cant) (d.secondary_kerfs || []).forEach(([a, b]) =>
    parts.push(`<rect x="${d.cant.lo}" y="${-b}" width="${d.cant.hi - d.cant.lo}" height="${b - a}" fill="var(--kerf)" opacity=".55"/>`));
  // scale bar: 50 mm
  const sx = minX + pad * 0.4, sy = -minY - pad * 0.35;
  parts.push(`<line x1="${sx}" y1="${sy}" x2="${sx + 50}" y2="${sy}" stroke="#333" stroke-width="${W / 300}"/>
    <text x="${sx + 25}" y="${sy - W / 120}" font-size="${W / 45}" text-anchor="middle" fill="#333">50 mm</text>`);
  box.innerHTML = `<svg class="diagram" viewBox="${minX} ${-maxY} ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img"
    aria-label="End view of log ${d.log.no} with the pattern drawn over it">${parts.join("")}</svg>`;
  const svg = box.querySelector("svg");
  svg.ondragover = e => { e.preventDefault(); svg.classList.add("drop-target"); };
  svg.ondragleave = () => svg.classList.remove("drop-target");
  svg.ondrop = e => {
    e.preventDefault();
    svg.classList.remove("drop-target");
    let item;
    try { item = JSON.parse(e.dataTransfer.getData("text/plain")); } catch { return; }
    if (item.kind === "cant") return setCant(item.v);
    const x = svgPoint(svg, e).x;
    const half = d.cant ? (d.cant.hi - d.cant.lo) / 2 : 0;
    addBoard(Math.abs(x) <= half ? "sec" : x < 0 ? "left" : "right", item.v);
  };
}

function renderLogResult(d) {
  const r = d.result;
  if (!r) { $("log-result").innerHTML = '<p class="help">Nothing sawn.</p>'; return; }
  const rows = d.boards.map(b => `<tr><td class="text">${esc(b.kind)} ${b.board_no + 1}</td><td class="text">${esc(b.label)}${b.resawn ? ' <span class="tag">resawn</span>' : ""}</td>
    <td>${fmt(b.dry_volume * 1000, 2)}</td></tr>`).join("");
  $("log-result").innerHTML = `
    <dl class="kv">
      <dt>Log volume</dt><dd>${fmt(r.log_volume, 4)} m³</dd>
      <dt>Boards</dt><dd>${r.boards}</dd>
      <dt>Dry board volume</dt><dd>${fmt(r.dry_volume, 4)} m³</dd>
      <dt>Dry recovery</dt><dd><strong>${pct(r.dry_recovery)}</strong></dd>
      <dt>Board value</dt><dd>${rand(r.value)}</dd>
      <dt>Shrinkage</dt><dd>${fmt(r.shrinkage, 4)} m³</dd>
      <dt>Sawdust</dt><dd>${fmt(r.sawdust, 4)} m³</dd>
      <dt>Chips</dt><dd>${fmt(r.chips, 4)} m³</dd>
    </dl>
    <table class="data" style="margin-top:.6rem; width:100%"><thead><tr><th class="text">Board</th><th class="text">Size</th><th>Dry<span class="unit">litres</span></th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

async function refresh(delay = 250) {
  clearTimeout(state.timer);
  state.timer = setTimeout(async () => {
    const g = state.logs[state.logIndex];
    if (!g) {
      $("diagram-box").innerHTML = '<p class="help">No logs fall in this class. Add logs or widen the class on the Logs page.</p>';
      $("log-result").innerHTML = ""; $("log-facts").textContent = ""; $("problems").textContent = "";
      return;
    }
    $("log-facts").textContent = `taper ${fmt(g.taper, 1)} mm/m · sweep ${fmt(g.sweep_mm, 1)} mm (${fmt(g.sweep_mm_per_m, 1)} mm/m) · ovality ${fmt(g.ovality, 2)}`;
    const { line } = selection();
    const q = new URLSearchParams({ line_id: line, log_no: g.no, primary: $("primary").value, secondary: $("secondary").value });
    let d;
    try { d = await getJSON(`/api/d/${DS}/diagram?${q}`); }
    catch (e) { $("problems").textContent = e.message; return; }
    state.diagram = d;
    const typed = $("primary").value.trim() !== "";
    $("problems").innerHTML = typed && d.problems.length ? d.problems.map(esc).join("<br>") : "";
    drawDiagram(d);
    if (typed && !d.problems.length) renderLogResult(d);
    else $("log-result").innerHTML = '<p class="help">Type or pick a pattern.</p>';
  }, delay);
}

function stepLog(by) {
  if (!state.logs.length) return;
  state.logIndex = (state.logIndex + by + state.logs.length) % state.logs.length;
  $("log").value = state.logIndex;
  refresh(0);
}

// ------------------------------------------------------------------ class run

async function runClass() {
  const { line, cls } = selection();
  const q = new URLSearchParams({ line_id: line, class_id: cls, primary: $("primary").value, secondary: $("secondary").value });
  $("class-result").innerHTML = '<p class="help">Sawing…</p>';
  const t0 = performance.now();
  let r;
  try { r = await getJSON(`/api/d/${DS}/simulate_class?${q}`); }
  catch (e) { $("class-result").innerHTML = `<div class="error">${esc(e.message)}</div>`; return; }
  if (r.problems.length) { $("class-result").innerHTML = `<div class="error">${r.problems.map(esc).join("<br>")}</div>`; return; }
  const secs = ((performance.now() - t0) / 1000).toFixed(1);
  $("class-result").innerHTML = `
    <dl class="kv" style="margin-top:.6rem">
      <dt>Logs</dt><dd>${r.logs}</dd>
      <dt>Dry recovery</dt><dd><strong>${pct(r.dry_recovery)}</strong></dd>
      <dt>Wet recovery</dt><dd>${pct(r.wet_recovery)}</dd>
      <dt>Gross value</dt><dd>${rand(r.gross_value)} /m³ log</dd>
      <dt>Nett value</dt><dd>${rand(r.nett_value)} /m³ log</dd>
      <dt>Boards</dt><dd>${r.boards} (${fmt(r.boards_per_log, 1)} per log)</dd>
      <dt>Average length</dt><dd>${fmt(r.average_length, 2)} m</dd>
    </dl>
    <h3>Product mix</h3>
    <table class="data" style="width:100%"><thead><tr><th class="text">Size</th><th>Pieces</th><th>Dry<span class="unit">m³</span></th><th>Share</th></tr></thead><tbody>
    ${r.mix.map(x => `<tr><td class="text">${x.thickness} × ${x.width}</td><td>${x.pieces}</td><td>${fmt(x.dry_volume, 3)}</td><td>${pct(x.share)}</td></tr>`).join("")}
    </tbody></table>
    <h3>Per log <small class="help">(click a log to draw it)</small></h3>
    <div style="max-height: 22rem; overflow:auto">
    <table class="data" style="width:100%"><thead><tr><th>Log</th><th>SED<span class="unit">cm</span></th><th>Boards</th><th>Recovery</th></tr></thead><tbody>
    ${r.per_log.map(x => `<tr class="clickable" data-no="${x.no}"><td>${x.no}</td><td>${fmt(x.sed_cm, 1)}</td><td>${x.boards}</td><td>${pct(x.dry_recovery)}</td></tr>`).join("")}
    </tbody></table></div>
    <p class="help">Sawn in ${secs} s.</p>`;
  $("class-result").querySelectorAll("tr[data-no]").forEach(tr => tr.onclick = () => {
    const i = state.logs.findIndex(g => g.no === +tr.dataset.no);
    if (i >= 0) { state.logIndex = i; $("log").value = i; refresh(0); }
  });
}

// ------------------------------------------------------------------ save and delete

async function save(asNew) {
  const { line, cls } = selection();
  const body = { line_id: line, class_id: cls, primary: $("primary").value, secondary: $("secondary").value };
  if (!asNew && state.current) body.id = state.current.id;
  try {
    const r = await getJSON(`/api/d/${DS}/patterns`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    $("save-status").textContent = "Saved";
    await loadList(r.id);
  } catch (e) { $("save-status").textContent = e.message; }
}

async function remove() {
  if (!state.current || !confirm(`Delete pattern ${state.current.pattern_no}?`)) return;
  await getJSON(`/api/d/${DS}/patterns/${state.current.id}/delete`, { method: "POST" });
  state.current = null;
  await loadList();
}

// ------------------------------------------------------------------ wire up

fromHash();
buildPalette();
$("line").onchange = () => loadList();
$("cls").onchange = () => { state.logIndex = 0; loadList(); };
$("new").onclick = newPattern;
$("primary").oninput = () => { $("save-status").textContent = ""; refresh(); };
$("secondary").oninput = () => { $("save-status").textContent = ""; refresh(); };
$("prev").onclick = () => stepLog(-1);
$("next").onclick = () => stepLog(1);
$("log").onchange = () => { state.logIndex = +$("log").value; refresh(0); };
$("run-class").onclick = runClass;
$("save").onclick = () => save(false);
$("saveas").onclick = () => save(true);
$("delete").onclick = remove;
loadList();

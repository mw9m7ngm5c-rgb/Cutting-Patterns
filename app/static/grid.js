// Editable table used on every data-entry screen.
// <div class="grid" data-url="/api/d/1/grid/logs"></div>  ->  load, edit, add, delete, paste from Excel, save.
"use strict";

class Grid {
  constructor(el) {
    this.el = el;
    this.url = el.dataset.url;
    this.dirty = false;
    this.el.innerHTML = '<div class="grid-status">Loading…</div>';
    this.load();
  }

  async load() {
    const r = await fetch(this.url);
    if (!r.ok) { this.el.innerHTML = '<div class="error">Could not load this table.</div>'; return; }
    this.setData(await r.json());
  }

  setData(data) {
    this.data = data;
    this.cols = data.columns;
    this.rows = data.rows.map(r => ({ ...r }));
    this.dirty = false;
    this.render();
  }

  editable() { return this.cols.filter(c => !c.readonly); }

  render() {
    const d = this.data;
    const head = this.cols.map(c =>
      `<th class="${c.type === "str" || c.type === "tags" ? "text" : ""}" title="${esc(c.help || "")}">${esc(c.label)}` +
      (c.unit ? `<span class="unit">${esc(c.unit)}</span>` : "") + "</th>").join("");
    this.el.innerHTML = `
      ${d.note ? `<p class="help">${esc(d.note)}</p>` : ""}
      <div class="grid-bar">
        ${d.can_add ? '<button type="button" class="secondary" data-act="add">Add row</button>' : ""}
        ${d.can_delete ? '<button type="button" class="secondary" data-act="del">Delete selected</button>' : ""}
        <button type="button" data-act="save">Save</button>
        <button type="button" class="secondary" data-act="revert">Undo changes</button>
        <span class="grid-status"></span>
      </div>
      <div class="grid-errors"></div>
      <div class="grid-wrap"><table class="data">
        <thead><tr>${d.can_delete ? "<th></th>" : ""}${head}</tr></thead>
        <tbody></tbody>
      </table></div>`;
    this.tbody = this.el.querySelector("tbody");
    this.rows.forEach((row, i) => this.tbody.appendChild(this.renderRow(row, i)));
    this.el.querySelector('[data-act="save"]').onclick = () => this.save();
    this.el.querySelector('[data-act="revert"]').onclick = () => this.setData(this.data);
    const add = this.el.querySelector('[data-act="add"]');
    if (add) add.onclick = () => this.addRow();
    const del = this.el.querySelector('[data-act="del"]');
    if (del) del.onclick = () => this.deleteSelected();
    this.status(`${this.rows.length} row${this.rows.length === 1 ? "" : "s"}`);
  }

  renderRow(row, i) {
    const tr = document.createElement("tr");
    tr.dataset.index = i;
    if (this.data.can_delete) {
      tr.innerHTML = '<td class="sel"><input type="checkbox" aria-label="Select row"></td>';
    }
    this.cols.forEach((c, ci) => {
      const td = document.createElement("td");
      const v = row[c.name];
      if (c.readonly) {
        td.className = "ro" + (c.type === "str" ? " text" : "");
        td.textContent = this.display(c, v);
      } else if (c.type === "tags") {
        td.className = "tags";
        (c.choices || []).forEach(([val, label]) => {
          const lab = document.createElement("label");
          const cb = document.createElement("input");
          cb.type = "checkbox";
          cb.checked = (v || []).includes(val);
          cb.onchange = () => {
            const set = new Set(row[c.name] || []);
            cb.checked ? set.add(val) : set.delete(val);
            row[c.name] = [...set];
            this.markDirty(td);
          };
          lab.append(cb, " " + label);
          td.appendChild(lab);
        });
      } else {
        let input;
        if (c.type === "choice") {
          input = document.createElement("select");
          input.innerHTML = (c.required ? "" : '<option value="">–</option>') +
            (c.choices || []).map(([val, label]) => `<option value="${esc(String(val))}">${esc(label)}</option>`).join("");
          input.value = v == null ? "" : String(v);
        } else if (c.type === "bool") {
          input = document.createElement("input");
          input.type = "checkbox";
          input.checked = !!v;
          input.style.width = "auto";
        } else {
          input = document.createElement("input");
          input.value = v == null ? "" : v;
          input.inputMode = c.type === "str" ? "text" : "decimal";
          if (c.type === "str") input.className = "text";
        }
        input.dataset.col = ci;
        input.setAttribute("aria-label", c.label);
        input.addEventListener(c.type === "bool" || c.type === "choice" ? "change" : "input", () => {
          row[c.name] = c.type === "bool" ? input.checked : input.value;
          if (c.placeholder_flag) { row[c.placeholder_flag] = false; td.classList.remove("placeholder"); }
          this.markDirty(td);
        });
        input.addEventListener("paste", e => this.paste(e, i, ci));
        input.addEventListener("keydown", e => this.keys(e, i, ci));
        td.appendChild(input);
        if (c.placeholder_flag && row[c.placeholder_flag]) {
          td.classList.add("placeholder");
          td.title = "Placeholder value: replace it with the mill's own figure";
        }
      }
      tr.appendChild(td);
    });
    return tr;
  }

  display(c, v) {
    if (v == null) return "";
    if (c.type === "choice") { const f = (c.choices || []).find(([val]) => val === v); return f ? f[1] : v; }
    if (c.type === "bool") return v ? "yes" : "no";
    return v;
  }

  markDirty(td) {
    td.classList.add("dirty");
    this.dirty = true;
    this.status("Unsaved changes");
  }

  status(t) { const s = this.el.querySelector(".grid-status"); if (s) s.textContent = t; }

  blankRow() {
    const r = { id: null };
    this.cols.forEach(c => {
      if (c.readonly) return;
      if (c.type === "bool") r[c.name] = true;
      else if (c.type === "tags") r[c.name] = [];
      else if (c.type === "choice" && c.required && c.choices && c.choices.length) r[c.name] = c.choices[0][0];
      else r[c.name] = "";
    });
    // carry the last row's values forward where that helps (e.g. log class limits), except numbering
    const last = this.rows[this.rows.length - 1];
    if (last) this.cols.forEach(c => {
      if (c.readonly || c.type === "str") return;
      if (c.type === "int" && /no$/.test(c.name)) r[c.name] = (Number(last[c.name]) || 0) + 1;
      else r[c.name] = Array.isArray(last[c.name]) ? [...last[c.name]] : last[c.name];
    });
    return r;
  }

  addRow(focus = true) {
    const row = this.blankRow();
    this.rows.push(row);
    const tr = this.renderRow(row, this.rows.length - 1);
    tr.querySelectorAll("td").forEach(td => td.classList.add("dirty"));
    this.tbody.appendChild(tr);
    this.dirty = true;
    this.status("Unsaved changes");
    if (focus) { const inp = tr.querySelector("input:not([type=checkbox]), select"); if (inp) inp.focus(); }
    return row;
  }

  deleteSelected() {
    const keep = [];
    let n = 0;
    this.tbody.querySelectorAll("tr").forEach(tr => {
      const cb = tr.querySelector(".sel input");
      if (cb && cb.checked) n++; else keep.push(this.rows[+tr.dataset.index]);
    });
    if (!n) { this.status("Tick the rows to delete first"); return; }
    this.rows = keep;
    this.tbody.innerHTML = "";
    this.rows.forEach((row, i) => this.tbody.appendChild(this.renderRow(row, i)));
    this.dirty = true;
    this.status(`${n} row${n === 1 ? "" : "s"} marked for deletion. Save to confirm.`);
  }

  keys(e, i, ci) {
    if (e.key === "Enter" || e.key === "ArrowDown" || e.key === "ArrowUp") {
      const next = i + (e.key === "ArrowUp" ? -1 : 1);
      const tr = this.tbody.querySelector(`tr[data-index="${next}"]`);
      if (!tr) return;
      const inp = tr.querySelector(`[data-col="${ci}"]`);
      if (inp) { e.preventDefault(); inp.focus(); if (inp.select) inp.select(); }
    }
  }

  // Excel puts tab-separated rows on the clipboard. Fill from the focused cell to the right and down,
  // over the editable columns, adding rows when the paste runs past the end.
  paste(e, i, ci) {
    const text = (e.clipboardData || window.clipboardData).getData("text");
    if (!/[\t\n]/.test(text.trim())) return;          // a single value: let the browser paste it
    e.preventDefault();
    const lines = text.replace(/\r/g, "").replace(/\n$/, "").split("\n").map(l => l.split("\t"));
    const editableIdx = this.cols.map((c, k) => (c.readonly || c.type === "tags") ? -1 : k).filter(k => k >= 0);
    const start = editableIdx.indexOf(ci);
    let added = 0;
    lines.forEach((cells, r) => {
      let rowIndex = i + r;
      if (rowIndex >= this.rows.length) {
        if (!this.data.can_add) return;
        this.addRow(false); added++;
      }
      const row = this.rows[rowIndex];
      cells.forEach((val, k) => {
        const colIndex = editableIdx[start + k];
        if (colIndex === undefined) return;
        const c = this.cols[colIndex];
        val = val.trim();
        if (c.type === "choice") {
          const hit = (c.choices || []).find(([v, label]) => String(v) === val || String(label).toLowerCase() === val.toLowerCase());
          row[c.name] = hit ? hit[0] : val;
        } else if (c.type === "bool") {
          row[c.name] = /^(1|true|yes|y|x|on)$/i.test(val);
        } else {
          row[c.name] = val;
        }
        if (c.placeholder_flag) row[c.placeholder_flag] = false;
      });
    });
    this.tbody.innerHTML = "";
    this.rows.forEach((row, k) => {
      const tr = this.renderRow(row, k);
      if (k >= i && k < i + lines.length) tr.querySelectorAll("td").forEach(td => td.classList.add("dirty"));
      this.tbody.appendChild(tr);
    });
    this.dirty = true;
    this.status(`Pasted ${lines.length} row${lines.length === 1 ? "" : "s"}${added ? ` (${added} new)` : ""}. Save to keep them.`);
  }

  async save() {
    const errBox = this.el.querySelector(".grid-errors");
    errBox.innerHTML = "";
    this.status("Saving…");
    const r = await fetch(this.url, { method: "POST", headers: { "Content-Type": "application/json" },
                                      body: JSON.stringify({ rows: this.rows }) });
    const body = await r.json().catch(() => ({ errors: ["The server did not answer."] }));
    if (!r.ok) {
      const errs = body.errors || [body.detail || "Could not save."];
      errBox.innerHTML = `<div class="error"><strong>Nothing was saved.</strong><ul>${errs.slice(0, 12).map(e => `<li>${esc(e)}</li>`).join("")}</ul>` +
        (errs.length > 12 ? `<p>…and ${errs.length - 12} more.</p>` : "") + "</div>";
      this.status("Not saved");
      return false;
    }
    this.setData(body);
    this.status("Saved");
    this.el.dispatchEvent(new CustomEvent("grid:saved", { bubbles: true }));
    return true;
  }
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

const grids = [];
document.querySelectorAll(".grid[data-url]").forEach(el => grids.push(new Grid(el)));
window.addEventListener("beforeunload", e => {
  if (grids.some(g => g.dirty)) { e.preventDefault(); e.returnValue = ""; }
});

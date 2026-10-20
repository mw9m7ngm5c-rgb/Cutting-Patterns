// Planner page: add and remove rows, keep the "which sizes" grid in step with the size lists, show progress.
(() => {
  const form = document.getElementById("plan-form");
  if (form) {
    const matrix = document.getElementById("cut-matrix");
    const ticked = new Set([...document.querySelectorAll(".cut-initial")].map(i => i.value));
    const fmt = v => String(parseFloat(String(v).replace(",", ".")));
    const sizes = prefix => [...form.querySelectorAll(`input[name="${prefix}_dry"]`)]
      .map(i => i.value.trim()).filter(v => v && !isNaN(parseFloat(v.replace(",", ".")))).map(fmt)
      .filter((v, i, a) => a.indexOf(v) === i).sort((a, b) => a - b);

    const drawMatrix = () => {
      matrix.querySelectorAll("input:checked").forEach(i => ticked.add(i.value));
      matrix.querySelectorAll("input:not(:checked)").forEach(i => ticked.delete(i.value));
      const th = sizes("th"), wd = sizes("wd");
      if (!th.length || !wd.length) {
        matrix.innerHTML = '<p class="help">Enter thicknesses and widths, and a tick box appears for each size.</p>';
        return;
      }
      let html = '<table class="data cut"><thead><tr><th>Thickness ↓ · Width →</th>' +
        wd.map(w => `<th>${w}</th>`).join("") + "</tr></thead><tbody>";
      for (const t of th) {
        html += `<tr><th>${t}</th>` + wd.map(w => {
          const v = `${t}x${w}`;
          return `<td style="text-align:center"><input type="checkbox" name="cut" value="${v}" title="${t} × ${w}" ${ticked.has(v) ? "checked" : ""}></td>`;
        }).join("") + "</tr>";
      }
      matrix.innerHTML = html + "</tbody></table>";
    };

    const renumber = () => form.querySelectorAll("table.classes tbody tr").forEach((tr, i) => {
      tr.querySelector(".no").textContent = i + 1;
    });

    form.addEventListener("click", e => {
      const btn = e.target.closest("button");
      if (!btn) return;
      if (btn.classList.contains("remove")) {
        btn.closest("tr").remove();
        renumber();
        drawMatrix();
      } else if (btn.classList.contains("add-row")) {
        const table = btn.previousElementSibling;
        if (table.classList.contains("classes")) {
          table.tBodies[0].appendChild(document.getElementById("class-row").content.cloneNode(true));
          renumber();
        } else {
          const row = document.getElementById("size-row").content.cloneNode(true);
          const [dry, wet] = row.querySelectorAll("input");
          dry.name = `${table.dataset.prefix}_dry`;
          wet.name = `${table.dataset.prefix}_wet`;
          table.tBodies[0].appendChild(row);
        }
        table.tBodies[0].lastElementChild.querySelector("input").focus();
      }
    });
    form.addEventListener("change", e => {
      if (e.target.matches('input[name$="_dry"]')) drawMatrix();
    });
    drawMatrix();
  }

  const live = document.getElementById("live");
  if (live) {
    const poll = async () => {
      const r = await fetch(`/api/genjobs/${live.dataset.job}`).then(r => r.json());
      document.getElementById("stage").textContent = r.stage || r.status;
      document.getElementById("bar").style.width = (r.total ? 100 * r.progress / r.total : 0) + "%";
      document.getElementById("count").textContent = r.total > 1 ? `${r.progress} / ${r.total}` : "";
      if (["running", "queued"].includes(r.status)) setTimeout(poll, 800);
      else location.reload();
    };
    poll();
  }
})();

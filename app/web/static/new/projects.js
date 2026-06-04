// Projects view. mountProjects(viewEl, sideListEl, deps) renders the project list
// into the sidebar and a workspace into the main view.
import { escapeHtml, getJSON, postJSON } from "./api.js";
import { mountChat } from "./chat.js";

function cell(v) {
  const text = (v && typeof v === "object") ? (v.text ?? "") : (v ?? "");
  const s = String(text);
  const gap = /tidak disebutkan|tidak dilaporkan|tidak ada paper/i.test(s);
  return `<td${gap ? ' class="gap"' : ""}>${escapeHtml(s)}</td>`;
}

function matrixTable(res) {
  const rows = res.rows || [];
  if (!rows.length) return `<p class="gap">Belum ada hasil. Klik "Bangun matrix".</p>`;
  const cols = res.columns || Object.keys(rows[0].fields || {});
  return `<table class="matrix"><thead><tr><th>Source</th><th>Tahun</th><th>Skema</th>` +
    cols.map(c => `<th>${escapeHtml(c)}</th>`).join("") + `</tr></thead><tbody>` +
    rows.map(r => `<tr><td>${escapeHtml(r.source || "")}</td><td>${r.year || ""}</td><td>${escapeHtml(r.schema || "")}</td>` +
      cols.map(c => cell((r.fields || {})[c])).join("") + `</tr>`).join("") +
    `</tbody></table>`;
}

export function mountProjects(viewEl, sideListEl, deps) {
  let current = null;

  async function loadList() {
    const { projects } = await getJSON("/projects");
    sideListEl.innerHTML = projects.map(p =>
      `<div class="hist${current === p.id ? " active" : ""}" data-pid="${p.id}">${escapeHtml(p.name)}</div>`).join("")
      || `<div class="gap" style="padding:6px 11px">Belum ada proyek.</div>`;
    sideListEl.querySelectorAll("[data-pid]").forEach(el =>
      el.addEventListener("click", () => open(Number(el.dataset.pid))));
  }

  async function open(pid) {
    current = pid;
    deps.activateProjectsView();
    const p = await getJSON(`/projects/${pid}`);
    const papers = p.papers || [];
    viewEl.innerHTML = `
      <div class="proj-head">
        <div class="proj-title">${escapeHtml(p.name)}</div>
        <div class="proj-sub">${papers.length} papers</div>
        <div class="tabs">
          <button class="tab active" data-tab="papers" type="button">Papers</button>
          <button class="tab" data-tab="matrix" type="button">Matrix</button>
          <button class="tab" data-tab="chat" type="button">Chat proyek</button>
          <button class="tab" data-tab="export" type="button">Export</button>
        </div>
      </div>
      <div class="panel" data-panel="papers">
        ${papers.map(d => `<div class="paper-item"><span>${escapeHtml(d.title || "(untitled)")} ${d.year ? "· " + d.year : ""}</span></div>`).join("") || `<p class="gap">Belum ada paper.</p>`}
      </div>
      <div class="panel" data-panel="matrix" hidden>
        <button class="row-btn" id="m-build" type="button">Bangun matrix</button>
        <select id="m-view"><option value="matrix">matrix</option><option value="linimasa">linimasa</option><option value="tema">tema</option></select>
        <div id="m-out" style="margin-top:12px"></div>
      </div>
      <div class="panel" data-panel="chat" hidden></div>
      <div class="panel" data-panel="export" hidden>
        <a class="row-btn" id="x-xlsx" target="_blank">⬇ export.xlsx</a>
        <a class="row-btn" id="x-csv" target="_blank">⬇ export.csv</a>
      </div>`;

    const panels = viewEl.querySelectorAll(".panel");
    viewEl.querySelectorAll(".tab").forEach(t =>
      t.addEventListener("click", () => {
        viewEl.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
        t.classList.add("active");
        panels.forEach(pn => { pn.hidden = pn.dataset.panel !== t.dataset.tab; });
      }));

    // chat tab (scoped)
    mountChat(viewEl.querySelector('[data-panel="chat"]'), {
      examples: [],
      showNudge: true,
      endpoint: q => postJSON(`/projects/${pid}/ask`, { question: q, expand: false }),
      onAddPaper: async docId => { await postJSON(`/projects/${pid}/papers`, { doc_ids: [docId] }); open(pid); },
    });

    // matrix tab
    const out = viewEl.querySelector("#m-out");
    const viewSel = viewEl.querySelector("#m-view");
    function exportLinks() {
      viewEl.querySelector("#x-xlsx").href = `/projects/${pid}/matrix/export.xlsx?view=${viewSel.value}`;
      viewEl.querySelector("#x-csv").href = `/projects/${pid}/matrix/export.csv?view=${viewSel.value}`;
    }
    viewEl.querySelector("#m-build").addEventListener("click", async () => {
      out.textContent = "Mengekstrak matriks (grounded)…";
      try { out.innerHTML = matrixTable(await postJSON(`/projects/${pid}/matrix`, { view: viewSel.value })); }
      catch (e) { out.textContent = "Error: " + e.message; }
      exportLinks();
    });
    viewSel.addEventListener("change", exportLinks);
    exportLinks();
  }

  async function createProject(name) {
    const p = await postJSON("/projects", { name });
    await loadList();
    open(p.id);
  }

  return { loadList, open, createProject };
}

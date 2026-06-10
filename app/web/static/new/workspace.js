// Ruang kerja satu naskah: tab Tanya / Paper / Draft / Matriks.
import { escapeHtml, getJSON, postJSON, friendlyError } from "./api.js";
import { mountChat } from "./chat.js";
import { mountDraft } from "./draft.js";
import { mountPapers } from "./papers.js";

function cell(v) {
  const text = (v && typeof v === "object") ? (v.text ?? "") : (v ?? "");
  const s = String(text);
  const gap = /tidak disebutkan|tidak dilaporkan|tidak ada paper/i.test(s);
  return `<td${gap ? ' class="gap"' : ""}>${escapeHtml(s)}</td>`;
}

function matrixTable(res) {
  const rows = res.rows || [];
  if (!rows.length) return `<p class="gap">Belum ada hasil. Klik "Bangun matriks".</p>`;
  const cols = res.columns || Object.keys(rows[0].fields || {});
  return `<table class="matrix"><thead><tr><th>Sumber</th><th>Tahun</th><th>Skema</th>` +
    cols.map(c => `<th>${escapeHtml(c)}</th>`).join("") + `</tr></thead><tbody>` +
    rows.map(r => `<tr><td>${escapeHtml(r.source || "")}</td><td>${r.year || ""}</td><td>${escapeHtml(r.schema || "")}</td>` +
      cols.map(c => cell((r.fields || {})[c])).join("") + `</tr>`).join("") +
    `</tbody></table>`;
}

export async function mountWorkspace(screen, pid, deps) { // deps: {history, mindmaps, onBack}
  let p;
  try {
    p = await getJSON(`/projects/${pid}`);
  } catch (e) {
    screen.innerHTML = `<p style="padding:24px">${escapeHtml(friendlyError(e))}</p>`;
    return;
  }
  let paperIds = (p.papers || []).map(d => d.id);

  screen.innerHTML = `
    <div class="ws">
      <div class="ws-head">
        <button class="ws-back" id="ws-back" type="button">← Naskah Saya</button>
        <div class="ws-title">${escapeHtml(p.name)}</div>
        <div class="ws-tabs">
          <button class="tab active" data-tab="tanya" type="button">💬 Tanya</button>
          <button class="tab" data-tab="paper" type="button">📄 Paper (<span id="ws-count">${paperIds.length}</span>)</button>
          <button class="tab" data-tab="draft" type="button">📝 Draft</button>
          <button class="tab" data-tab="matriks" type="button">📊 Matriks</button>
        </div>
      </div>
      <div class="ws-panel" data-panel="tanya"></div>
      <div class="ws-panel" data-panel="paper" hidden></div>
      <div class="ws-panel" data-panel="draft" hidden></div>
      <div class="ws-panel" data-panel="matriks" hidden></div>
    </div>`;

  screen.querySelector("#ws-back").addEventListener("click", deps.onBack);
  const panels = screen.querySelectorAll(".ws-panel");
  screen.querySelectorAll(".ws-tabs .tab").forEach(t =>
    t.addEventListener("click", () => {
      screen.querySelectorAll(".ws-tabs .tab").forEach(x => x.classList.remove("active"));
      t.classList.add("active");
      panels.forEach(pn => { pn.hidden = pn.dataset.panel !== t.dataset.tab; });
    }));

  // ----- Tanya (default): per-naskah history sidebar + scoped chat -----
  const tanyaPanel = screen.querySelector('[data-panel="tanya"]');
  tanyaPanel.innerHTML = `
    <div class="tanya">
      <aside class="tanya-side">
        <button class="side-btn" id="t-new" type="button">+ Percakapan baru</button>
        <div class="side-label">Riwayat</div>
        <div id="t-recent"></div>
      </aside>
      <div class="tanya-main" id="t-chat"></div>
    </div>`;
  const scope = String(pid);
  const chatEl = tanyaPanel.querySelector("#t-chat");
  const recentEl = tanyaPanel.querySelector("#t-recent");
  let convId = null;

  function renderRecent() {
    const items = deps.history.list(scope);
    recentEl.innerHTML = items.map(c =>
      `<div class="hist${c.id === convId ? " active" : ""}" data-cid="${c.id}">` +
      `<span>${escapeHtml(c.title || "(tanpa judul)")}</span>` +
      `<button class="del" data-del="${c.id}" type="button" title="Hapus">✕</button></div>`).join("")
      || `<div class="gap" style="padding:6px 11px">Belum ada percakapan.</div>`;
    recentEl.querySelectorAll("[data-cid]").forEach(el =>
      el.addEventListener("click", e => {
        if (e.target.matches("[data-del]")) return;
        openConv(el.dataset.cid);
      }));
    recentEl.querySelectorAll("[data-del]").forEach(b =>
      b.addEventListener("click", () => {
        deps.history.remove(b.dataset.del);
        if (convId === b.dataset.del) newConv(); else renderRecent();
      }));
  }
  function persist(messages) {
    if (!messages.length) return;
    deps.history.save({
      id: convId, title: messages[0].q.slice(0, 48), scope,
      messages, updatedAt: Date.now(),
    });
    renderRecent();
  }
  function chatOpts(initial) {
    return {
      examples: [],
      expandToggle: true,
      showNudge: true,
      placeholder: "Tanya tentang paper di naskah ini…",
      emptyText: paperIds.length
        ? "Tanya apa saja tentang paper di naskah ini. Jawaban disertai sumber yang bisa diklik ke halaman PDF."
        : "Tambahkan paper dulu di tab Paper, lalu tanya apa saja di sini.",
      initial,
      endpoint: (q, o) => postJSON(`/projects/${pid}/ask`, { question: q, expand: !!(o && o.expand) }),
      onExchange: persist,
      onAddPaper: async id => { await postJSON(`/projects/${pid}/papers`, { doc_ids: [id] }); papersTab.refresh(); },
    };
  }
  function newConv() {
    convId = "c" + Date.now();
    mountChat(chatEl, chatOpts());
    renderRecent();
  }
  function openConv(id) {
    const c = deps.history.get(id);
    if (!c) return;
    convId = id;
    mountChat(chatEl, chatOpts(c.messages));
    renderRecent();
  }
  tanyaPanel.querySelector("#t-new").addEventListener("click", newConv);

  // ----- Paper -----
  const papersTab = mountPapers(screen.querySelector('[data-panel="paper"]'), pid, {
    mindmaps: deps.mindmaps,
    onChanged: papers => {
      paperIds = papers.map(d => d.id);
      screen.querySelector("#ws-count").textContent = paperIds.length;
    },
  });

  // ----- Draft (scoped to current naskah papers) -----
  mountDraft(screen.querySelector('[data-panel="draft"]'), { getDocIds: () => paperIds });

  // ----- Matriks (ported from old projects.js) -----
  const mx = screen.querySelector('[data-panel="matriks"]');
  mx.innerHTML = `
    <div class="paper-actions">
      <button class="df-btn" id="m-build" type="button">Bangun matriks</button>
      <select id="m-view"><option value="matrix">matriks</option><option value="linimasa">linimasa</option><option value="tema">tema</option></select>
      <a class="df-btn ghost" id="x-xlsx" target="_blank">⬇ Excel</a>
      <a class="df-btn ghost" id="x-csv" target="_blank">⬇ CSV</a>
    </div>
    <div id="m-out" style="padding:12px 20px"></div>`;
  const out = mx.querySelector("#m-out");
  const viewSel = mx.querySelector("#m-view");
  function exportLinks() {
    mx.querySelector("#x-xlsx").href = `/projects/${pid}/matrix/export.xlsx?view=${viewSel.value}`;
    mx.querySelector("#x-csv").href = `/projects/${pid}/matrix/export.csv?view=${viewSel.value}`;
  }
  mx.querySelector("#m-build").addEventListener("click", async () => {
    out.textContent = "Mengekstrak matriks dari paper naskah…";
    try { out.innerHTML = matrixTable(await postJSON(`/projects/${pid}/matrix`, { view: viewSel.value })); }
    catch (e) { out.textContent = friendlyError(e); }
    exportLinks();
  });
  viewSel.addEventListener("change", exportLinks);
  exportLinks();
  // Show the persisted matrix on open (no re-extraction).
  getJSON(`/projects/${pid}/matrix?view=matrix`).then(res => {
    if ((res.rows || []).length) out.innerHTML = matrixTable(res);
  }).catch(() => {});

  newConv();
}

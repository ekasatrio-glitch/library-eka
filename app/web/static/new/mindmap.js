// Mindmap view: generate, autosave to a localStorage store, reopen + delete saved
// maps, and scope retrieval to selected papers via a /library doc picker.
import { escapeHtml, getJSON, postJSON } from "./api.js";

export function mountMindmap(viewEl, opts = {}) {
  const store = opts.store;            // makeMindmapStore(localStorage)
  const recentEl = opts.recentEl;      // sidebar list container (#mindmap-recent)

  viewEl.innerHTML = `
    <div class="scroll"><div class="inner">
      <form id="mm-form" class="df-form">
        <textarea id="mm-topic" rows="2" placeholder="Topik mindmap…"></textarea>
        <div class="df-row">
          <input id="mm-breadth" type="number" min="2" max="8" value="4" title="Jumlah subtopik" />
          <button class="df-btn ghost" id="mm-source" type="button">Sumber: semua korpus</button>
          <button class="df-btn" id="mm-submit" type="button">Buat mindmap</button>
        </div>
      </form>
      <pre id="mm-md" class="md"></pre>
      <div id="mm-svg" class="markmap-wrap"></div>
    </div></div>`;

  const topic = viewEl.querySelector("#mm-topic");
  const breadth = viewEl.querySelector("#mm-breadth");
  const md = viewEl.querySelector("#mm-md");
  const svg = viewEl.querySelector("#mm-svg");
  const sourceBtn = viewEl.querySelector("#mm-source");

  let selectedDocs = [];   // [] = whole corpus
  let libraryCache = null;  // cached /library items

  function sourceLabel() {
    return selectedDocs.length ? `${selectedDocs.length} paper` : "semua korpus";
  }
  function refreshSourceBtn() {
    sourceBtn.textContent = "Sumber: " + sourceLabel();
  }

  // ---- explicit markmap render (fills container; falls back to autoloader) ----
  function renderMindmap(host, markdown) {
    host.innerHTML = "";
    const mk = window.markmap;
    if (mk && mk.Markmap && mk.Transformer) {
      const svgEl = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svgEl.classList.add("markmap-svg");
      host.appendChild(svgEl);
      const { root } = new mk.Transformer().transform(markdown);
      const inst = mk.Markmap.create(svgEl, undefined, root);
      requestAnimationFrame(() => inst.fit());
      return;
    }
    const div = document.createElement("div");
    div.className = "markmap";
    const tpl = document.createElement("script");
    tpl.type = "text/template";
    tpl.textContent = markdown;
    div.appendChild(tpl);
    host.appendChild(div);
    if (mk && mk.autoLoader) mk.autoLoader.renderAll();
  }

  // ---- saved-list (sidebar) ----
  function renderRecent() {
    if (!recentEl || !store) return;
    const items = store.list();
    if (!items.length) {
      recentEl.innerHTML = `<div class="side-empty">Belum ada mindmap.</div>`;
      return;
    }
    recentEl.innerHTML = items.map(m =>
      `<div class="recent-row"><button class="recent-open" data-mid="${m.id}" type="button">${escapeHtml(m.topic)}</button>` +
      `<button class="recent-del" data-del="${m.id}" title="Hapus" type="button">🗑</button></div>`).join("");
    recentEl.querySelectorAll("[data-mid]").forEach(b =>
      b.addEventListener("click", () => openSaved(b.dataset.mid)));
    recentEl.querySelectorAll("[data-del]").forEach(b =>
      b.addEventListener("click", () => { store.remove(b.dataset.del); renderRecent(); }));
  }

  function openSaved(id) {
    const m = store && store.get(id);
    if (!m) return;
    topic.value = m.topic || "";
    breadth.value = m.breadth || 4;
    selectedDocs = Array.isArray(m.docIds) ? m.docIds.slice() : [];
    refreshSourceBtn();
    md.textContent = m.markdown || "";
    if (m.markdown) renderMindmap(svg, m.markdown); else svg.innerHTML = "";
  }

  // ---- doc picker modal ----
  function openPicker() {
    const overlay = document.createElement("div");
    overlay.className = "mm-modal";
    overlay.innerHTML = `
      <div class="mm-modal-box">
        <div class="mm-modal-head">
          <strong>Pilih paper sumber</strong>
          <input id="mm-pick-search" placeholder="Cari judul…" />
        </div>
        <div id="mm-pick-list" class="mm-pick-list">Memuat…</div>
        <div class="mm-modal-foot">
          <button id="mm-pick-all" type="button" class="df-btn ghost">Pilih semua</button>
          <button id="mm-pick-none" type="button" class="df-btn ghost">Kosongkan</button>
          <span class="grow"></span>
          <button id="mm-pick-cancel" type="button" class="df-btn ghost">Batal</button>
          <button id="mm-pick-ok" type="button" class="df-btn">Terapkan</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const listEl = overlay.querySelector("#mm-pick-list");
    const searchEl = overlay.querySelector("#mm-pick-search");
    const chosen = new Set(selectedDocs);

    function rowHtml(it) {
      const yr = it.year ? ` (${it.year})` : "";
      return `<label class="mm-pick-row"><input type="checkbox" data-id="${it.id}"${chosen.has(it.id) ? " checked" : ""}/>` +
        `<span>${escapeHtml(it.title || "(untitled)")}${escapeHtml(yr)}</span></label>`;
    }
    function paint(items) {
      listEl.innerHTML = items.map(rowHtml).join("") || `<div class="side-empty">Tidak ada paper.</div>`;
      listEl.querySelectorAll("input[data-id]").forEach(cb =>
        cb.addEventListener("change", () => {
          const id = Number(cb.dataset.id);
          if (cb.checked) chosen.add(id); else chosen.delete(id);
        }));
    }
    function close() { overlay.remove(); }

    async function load() {
      try {
        if (!libraryCache) libraryCache = (await getJSON("/library")).items || [];
        paint(libraryCache);
      } catch (err) {
        listEl.innerHTML = `<div class="side-empty">Gagal memuat daftar paper.</div>`;
      }
    }
    load();

    searchEl.addEventListener("input", () => {
      const q = searchEl.value.toLowerCase();
      paint((libraryCache || []).filter(it => (it.title || "").toLowerCase().includes(q)));
    });
    overlay.querySelector("#mm-pick-all").addEventListener("click", () => {
      (libraryCache || []).forEach(it => chosen.add(it.id));
      paint(libraryCache || []);
    });
    overlay.querySelector("#mm-pick-none").addEventListener("click", () => {
      chosen.clear(); paint(libraryCache || []);
    });
    overlay.querySelector("#mm-pick-cancel").addEventListener("click", close);
    overlay.addEventListener("click", e => { if (e.target === overlay) close(); });
    overlay.querySelector("#mm-pick-ok").addEventListener("click", () => {
      selectedDocs = [...chosen];
      refreshSourceBtn();
      close();
    });
  }

  // ---- generate ----
  async function submit() {
    const t = topic.value.trim();
    if (!t) return;
    md.textContent = "Menyusun mindmap…";
    svg.innerHTML = "";
    try {
      const body = { topic: t, breadth: Number(breadth.value) || 4 };
      if (selectedDocs.length) body.doc_ids = selectedDocs;
      const res = await postJSON("/mindmap", body);
      md.textContent = res.markdown;
      renderMindmap(svg, res.markdown);
      if (store) {
        const now = Date.now();
        store.save({
          id: "m" + now,
          topic: t,
          breadth: Number(breadth.value) || 4,
          markdown: res.markdown,
          citations: res.citations || [],
          docIds: selectedDocs.slice(),
          docLabel: sourceLabel(),
          updatedAt: now,
        });
        renderRecent();
      }
    } catch (err) {
      md.textContent = "Error: " + err.message;
    }
  }

  viewEl.querySelector("#mm-submit").addEventListener("click", submit);
  sourceBtn.addEventListener("click", openPicker);
  refreshSourceBtn();
  renderRecent();
}

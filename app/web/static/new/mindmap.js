// Peta-konsep modal: generate a markmap from given papers; autosave + reopen + delete.
import { escapeHtml, postJSON, friendlyError } from "./api.js";

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

export function openMindmapModal({ docIds = [], store = null, scopeLabel = "" } = {}) {
  const overlay = document.createElement("div");
  overlay.className = "mm-modal";
  overlay.innerHTML = `
    <div class="mm-modal-box mm-wide">
      <div class="mm-modal-head">
        <strong>🗺️ Peta konsep</strong>
        <span class="gap">${escapeHtml(scopeLabel || (docIds.length + " paper"))}</span>
        <span class="grow"></span>
        <button id="mm-close" type="button" class="df-btn ghost">Tutup</button>
      </div>
      <form class="df-form" id="mm-form">
        <textarea id="mm-topic" rows="2" placeholder="Topik peta konsep…"></textarea>
        <div class="df-row">
          <input id="mm-breadth" type="number" min="2" max="8" value="4" title="Jumlah cabang" />
          <button class="df-btn" id="mm-submit" type="button">Buat peta</button>
        </div>
      </form>
      <div id="mm-saved" class="mm-pick-list"></div>
      <div id="mm-svg" class="markmap-wrap"></div>
    </div>`;
  document.body.appendChild(overlay);
  const topic = overlay.querySelector("#mm-topic");
  const breadth = overlay.querySelector("#mm-breadth");
  const svg = overlay.querySelector("#mm-svg");
  const savedEl = overlay.querySelector("#mm-saved");
  const close = () => overlay.remove();
  overlay.querySelector("#mm-close").addEventListener("click", close);
  overlay.addEventListener("click", e => { if (e.target === overlay) close(); });

  function renderSaved() {
    if (!store) { savedEl.hidden = true; return; }
    const items = store.list();
    savedEl.innerHTML = items.length
      ? items.map(m =>
          `<div class="recent-row"><button class="recent-open" data-mid="${m.id}" type="button">${escapeHtml(m.topic)}</button>` +
          `<button class="recent-del" data-del="${m.id}" title="Hapus" type="button">🗑</button></div>`).join("")
      : `<div class="side-empty">Belum ada peta tersimpan.</div>`;
    savedEl.querySelectorAll("[data-mid]").forEach(b =>
      b.addEventListener("click", () => {
        const m = store.get(b.dataset.mid);
        if (!m) return;
        topic.value = m.topic || "";
        breadth.value = m.breadth || 4;
        if (m.markdown) renderMindmap(svg, m.markdown);
      }));
    savedEl.querySelectorAll("[data-del]").forEach(b =>
      b.addEventListener("click", () => { store.remove(b.dataset.del); renderSaved(); }));
  }

  overlay.querySelector("#mm-submit").addEventListener("click", async () => {
    const t = topic.value.trim();
    if (!t) return;
    svg.innerHTML = "Menyusun peta…";
    try {
      const body = { topic: t, breadth: Number(breadth.value) || 4 };
      if (docIds.length) body.doc_ids = docIds;
      const res = await postJSON("/mindmap", body);
      renderMindmap(svg, res.markdown);
      if (store) {
        const now = Date.now();
        store.save({
          id: "m" + now, topic: t, breadth: Number(breadth.value) || 4,
          markdown: res.markdown, citations: res.citations || [],
          docIds: docIds.slice(), docLabel: scopeLabel, updatedAt: now,
        });
        renderSaved();
      }
    } catch (err) {
      svg.textContent = friendlyError(err);
    }
  });

  renderSaved();
}

// Library doc-picker modal. Resolves with the chosen doc_id array, or null on cancel.
import { escapeHtml, getJSON } from "./api.js";

let libraryCache = null;

export function openLibraryPicker({ preselected = [], title = "Pilih paper" } = {}) {
  return new Promise(resolve => {
    const overlay = document.createElement("div");
    overlay.className = "mm-modal";
    overlay.innerHTML = `
      <div class="mm-modal-box">
        <div class="mm-modal-head">
          <strong>${escapeHtml(title)}</strong>
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
    const chosen = new Set(preselected);

    function rowHtml(it) {
      const yr = it.year ? ` (${it.year})` : "";
      return `<label class="mm-pick-row"><input type="checkbox" data-id="${it.id}"${chosen.has(it.id) ? " checked" : ""}/>` +
        `<span>${escapeHtml(it.title || "(tanpa judul)")}${escapeHtml(yr)}</span></label>`;
    }
    function paint(items) {
      listEl.innerHTML = items.map(rowHtml).join("") || `<div class="side-empty">Tidak ada paper.</div>`;
      listEl.querySelectorAll("input[data-id]").forEach(cb =>
        cb.addEventListener("change", () => {
          const id = Number(cb.dataset.id);
          if (cb.checked) chosen.add(id); else chosen.delete(id);
        }));
    }
    function close(result) { overlay.remove(); resolve(result); }

    (async () => {
      try {
        if (!libraryCache) libraryCache = (await getJSON("/library")).items || [];
        paint(libraryCache);
      } catch {
        listEl.innerHTML = `<div class="side-empty">Gagal memuat daftar paper.</div>`;
      }
    })();

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
    overlay.querySelector("#mm-pick-cancel").addEventListener("click", () => close(null));
    overlay.addEventListener("click", e => { if (e.target === overlay) close(null); });
    overlay.querySelector("#mm-pick-ok").addEventListener("click", () => close([...chosen]));
  });
}

// ⚙ mini-panel: pick the active generation model (GET/POST /admin/llm).
// Deliberately tucked away — the primary user never needs it.
import { escapeHtml, getJSON, postJSON, friendlyError } from "./api.js";

export function wireAdminGear(btn) {
  if (!btn) return;
  btn.addEventListener("click", async () => {
    const overlay = document.createElement("div");
    overlay.className = "mm-modal";
    overlay.innerHTML = `
      <div class="mm-modal-box">
        <div class="mm-modal-head"><strong>Model penjawab</strong></div>
        <div id="adm-list" class="mm-pick-list">Memuat…</div>
        <div class="mm-modal-foot">
          <span class="grow"></span>
          <button id="adm-cancel" type="button" class="df-btn ghost">Batal</button>
          <button id="adm-save" type="button" class="df-btn">Simpan</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const list = overlay.querySelector("#adm-list");
    const close = () => overlay.remove();
    overlay.addEventListener("click", e => { if (e.target === overlay) close(); });
    overlay.querySelector("#adm-cancel").addEventListener("click", close);
    try {
      const { choices, active } = await getJSON("/admin/llm");
      list.innerHTML = choices.map(c =>
        `<label class="mm-pick-row"><input type="radio" name="llm" value="${escapeHtml(c)}"${c === active ? " checked" : ""}/>` +
        `<span>${escapeHtml(c)}</span></label>`).join("");
    } catch (e) {
      list.textContent = friendlyError(e);
    }
    overlay.querySelector("#adm-save").addEventListener("click", async () => {
      const sel = overlay.querySelector('input[name="llm"]:checked');
      try {
        if (sel) await postJSON("/admin/llm", { choice: sel.value });
        close();
      } catch (e) {
        list.textContent = friendlyError(e);
      }
    });
  });
}

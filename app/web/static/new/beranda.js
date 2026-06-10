// Beranda: naskah card list + create. Calm grid style, no suggestion cards.
import { escapeHtml, getJSON, postJSON, friendlyError } from "./api.js";

export async function mountBeranda(screen, { onOpen }) {
  screen.innerHTML = `
    <div class="beranda">
      <div class="beranda-head">
        <h1>Naskah Saya</h1>
        <button class="df-btn" id="b-new" type="button">+ Naskah baru</button>
      </div>
      <div class="naskah-cards" id="b-cards">Memuat…</div>
    </div>`;
  screen.querySelector("#b-new").addEventListener("click", async () => {
    const name = prompt("Nama naskah baru:");
    if (!name || !name.trim()) return;
    const p = await postJSON("/projects", { name: name.trim() });
    onOpen(p.id);
  });
  const cards = screen.querySelector("#b-cards");
  try {
    const { projects } = await getJSON("/projects");
    cards.innerHTML = projects.map(p =>
      `<button class="naskah-card" data-pid="${p.id}" type="button">` +
      `<b>${escapeHtml(p.name)}</b>` +
      `<small>${escapeHtml(p.description || "")}</small></button>`).join("")
      || `<p class="gap">Belum ada naskah. Mulai dengan "+ Naskah baru".</p>`;
    cards.querySelectorAll("[data-pid]").forEach(el =>
      el.addEventListener("click", () => onOpen(Number(el.dataset.pid))));
  } catch (e) {
    cards.textContent = friendlyError(e);
  }
}

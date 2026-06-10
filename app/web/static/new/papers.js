// Paper tab: list with checkboxes, upload with progress, import from library,
// peta-konsep launcher. onChanged() tells the workspace to refresh counts.
import { escapeHtml, getJSON, postJSON, friendlyError } from "./api.js";
import { openLibraryPicker } from "./picker.js";
import { openMindmapModal } from "./mindmap.js";
import { postFile, pollJob, STAGE_LABELS } from "./upload.js";

export function mountPapers(panel, pid, deps = {}) { // deps: {mindmaps, onChanged}
  let papers = [];
  const selected = new Set();

  async function refresh() {
    const res = await getJSON(`/projects/${pid}/papers`);
    papers = res.papers || [];
    selected.clear();
    render();
    if (deps.onChanged) deps.onChanged(papers);
  }

  function render() {
    panel.innerHTML = `
      <div class="paper-actions">
        <button class="df-btn" id="pp-upload" type="button">⬆ Unggah PDF</button>
        <input id="pp-file" type="file" accept="application/pdf" multiple hidden>
        <button class="df-btn ghost" id="pp-import" type="button">+ Dari Semua PDF</button>
        <button class="df-btn ghost" id="pp-map" type="button">🗺️ Peta konsep</button>
      </div>
      <div class="dropzone" id="pp-drop">Seret PDF ke sini untuk menambahkan ke naskah</div>
      <div id="pp-jobs"></div>
      <div class="paper-rows" id="pp-list">${papers.map(d =>
        `<div class="paper-row"><input type="checkbox" data-sel="${d.id}">` +
        `<span>${escapeHtml(d.title || "(tanpa judul)")}${d.year ? " · " + d.year : ""}</span>` +
        `<span class="grow"></span>` +
        `<button class="recent-del" data-rm="${d.id}" title="Keluarkan dari naskah" type="button">✕</button></div>`).join("")
        || `<p class="gap">Belum ada paper. Unggah PDF atau ambil dari Semua PDF.</p>`}</div>`;

    panel.querySelectorAll("[data-sel]").forEach(cb =>
      cb.addEventListener("change", () => {
        const id = Number(cb.dataset.sel);
        if (cb.checked) selected.add(id); else selected.delete(id);
      }));
    panel.querySelectorAll("[data-rm]").forEach(b =>
      b.addEventListener("click", async () => {
        await fetch(`/projects/${pid}/papers/${b.dataset.rm}`, { method: "DELETE" });
        refresh();
      }));

    const fileInput = panel.querySelector("#pp-file");
    panel.querySelector("#pp-upload").addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => uploadAll([...fileInput.files]));

    const drop = panel.querySelector("#pp-drop");
    drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("drag"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
    drop.addEventListener("drop", e => {
      e.preventDefault();
      drop.classList.remove("drag");
      uploadAll([...e.dataTransfer.files].filter(f => /\.pdf$/i.test(f.name)));
    });

    panel.querySelector("#pp-import").addEventListener("click", async () => {
      const ids = await openLibraryPicker({
        preselected: papers.map(p => p.id),
        title: "Ambil paper dari Semua PDF",
      });
      if (!ids) return;
      const add = ids.filter(id => !papers.some(p => p.id === id));
      if (add.length) await postJSON(`/projects/${pid}/papers`, { doc_ids: add });
      refresh();
    });

    panel.querySelector("#pp-map").addEventListener("click", () => {
      const ids = selected.size ? [...selected] : papers.map(p => p.id);
      openMindmapModal({
        docIds: ids,
        store: deps.mindmaps,
        scopeLabel: selected.size ? `${selected.size} paper terpilih` : "semua paper naskah",
      });
    });
  }

  async function uploadAll(files) {
    const jobsEl = panel.querySelector("#pp-jobs");
    await Promise.all(files.map(async file => {
      const row = document.createElement("div");
      row.className = "upload-job";
      row.innerHTML = `<span class="uj-name">${escapeHtml(file.name)}</span>` +
        `<div class="upload-bar"><i></i></div><span class="uj-stage">mengunggah…</span>`;
      jobsEl.appendChild(row);
      const bar = row.querySelector("i");
      const stageEl = row.querySelector(".uj-stage");
      try {
        const { job_id } = await postFile(`/projects/${pid}/upload`, file);
        const job = await pollJob(job_id, j => {
          stageEl.textContent = STAGE_LABELS[j.stage] || j.stage;
          bar.style.width = j.total ? Math.round(100 * j.done / j.total) + "%" : "10%";
        });
        if (job.error) {
          stageEl.textContent = "gagal: " + job.error;
        } else {
          bar.style.width = "100%";
          stageEl.textContent = job.already
            ? "sudah ada di perpustakaan — ditautkan ke naskah ini"
            : "selesai";
        }
      } catch (err) {
        stageEl.textContent = friendlyError(err);
      }
    }));
    refresh();
  }

  refresh();
  return { refresh };
}

document.querySelectorAll(".top nav a").forEach((a) => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    document.querySelectorAll(".top nav a").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    a.classList.add("active");
    document.getElementById("tab-" + a.dataset.tab).classList.add("active");
  });
});

function citationLinks(cits) {
  return cits.map(c => {
    const href = `/viewer?doc=${c.doc_id}#page=${c.page_start}`;
    const pg = c.page_start === c.page_end ? `p.${c.page_start}` : `p.${c.page_start}-${c.page_end}`;
    return `<li><a href="${href}" target="_blank">[${c.n}] ${escapeHtml(c.title)} (${pg})</a></li>`;
  }).join("");
}

function citationBlock(citations) {
  if (!citations || !citations.length) return "";
  const cited = citations.filter(c => c.cited !== false);
  const uncited = citations.filter(c => c.cited === false);
  // No split needed (old payloads, or LLM cited everything): classic single block.
  if (!uncited.length) {
    return `<details class="cites-toggle"><summary>📎 Sumber (${citations.length})</summary>` +
      `<ol class="cites">${citationLinks(citations)}</ol></details>`;
  }
  return `<details class="cites-toggle" open><summary>📎 Sumber dikutip (${cited.length})</summary>` +
    `<ol class="cites">${citationLinks(cited)}</ol></details>` +
    `<details class="cites-toggle cites-uncited"><summary>Diambil, tidak dikutip (${uncited.length})</summary>` +
    `<ol class="cites">${citationLinks(uncited)}</ol></details>`;
}

function appendChat(threadId, question, answer, citations, nudgeHtml) {
  const thread = document.getElementById(threadId);
  const u = document.createElement("div");
  u.className = "chat-msg user";
  u.textContent = question;
  const b = document.createElement("div");
  b.className = "chat-msg bot";
  b.innerHTML = escapeHtml(answer).replace(/\n/g, "<br>") +
    citationBlock(citations) +
    (nudgeHtml ? `<div class="nudge">${nudgeHtml}</div>` : "");
  thread.appendChild(u);
  thread.appendChild(b);
  thread.scrollTop = thread.scrollHeight;
  return b;
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

async function postJSON(url, body) {
  const r = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  if (!r.ok) {
    const detail = await r.text();
    throw new Error(`${r.status}: ${detail}`);
  }
  return r.json();
}

function formToBody(form) {
  const data = {};
  new FormData(form).forEach((v, k) => {
    if (v === "" || v == null) return;
    if (form.elements[k].type === "number") data[k] = Number(v);
    else data[k] = v;
  });
  return data;
}

function enterToSend(form) {
  const ta = form.querySelector("textarea");
  if (!ta) return;
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
}

enterToSend(document.getElementById("ask-form"));
enterToSend(document.getElementById("proj-ask-form"));
enterToSend(document.getElementById("mindmap-form"));


document.getElementById("ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = formToBody(e.target);
  const ta = e.target.elements.question;
  const q = ta.value;
  const pending = appendChat("ask-chat-thread", q, "…", [], "");
  ta.value = "";
  try {
    const res = await postJSON("/ask", body);
    pending.innerHTML = escapeHtml(res.answer).replace(/\n/g, "<br>") +
      citationBlock(res.citations);
  } catch (err) { pending.textContent = "Error: " + err.message; }
});

document.getElementById("draft-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const para = document.getElementById("draft-paragraph");
  const refsEl = document.getElementById("draft-refs");
  para.textContent = "Menulis draft...";
  refsEl.innerHTML = "";
  try {
    const res = await postJSON("/draft", formToBody(e.target));
    para.textContent = res.paragraph;
    const refs = res.references || [];
    const cits = res.citations || [];
    // references[i] pairs with citations[i] (same retrieval order).
    const cited = [], uncited = [];
    refs.forEach((r, i) => {
      ((cits[i] && cits[i].cited === false) ? uncited : cited).push(r);
    });
    let html = `<ol class="citations">${cited.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ol>`;
    if (uncited.length) {
      html += `<details class="cites-toggle cites-uncited"><summary>Diambil, tidak dikutip (${uncited.length})</summary>` +
        `<ol class="citations">${uncited.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ol></details>`;
    }
    refsEl.innerHTML = html;
  } catch (err) { para.textContent = "Error: " + err.message; }
});

document.getElementById("mindmap-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const md = document.getElementById("mindmap-markdown");
  const svgDiv = document.getElementById("mindmap-svg");
  md.textContent = "Menyusun mindmap...";
  svgDiv.innerHTML = "";
  try {
    const res = await postJSON("/mindmap", formToBody(e.target));
    md.textContent = res.markdown;
    const div = document.createElement("div");
    div.className = "markmap";
    const script = document.createElement("script");
    script.type = "text/template";
    script.textContent = res.markdown;
    div.appendChild(script);
    svgDiv.appendChild(div);
    if (window.markmap && window.markmap.autoLoader) window.markmap.autoLoader.renderAll();
  } catch (err) { md.textContent = "Error: " + err.message; }
});

document.getElementById("lib-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = formToBody(e.target);
  const params = new URLSearchParams(body).toString();
  const r = await fetch("/library?" + params);
  const data = await r.json();
  const tbody = document.querySelector("#lib-table tbody");
  tbody.innerHTML = (data.items || []).map(it => {
    const view = `<a href="/viewer?doc=${it.id}" target="_blank">buka</a>`;
    return `<tr>
      <td>${escapeHtml(it.title)}</td>
      <td>${escapeHtml(it.authors || "")}</td>
      <td>${it.year || ""}</td>
      <td>${escapeHtml(it.folder || "")}</td>
      <td>${view}</td>
    </tr>`;
  }).join("");
});

document.querySelector("#lib-form").dispatchEvent(new Event("submit"));

// ---------- Projects (Phase 11) + Matrix (Phase 12-13) ----------
const PROJ = { current: null };

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}
async function delJSON(url) {
  const r = await fetch(url, { method: "DELETE" });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

async function loadProjects() {
  const data = await getJSON("/projects");
  const grid = document.getElementById("proj-grid");
  grid.innerHTML = (data.projects || []).map(p =>
    `<div class="proj-card" data-pid="${p.id}">
       <h4>${escapeHtml(p.name)}</h4>
       <div class="muted">${p.n_papers} paper</div>
     </div>`
  ).join("");
  grid.querySelectorAll(".proj-card[data-pid]").forEach(card =>
    card.addEventListener("click", () => openProject(Number(card.dataset.pid)))
  );
}

function showProjectsHome() {
  PROJ.current = null;
  document.getElementById("proj-workspace").hidden = true;
  document.getElementById("proj-home").hidden = false;
  loadProjects();
}

function setSubtab(name) {
  document.querySelectorAll("#proj-subnav .subnav-btn").forEach(b =>
    b.classList.toggle("active", b.dataset.subtab === name));
  document.querySelectorAll("#proj-workspace .subpanel").forEach(p => {
    const on = p.dataset.panel === name;
    p.classList.toggle("active", on);
    p.hidden = !on;
  });
}

async function openProject(pid) {
  PROJ.current = pid;
  const d = await getJSON(`/projects/${pid}`);
  document.getElementById("proj-home").hidden = true;
  document.getElementById("proj-workspace").hidden = false;
  document.getElementById("proj-title").textContent = d.name;
  document.getElementById("proj-count").textContent = `${(d.papers || []).length} paper`;
  document.getElementById("proj-folder").textContent =
    d.folder_path ? `📁 Drop PDF ke: ${d.folder_path}` : "";
  renderProjPapers(d.papers || []);
  document.getElementById("proj-chat-thread").innerHTML = "";
  document.getElementById("matrix-output").innerHTML = "";
  document.getElementById("proj-add-panel").hidden = true;
  document.getElementById("proj-import-panel").hidden = true;
  setSubtab("paper");
  updateMatrixExportLinks();
}

document.getElementById("proj-back").addEventListener("click", showProjectsHome);
document.querySelectorAll("#proj-subnav .subnav-btn").forEach(b =>
  b.addEventListener("click", () => setSubtab(b.dataset.subtab)));
document.getElementById("proj-addpaper-toggle").addEventListener("click", () => {
  const el = document.getElementById("proj-add-panel");
  el.hidden = !el.hidden;
});

function renderProjPapers(papers) {
  const tb = document.querySelector("#proj-papers tbody");
  tb.innerHTML = papers.map(p =>
    `<tr><td><a href="/viewer?doc=${p.id}" target="_blank">${escapeHtml(p.title || "(untitled)")}</a></td>
     <td>${p.year || ""}</td><td>${escapeHtml(p.authors || "")}</td>
     <td><button data-rm="${p.id}" class="danger">x</button></td></tr>`
  ).join("");
  tb.querySelectorAll("button[data-rm]").forEach(b =>
    b.addEventListener("click", async () => {
      const res = await delJSON(`/projects/${PROJ.current}/papers/${b.dataset.rm}`);
      renderProjPapers(res.papers || []);
      loadProjects();
    })
  );
}

document.getElementById("proj-create-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = formToBody(e.target);
  await postJSON("/projects", body);
  e.target.reset();
  loadProjects();
});

document.getElementById("proj-delete-btn").addEventListener("click", async () => {
  if (!PROJ.current || !confirm("Hapus proyek ini? (paper tetap di korpus)")) return;
  await delJSON(`/projects/${PROJ.current}`);
  showProjectsHome();
});

document.getElementById("proj-import-toggle").addEventListener("click", async () => {
  const panel = document.getElementById("proj-import-panel");
  panel.hidden = !panel.hidden;
  if (!panel.hidden) renderImportList("");
});
document.getElementById("proj-import-search").addEventListener("input", (e) => renderImportList(e.target.value));

async function renderImportList(q) {
  const data = await getJSON("/library?" + new URLSearchParams(q ? { q } : {}).toString());
  const div = document.getElementById("proj-import-list");
  div.innerHTML = (data.items || []).map(it =>
    `<label class="chk"><input type="checkbox" value="${it.id}" /> ${escapeHtml(it.title || "(untitled)")} <span class="muted">${it.year || ""}</span></label>`
  ).join("");
}

document.getElementById("proj-import-apply").addEventListener("click", async () => {
  const ids = [...document.querySelectorAll("#proj-import-list input:checked")].map(c => Number(c.value));
  if (!ids.length) return;
  const res = await postJSON(`/projects/${PROJ.current}/papers`, { doc_ids: ids });
  renderProjPapers(res.papers || []);
  document.getElementById("proj-import-panel").hidden = true;
  loadProjects();
});

document.getElementById("proj-upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = e.target.elements.file;
  if (!input.files.length) return;
  const fd = new FormData();
  fd.append("file", input.files[0]);
  const r = await fetch(`/projects/${PROJ.current}/upload`, { method: "POST", body: fd });
  if (!r.ok) { alert("Gagal: " + await r.text()); return; }
  const res = await r.json();
  renderProjPapers(res.papers || []);
  e.target.reset();
  loadProjects();
});

document.getElementById("proj-ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const ta = e.target.elements.question;
  const q = ta.value;
  const expand = document.getElementById("proj-expand").checked;
  const pending = appendChat("proj-chat-thread", q, "…", [], "");
  ta.value = "";
  try {
    const res = await postJSON(`/projects/${PROJ.current}/ask`, { question: q, expand });
    let nudgeHtml = "";
    if ((res.nudge || []).length) {
      nudgeHtml = `${res.nudge.length} paper lain mungkin relevan: ` +
        res.nudge.map(n => `<button class="link" data-add="${n.doc_id}">+ ${escapeHtml(n.title || "(untitled)")}</button>`).join(" ");
    }
    pending.innerHTML = escapeHtml(res.answer).replace(/\n/g, "<br>") +
      citationBlock(res.citations) +
      (nudgeHtml ? `<div class="nudge">${nudgeHtml}</div>` : "");
    pending.querySelectorAll("button[data-add]").forEach(btn =>
      btn.addEventListener("click", async () => {
        const r = await postJSON(`/projects/${PROJ.current}/papers`, { doc_ids: [Number(btn.dataset.add)] });
        renderProjPapers(r.papers || []); btn.remove(); loadProjects();
      }));
  } catch (err) { pending.textContent = "Error: " + err.message; }
});

// Matrix (wired in Phase 12-13)
document.getElementById("proj-matrix-btn").addEventListener("click", async () => {
  const out = document.getElementById("matrix-output");
  out.textContent = "Mengekstrak matriks (grounded)...";
  try {
    const view = document.getElementById("matrix-view").value;
    const res = await postJSON(`/projects/${PROJ.current}/matrix`, { view });
    renderMatrix(res);
  } catch (err) { out.textContent = "Error: " + err.message; }
  updateMatrixExportLinks();
});
document.getElementById("matrix-view").addEventListener("change", () => {
  document.getElementById("proj-matrix-btn").click();
});

function updateMatrixExportLinks() {
  if (!PROJ.current) return;
  const view = document.getElementById("matrix-view").value;
  document.getElementById("matrix-xlsx").href = `/projects/${PROJ.current}/matrix/export.xlsx?view=${view}`;
  document.getElementById("matrix-csv").href = `/projects/${PROJ.current}/matrix/export.csv?view=${view}`;
}

function renderMatrix(res) {
  const out = document.getElementById("matrix-output");
  const rows = res.rows || [];
  if (!rows.length) { out.textContent = "Tidak ada paper / hasil."; return; }
  const cols = res.columns || Object.keys(rows[0].fields || {});
  let html = `<div class="muted">Skema terdeteksi per paper; sel "tidak disebutkan" = gap eksplisit.</div>`;
  html += "<table class='matrix'><thead><tr><th>Source</th><th>Tahun</th><th>Skema</th>" +
    cols.map(c => `<th>${escapeHtml(c)}</th>`).join("") + "</tr></thead><tbody>";
  for (const row of rows) {
    html += `<tr><td>${escapeHtml(row.source || "")}</td><td>${row.year || ""}</td><td>${escapeHtml(row.schema || "")}</td>` +
      cols.map(c => `<td>${escapeHtml(String((row.fields || {})[c] ?? ""))}</td>`).join("") + "</tr>";
  }
  html += "</tbody></table>";
  out.innerHTML = html;
}

loadProjects();

document.getElementById("codebook-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = e.target.elements.file;
  if (!PROJ.current || !input.files.length) return;
  const fd = new FormData();
  fd.append("file", input.files[0]);
  const r = await fetch(`/projects/${PROJ.current}/codebook/bootstrap`, { method: "POST", body: fd });
  const info = document.getElementById("codebook-info");
  if (!r.ok) { info.textContent = "Gagal: " + await r.text(); return; }
  const res = await r.json();
  info.textContent = `Codebook: ${res.learned} tag dipelajari (closed coding aktif untuk matriks berikutnya).`;
  e.target.reset();
});

// ---------- Rename by title (Phase 14) ----------
function baseName(p) { return (p || "").split("/").pop(); }

document.getElementById("rename-preview-btn").addEventListener("click", async () => {
  const status = document.getElementById("rename-status");
  const tb = document.querySelector("#rename-table tbody");
  status.textContent = "Menyusun preview (LLM+Crossref)...";
  tb.innerHTML = "";
  try {
    const data = await getJSON("/rename/preview");
    tb.innerHTML = (data.plan || []).map(p =>
      `<tr><td>${escapeHtml(baseName(p.old_path))}</td>
       <td>${escapeHtml(p.new_path ? baseName(p.new_path) : "")}</td>
       <td>${escapeHtml(p.status)}</td></tr>`
    ).join("");
    status.textContent = `${data.count} file akan di-rename.`;
    document.getElementById("rename-apply-btn").disabled = data.count === 0;
  } catch (err) { status.textContent = "Error: " + err.message; }
});

document.getElementById("rename-apply-btn").addEventListener("click", async () => {
  const status = document.getElementById("rename-status");
  if (!confirm("Terapkan rename ke semua file di preview?")) return;
  status.textContent = "Menerapkan...";
  try {
    const res = await postJSON("/rename/apply", { batch: "ui-" + Date.now() });
    status.textContent = `Diterapkan: ${res.applied}, error: ${(res.errors || []).length}.`;
    document.getElementById("rename-apply-btn").disabled = true;
    document.querySelector("#lib-form").dispatchEvent(new Event("submit"));
  } catch (err) { status.textContent = "Error: " + err.message; }
});

document.getElementById("rename-undo-btn").addEventListener("click", async () => {
  const status = document.getElementById("rename-status");
  status.textContent = "Undo...";
  try {
    const res = await postJSON("/rename/undo", {});
    status.textContent = res.batch ? `Undo batch ${res.batch}: ${res.reverted.length} dikembalikan.` : "Tidak ada batch untuk di-undo.";
    document.querySelector("#lib-form").dispatchEvent(new Event("submit"));
  } catch (err) { status.textContent = "Error: " + err.message; }
});

// ---------- Perbaiki judul (LLM + Crossref) ----------
document.getElementById("retitle-btn").addEventListener("click", async () => {
  const status = document.getElementById("retitle-status");
  if (!confirm("Perbaiki judul semua paper via LLM + Crossref? (butuh API key + internet)")) return;
  status.textContent = "Memperbaiki judul...";
  try {
    const res = await postJSON("/library/retitle", {});
    status.textContent = `${res.updated} judul diperbarui.`;
    document.querySelector("#lib-form").dispatchEvent(new Event("submit"));
  } catch (err) { status.textContent = "Error: " + err.message; }
});

// ---------- Reembed admin (Phase C) ----------
const reembedBtn = document.getElementById("reembed-btn");
if (reembedBtn) {
  const statusEl = document.getElementById("reembed-status");
  const progEl = document.getElementById("reembed-progress");
  let polling = null;

  async function pollReembed() {
    try {
      const st = await getJSON("/admin/reembed/status");
      const pct = st.total ? Math.round((st.done / st.total) * 100) : 0;
      progEl.textContent = `${st.done}/${st.total} (${pct}%)` + (st.model ? ` → ${st.model} ${st.dim}-d` : "");
      if (!st.running) {
        clearInterval(polling); polling = null;
        reembedBtn.disabled = false;
        statusEl.textContent = st.error ? ("Gagal: " + st.error) : "Selesai.";
      }
    } catch (err) {
      clearInterval(polling); polling = null;
      reembedBtn.disabled = false;
      statusEl.textContent = "Error: " + err.message;
    }
  }

  reembedBtn.addEventListener("click", async () => {
    if (!confirm("Reembed seluruh korpus dengan model embedding aktif? Bisa lama.")) return;
    reembedBtn.disabled = true;
    statusEl.textContent = "Memulai...";
    progEl.textContent = "";
    try {
      const res = await postJSON("/admin/reembed/start", { force: true });
      statusEl.textContent = `Berjalan (${res.total} chunk)...`;
      polling = setInterval(pollReembed, 1000);
    } catch (err) {
      reembedBtn.disabled = false;
      statusEl.textContent = "Error: " + err.message;
    }
  });
}

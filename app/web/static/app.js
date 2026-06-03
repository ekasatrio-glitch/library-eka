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

document.getElementById("ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const ans = document.getElementById("ask-answer");
  const cits = document.getElementById("ask-citations");
  ans.textContent = "Mencari & menyusun jawaban...";
  cits.innerHTML = "";
  try {
    const res = await postJSON("/ask", formToBody(e.target));
    ans.textContent = res.answer;
    cits.innerHTML = citationLinks(res.citations || []);
  } catch (err) { ans.textContent = "Error: " + err.message; }
});

document.getElementById("draft-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const para = document.getElementById("draft-paragraph");
  const refs = document.getElementById("draft-refs");
  para.textContent = "Menulis draft...";
  refs.innerHTML = "";
  try {
    const res = await postJSON("/draft", formToBody(e.target));
    para.textContent = res.paragraph;
    refs.innerHTML = (res.references || []).map(r => `<li>${escapeHtml(r)}</li>`).join("");
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
  const ul = document.getElementById("proj-list");
  ul.innerHTML = (data.projects || []).map(p =>
    `<li><a href="#" data-pid="${p.id}">${escapeHtml(p.name)}</a> <span class="muted">(${p.n_papers})</span></li>`
  ).join("");
  ul.querySelectorAll("a[data-pid]").forEach(a =>
    a.addEventListener("click", (e) => { e.preventDefault(); openProject(Number(a.dataset.pid)); })
  );
}

async function openProject(pid) {
  PROJ.current = pid;
  const d = await getJSON(`/projects/${pid}`);
  document.getElementById("proj-detail").hidden = false;
  document.getElementById("proj-title").textContent = d.name;
  renderProjPapers(d.papers || []);
  document.getElementById("proj-matrix-wrap").hidden = true;
  document.getElementById("proj-answer").textContent = "";
  document.getElementById("proj-citations").innerHTML = "";
  document.getElementById("proj-nudge").innerHTML = "";
  updateMatrixExportLinks();
}

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
  document.getElementById("proj-detail").hidden = true;
  PROJ.current = null;
  loadProjects();
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
  const ans = document.getElementById("proj-answer");
  const cits = document.getElementById("proj-citations");
  const nudge = document.getElementById("proj-nudge");
  ans.textContent = "Mencari dalam proyek...";
  cits.innerHTML = ""; nudge.innerHTML = "";
  try {
    const res = await postJSON(`/projects/${PROJ.current}/ask`, {
      question: e.target.elements.question.value,
      expand: document.getElementById("proj-expand").checked,
    });
    ans.textContent = res.answer;
    cits.innerHTML = citationLinks(res.citations || []);
    if ((res.nudge || []).length) {
      nudge.innerHTML = `<p class="muted">${res.nudge.length} paper lain di library mungkin relevan — tambahkan ke proyek?</p>` +
        res.nudge.map(n => `<button class="link" data-add="${n.doc_id}">+ ${escapeHtml(n.title || "(untitled)")}</button>`).join(" ");
      nudge.querySelectorAll("button[data-add]").forEach(b =>
        b.addEventListener("click", async () => {
          const r = await postJSON(`/projects/${PROJ.current}/papers`, { doc_ids: [Number(b.dataset.add)] });
          renderProjPapers(r.papers || []); b.remove(); loadProjects();
        })
      );
    }
  } catch (err) { ans.textContent = "Error: " + err.message; }
});

// Matrix (wired in Phase 12-13)
document.getElementById("proj-matrix-btn").addEventListener("click", async () => {
  const wrap = document.getElementById("proj-matrix-wrap");
  const out = document.getElementById("matrix-output");
  wrap.hidden = false;
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

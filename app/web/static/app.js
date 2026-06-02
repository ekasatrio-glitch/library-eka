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

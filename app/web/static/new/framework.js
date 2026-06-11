// Kerangka teori tab: title input -> confirm variables -> build grounded graph
// -> render SVG (viz.js) -> edit DSL -> source-badge overlay -> export PNG.
// DOM view, verified manually. Pure compiler lives in dsl.js (unit-tested).
import { escapeHtml, getJSON, postJSON, friendlyError } from "./api.js";
import { parseDSL, dslToDot, slug } from "./dsl.js";

let _vizPromise = null;
function getViz() {
  // viz.js (window.Viz) is loaded async from CDN; retry until ready.
  if (_vizPromise) return _vizPromise;
  // Clear the cache on failure so a later render can retry once the CDN script
  // finishes loading — otherwise a slow first load would stick "belum siap".
  _vizPromise = new Promise((resolve, reject) => {
    const tryLoad = (attempt) => {
      if (window.Viz && window.Viz.instance) {
        window.Viz.instance().then(resolve).catch(reject);
      } else if (attempt < 20) {
        setTimeout(() => tryLoad(attempt + 1), 250);
      } else {
        reject(new Error("mesin diagram belum siap"));
      }
    };
    tryLoad(0);
  });
  _vizPromise.catch(() => { _vizPromise = null; });
  return _vizPromise;
}

export function mountFramework(panel, pid, deps = {}) {
  let citations = {};

  panel.innerHTML = `
    <div class="kt">
      <div class="kt-setup">
        <input id="kt-title" type="text" placeholder="Tempel judul penelitian…" />
        <button class="df-btn" id="kt-parse" type="button" disabled>Parse judul</button>
        <div id="kt-vars"></div>
        <button class="df-btn" id="kt-build" type="button" hidden>Bangun kerangka</button>
      </div>
      <div class="kt-main" hidden>
        <div class="kt-diagram" id="kt-diagram"></div>
        <div class="kt-side">
          <textarea id="kt-dsl" spellcheck="false" placeholder="DSL kerangka…"></textarea>
          <div class="kt-actions">
            <button class="df-btn" id="kt-render" type="button">Render ulang</button>
            <button class="df-btn ghost" id="kt-png" type="button" disabled>⬇ PNG</button>
            <button class="df-btn ghost" id="kt-copy" type="button">Salin DSL</button>
          </div>
          <div class="kt-errors" id="kt-errors"></div>
          <div class="kt-sources" id="kt-sources"></div>
        </div>
      </div>
    </div>`;

  const titleEl = panel.querySelector("#kt-title");
  const parseBtn = panel.querySelector("#kt-parse");
  const varsEl = panel.querySelector("#kt-vars");
  const buildBtn = panel.querySelector("#kt-build");
  const mainEl = panel.querySelector(".kt-main");
  const diagramEl = panel.querySelector("#kt-diagram");
  const dslEl = panel.querySelector("#kt-dsl");
  const errEl = panel.querySelector("#kt-errors");
  const srcEl = panel.querySelector("#kt-sources");
  const pngBtn = panel.querySelector("#kt-png");

  titleEl.addEventListener("input", () => { parseBtn.disabled = !titleEl.value.trim(); });

  // ----- Parse title -> variable confirmation checklist -----
  parseBtn.addEventListener("click", async () => {
    parseBtn.disabled = true;
    varsEl.textContent = "Mengurai judul…";
    try {
      const res = await postJSON(`/projects/${pid}/framework/parse-title`,
        { title: titleEl.value.trim() });
      renderVarConfirm(res.variables || { bebas: [], terikat: "", populasi: "" });
    } catch (e) {
      varsEl.textContent = friendlyError(e);
    } finally {
      parseBtn.disabled = !titleEl.value.trim();
    }
  });

  function renderVarConfirm(v) {
    const bebas = v.bebas || [];
    varsEl.innerHTML =
      `<div class="kt-vargroup"><div class="side-label">Variabel bebas</div>` +
      bebas.map((b, i) =>
        `<label><input type="checkbox" data-bebas="${i}" checked> ${escapeHtml(b)}</label>`).join("") +
      `</div>` +
      `<label class="kt-field">Terikat <input id="kt-terikat" value="${escapeHtml(v.terikat || "")}"></label>` +
      `<label class="kt-field">Populasi <input id="kt-populasi" value="${escapeHtml(v.populasi || "")}"></label>`;
    varsEl._bebas = bebas;
    buildBtn.hidden = false;
  }

  // ----- Build framework -----
  buildBtn.addEventListener("click", async () => {
    const bebas = (varsEl._bebas || []).filter((_, i) =>
      varsEl.querySelector(`[data-bebas="${i}"]`)?.checked);
    const terikat = panel.querySelector("#kt-terikat")?.value.trim() || "";
    const populasi = panel.querySelector("#kt-populasi")?.value.trim() || "";
    buildBtn.disabled = true;
    buildBtn.textContent = "Menyusun kerangka…";
    try {
      const res = await postJSON(`/projects/${pid}/framework`, {
        variables: { bebas, terikat, populasi },
        title: titleEl.value.trim(),
      });
      citations = res.citations || {};
      dslEl.value = res.dsl || "";
      mainEl.hidden = false;
      await renderDsl();
    } catch (e) {
      errEl.textContent = friendlyError(e);
    } finally {
      buildBtn.disabled = false;
      buildBtn.textContent = "Bangun kerangka";
    }
  });

  // ----- Render DSL -> SVG (debounced on edit) -----
  let renderTimer = null;
  dslEl.addEventListener("input", () => {
    clearTimeout(renderTimer);
    renderTimer = setTimeout(renderDsl, 400);
  });
  panel.querySelector("#kt-render").addEventListener("click", renderDsl);

  async function renderDsl() {
    const parsed = parseDSL(dslEl.value);
    if (parsed.errors.length) {
      errEl.innerHTML = `<div class="side-label">Kesalahan DSL</div>` +
        parsed.errors.map(e =>
          `<div class="kt-err">baris ${e.line}, kol ${e.col}: ${escapeHtml(e.msg)}</div>`).join("");
      return; // keep the last good SVG
    }
    errEl.textContent = "";
    const dot = dslToDot(parsed, citations);
    let viz;
    try {
      viz = await getViz();
    } catch (e) {
      diagramEl.innerHTML = `<p class="gap">Render diagram perlu koneksi pertama kali.</p>`;
      return;
    }
    const svg = viz.renderSVGElement(dot);
    diagramEl.innerHTML = "";
    diagramEl.appendChild(svg);
    pngBtn.disabled = false;
    overlayBadges(parsed);
    renderSources(parsed);
  }

  // ----- Source badges over rendered nodes -----
  function overlayBadges(parsed) {
    for (const n of parsed.nodes) {
      const cit = citations[n.label];
      if (!cit) continue;
      const g = diagramEl.querySelector(`#node-${cssEscape(slug(n.label))}`);
      if (!g) continue;
      const badge = document.createElement("span");
      badge.className = "kt-badge " +
        (cit.src === "korpus" ? "korpus"
          : cit.status === "tak_terverifikasi" ? "tak" : "perlu");
      badge.textContent = cit.src === "korpus" ? "📄" : "🌐";
      badge.title = badgeTitle(cit);
      if (cit.src === "korpus" && cit.doc_id) {
        badge.style.cursor = "pointer";
        badge.addEventListener("click", () =>
          window.open(`/viewer?doc=${cit.doc_id}#page=${cit.page}`, "_blank"));
      }
      g.appendChild(badge);
    }
  }

  function badgeTitle(cit) {
    if (cit.src === "korpus") return `${cit.title || ""} (hlm ${cit.page})`;
    if (cit.ref) {
      const r = cit.ref;
      return `${r.title || ""} — ${(r.authors || []).join(", ")} (${r.year || "?"})` +
        (r.doi ? `\n${r.url || r.doi}` : "");
    }
    return "sumber tak ditemukan — perlu verifikasi";
  }

  function renderSources(parsed) {
    const items = parsed.nodes.map(n => [n.label, citations[n.label]]).filter(x => x[1]);
    if (!items.length) { srcEl.innerHTML = ""; return; }
    srcEl.innerHTML = `<div class="side-label">Sumber</div>` + items.map(([label, cit]) => {
      if (cit.src === "korpus") {
        return `<div class="kt-src korpus">📄 <b>${escapeHtml(label)}</b> — ${escapeHtml(cit.title || "")} (hlm ${cit.page})</div>`;
      }
      const tag = cit.status === "tak_terverifikasi"
        ? `<span class="kt-tag tak">sumber tak ditemukan</span>`
        : `<span class="kt-tag perlu">perlu verifikasi</span>`;
      const ref = cit.ref ? ` — ${escapeHtml(cit.ref.title || "")} (${cit.ref.year || "?"})` : "";
      return `<div class="kt-src eksternal">🌐 <b>${escapeHtml(label)}</b>${ref} ${tag}</div>`;
    }).join("");
  }

  // ----- Export PNG -----
  pngBtn.addEventListener("click", async () => {
    const svg = diagramEl.querySelector("svg");
    if (!svg) return;
    try { await document.fonts.ready; } catch (_) {}
    const xml = new XMLSerializer().serializeToString(svg);
    const img = new Image();
    const blobUrl = URL.createObjectURL(new Blob([xml], { type: "image/svg+xml" }));
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = img.width || svg.clientWidth || 800;
      canvas.height = img.height || svg.clientHeight || 600;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(blobUrl);
      canvas.toBlob(b => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(b);
        a.download = `kerangka-${pid}.png`;
        a.click();
        URL.revokeObjectURL(a.href);
      }, "image/png");
    };
    img.onerror = () => URL.revokeObjectURL(blobUrl);
    img.src = blobUrl;
  });

  panel.querySelector("#kt-copy").addEventListener("click", () => {
    navigator.clipboard?.writeText(dslEl.value);
  });

  // CSS.escape fallback for older engines.
  function cssEscape(s) {
    return window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/[^A-Za-z0-9_-]/g, "\\$&");
  }

  // ----- On mount: load persisted framework, render if present -----
  getJSON(`/projects/${pid}/framework`).then(res => {
    if (res.title) titleEl.value = res.title;
    parseBtn.disabled = !titleEl.value.trim();
    if (res.dsl) {
      citations = res.citations || {};
      dslEl.value = res.dsl;
      mainEl.hidden = false;
      renderDsl();
    }
  }).catch(() => {});

  return { refresh: () => getJSON(`/projects/${pid}/framework`) };
}

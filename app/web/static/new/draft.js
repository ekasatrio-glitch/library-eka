// Draft view: academic paragraph (Vancouver/APA) with cite-pills + split references.
import { escapeHtml, postJSON, friendlyError } from "./api.js";
import { pillsForAnswer } from "./citations.js";

export function mountDraft(viewEl, opts = {}) {
  viewEl.innerHTML = `
    <div class="scroll"><div class="inner">
      <form id="df-form" class="df-form">
        <textarea id="df-topic" rows="3" placeholder="Topik paragraf akademik dari paper naskah ini…"></textarea>
        <div class="df-row">
          <select id="df-style">
            <option value="vancouver">Vancouver</option>
            <option value="apa">APA</option>
          </select>
          <button class="df-btn" id="df-submit" type="button">Tulis draft</button>
        </div>
      </form>
      <div id="df-paragraph" class="msg-a"></div>
      <div id="df-refs"></div>
    </div></div>`;

  const topic = viewEl.querySelector("#df-topic");
  const styleSel = viewEl.querySelector("#df-style");
  const para = viewEl.querySelector("#df-paragraph");
  const refsEl = viewEl.querySelector("#df-refs");

  function refsHtml(references, citations) {
    const cited = [], uncited = [];
    references.forEach((r, i) => {
      ((citations[i] && citations[i].cited === false) ? uncited : cited).push(r);
    });
    let html = `<div class="ref-title">Referensi</div>` +
      `<ol class="reflist">${cited.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ol>`;
    if (uncited.length) {
      html += `<details class="cites uncited"><summary>Diambil, tidak dikutip (${uncited.length})</summary>` +
        `<ol class="reflist">${uncited.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ol></details>`;
    }
    return html;
  }

  async function submit() {
    const t = topic.value.trim();
    if (!t) return;
    const style = styleSel.value;
    para.innerHTML = `<div class="ai">Menulis draft…</div>`;
    refsEl.innerHTML = "";
    try {
      const body = { topic: t, style };
      const ids = opts.getDocIds ? opts.getDocIds() : [];
      if (ids && ids.length) body.doc_ids = ids;
      const res = await postJSON("/draft", body);
      const markerStyle = style === "vancouver" ? "paren" : "square";
      para.innerHTML = `<div class="ai">${pillsForAnswer(res.paragraph, res.citations || [], markerStyle)}</div>`;
      refsEl.innerHTML = refsHtml(res.references || [], res.citations || []);
    } catch (err) {
      para.innerHTML = `<div class="ai">${escapeHtml(friendlyError(err))}</div>`;
    }
  }

  viewEl.querySelector("#df-submit").addEventListener("click", submit);
}

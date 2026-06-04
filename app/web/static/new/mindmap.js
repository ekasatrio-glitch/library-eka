// Mindmap view: MarkMap rendered from /mindmap markdown via the autoloader CDN.
import { postJSON } from "./api.js";

export function mountMindmap(viewEl) {
  viewEl.innerHTML = `
    <div class="scroll"><div class="inner">
      <form id="mm-form" class="df-form">
        <textarea id="mm-topic" rows="2" placeholder="Topik mindmap…"></textarea>
        <div class="df-row">
          <input id="mm-breadth" type="number" min="2" max="8" value="4" title="Jumlah subtopik" />
          <button class="df-btn" id="mm-submit" type="button">Buat mindmap</button>
        </div>
      </form>
      <pre id="mm-md" class="md"></pre>
      <div id="mm-svg" class="markmap-wrap"></div>
    </div></div>`;

  const topic = viewEl.querySelector("#mm-topic");
  const breadth = viewEl.querySelector("#mm-breadth");
  const md = viewEl.querySelector("#mm-md");
  const svg = viewEl.querySelector("#mm-svg");

  async function submit() {
    const t = topic.value.trim();
    if (!t) return;
    md.textContent = "Menyusun mindmap…";
    svg.innerHTML = "";
    try {
      const res = await postJSON("/mindmap", { topic: t, breadth: Number(breadth.value) || 4 });
      md.textContent = res.markdown;
      const div = document.createElement("div");
      div.className = "markmap";
      const tpl = document.createElement("script");
      tpl.type = "text/template";
      tpl.textContent = res.markdown;
      div.appendChild(tpl);
      svg.appendChild(div);
      if (window.markmap && window.markmap.autoLoader) window.markmap.autoLoader.renderAll();
    } catch (err) {
      md.textContent = "Error: " + err.message;
    }
  }

  viewEl.querySelector("#mm-submit").addEventListener("click", submit);
}

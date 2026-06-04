// Chat surface. mountChat(container, opts) renders an empty state + thread + input.
// opts: { endpoint(question)->Promise(result), examples:[string], showNudge:bool,
//         initial:[{q,a,citations}], onExchange(messages), onAddPaper(docId) }
// Keeps an internal messages[] log; calls onExchange(messages) after each answer
// so the caller (main.js) can persist the whole conversation to history.
import { escapeHtml } from "./api.js";
import { renderAnswerHtml } from "./citations.js";

const DEFAULT_EXAMPLES = [
  "Apa temuan utama lintas paper tentang topik X?",
  "Bandingkan metode di dua studi terbaru.",
  "Ringkas bukti untuk klaim Y dengan sitasi.",
  "Apa keterbatasan yang disebut penulis?",
];

export function mountChat(container, opts) {
  const examples = opts.examples || DEFAULT_EXAMPLES;
  container.innerHTML = `
    <div class="scroll"><div class="inner" id="thread">
      <div class="empty" id="empty">
        <h1>library-eka</h1>
        <p>Tanya apa saja ke korpusmu. Jawaban presisi dengan sitasi klik-ke-halaman.</p>
        <div class="eg">${examples.map(e => `<button class="ecard" type="button">${escapeHtml(e)}</button>`).join("")}</div>
      </div>
    </div></div>
    <div class="input"><div class="input-in">
      <textarea id="q" rows="1" placeholder="Tanya korpus… (Enter kirim · Shift+Enter baris baru)"></textarea>
      <button class="send" id="send" type="button" aria-label="Kirim">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
      </button>
    </div></div>`;

  const thread = container.querySelector("#thread");
  let empty = container.querySelector("#empty");
  const ta = container.querySelector("#q");
  const send = container.querySelector("#send");
  const messages = [];

  function clearEmpty() { if (empty) { empty.remove(); empty = null; } }

  function bubbleUser(q) {
    const d = document.createElement("div");
    d.className = "msg msg-u";
    d.innerHTML = `<div class="bub"></div>`;
    d.querySelector(".bub").textContent = q;
    thread.appendChild(d);
  }
  function bubbleAI(html) {
    const d = document.createElement("div");
    d.className = "msg msg-a";
    d.innerHTML = `<div class="ai">${html}</div>`;
    thread.appendChild(d);
    return d.querySelector(".ai");
  }
  function nudgeHtml(nudge) {
    if (!opts.showNudge || !(nudge || []).length) return "";
    return `<div class="nudge">${nudge.length} paper lain mungkin relevan: ` +
      nudge.map(n => `<button data-add="${n.doc_id}" type="button">+ ${escapeHtml(n.title || "(untitled)")}</button>`).join("") +
      `</div>`;
  }

  async function submit() {
    const q = ta.value.trim();
    if (!q) return;
    clearEmpty();
    ta.value = "";
    bubbleUser(q);
    const pending = bubbleAI("…");
    try {
      const res = await opts.endpoint(q);
      pending.innerHTML = renderAnswerHtml(res.answer, res.citations || []) + nudgeHtml(res.nudge);
      pending.querySelectorAll("button[data-add]").forEach(b =>
        b.addEventListener("click", () => { opts.onAddPaper && opts.onAddPaper(Number(b.dataset.add)); b.remove(); }));
      messages.push({ q, a: res.answer, citations: res.citations || [] });
      if (opts.onExchange) opts.onExchange(messages);
    } catch (err) {
      pending.textContent = "Error: " + err.message;
    }
    const sc = container.querySelector(".scroll");
    sc.scrollTop = sc.scrollHeight;
  }

  // Replay a saved conversation, if provided.
  (opts.initial || []).forEach(m => {
    clearEmpty();
    bubbleUser(m.q);
    bubbleAI(renderAnswerHtml(m.a, m.citations || []));
    messages.push({ q: m.q, a: m.a, citations: m.citations || [] });
  });

  send.addEventListener("click", submit);
  ta.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  });
  container.querySelectorAll(".ecard").forEach(c =>
    c.addEventListener("click", () => { ta.value = c.textContent; submit(); }));
}

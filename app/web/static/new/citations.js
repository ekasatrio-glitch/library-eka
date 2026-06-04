// Render an answer with click-to-page cite-pills and a collapsed sources list
// split into cited vs retrieved-but-uncited. DOM-free: returns HTML strings.

import { escapeHtml, viewerHref } from "./api.js";

function citeLink(c) {
  const pg = c.page_start === c.page_end ? `p.${c.page_start}` : `p.${c.page_start}-${c.page_end}`;
  return `<li><a href="${viewerHref(c)}" target="_blank">[${c.n}] ${escapeHtml(c.title)} (${pg})</a></li>`;
}

// Replace [n] (square) or (n) (paren) markers in the (escaped) answer with pills.
export function pillsForAnswer(answer, citations, style = "square") {
  const byN = new Map(citations.map(c => [c.n, c]));
  const re = style === "paren" ? /\((\d+)\)/g : /\[(\d+)\]/g;
  return escapeHtml(answer).replace(re, (m, d) => {
    const c = byN.get(Number(d));
    if (!c) return m; // out-of-range marker: leave as text
    return `<a class="pill" href="${viewerHref(c)}" target="_blank" title="${escapeHtml(c.title)}">${c.n}</a>`;
  });
}

export function sourcesBlock(citations) {
  if (!citations || !citations.length) return "";
  const cited = citations.filter(c => c.cited !== false);
  const uncited = citations.filter(c => c.cited === false);
  if (!uncited.length) {
    return `<details class="cites"><summary>📎 Sumber (${citations.length})</summary>` +
      `<ul class="reflist">${cited.map(citeLink).join("")}</ul></details>`;
  }
  return `<details class="cites"><summary>📎 Sumber dikutip (${cited.length})</summary>` +
    `<ul class="reflist">${cited.map(citeLink).join("")}</ul></details>` +
    `<details class="cites uncited"><summary>Diambil, tidak dikutip (${uncited.length})</summary>` +
    `<ul class="reflist">${uncited.map(citeLink).join("")}</ul></details>`;
}

export function renderAnswerHtml(answer, citations, style = "square") {
  return pillsForAnswer(answer, citations, style) + sourcesBlock(citations);
}

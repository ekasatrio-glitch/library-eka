// Fetch + HTML helpers. DOM-free so it is unit-testable under node:test.

export function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function viewerHref(citation) {
  return `/viewer?doc=${citation.doc_id}#page=${citation.page_start}`;
}

export async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

export async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

// Map raw HTTP errors to layperson Indonesian. Keep technical detail out of the
// primary user's face; Eka can read the server logs.
export function friendlyError(err) {
  const m = String((err && err.message) || err);
  if (m.startsWith("503")) return "Mesin penjawab sedang tidak aktif. Minta Eka menyalakannya.";
  if (m.startsWith("409")) return "Indeks perpustakaan sedang tidak sinkron. Minta Eka membukanya di /tools.";
  return "Terjadi kesalahan: " + m;
}

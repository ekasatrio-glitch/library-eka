// Conversation history in localStorage. DOM-free; storage is injected so it is
// unit-testable. Callers pass id/updatedAt (no Date.now() inside => deterministic).

const KEY = "libeka.conversations";

export function makeHistory(storage) {
  function readAll() {
    try {
      const v = JSON.parse(storage.getItem(KEY) || "[]");
      return Array.isArray(v) ? v : [];
    } catch {
      return [];
    }
  }
  function writeAll(arr) {
    storage.setItem(KEY, JSON.stringify(arr));
  }
  return {
    list() {
      return readAll().slice().sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
    },
    get(id) {
      return readAll().find(c => c.id === id) || null;
    },
    save(conv) {
      const arr = readAll().filter(c => c.id !== conv.id);
      arr.push(conv);
      writeAll(arr);
    },
    remove(id) {
      writeAll(readAll().filter(c => c.id !== id));
    },
  };
}

// Saved mindmaps in localStorage. DOM-free; storage injected so it is unit-testable.
// Callers pass id/updatedAt (no Date.now() inside => deterministic), like history.js.

const KEY = "libeka.mindmaps";

export function makeMindmapStore(storage) {
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
      return readAll().find(m => m.id === id) || null;
    },
    save(mm) {
      const arr = readAll().filter(m => m.id !== mm.id);
      arr.push(mm);
      writeAll(arr);
    },
    remove(id) {
      writeAll(readAll().filter(m => m.id !== id));
    },
  };
}

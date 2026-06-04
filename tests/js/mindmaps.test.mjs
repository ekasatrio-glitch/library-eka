import { test } from "node:test";
import assert from "node:assert/strict";
import { makeMindmapStore } from "../../app/web/static/new/mindmaps.js";

function fakeStorage() {
  const m = new Map();
  return {
    getItem: k => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
  };
}

function item(over = {}) {
  return {
    id: "m1", topic: "sedasi", breadth: 4, markdown: "# sedasi",
    citations: [], docIds: [], docLabel: "semua korpus", updatedAt: 100, ...over,
  };
}

test("save then get returns the item", () => {
  const s = makeMindmapStore(fakeStorage());
  s.save(item());
  assert.equal(s.get("m1").topic, "sedasi");
});

test("save upserts by id (no duplicate)", () => {
  const s = makeMindmapStore(fakeStorage());
  s.save(item());
  s.save(item({ topic: "sedasi v2", updatedAt: 200 }));
  assert.equal(s.list().length, 1);
  assert.equal(s.get("m1").topic, "sedasi v2");
});

test("list is newest-first by updatedAt", () => {
  const s = makeMindmapStore(fakeStorage());
  s.save(item({ id: "a", updatedAt: 100 }));
  s.save(item({ id: "b", updatedAt: 300 }));
  s.save(item({ id: "c", updatedAt: 200 }));
  assert.deepEqual(s.list().map(x => x.id), ["b", "c", "a"]);
});

test("remove drops by id", () => {
  const s = makeMindmapStore(fakeStorage());
  s.save(item({ id: "a" }));
  s.save(item({ id: "b" }));
  s.remove("a");
  assert.deepEqual(s.list().map(x => x.id), ["b"]);
});

test("get missing returns null", () => {
  const s = makeMindmapStore(fakeStorage());
  assert.equal(s.get("nope"), null);
});

test("corrupt storage yields empty list", () => {
  const st = fakeStorage();
  st.setItem("libeka.mindmaps", "{not json");
  const s = makeMindmapStore(st);
  assert.deepEqual(s.list(), []);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makeHistory } from '../../app/web/static/new/history.js';

function fakeStorage() {
  const m = new Map();
  return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)) };
}

test('starts empty', () => {
  const h = makeHistory(fakeStorage());
  assert.deepEqual(h.list(), []);
});

test('save then list returns newest-first', () => {
  const h = makeHistory(fakeStorage());
  h.save({ id: 'a', title: 'first', scope: 'global', messages: [], updatedAt: 1 });
  h.save({ id: 'b', title: 'second', scope: 'global', messages: [], updatedAt: 2 });
  assert.deepEqual(h.list().map(c => c.id), ['b', 'a']);
});

test('save with existing id updates in place', () => {
  const h = makeHistory(fakeStorage());
  h.save({ id: 'a', title: 't', scope: 'global', messages: [], updatedAt: 1 });
  h.save({ id: 'a', title: 't', scope: 'global', messages: [{ q: 'x', a: 'y', citations: [] }], updatedAt: 3 });
  assert.equal(h.list().length, 1);
  assert.equal(h.get('a').messages.length, 1);
});

test('remove deletes by id', () => {
  const h = makeHistory(fakeStorage());
  h.save({ id: 'a', title: 't', scope: 'global', messages: [], updatedAt: 1 });
  h.remove('a');
  assert.deepEqual(h.list(), []);
});

test('persists across instances sharing storage', () => {
  const s = fakeStorage();
  makeHistory(s).save({ id: 'a', title: 't', scope: 'global', messages: [], updatedAt: 1 });
  assert.equal(makeHistory(s).list().length, 1);
});

test('tolerates corrupt storage value', () => {
  const s = fakeStorage();
  s.setItem('libeka.conversations', 'not json');
  assert.deepEqual(makeHistory(s).list(), []);
});

test('list(scope) filters by scope', () => {
  const h = makeHistory(fakeStorage());
  h.save({ id: 'a', title: 'g', scope: 'global', messages: [], updatedAt: 1 });
  h.save({ id: 'b', title: 'p1', scope: '7', messages: [], updatedAt: 2 });
  h.save({ id: 'c', title: 'p2', scope: '7', messages: [], updatedAt: 3 });
  assert.deepEqual(h.list('7').map(c => c.id), ['c', 'b']);
  assert.deepEqual(h.list('global').map(c => c.id), ['a']);
});

test('list() without scope returns everything', () => {
  const h = makeHistory(fakeStorage());
  h.save({ id: 'a', title: 'g', scope: 'global', messages: [], updatedAt: 1 });
  h.save({ id: 'b', title: 'p', scope: '7', messages: [], updatedAt: 2 });
  assert.equal(h.list().length, 2);
});

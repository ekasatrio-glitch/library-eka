import { test } from 'node:test';
import assert from 'node:assert/strict';
import { shouldShowSplash, markSplashSeen } from '../../app/web/static/new/splash.js';

function fakeStorage() {
  const m = new Map();
  return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)) };
}

test('shows on first visit', () => {
  assert.equal(shouldShowSplash(fakeStorage()), true);
});

test('hidden after marked seen', () => {
  const s = fakeStorage();
  markSplashSeen(s);
  assert.equal(shouldShowSplash(s), false);
});

// tests/js/upload.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { STAGE_LABELS, pollJob } from '../../app/web/static/new/upload.js';

test('stage labels are layperson Indonesian', () => {
  assert.equal(STAGE_LABELS.membaca, 'membaca halaman…');
  assert.equal(STAGE_LABELS.mengindeks, 'mengindeks…');
  assert.equal(STAGE_LABELS.selesai, 'selesai');
  assert.ok(STAGE_LABELS.antri);
});

test('pollJob ticks until finished and resolves with last job', async () => {
  const states = [
    { stage: 'membaca', done: 0, total: 0, finished: false },
    { stage: 'mengindeks', done: 4, total: 8, finished: false },
    { stage: 'selesai', done: 8, total: 8, finished: true },
  ];
  let i = 0;
  const ticks = [];
  const job = await pollJob('j1', j => ticks.push(j.stage), {
    delayMs: 0,
    fetchJson: async url => {
      assert.equal(url, '/uploads/j1');
      return states[i++];
    },
  });
  assert.equal(job.stage, 'selesai');
  assert.deepEqual(ticks, ['membaca', 'mengindeks', 'selesai']);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pillsForAnswer, sourcesBlock, renderAnswerHtml } from '../../app/web/static/new/citations.js';

const cits = [
  { n: 1, doc_id: 10, title: 'A', page_start: 1, page_end: 2, cited: false },
  { n: 2, doc_id: 11, title: 'B', page_start: 5, page_end: 5, cited: true },
  { n: 3, doc_id: 12, title: 'C', page_start: 7, page_end: 8, cited: true },
];

test('pillsForAnswer turns [n] into a pill anchor to the right page', () => {
  const html = pillsForAnswer('Klaim [2] dan [3].', cits);
  assert.match(html, /class="pill"[^>]*href="\/viewer\?doc=11#page=5"/);
  assert.match(html, /href="\/viewer\?doc=12#page=7"/);
  assert.ok(!html.includes('[2]'), 'marker should be replaced');
});

test('pillsForAnswer leaves out-of-range markers as text', () => {
  const html = pillsForAnswer('Lihat [9].', cits);
  assert.match(html, /\[9\]/);
});

test('pillsForAnswer escapes answer text', () => {
  const html = pillsForAnswer('a <b> [2]', cits);
  assert.match(html, /a &lt;b&gt;/);
});

test('sourcesBlock splits cited vs uncited', () => {
  const html = sourcesBlock(cits);
  assert.match(html, /Sumber dikutip \(2\)/);
  assert.match(html, /Diambil, tidak dikutip \(1\)/);
});

test('sourcesBlock single block when all cited', () => {
  const html = sourcesBlock([cits[1], cits[2]]);
  assert.match(html, /Sumber \(2\)/);
  assert.ok(!html.includes('tidak dikutip'));
});

test('renderAnswerHtml combines pills + sources', () => {
  const html = renderAnswerHtml('Klaim [2].', cits);
  assert.match(html, /class="pill"/);
  assert.match(html, /Sumber dikutip/);
});

test('renderAnswerHtml with no citations returns just escaped text', () => {
  assert.equal(renderAnswerHtml('halo', []), 'halo');
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { escapeHtml, viewerHref } from '../../app/web/static/new/api.js';

test('escapeHtml neutralizes HTML metacharacters', () => {
  assert.equal(escapeHtml('<b>a&"\'</b>'), '&lt;b&gt;a&amp;&quot;&#39;&lt;/b&gt;');
});

test('escapeHtml tolerates null/undefined', () => {
  assert.equal(escapeHtml(null), '');
  assert.equal(escapeHtml(undefined), '');
});

test('viewerHref builds doc+page anchor', () => {
  assert.equal(viewerHref({ doc_id: 7, page_start: 3 }), '/viewer?doc=7#page=3');
});

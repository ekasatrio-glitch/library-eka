import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseDSL, dslToDot, slug } from '../../app/web/static/new/dsl.js';

test('parseDSL reads the three node kinds', () => {
  const p = parseDSL('[diteliti] A\n[latar] B\n[latar*] C');
  assert.equal(p.errors.length, 0);
  const byLabel = Object.fromEntries(p.nodes.map(n => [n.label, n.kind]));
  assert.equal(byLabel['A'], 'diteliti');
  assert.equal(byLabel['B'], 'latar');
  assert.equal(byLabel['C'], 'latar*');
});

test('parseDSL: -> defaults to memicu, -| is menghambat', () => {
  const p = parseDSL('[diteliti] A\n[diteliti] B\nA -> B\nB -| A');
  const types = p.edges.map(e => e.type);
  assert.deepEqual(types, ['memicu', 'menghambat']);
});

test('parseDSL: -> with : menghambat resolves to menghambat', () => {
  const p = parseDSL('[diteliti] A\n[diteliti] B\nA -> B : menghambat');
  assert.equal(p.edges[0].type, 'menghambat');
});

test('parseDSL: -| with : memicu is a parse error (contradiction)', () => {
  const p = parseDSL('[diteliti] A\n[diteliti] B\nA -| B : memicu');
  assert.equal(p.edges.length, 0);
  assert.equal(p.errors.length, 1);
  assert.equal(p.errors[0].line, 3);
  assert.match(p.errors[0].msg, /kontradiksi/i);
});

test('parseDSL ignores comments and blank lines', () => {
  const p = parseDSL('# judul\n\n[diteliti] A\n   \n# komentar');
  assert.equal(p.nodes.length, 1);
  assert.equal(p.errors.length, 0);
});

test('parseDSL makes an implicit [latar] node for an edge-only label', () => {
  const p = parseDSL('[diteliti] A\nA -> Z');
  const z = p.nodes.find(n => n.label === 'Z');
  assert.ok(z, 'Z node created');
  assert.equal(z.kind, 'latar');
  assert.equal(z.implicit, true);
});

test('parseDSL merges duplicate labels (label is identity)', () => {
  const p = parseDSL('[diteliti] A\n[latar] A');
  assert.equal(p.nodes.filter(n => n.label === 'A').length, 1);
});

test('parseDSL reports line+col for a malformed node decl', () => {
  const p = parseDSL('[salah] A');
  assert.equal(p.errors.length, 1);
  assert.equal(p.errors[0].line, 1);
  assert.ok(typeof p.errors[0].col === 'number');
});

test('dslToDot styles diteliti bold, latar dashed', () => {
  const dot = dslToDot(parseDSL('[diteliti] A\n[latar] B'), {});
  assert.match(dot, /penwidth=2\.5/);
  assert.match(dot, /style=dashed/);
});

test('dslToDot colors memicu red and menghambat blue with diamond', () => {
  const dot = dslToDot(parseDSL('[diteliti] A\n[diteliti] B\nA -> B\nB -| A'), {});
  assert.match(dot, /color="#c0392b"/);
  assert.match(dot, /color="#2c5fa8"/);
  assert.match(dot, /arrowhead=diamond/);
});

test('dslToDot escapes double quotes in labels (DOT injection guard)', () => {
  const dot = dslToDot(parseDSL('[diteliti] He said "hi"'), {});
  assert.ok(!/[^\\]"hi"/.test(dot), 'inner quotes must be escaped');
  assert.match(dot, /\\"hi\\"/);
});

test('dslToDot emits a stable id per node, matching slug()', () => {
  const dot = dslToDot(parseDSL('[diteliti] ↑ ROS'), {});
  assert.match(dot, new RegExp(`id="node-${slug('↑ ROS')}"`));
});

test('slug is deterministic and reversible-enough for distinct labels', () => {
  assert.equal(slug('↑ ROS'), slug('↑ ROS'));
  assert.notEqual(slug('A'), slug('B'));
});

test('slug never starts with a digit (valid CSS/HTML id)', () => {
  assert.match(slug('1 Inflamasi'), /^[A-Za-z_]/);
  assert.equal(slug('1 Inflamasi'), slug('1 Inflamasi')); // still deterministic
});

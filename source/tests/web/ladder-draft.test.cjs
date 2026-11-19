'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const draftModel = require('../../web/ladder-draft.js');
const graph = require('../../web/ladder-graph.js');

const op = (name, ...args) => ({name, args});
function fixture() {
  return {kind: 'RLL', key: 'MainProgram/Main', problems: [], rungs: [
    {number: '0', text: '  XIC(Start) OTE(Run);', comment: 'Seal in', nodes: [op('XIC', 'Start'), op('OTE', 'Run')]},
    {number: '1', text: 'MOV(0, Count);', comment: 'Reset', nodes: [op('MOV', '0', 'Count')]}
  ]};
}

test('draft uses wire gaps and preserves source and stable node identity through history', () => {
  const routine = fixture(), original = structuredClone(routine);
  const draft = draftModel.create(routine);
  const first = graph.compile(draft.rungs[0], routine.key, true);
  const oldIds = first.order.slice();
  const branchId = draft.insert(0, first.edges[1].gap, 'Branch');
  const branched = graph.compile(draft.rungs[0], routine.key, true);
  const branch = branched.nodes.find(node => node.id.endsWith(':draft:' + branchId + ':split'));
  assert.deepEqual(branched.order, oldIds);
  const path = branched.edges.find(edge => edge.from.node === branch.id && edge.from.port === 'path1');
  assert.deepEqual(path.gap, {legs: [[1, 1]], index: 0});
  assert.equal(draft.rungs[0].text, 'XIC(Start)[,]OTE(Run);');
  const id = draft.insert(0, path.gap, 'XIO');
  assert.equal(draft.setOperands(0, id, ['Stop']), id);
  assert.equal(draft.rungs[0].text, 'XIC(Start)[,XIO(Stop)]OTE(Run);');
  assert.equal(draft.rungs[1].text, original.rungs[1].text);
  assert.deepEqual(routine, original);
  assert.equal(draft.undo(), true);
  assert.equal(draft.rungs[0].text, 'XIC(Start)[,XIO(?)]OTE(Run);');
  draft.undo();
  draft.undo();
  assert.equal(draft.changed, false);
  assert.equal(draft.rungs[0].text, original.rungs[0].text);
  draft.redo();
  draft.redo();
  draft.redo();
  assert.equal(graph.compile(draft.rungs[0], routine.key, true).nodes.some(node => node.draftId === id), true);
  assert.equal(draft.rungs[0].text, 'XIC(Start)[,XIO(Stop)]OTE(Run);');
});

test('nested gaps compile to drawable wires and never appear on the monitor graph', () => {
  const routine = fixture(), draft = draftModel.create(routine);
  assert(draft.insert(0, {legs: [], index: 0}, 'Branch'));
  assert(draft.insert(0, {legs: [[0, 0]], index: 0}, 'Branch'));
  const ladder = graph.compile(draft.rungs[0], routine.key, true);
  const point = ladder.edges.find(edge => edge.gap.legs.length === 2 &&
    edge.gap.legs.at(-1)[1] === 0);
  assert(draft.insert(0, point.gap, 'MOV'));
  const layout = graph.layout(ladder);
  for (const edge of ladder.edges) {
    assert(layout.ports[edge.from.node + '/' + edge.from.port]);
    assert(layout.ports[edge.to.node + '/' + edge.to.port]);
  }
  assert.equal(draft.rungs[0].text, '[[MOV(?,?),],]XIC(Start)OTE(Run);');
  assert(graph.compile(routine.rungs[0], routine.key).edges.every(edge => !('gap' in edge)));
});

test('operand boundary checks are transactional and preserve literal punctuation', () => {
  const draft = draftModel.create(fixture()), id = draft.rungs[1].nodes[0].draftId;
  for (const label of ['A,B', 'A);OTE(B', "'unfinished", 'Index[(1])', " 'dangling$' "]) {
    assert.throws(() => draft.setOperands(1, id, [label, 'Count']), /operand/i);
    assert.equal(draft.canUndo, false);
  }
  assert(draft.setOperands(1, id, ["'a$,b$'c'", 'Target[Index(1,2),3]']));
  assert.equal(draft.rungs[1].text, "MOV('a$,b$'c',Target[Index(1,2),3]);");
  draft.remove(1, id);
  assert.equal(draft.rungs[1].text, ';');
  draft.undo();
  assert.equal(draft.rungs[1].nodes[0].draftId, id);
  draft.setOperands(1, id, ['0', 'Count']);
  assert.equal(draft.canRedo, false);
  assert.equal(draft.changed, false);
  assert.equal(draft.rungs[1].text, 'MOV(0, Count);');
});

test('non-RLL, AOI and diagnosed routines stay in Monitor', () => {
  const routine = fixture();
  for (const override of [{kind: 'ST'}, {kind: 'FBD'}, {key: 'AOI:Sample/Logic'},
    {problems: ['Rung 1: pending/test edit rung type']}, {rungs: []}]) {
    assert.equal(draftModel.canEdit({...routine, ...override}), false);
  }
  assert.equal(draftModel.canEdit(routine), true);
  assert.throws(() => draftModel.create({...routine, kind: 'FBD'}), /read-only/);
});
